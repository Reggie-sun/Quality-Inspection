import base64
import json
from types import SimpleNamespace

import pytest

from app.providers.tencent_ocr import TencentOcrProvider, normalize_response


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
