import base64
import json
from types import SimpleNamespace

import pytest

from app.providers.tencent_ocr import TencentOcrProvider, normalize_response
from tests.support.provider_cycle import open_cycle_ledger


def test_normalizes_text_polygon_angle_and_request_id(tencent_fixture: dict) -> None:
    """P0-REC-004: Tencent response becomes an independent OCR observation."""
    result = normalize_response(tencent_fixture)

    assert result.request_id == "fixture-request-id"
    assert result.observations[0].raw_text == "M6深10"
    assert result.observations[0].confidence == 97.5
    assert result.observations[0].polygon == (
        (12.0, 14.0),
        (72.0, 14.0),
        (72.0, 34.0),
        (12.0, 34.0),
    )
    assert result.observations[0].angle == 0.0


def test_general_accurate_request_shape_is_exact() -> None:
    """P0-REC-004: Tencent adapter pins the approved five request fields."""

    class FakeTencentClient:
        def __init__(self) -> None:
            self.requests: list[object] = []

        def GeneralAccurateOCR(self, request):
            self.requests.append(request)
            return SimpleNamespace(
                RequestId="fake-request-id",
                Angle=0.0,
                TextDetections=[],
            )

    image = b"\x89PNG\r\ncontrolled-crop"
    client = FakeTencentClient()

    result = TencentOcrProvider(client).recognize_png(image)

    assert result.request_id == "fake-request-id"
    assert len(client.requests) == 1
    request_payload = {
        key: value
        for key, value in json.loads(client.requests[0].to_json_string()).items()
        if value is not None
    }
    assert request_payload == {
        "ImageBase64": base64.b64encode(image).decode("ascii"),
        "ConfigID": "OCR",
        "WordsType": "2",
        "IsWords": False,
        "EnableDetectSplit": True,
    }


def test_exact_cycle_tencent_adapter_requires_and_consumes_one_permit(
    tmp_path,
) -> None:
    class FakeTencentClient:
        def __init__(self) -> None:
            self.calls = 0

        def GeneralAccurateOCR(self, _request):
            self.calls += 1
            return SimpleNamespace(
                RequestId="fake-cycle-request-id",
                Angle=0.0,
                TextDetections=[],
            )

    ledger = open_cycle_ledger(tmp_path, project_id="project-tencent-adapter")
    client = FakeTencentClient()
    provider = TencentOcrProvider(client, require_cycle_permit=True)
    image = b"\x89PNG\r\ncontrolled-crop"

    with pytest.raises(ValueError, match="permit"):
        provider.recognize_png(image)
    assert client.calls == 0

    permit = ledger.reserve(
        provider="tencent-ocr",
        operation="GeneralAccurateOCR",
        page_index=0,
        subject_kind="ocr_region",
        subject_id="fixture-region",
        retry_index=0,
        crop_expansion_count=0,
    )
    result = provider.recognize_png(image, reservation_permit=permit)
    assert result.request_id == "fake-cycle-request-id"
    assert client.calls == 1
    assert ledger.snapshot().submission_started_count == 1

    with pytest.raises(ValueError, match="permit"):
        provider.recognize_png(image, reservation_permit=permit)
    assert client.calls == 1


@pytest.mark.parametrize(
    "response",
    (
        {"Angle": 0.0, "TextDetections": []},
        {
            "RequestId": "request-id",
            "Angle": 0.0,
            "TextDetections": [{"DetectedText": "M6", "Confidence": 99.0}],
        },
        {
            "RequestId": "request-id",
            "Angle": 0.0,
            "TextDetections": [
                {
                    "DetectedText": "M6",
                    "Confidence": 101.0,
                    "Polygon": [{"X": 1, "Y": 1}] * 4,
                }
            ],
        },
        {
            "RequestId": "request-id",
            "Angle": 0.0,
            "TextDetections": [
                {
                    "DetectedText": "M6",
                    "Confidence": 99.0,
                    "Polygon": [{"X": 1, "Y": 1}],
                }
            ],
        },
        {
            "RequestId": "request-id",
            "Angle": 0.0,
            "TextDetections": [
                {
                    "DetectedText": "   ",
                    "Confidence": 99.0,
                    "Polygon": [{"X": 1, "Y": 1}] * 4,
                }
            ],
        },
    ),
)
def test_malformed_tencent_response_is_rejected(response: dict) -> None:
    """P0-REC-004: incomplete OCR responses cannot become normal observations."""
    with pytest.raises(ValueError, match="Tencent OCR response"):
        normalize_response(response)
