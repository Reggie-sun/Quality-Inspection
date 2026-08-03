from __future__ import annotations

import re
from collections.abc import Callable

from openai import OpenAI
from tencentcloud.common import credential as tencent_credential
from tencentcloud.ocr.v20181119 import ocr_client

from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.providers.base import OcrProvider, VisionLlmProvider
from app.providers.qwen_vl import QwenVisionProvider
from app.providers.tencent_ocr import TencentOcrProvider


OcrProviderFactory = Callable[[Settings], OcrProvider]
VisionProviderFactory = Callable[[Settings], VisionLlmProvider]
_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


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
    return TencentOcrProvider(
        client,
        require_cycle_permit=(
            settings.provider_cycle_authorization_id is not None
        ),
    )


def build_vision_provider(settings: Settings) -> VisionLlmProvider:
    api_key = (settings.qwen_api_key or "").strip()
    workspace_id = (settings.qwen_workspace_id or "").strip()
    model = (settings.qwen_model or "").strip()
    if (
        not api_key
        or not model
        or _WORKSPACE_ID.fullmatch(workspace_id) is None
    ):
        raise CapabilityUnavailable(
            "vision_provider_unavailable",
            "Vision Provider configuration is unavailable",
        )
    client = OpenAI(
        api_key=api_key,
        base_url=(
            f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/"
            "compatible-mode/v1"
        ),
        timeout=60.0,
        max_retries=0,
    )
    return QwenVisionProvider(
        client,
        model=model,
        require_cycle_permit=(
            settings.provider_cycle_authorization_id is not None
        ),
    )
