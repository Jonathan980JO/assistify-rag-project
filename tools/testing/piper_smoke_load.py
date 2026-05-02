from pathlib import Path
from piper import PiperVoice
import wave, io

ROOT = Path(r"G:\Grad_Project\assistify-rag-project-main")
try:
    en = PiperVoice.load(str(ROOT / "models" / "piper" / "en" / "voice.onnx"))
    ar = PiperVoice.load(str(ROOT / "models" / "piper" / "ar" / "voice.onnx"))
    
    for tag, voice, text in [("EN", en, "Hello, this is a test."), ("AR", ar, "مرحبا كيف حالك")]:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf)
        print(tag, "ok bytes=", len(buf.getvalue()), "sr=", voice.config.sample_rate)
except Exception as e:
    print(f"Error: {e}")
