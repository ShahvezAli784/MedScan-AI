"""EasyOCR wrapper: lazy cached reader, text lines with confidences, merged over image variants."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np

import config
from src.utils.logging_setup import get_logger

log = get_logger(__name__)
_READER: Any = None
_LOCK = threading.Lock()


class OcrError(RuntimeError):
    """Raised when OCR is unavailable or fails."""


@dataclass(frozen=True)
class OcrLine:
    """A recognised text line."""

    text: str
    confidence: float  # 0-1
    source: str        # "original" or "processed"


@dataclass
class OcrResult:
    """Merged OCR output."""

    lines: list[OcrLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        """All lines joined by newlines."""
        return "\n".join(line.text for line in self.lines)

    @property
    def is_empty(self) -> bool:
        """True when no text was found."""
        return not self.lines


def load_reader(languages: Optional[list[str]] = None) -> Any:
    """Return a process-wide EasyOCR reader, creating it on first use (CPU only)."""
    global _READER
    with _LOCK:
        if _READER is None:
            try:
                import easyocr  # imported lazily: heavy dependency
            except ImportError as exc:
                raise OcrError("EasyOCR is not installed. Run: pip install easyocr") from exc
            try:
                _READER = easyocr.Reader(languages or config.OCR_LANGUAGES, gpu=False, verbose=False)
            except Exception as exc:  # noqa: BLE001
                raise OcrError(f"Could not load the OCR model: {exc}") from exc
        return _READER


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def merge_lines(lines: Iterable[OcrLine]) -> list[OcrLine]:
    """De-duplicate lines by normalised text, keeping the most confident version (stable order)."""
    best: dict[str, OcrLine] = {}
    for line in lines:
        k = _key(line.text)
        if k and (k not in best or line.confidence > best[k].confidence):
            best[k] = line
    return list(best.values())


def read_image(reader: Any, image: np.ndarray, source: str) -> list[OcrLine]:
    """Run OCR on one image and return lines above the minimum confidence."""
    try:
        raw = reader.readtext(image, detail=1, paragraph=False)
    except Exception as exc:  # noqa: BLE001
        raise OcrError(f"OCR failed: {exc}") from exc
    lines = []
    for item in raw:
        text, conf = str(item[1]).strip(), float(item[2])
        if text and conf >= config.OCR_MIN_LINE_CONFIDENCE:
            lines.append(OcrLine(text=text, confidence=conf, source=source))
    return lines


def extract_text(original: np.ndarray, processed: np.ndarray, reader: Any = None) -> OcrResult:
    """OCR both the original and processed images and merge the results."""
    reader = reader or load_reader()
    lines = read_image(reader, original, "original") + read_image(reader, processed, "processed")
    merged = merge_lines(lines)
    log.info("OCR found %d merged lines", len(merged))
    return OcrResult(lines=merged)
