import os, warnings, time
warnings.filterwarnings('ignore')
os.environ['COQUI_TOS_AGREED'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

from TTS.api import TTS
import torch

print("Loading XTTS v2...")
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)

sm = tts.synthesizer.tts_model.speaker_manager
# name_to_id may be a dict OR dict_keys depending on XTTS version
nti = sm.name_to_id
names = list(nti) if not isinstance(nti, dict) else list(nti.keys())
print(f"\nAvailable speakers ({len(names)} total):")
for i, n in enumerate(names):
    print(f"  {i:2d}. {n}")

# Pick the first English-sounding speakers to test
test_speakers = [names[0], names[1], names[2]]
print(f"\nTesting speakers: {test_speakers}")

for speaker in test_speakers:
    t0 = time.time()
    try:
        wav = tts.tts(
            text="Hello, I am Assistify, your voice assistant.",
            speaker=speaker,
            language="en"
        )
        lat = (time.time() - t0) * 1000
        dur = len(wav) / 24000 * 1000
        print(f"  '{speaker}' → {lat:.0f}ms | {dur:.0f}ms audio | RTF={lat/dur:.2f} | OK")
    except Exception as e:
        print(f"  '{speaker}' → FAILED: {e}")
