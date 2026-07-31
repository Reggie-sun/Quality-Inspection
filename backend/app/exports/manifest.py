from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ArtifactDigest:
    kind: str
    filename: str
    sha256: str
    size_bytes: int
    reviewed_result_id: str


@dataclass(frozen=True)
class ExportManifest:
    schema_version: str
    export_id: str
    project_id: str
    reviewed_result_id: str
    input_pdf_sha256: str
    template_id: str
    template_version: str
    template_sha256: str
    mapping_version: str
    mapping_sha256: str
    font_sha256: str
    renderer_version: str
    reviewed_item_count: int
    balloon_required_count: int
    balloon_count: int
    source_page_count: int
    confidence_policy_versions: tuple[str, ...]
    auto_accepted_item_count: int
    manual_override_item_count: int
    artifacts: tuple[ArtifactDigest, ...]

    def to_bytes(self) -> bytes:
        payload = asdict(self)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"{encoded}\n".encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
