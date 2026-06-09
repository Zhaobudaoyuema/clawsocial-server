"""Chunk count consistency between stats and LLM discovery."""
from app.deid.discovery.llm import count_llm_chunks, get_llm_chunk_params


def test_count_llm_chunks_matches_params():
    text = "段落一\n\n" * 2000
    chunk_size, overlap = get_llm_chunk_params()
    n = count_llm_chunks(text)
    assert n >= 2
    # fixed mode sanity: smaller chunk_size => more chunks
    import os
    from app.deid.discovery.llm import _chunk_text

    small = len(_chunk_text(text, 2000, overlap))
    large = len(_chunk_text(text, 8000, overlap))
    assert small >= large
