import cv2
import numpy as np
import pytest

from src.vision import ocr
from src.vision.preprocess import ImageQualityError, estimate_skew_angle, preprocess_image


def text_image(angle=0.0):
    img = np.full((600, 900, 3), 255, np.uint8)
    for i, word in enumerate(["PANADOL 500 mg", "Paracetamol Tablets", "EXP 03/2027"]):
        cv2.putText(img, word, (60, 150 + i * 140), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 4)
    if angle:
        m = cv2.getRotationMatrix2D((450, 300), angle, 1.0)
        img = cv2.warpAffine(img, m, (900, 600), borderValue=(255, 255, 255))
    return img


def test_preprocess_returns_both_images():
    res = preprocess_image(text_image())
    assert res.original.ndim == 3 and res.processed.ndim == 2
    assert set(np.unique(res.processed)) <= {0, 255}


def test_deskew_detects_rotation():
    gray = cv2.cvtColor(text_image(5.0), cv2.COLOR_RGB2GRAY)
    assert abs(abs(estimate_skew_angle(gray)) - 5.0) <= 1.5


def test_blank_and_garbage_images_rejected():
    with pytest.raises(ImageQualityError):
        preprocess_image(np.full((400, 400, 3), 255, np.uint8))
    with pytest.raises(ImageQualityError):
        preprocess_image(b"not an image")
    with pytest.raises(ImageQualityError):
        preprocess_image(np.zeros((20, 20, 3), np.uint8))


class FakeReader:
    def readtext(self, image, detail=1, paragraph=False):
        return [([0], "PANADOL", 0.95), ([0], "noise", 0.1), ([0], "Exp 03/2027", 0.8)]


def test_ocr_merge_and_threshold():
    img = np.zeros((10, 10), np.uint8)
    res = ocr.extract_text(img, img, FakeReader())
    assert [l.text for l in res.lines] == ["PANADOL", "Exp 03/2027"] and not res.is_empty


def test_ocr_failure_wrapped():
    class Bad:
        def readtext(self, *a, **k):
            raise ValueError("boom")
    with pytest.raises(ocr.OcrError):
        ocr.extract_text(np.zeros((5, 5)), np.zeros((5, 5)), Bad())
