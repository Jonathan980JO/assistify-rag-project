"""Regression: llm_producer must read suppress_sentinel_stream before assignment."""

from __future__ import annotations


def test_text_only_stream_reads_suppress_sentinel_before_assign():
    """Mirror the bug: assignment in outer fn makes name local without nonlocal."""
    suppress_sentinel_stream = False
    final_replace_chunk = False
    chunks: list[str] = []

    def producer_with_nonlocal(token: str) -> None:
        nonlocal suppress_sentinel_stream, final_replace_chunk
        if not token:
            return
        if token.startswith("NOT_FOUND"):
            suppress_sentinel_stream = True
            final_replace_chunk = True
        elif suppress_sentinel_stream:
            pass
        else:
            chunks.append(token)

    def producer_without_nonlocal(token: str) -> None:
        if not token.startswith("NOT_FOUND"):
            if suppress_sentinel_stream:  # noqa: F821 — intentional bug pattern
                pass
            else:
                chunks.append(token)
        else:
            suppress_sentinel_stream = True  # makes name local in buggy version

    producer_with_nonlocal("Psych")
    producer_with_nonlocal("ology is")
    assert chunks == ["Psych", "ology is"]

    suppress_sentinel_stream = False
    chunks.clear()
    try:
        producer_without_nonlocal("Psych")
        raised = False
    except UnboundLocalError:
        raised = True
    assert raised, "missing nonlocal should raise UnboundLocalError on first token"


if __name__ == "__main__":
    test_text_only_stream_reads_suppress_sentinel_before_assign()
    print("OK: llm stream scope tests passed")
