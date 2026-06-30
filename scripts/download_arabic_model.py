"""
Download the multilingual faster-whisper-medium model for Arabic STT support.
Run with:
    conda run -n assistify_main python scripts/download_arabic_model.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
dest = ROOT / "backend" / "Models" / "faster-whisper-medium"
dest.mkdir(parents=True, exist_ok=True)

print(f"[Arabic Setup] Destination: {dest}")
print("[Arabic Setup] Downloading Systran/faster-whisper-medium from HuggingFace Hub...")
print("[Arabic Setup] This may take several minutes depending on your connection speed.")
print()

try:
    from huggingface_hub import snapshot_download
    path = snapshot_download(
        repo_id="Systran/faster-whisper-medium",
        local_dir=str(dest),
        local_dir_use_symlinks=False,
        ignore_patterns=["*.msgpack", "*.h5", "flax_model*", "tf_model*", "rust_model*"],
    )
    print(f"\n[Arabic Setup] ✓ Download complete! Model saved to: {path}")
    print("[Arabic Setup] Verifying model files...")
    files = list(dest.glob("*"))
    for f in sorted(files):
        size_mb = f.stat().st_size / (1024 * 1024) if f.is_file() else 0
        print(f"  {f.name} ({size_mb:.1f} MB)" if f.is_file() else f"  {f.name}/")
    print("\n[Arabic Setup] Arabic voice input (STT) is now ready.")
    print("[Arabic Setup] Restart the RAG server to use the multilingual model.")
except ImportError:
    print("[ERROR] huggingface_hub not installed. Trying pip install...")
    os.system(f"{sys.executable} -m pip install huggingface_hub")
    print("Please re-run this script after installation.")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Download failed: {e}")
    print("\nAlternative: download manually from https://huggingface.co/Systran/faster-whisper-medium")
    print(f"and place the files in: {dest}")
    sys.exit(1)
