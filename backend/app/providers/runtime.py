from __future__ import annotations

from collections.abc import Callable

from tencentcloud.common import credential as tencent_credential
from tencentcloud.ocr.v20181119 import ocr_client

from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.providers.base import OcrProvider
from app.providers.tencent_ocr import TencentOcrProvider


OcrProviderFactory = Callable[[Settings], OcrProvider]


def build_ocr_provider(settings: Settings) -> OcrProvider:
    secret_id = (settings.tencent_secret_id or "").strip()
    secret_key = (settings.tencent_secret_key or "").strip()
    region = (settings.tencent_region or "").strip()
    if not secret_id or not secret_key or not region:
        raise CapabilityUnavailable(
            "ocr_provider_unavailable",
            "OCR Provider configuration is unavailable",
        )
    credential = tencent_credential.Credential(secret_id, secret_key)
    client = ocr_client.OcrClient(credential, region)
    return TencentOcrProvider(client)
