"""Bounded WebSocket frames for standalone remote-command agents."""
import json

# Even JSON control-character escaping (six bytes/character) stays below 256 KiB.
CHUNK_CHARACTERS = 16 * 1024
LEGACY_FRAME_BYTES = 256 * 1024


def output_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


async def send_result(websocket, request_id, result, *, chunks_supported):
    result = {**result, "type": "result", "request_id": request_id,
              "stdout": output_text(result.get("stdout")),
              "stderr": output_text(result.get("stderr"))}
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded.encode("utf-8")) <= LEGACY_FRAME_BYTES:
        await websocket.send(encoded)
        return
    if not chunks_supported:
        await websocket.send(json.dumps({
            "type": "result", "request_id": request_id, "exit_code": 125,
            "stdout": "", "stderr": "Output exceeds the legacy relay frame limit; upgrade relay for chunked results. Command already ran; do not automatically repeat it.",
            "duration_ms": result.get("duration_ms"),
        }))
        return
    sequence = 0
    for stream in ("stdout", "stderr"):
        text = result[stream]
        for offset in range(0, len(text), CHUNK_CHARACTERS):
            await websocket.send(json.dumps({
                "type": "result_chunk", "request_id": request_id,
                "sequence": sequence, "stream": stream,
                "data": text[offset:offset + CHUNK_CHARACTERS],
            }, ensure_ascii=False))
            sequence += 1
    await websocket.send(json.dumps({**result, "stdout": "", "stderr": "",
                                    "chunk_count": sequence}, ensure_ascii=False))
