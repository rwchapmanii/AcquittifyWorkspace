from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ChunkSpec:
    text: str
    start_offset: int | None
    end_offset: int | None


def chunk_text(
    text: str, chunk_size: int = 800, overlap: int = 120, min_chunk: int = 200
) -> list[ChunkSpec]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be < chunk_size")
    if min_chunk <= 0:
        raise ValueError("min_chunk must be > 0")

    chunks: list[ChunkSpec] = []
    cursor = 0
    length = len(text)

    while cursor < length:
        target_end = min(cursor + chunk_size, length)
        break_pos = _find_break(text, cursor, target_end, min_chunk=min_chunk)
        end = break_pos if break_pos is not None else target_end
        if end <= cursor:
            end = target_end

        chunk_text = text[cursor:end]
        if chunk_text.strip():
            chunks.append(
                ChunkSpec(text=chunk_text, start_offset=cursor, end_offset=end)
            )
        if end >= length:
            break
        cursor = max(0, end - overlap)

    return chunks


def _find_break(text: str, start: int, end: int, min_chunk: int) -> int | None:
    if end - start < min_chunk:
        return None
    window = text[start:end]
    paragraph_breaks = [
        m.start() for m in re.finditer(r"\n\s*\n", window)
    ]
    if paragraph_breaks:
        candidate = start + paragraph_breaks[-1]
        if candidate - start >= min_chunk:
            return candidate

    sentence_breaks = [
        m.end() for m in re.finditer(r"[.!?]\s", window)
    ]
    if sentence_breaks:
        candidate = start + sentence_breaks[-1]
        if candidate - start >= min_chunk:
            return candidate
    return None
