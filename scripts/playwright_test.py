"""SAFE LATENCY TEST — Stabilization Mode (Part 8)

Runs exactly 5 voice pipeline tests sequentially.
Waits for each pipeline to fully finish before starting next.
3-second cooldown between runs.
Then exits.

NEVER infinite-loops.  NEVER auto-repeats.
If any single test times out → abort entire batch.
If preflight check fails → refuse to run.

Usage:  python scripts/playwright_test.py
"""
import asyncio
import sys
import json
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

MAX_TESTS = 5
COOLDOWN_SEC = 3
PIPELINE_TIMEOUT_SEC = 45

# Get absolute path to speech_44100.wav
REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_FILE = REPO_ROOT / "speech_44100.wav"


def preflight() -> bool:
    """Check backend preflight before running tests."""
    print("[PREFLIGHT] Checking system configuration...")
    try:
        resp = urllib.request.urlopen("http://localhost:7000/internal/preflight", timeout=5)
        data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[PREFLIGHT] FAIL — backend not reachable: {e}")
        return False

    if data.get("sessions_blocked"):
        print("[PREFLIGHT] FAIL — sessions are BLOCKED (memory leak suspected)")
        return False

    issues = data.get("issues", [])
    if issues:
        for issue in issues:
            print(f"[PREFLIGHT] ⚠ {issue}")
        print("[PREFLIGHT] FAIL — config mismatch. Fix issues above before testing.")
        return False

    mem = data.get("memory", {})
    print(f"[PREFLIGHT] OK — STT={data.get('stt_model')}/{data.get('stt_device')}/{data.get('stt_compute')} "
          f"beam={data.get('stt_beam')} "
          f"GPU={mem.get('gpu_reserved_mb', 0):.0f}MB CPU={mem.get('cpu_rss_mb', 0):.0f}MB")
    return True

async def run_tests():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={AUDIO_FILE}",
            ]
        )
        context = await browser.new_context(
            permissions=["microphone"]
        )
        page = await context.new_page()

        print("Navigating to local site...")
        await page.goto("http://localhost:7001/login", wait_until="networkidle")

        title = await page.title()
        print(f"Initial Title: {title}")
        print(f"Page URL: {page.url}")
        
        if "login" in title.lower() or "Assistify" in title:
            try:
                await page.fill('input[name="username"]', 'admin', timeout=2000)
                await page.fill('input[name="password"]', 'admin', timeout=2000)
                print("Filled login form.")
                
                # Use click on the submit button instead of Enter
                await page.click('input[type="submit"]')
                print("Clicked Submit")
                
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Login error: {e}")

        await page.goto("http://localhost:7001/frontend/", wait_until="networkidle")
        
        print(f"Post-nav Title: {await page.title()}")
        print(f"Post-nav URL: {page.url}")
        
        # Take a visual check if it's the chat page
        content = await page.content()
        if "btnStart" not in content:
            print("ERROR: btnStart not found on page! We are not on the chat page.")
            await browser.close()
            return

        print("Waiting extra time to ensure WebSocket connects...")
        await page.wait_for_timeout(4000)

        reports = []
        current_report = {}

        def handle_console(msg):
            text = msg.text
            print(f"[BROWSER] {text}")
            if "VOICE PIPELINE LATENCY REPORT" in text:
                current_report.clear()
            elif "Speech End" in text and "STT Start:" in text:
                try:
                    val = float(text.split(":")[1].replace("ms", "").strip())
                    current_report["speech_to_stt"] = val
                except:
                    pass
            elif "STT Duration:" in text:
                try:
                    val = float(text.split(":")[1].replace("ms", "").strip())
                    current_report["stt_dur"] = val
                except:
                    pass
            elif "LLM First Token:" in text:
                try:
                    val = float(text.split(":")[1].replace("ms", "").strip())
                    current_report["llm_first"] = val
                except:
                    pass
            elif "XTTS First Audio:" in text:
                try:
                    val = float(text.split(":")[1].replace("ms", "").strip())
                    current_report["xtts_first"] = val
                except:
                    pass
            elif "Total Latency:" in text:
                try:
                    val = float(text.split(":")[1].replace("ms", "").strip())
                    current_report["total"] = val
                    reports.append(dict(current_report))
                    print(f"✓ Captured Report! {len(reports)}/5: {current_report}")
                except:
                    pass

        page.on("console", handle_console)

        for i in range(MAX_TESTS):
            print(f"\n{'='*50}")
            print(f"  TEST {i+1}/{MAX_TESTS}")
            print(f"{'='*50}")

            print("Triggering voice recording manually...")
            # Mock startRecording to bypass getUserMedia issues in headless mode
            await page.evaluate("""
              async () => {
                window.isRecording = true;
                window.isMuted = false;
                window.pauseAudioSending = false;
                window.consecutiveVoiceFrames = 0;
                document.getElementById('btnStart').disabled = true;
                document.getElementById('btnMute').disabled = false;
                document.getElementById('btnStop').disabled = false;
                document.getElementById('btnStart').classList.add('recording');
                document.getElementById('btnMute').textContent = '🔇 Stop Recording';
                console.log("[MOCK] Recording state activated");
                
                // Generate synthetic audio with some energy (not pure silence)
                // This is 16-bit PCM at 16kHz for ~2 seconds of noise + 2 seconds silence
                const duration_ms = 4000;
                const sample_rate = 16000;
                const total_samples = (sample_rate * duration_ms) / 1000;
                const samples = new Int16Array(total_samples);
                
                // First 50% = low-energy noise/speech-like pattern
                const speech_duration_samples = total_samples / 2;
                for (let i = 0; i < speech_duration_samples; i++) {
                  // Simple sine wave at 440 Hz to create speech-like acoustic energy
                  samples[i] = Math.sin(2 * Math.PI * 440 * i / sample_rate) * 16000 * 0.3;
                }
                // Second 50% = silence (zeros)
                
                const pcm16_data = samples.buffer;
                
                return new Promise(resolve => {
                  const start_time = Date.now();
                  const interval = setInterval(() => {
                    if (window.ws && window.ws.readyState === 1) { // OPEN
                      window.ws.send(pcm16_data);
                    }
                    if (Date.now() - start_time >= duration_ms) {
                      clearInterval(interval);
                      resolve();
                    }
                  }, 100);
                });
              }
            """)
            print("Recording mock complete, stopping...")
            
            # Stop recording
            await page.evaluate("""
              () => {
                window.isRecording = false;
                window.pauseAudioSending = false;
                window.consecutiveVoiceFrames = 0;
                document.getElementById('btnStart').disabled = false;
                document.getElementById('btnMute').disabled = true;
                document.getElementById('btnStop').disabled = true;
                document.getElementById('btnStart').classList.remove('recording');
                document.getElementById('btnMute').textContent = '🔇 Mute';
                console.log("[MOCK] Recording state deactivated");
              }
            """)
            
            print("Waiting for text processing...")

            timed_out = True
            for t in range(PIPELINE_TIMEOUT_SEC):
                if len(reports) > i:
                    timed_out = False
                    break
                await page.wait_for_timeout(1000)

            if timed_out:
                print(f"\n  TIMEOUT: Test {i+1} did not complete after {PIPELINE_TIMEOUT_SEC}s — ABORTING ENTIRE BATCH")
                break

            # Check backend memory between tests
            try:
                resp = urllib.request.urlopen("http://localhost:7000/internal/preflight", timeout=5)
                pf = json.loads(resp.read().decode())
                if pf.get("sessions_blocked"):
                    print(f"\n  🛑 MEMORY LEAK SUSPECTED by backend — ABORTING TEST BATCH")
                    break
                mem = pf.get("memory", {})
                print(f"  [MEM] GPU={mem.get('gpu_reserved_mb', 0):.0f}MB  CPU={mem.get('cpu_rss_mb', 0):.0f}MB  growth_count={pf.get('consecutive_gpu_growth', 0)}")
            except Exception:
                pass
            
            # Cooldown — let backend release resources
            if i < MAX_TESTS - 1:
                print(f"  Cooldown {COOLDOWN_SEC}s...")
                await page.wait_for_timeout(COOLDOWN_SEC * 1000)

        await browser.close()

        print("\n\n" + "=" * 60)
        print("  LATENCY TEST RESULTS")
        print("=" * 60)
        for i, r in enumerate(reports):
            print(f"  Test {i+1}: {r}")

        if len(reports) > 0:
            for key in ["speech_to_stt", "stt_dur", "llm_first", "xtts_first", "total"]:
                vals = [r[key] for r in reports if key in r]
                if vals:
                    print(f"  {key:>16s}  avg={sum(vals)/len(vals):7.1f}ms  min={min(vals):7.1f}ms  max={max(vals):7.1f}ms")
        print("=" * 60)
        print(f"  Completed {len(reports)}/{MAX_TESTS} tests.  Exiting.")

if __name__ == "__main__":
    if not preflight():
        print("[ABORT] Preflight failed — refusing to run tests.")
        sys.exit(1)
    asyncio.run(run_tests())
    sys.exit(0)
