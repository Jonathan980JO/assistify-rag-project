"""
faster-whisper Installation and GPU Verification Test
Run this script to verify your system is ready for faster-whisper ASR.
"""

import sys

def test_imports():
    """Test that all required packages are installed"""
    print("=" * 60)
    print("FASTER-WHISPER SYSTEM VERIFICATION")
    print("=" * 60)
    print()
    
    results = {}
    
    # Test 1: faster-whisper
    print("[1/6] Testing faster-whisper import...")
    try:
        import faster_whisper
        print(f"  ✓ faster-whisper version: {faster_whisper.__version__}")
        results['faster_whisper'] = True
    except ImportError as e:
        print(f"  ✗ FAILED: {e}")
        print("  Fix: pip install faster-whisper")
        results['faster_whisper'] = False
    
    # Test 2: PyTorch
    print("\n[2/6] Testing PyTorch import...")
    try:
        import torch
        print(f"  ✓ PyTorch version: {torch.__version__}")
        results['torch'] = True
    except ImportError as e:
        print(f"  ✗ FAILED: {e}")
        print("  Fix: pip install torch")
        results['torch'] = False
        return results
    
    # Test 3: CUDA availability
    print("\n[3/6] Testing CUDA availability...")
    if torch.cuda.is_available():
        print(f"  ✓ CUDA is available")
        print(f"  ✓ CUDA version: {torch.version.cuda}")
        print(f"  ✓ GPU detected: {torch.cuda.get_device_name(0)}")
        print(f"  ✓ GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        results['cuda'] = True
    else:
        print(f"  ✗ CUDA NOT AVAILABLE")
        print("  This is CRITICAL - faster-whisper requires GPU")
        print("  Fix: Install CUDA Toolkit from https://developer.nvidia.com/cuda-downloads")
        results['cuda'] = False
    
    # Test 4: NumPy
    print("\n[4/6] Testing NumPy import...")
    try:
        import numpy as np
        print(f"  ✓ NumPy version: {np.__version__}")
        results['numpy'] = True
    except ImportError as e:
        print(f"  ✗ FAILED: {e}")
        print("  Fix: pip install numpy")
        results['numpy'] = False
    
    # Test 5: Model path check
    print("\n[5/6] Testing model path...")
    from pathlib import Path
    model_path = Path("backend/Models/faster-whisper-medium.en")
    if model_path.exists():
        print(f"  ✓ Model found at: {model_path}")
        print(f"  ✓ Model files: {len(list(model_path.glob('*')))} files")
        results['model'] = True
    else:
        print(f"  ⚠ Model not found at: {model_path}")
        print("  This is OK - model will download automatically on first server start")
        results['model'] = False
    
    # Test 6: Model loading test (only if GPU available)
    print("\n[6/6] Testing model loading...")
    if results['cuda'] and results['faster_whisper']:
        try:
            from faster_whisper import WhisperModel
            print("  Loading tiny model for test (this may take a moment)...")
            model = WhisperModel("tiny", device="cuda", compute_type="float16")
            
            # Test transcription with dummy audio
            import numpy as np
            dummy_audio = np.zeros(16000, dtype=np.float32)  # 1 second of silence
            segments, info = model.transcribe(dummy_audio, language="en")
            
            print(f"  ✓ Model loaded successfully on GPU")
            print(f"  ✓ Test transcription completed")
            results['loading'] = True
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            results['loading'] = False
    else:
        print("  ⊘ Skipped (CUDA not available)")
        results['loading'] = False
    
    return results

def print_summary(results):
    """Print summary of test results"""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"\nTests passed: {passed}/{total}")
    print()
    
    if all(results.values()):
        print("✓ ALL TESTS PASSED!")
        print("✓ Your system is ready for faster-whisper ASR")
        print("\nNext steps:")
        print("1. Start the server: python scripts/project_start_server.py")
        print("2. The model will download automatically on first run")
        print("3. Test voice recording in the browser interface")
    elif results.get('cuda') and results.get('faster_whisper') and results.get('torch'):
        print("⚠ PARTIAL SUCCESS")
        print("✓ Core dependencies installed")
        print("✓ GPU is available")
        if not results.get('model'):
            print("⚠ Model not downloaded yet (will auto-download)")
        if not results.get('loading'):
            print("⚠ Model loading test skipped or failed")
        print("\nYou can proceed with server startup.")
    else:
        print("✗ SYSTEM NOT READY")
        print("\nCritical issues found:")
        if not results.get('cuda'):
            print("  • CUDA not available - GPU required for faster-whisper")
            print("    Install from: https://developer.nvidia.com/cuda-downloads")
        if not results.get('faster_whisper'):
            print("  • faster-whisper not installed")
            print("    Run: pip install faster-whisper")
        if not results.get('torch'):
            print("  • PyTorch not installed")
            print("    Run: pip install torch")
        if not results.get('numpy'):
            print("  • NumPy not installed")
            print("    Run: pip install numpy")
        
        print("\nAfter fixing issues, run this script again.")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    try:
        results = test_imports()
        print_summary(results)
        
        # Exit with appropriate code
        if all(results.values()):
            sys.exit(0)
        elif results.get('cuda') and results.get('faster_whisper'):
            sys.exit(0)  # Good enough to try
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
