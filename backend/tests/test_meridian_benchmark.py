from __future__ import annotations
import asyncio, sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from backend.run_meridian_benchmark import _run_benchmark
def test_meridian_benchmark_full():
    assert asyncio.run(_run_benchmark()) == 0