"""Tests for Ollama SSE chunk parsing."""
from app.deid.worker.sse_parse import parse_ollama_sse_chunk, parse_ollama_sse_tokens


def test_parse_multiple_data_lines_in_one_chunk():
    raw = (
        'data: {"choices":[{"delta":{"content":"company"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"|"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"测试公司"}}]}\n\n'
    )
    tokens = parse_ollama_sse_tokens(raw)
    assert tokens == ["company", "|", "测试公司"]
    assert parse_ollama_sse_chunk(raw) == "company|测试公司"
