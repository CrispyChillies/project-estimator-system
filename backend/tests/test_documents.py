from app.services.documents import CHUNK_WORDS, chunk_text


def test_chunking_preserves_lines_and_overlaps():
    text = "\n".join(f"- requirement number {i} with some words" for i in range(400))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c.split()) <= CHUNK_WORDS + 10 for c in chunks)
    assert chunks[0].splitlines()[0] == "- requirement number 0 with some words"
    assert chunks[0].splitlines()[-1] in chunks[1]  # overlap


def test_short_text_single_chunk():
    assert chunk_text("a\nb\nc") == ["a\nb\nc"]
