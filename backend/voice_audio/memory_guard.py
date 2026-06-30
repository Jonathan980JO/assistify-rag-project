"""Voice session memory-leak detection globals."""
from __future__ import annotations

import asyncio

SAFE_UNBLOCK_CPU_MB = 2000
SAFE_UNBLOCK_GPU_MB = 2000
GPU_GROWTH_DELTA_MB = 200
GPU_HIGH_WATER_MB = 4000
MEMORY_GROWTH_LIMIT = 3
CPU_GROWTH_DELTA_MB = 500
CPU_HIGH_WATER_MB = 4000

pipeline_run_count = 0
sessions_blocked = False
sessions_blocked_since = 0.0
consecutive_gpu_growth = 0
consecutive_cpu_growth = 0
last_gpu_reserved_mb = 0

active_voice_task: asyncio.Task | None = None
active_voice_conn_id: str | None = None


def voice_transcribe_in_flight(conn_id: str | None = None) -> bool:
    if active_voice_task is None or active_voice_task.done():
        return False
    if conn_id is not None and active_voice_conn_id != conn_id:
        return False
    return True


def assign_voice_transcribe_task(task: asyncio.Task, conn_id: str) -> None:
    global active_voice_task, active_voice_conn_id
    active_voice_task = task
    active_voice_conn_id = conn_id
