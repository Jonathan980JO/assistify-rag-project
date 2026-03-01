
import asyncio
import json
import time
import numpy as np
import websockets
import aiohttp

async def run_lat_test(test_name, stt_model="medium.en", stt_device="cuda", stt_compute="float16"):
    print(f"\n--- Starting {test_name} ---")
    
    # We simulate a "What is the weather today?" audio chunk
    # 16kHz, 16bit, mono. ~2 seconds of silence/noise/speech
    # We use a simple sine wave to trigger energy VAD on backend
    dur = 2.0
    sr = 16000
    t = np.linspace(0, dur, int(sr * dur))
    speech = np.sin(2 * np.pi * 440 * t) * 0.1
    audio_bytes = (speech * 32767).astype(np.int16).tobytes()

    uri = "ws://localhost:7000/ws"
    
    results = []
    
    for i in range(5):
        try:
            async with websockets.connect(uri) as ws:
                print(f"Test {i+1}/5...", end="", flush=True)
                
                # Send audio in chunks to simulate streaming
                chunk_size = 4096
                for j in range(0, len(audio_bytes), chunk_size):
                    await ws.send(audio_bytes[j:j+chunk_size])
                    await asyncio.sleep(0.01)

                # Wait for results
                stt_done = False
                llm_done = False
                while not (stt_done and llm_done):
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("type") == "transcript" and data.get("final"):
                        stt_done = True
                    if data.get("type") == "aiResponseDone":
                        llm_done = True
                        timing = data.get("timing", {})
                        results.append(timing)
                print(" Done")
        except Exception as e:
            print(f" Error: {e}")

    if not results:
        print("No results collected.")
        return

    # Average metrics
    avg_stt = sum((r["stt_end"] - r["stt_start"]) for r in results) / len(results) * 1000
    avg_llm_first = sum((r["llm_first_token"] - r["llm_send"]) for r in results) / len(results) * 1000
    # XTTS is harder to test from here without the browser fetch, but we can see the backend logs or assume consistency
    
    print(f"\nSummary for {test_name}:")
    print(f"Average STT time: {avg_stt:.1f}ms")
    print(f"Average LLM first token time: {avg_llm_first:.1f}ms")

async def main():
    # Step 3: Baseline
    await run_lat_test("medium.en GPU")
    
    # Step 4: Logic for switching would require editing config.py or the server
    # We will assume the user manually restarts or we provide the command
    print("\nTo compare models, please update config.py and restart servers as in Step 4.")

if __name__ == "__main__":
    asyncio.run(main())
