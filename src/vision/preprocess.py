"""OpenCV preprocessing: resize, grayscale, denoise, deskew, adaptive threshold."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Union

import cv2
import numpy as np
from PIL import Image, ImageOps

import config


class ImageQualityError(ValueError):
    """Raised when the image cannot be read or is blank / unusable."""


@dataclass
class PreprocessResult:
    """Output of :func:`preprocess_image`."""

    original: np.ndarray    # RGB uint8, resized only
    gray: np.ndarray        # deskewed, denoised grayscale
    processed: np.ndarray   # binary (adaptive threshold) uint8
    deskew_angle: float


ImageSource = Union[bytes, Image.Image, np.ndarray]


def load_image(source: ImageSource) -> np.ndarray:
    """Load bytes / PIL image / array into an RGB uint8 array (EXIF orientation applied)."""
    try:
        if isinstance(source, np.ndarray):
            arr = source
            if arr.ndim == 2:
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
            return arr[..., :3].astype(np.uint8)
        img = source if isinstance(source, Image.Image) else Image.open(io.BytesIO(source))
        return np.array(ImageOps.exif_transpose(img).convert("RGB"))
    except Exception as exc:  # noqa: BLE001 - any decode problem means an unusable image
        raise ImageQualityError("The image could not be read. Please upload a JPG or PNG photo.") from exc


def resize_image(rgb: np.ndarray) -> np.ndarray:
    """Scale so the longest side lies within [MIN_IMAGE_SIDE, MAX_IMAGE_SIDE]."""
    longest = max(rgb.shape[:2])
    if longest > config.MAX_IMAGE_SIDE:
        scale, interp = config.MAX_IMAGE_SIDE / longest, cv2.INTER_AREA
    elif longest < config.MIN_IMAGE_SIDE:
        scale, interp = config.MIN_IMAGE_SIDE / longest, cv2.INTER_CUBIC
    else:
        return rgb
    return cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=interp)


def _rotate(img: np.ndarray, angle: float, border: int = 0) -> np.ndarray:
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def estimate_skew_angle(gray: np.ndarray, max_angle: float = 10.0) -> float:
    """Estimate text skew with a projection-profile search; 0.0 when no clear improvement."""
    scale = 500 / max(gray.shape[:2])
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, inv = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    def score(angle: float) -> float:
        return float(np.var(_rotate(inv, angle).sum(axis=1) / 255.0))

    base = score(0.0)
    best_angle, best_score = 0.0, base
    for angle in np.arange(-max_angle, max_angle + 0.1, 1.0):
        s = score(float(angle))
        if s > best_score:
            best_angle, best_score = float(angle), s
    for angle in np.arange(best_angle - 0.75, best_angle + 0.76, 0.25):
        s = score(float(angle))
        if s > best_score:
            best_angle, best_score = float(angle), s
    return best_angle if best_score > base * 1.05 else 0.0


def preprocess_image(source: ImageSource) -> PreprocessResult:
    """Run the full pipeline and return both the original (resized) and processed images.

    Raises :class:`ImageQualityError` for unreadable, tiny or blank images.
    """
    rgb = load_image(source)
    if min(rgb.shape[:2]) < 50:
        raise ImageQualityError("The image is too small. Please use a clearer, larger photo.")
    gray0 = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if float(gray0.std()) < config.BLANK_IMAGE_STD_THRESHOLD:
        raise ImageQualityError("The image looks blank. Please retake the photo with the label visible.")
    rgb = resize_image(rgb)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    angle = estimate_skew_angle(gray)
    if angle:
        h, w = gray.shape
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        gray = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    processed = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    return PreprocessResult(original=rgb, gray=gray, processed=processed, deskew_angle=angle)
