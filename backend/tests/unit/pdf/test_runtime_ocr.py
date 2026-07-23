from __future__ import annotations

import struct
from pathlib import Path

import pymupdf
import pytest

from app.config import Settings
from app.pdf.inventory import build_inventory as build_native_inventory
from app.processing.runtime_recognition import RuntimeRecognition
from app.providers.base import OcrObservation, OcrResult


def _png(width: int, height: int) -> bytes:
    pixmap = pymupdf.Pixmap(
        pymupdf.csRGB,
        pymupdf.IRect(0, 0, width, height),
        False,
    )
    pixmap.clear_with(255)
    return pixmap.tobytes("png")


def _write_pdf(
    path: Path,
    *,
    native_text: str | None = None,
    native_point: tuple[float, float] = (10.0, 20.0),
    image_rect: pymupdf.Rect | None = None,
) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200.0, height=200.0)
    if native_text is not None:
        page.insert_text(native_point, native_text)
    if image_rect is not None:
        page.insert_image(
            image_rect,
            stream=_png(80, 60),
            keep_proportion=False,
        )
    document.save(path)
    document.close()


class RecordingOcrProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def recognize_png(self, image: bytes) -> OcrResult:
        assert image.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", image[16:24])
        self.calls.append((width, height))
        return OcrResult(
            request_id="fixture-runtime-ocr-request",
            observations=(
                OcrObservation(
                    raw_text="M8",
                    confidence=98.5,
                    polygon=(
                        (12.0, 8.0),
                        (72.0, 8.0),
                        (72.0, 32.0),
                        (12.0, 32.0),
                    ),
                    angle=0.0,
                ),
            ),
        )


def _recognition(
    provider: RecordingOcrProvider,
    factory_calls: list[str],
) -> RuntimeRecognition:
    def provider_factory(_settings: Settings) -> RecordingOcrProvider:
        factory_calls.append("factory")
        return provider

    return RuntimeRecognition(
        Settings(storage_root=Path("/tmp/not-used")),
        provider_factory=provider_factory,
    )


def test_vector_page_with_complete_native_text_makes_zero_ocr_calls(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "vector.pdf"
    _write_pdf(
        pdf_path,
        native_text="COMPLETE NATIVE ENGINEERING DIMENSION TEXT",
    )
    native = build_native_inventory(pdf_path)
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []
    recognition = _recognition(provider, factory_calls)

    enhanced = recognition.build_inventory(pdf_path)

    assert enhanced[0].processing_route == "native"
    assert enhanced[0].observations == native[0].observations
    assert provider.calls == []
    assert factory_calls == []


def test_hybrid_image_region_appends_separate_coordinate_safe_ocr_observation(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "hybrid.pdf"
    image_rect = pymupdf.Rect(100.0, 100.0, 160.0, 140.0)
    _write_pdf(pdf_path, native_text="M6", image_rect=image_rect)
    native = build_native_inventory(pdf_path)
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []
    recognition = _recognition(provider, factory_calls)

    enhanced = recognition.build_inventory(pdf_path)
    snapshot = recognition.build_candidate_snapshot(enhanced)

    assert enhanced[0].processing_route == "hybrid"
    assert enhanced[0].observations[: len(native[0].observations)] == (
        native[0].observations
    )
    appended = enhanced[0].observations[len(native[0].observations) :]
    assert len(appended) == 1
    assert appended[0].source_type == "ocr"
    assert appended[0].bbox_pdf == pytest.approx(
        (106.0, 104.0, 136.0, 116.0),
        abs=0.5,
    )
    assert all(0.0 <= value <= 1.0 for value in appended[0].bbox_normalized)
    assert snapshot.provider_call_ids == ("fixture-runtime-ocr-request",)
    assert provider.calls == [(120, 80)]
    assert factory_calls == ["factory"]


def test_supported_full_page_hybrid_uses_bounded_local_ocr_crops(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "supported-hybrid.pdf"
    _write_pdf(
        pdf_path,
        native_text="NATIVE DIMENSION TEXT REMAINS AUTHORITATIVE",
        image_rect=pymupdf.Rect(0.0, 0.0, 200.0, 200.0),
    )
    native = build_native_inventory(pdf_path)
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    enhanced = _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert enhanced[0].page_type == "hybrid"
    assert enhanced[0].support_level == "supported"
    assert enhanced[0].observations[: len(native[0].observations)] == (
        native[0].observations
    )
    assert 1 <= len(provider.calls) <= 16
    assert all(dimensions != (400, 400) for dimensions in provider.calls)
    assert sum(
        observation.source_type == "ocr"
        for observation in enhanced[0].observations
    ) == len(provider.calls)
    assert factory_calls == ["factory"]


def test_small_native_bbox_does_not_suppress_remaining_large_image_region(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "partially-native-image.pdf"
    _write_pdf(
        pdf_path,
        native_text="M6",
        native_point=(40.0, 45.0),
        image_rect=pymupdf.Rect(20.0, 20.0, 180.0, 160.0),
    )
    native = build_native_inventory(pdf_path)
    native_bbox = next(
        observation.bbox_pdf
        for observation in native[0].observations
        if observation.observation_level == "line"
    )
    image_rect = pymupdf.Rect(20.0, 20.0, 180.0, 160.0)
    assert image_rect.contains(pymupdf.Rect(native_bbox))
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    enhanced = _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert enhanced[0].processing_route == "hybrid"
    assert provider.calls
    assert any(
        observation.source_type == "ocr"
        for observation in enhanced[0].observations
    )
    assert enhanced[0].observations[: len(native[0].observations)] == (
        native[0].observations
    )
    assert factory_calls == ["factory"]


def test_runtime_ocr_is_capped_at_sixteen_local_crops(tmp_path: Path) -> None:
    pdf_path = tmp_path / "many-regions.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300.0, height=240.0)
    page.insert_text((5.0, 12.0), "M6")
    image = _png(40, 30)
    for row in range(4):
        for column in range(5):
            x0 = 20.0 + column * 52.0
            y0 = 24.0 + row * 48.0
            page.insert_image(
                pymupdf.Rect(x0, y0, x0 + 40.0, y0 + 30.0),
                stream=image,
                keep_proportion=False,
            )
    document.save(pdf_path)
    document.close()
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert len(provider.calls) == 16
    assert factory_calls == ["factory"]


def test_ocr_never_receives_whole_page_when_only_one_image_region_is_missing(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "bounded-region.pdf"
    _write_pdf(
        pdf_path,
        native_text="M6",
        image_rect=pymupdf.Rect(100.0, 100.0, 160.0, 140.0),
    )
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert provider.calls == [(120, 80)]
    assert provider.calls[0][0] < 400
    assert provider.calls[0][1] < 400
    assert factory_calls == ["factory"]


def test_pure_scanned_page_stays_unsupported_without_ocr_promotion(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    _write_pdf(
        pdf_path,
        image_rect=pymupdf.Rect(0.0, 0.0, 200.0, 200.0),
    )
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    pages = _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert pages[0].support_level == "unsupported"
    assert pages[0].processing_route == "unsupported"
    assert pages[0].observations == ()
    assert provider.calls == []
    assert factory_calls == []
