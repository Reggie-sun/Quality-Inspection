from __future__ import annotations

import base64
import json
import math
from collections.abc import Mapping
from typing import Any

from tencentcloud.ocr.v20181119 import models

from app.providers.base import OcrObservation, OcrResult
from app.providers.usage_ledger import ReservationPermit


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _response_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Tencent OCR response contains a non-numeric value")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Tencent OCR response contains a non-numeric value") from exc
    if not math.isfinite(number):
        raise ValueError("Tencent OCR response contains a non-finite value")
    return number


def normalize_response(response: Any) -> OcrResult:
    request_id = _value(response, "RequestId")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("Tencent OCR response is missing RequestId")
    angle = _response_number(_value(response, "Angle"))
    detections = _value(response, "TextDetections")
    if not isinstance(detections, (list, tuple)):
        raise ValueError("Tencent OCR response is missing TextDetections")
    observations = []
    for detection in detections:
        raw_text = _value(detection, "DetectedText")
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("Tencent OCR response has invalid DetectedText")
        confidence = _response_number(_value(detection, "Confidence"))
        if not 0.0 <= confidence <= 100.0:
            raise ValueError("Tencent OCR response has invalid Confidence")
        coordinates = _value(detection, "Polygon")
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 4:
            raise ValueError("Tencent OCR response has invalid Polygon")
        polygon = tuple(
            (
                _response_number(_value(coordinate, "X")),
                _response_number(_value(coordinate, "Y")),
            )
            for coordinate in coordinates
        )
        observations.append(
            OcrObservation(
                raw_text=raw_text,
                confidence=confidence,
                polygon=polygon,
                angle=angle,
            )
        )
    return OcrResult(
        request_id=request_id,
        observations=tuple(observations),
    )


class TencentOcrProvider:
    def __init__(self, client: Any, *, require_cycle_permit: bool = False) -> None:
        self._client = client
        self._require_cycle_permit = require_cycle_permit

    def recognize_png(
        self,
        image: bytes,
        *,
        reservation_permit: ReservationPermit | None = None,
    ) -> OcrResult:
        request = models.GeneralAccurateOCRRequest()
        request.from_json_string(
            json.dumps(
                {
                    "ImageBase64": base64.b64encode(image).decode("ascii"),
                    "ConfigID": "OCR",
                    "WordsType": "2",
                    "IsWords": False,
                    "EnableDetectSplit": True,
                }
            )
        )
        if reservation_permit is None:
            if self._require_cycle_permit:
                raise ValueError("exact-cycle Provider call requires one permit")
        elif not isinstance(reservation_permit, ReservationPermit):
            raise ValueError("reservation permit is invalid")
        else:
            reservation_permit.consume_for_adapter(
                provider="tencent-ocr",
                operation="GeneralAccurateOCR",
            )
        return normalize_response(self._client.GeneralAccurateOCR(request))
