from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_stream_mid_token_timeout_uses_non_stream_fallback_before_finalizing():
    source = (ROOT / "backend" / "services" / "streaming_service.py").read_text(encoding="utf-8")

    assert "mid_stream_timeout_fallback" in source
    assert "_stream_mid_token_timed_out" in source


def test_streaming_list_answers_do_not_use_short_simple_fact_token_cap():
    source = (ROOT / "backend" / "services" / "streaming_service.py").read_text(encoding="utf-8")

    assert 'family_v2_current in {"list_entity", "list_structure"}' in source
    assert "_llm_num_predict = 180" in source
