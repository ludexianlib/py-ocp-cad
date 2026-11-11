"""Prepare legacy STEP text for the UTF-8 reader, without modifying its source."""

import codecs
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path


_CHUNK_SIZE = 1024 * 1024
_SAMPLE_SIZE = 64 * 1024


def detect_step_encoding(source: str | Path) -> str:
    """Choose a candidate from the prefix; full decoding validates it later."""
    with Path(source).open("rb") as source_file:
        sample = source_file.read(_SAMPLE_SIZE)
    for encoding in ("utf-8", "gbk"):
        try:
            # The sample can end in the middle of a multibyte character.
            codecs.getincrementaldecoder(encoding)(errors="strict").decode(sample)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别 STEP 文本编码，请使用 UTF-8 或 GBK 编码重新导出。")


@contextmanager
def prepared_step_stream(source: str | Path):
    """Decode strictly into a UTF-8 stream; retry GBK if an ASCII prefix misleads."""
    path = Path(source)
    candidate = detect_step_encoding(path)
    encodings = ("utf-8", "gbk") if candidate == "utf-8" else ("gbk",)
    for encoding in encodings:
        with BytesIO() as stream:
            decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
            try:
                with path.open("rb") as source_file:
                    for block in iter(lambda: source_file.read(_CHUNK_SIZE), b""):
                        text = decoder.decode(block)
                        stream.write(block if encoding == "utf-8" else text.encode("utf-8"))
                stream.write(decoder.decode(b"", final=True).encode("utf-8"))
            except UnicodeDecodeError:
                continue
            stream.seek(0)
            yield stream
            return
    raise ValueError("无法识别 STEP 文本编码，请使用 UTF-8 或 GBK 编码重新导出。")
