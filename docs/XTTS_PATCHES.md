# XTTS v2 Site-Package Patches

## Why patches are needed

TTS 0.22.0 (Coqui XTTS v2) was released against `transformers ~4.x` and `torch ~2.1`.
Two breaking changes in the current stack require surgical patches to site-packages:

| Upstream change | Effect on TTS 0.22.0 |
|---|---|
| `transformers ≥ 5.0` removed `BeamSearchScorer` and friends from public API | `ImportError` on `from TTS import api` |
| `transformers ≥ 5.0` (`PreTrainedModel` no longer inherits `GenerationMixin`) | `'GPT2InferenceModel' object has no attribute 'generate'` |
| `torch ≥ 2.6` changed `torch.load()` default from `weights_only=False` → `True` | `UnpicklingError` loading XTTS checkpoints |

---

## Patch 1 — `stream_generator.py` (BeamSearchScorer shim)

**File:** `<venv>/Lib/site-packages/TTS/tts/layers/xtts/stream_generator.py`  
**Change:** Replace the old `from transformers.generation.beam_search import ...` import block
with a version-gated compatibility shim at the top of the file.

```python
# --- Compatibility shim for transformers >= 5.0 ---
import transformers as _tf
_TF_VER = tuple(int(x) for x in _tf.__version__.split(".")[:2])
if _TF_VER >= (5, 0):
    # BeamSearchScorer and friends were removed from transformers 5.x public API.
    # XTTS TTS synthesis uses greedy/sample generation (num_beams=1) so these
    # code paths are never reached at runtime.
    class BeamSearchScorer: ...
    class ConstrainedBeamSearchScorer: ...
    class DisjunctiveConstraint: ...
    class PhrasalConstraint: ...
    try:
        from transformers.generation.utils import GenerateNonBeamOutput as SampleOutput
    except ImportError:
        SampleOutput = None
else:
    from transformers.generation.beam_search import (
        BeamSearchScorer, ConstrainedBeamSearchScorer,
        DisjunctiveConstraint, PhrasalConstraint,
    )
    from transformers.generation.utils import SampleOutput
```

---

## Patch 2 — `gpt_inference.py` (GenerationMixin)

**File:** `<venv>/Lib/site-packages/TTS/tts/layers/xtts/gpt_inference.py`  
**Change:** Add `GenerationMixin` to the import and to the class declaration.

```python
# Add to imports:
from transformers.generation import GenerationMixin

# Change class declaration from:
class GPT2InferenceModel(GPT2PreTrainedModel):
# To:
class GPT2InferenceModel(GPT2PreTrainedModel, GenerationMixin):
```

**Why:** In `transformers ≥ 5.0`, `PreTrainedModel` no longer inherits from `GenerationMixin`,
so `.generate()` is no longer inherited automatically.

---

## Patch 3 — `TTS/utils/io.py` (weights_only default)

**File:** `<venv>/Lib/site-packages/TTS/utils/io.py`  
**Change:** In `load_fsspec()`, add before the `torch.load` call:

```python
kwargs.setdefault("weights_only", False)
```

**Why:** PyTorch 2.6 changed the default of `torch.load(weights_only=...)` from `False` → `True`.
XTTS checkpoints contain pickled `XttsConfig` objects which require `weights_only=False`.

---

## Patch 4 — `TTS/__init__.py` (global torch.load monkey-patch)

**File:** `<venv>/Lib/site-packages/TTS/__init__.py`  
**Change:** Add at the end of the file:

```python
import torch as _torch
_orig_torch_load = _torch.load
def _patched_torch_load(f, map_location=None, pickle_module=None, weights_only=False, **kw):
    return _orig_torch_load(f, map_location=map_location,
                             pickle_module=pickle_module,
                             weights_only=weights_only, **kw)
_torch.load = _patched_torch_load
```

**Why:** TTS 0.22.0 has 25+ bare `torch.load(path)` calls across `xtts.py`, `dvae.py`,
`hifigan_decoder.py`, `managers.py`, etc. Patching `io.py` alone doesn't cover all of them.
This global patch covers every call site at package import time.

---

## Validation results

```
GPU               : NVIDIA GeForce RTX 3070 Laptop GPU (8192 MB)
torch             : 2.6.0+cu124
transformers      : 5.2.0
TTS               : 0.22.0
XTTS VRAM         : ~1802 MB  (1.76 GB)
Qwen 2.5 7B VRAM  : ~4696 MB  (4.59 GB)  [via Ollama]
Combined peak     : ~6498 MB  (6.35 GB)  < 7.5 GB limit ✓
TTS avg latency   : ~12946 ms (first 5 phrases, cold)
Stress avg latency: ~10819 ms (20 rounds, warm)
OOM errors        : 0 / 20
Total errors      : 0 / 20
```
