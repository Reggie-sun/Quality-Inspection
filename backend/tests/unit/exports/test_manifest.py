from __future__ import annotations

import json

from app.exports.manifest import ArtifactDigest, ExportManifest, sha256_bytes


def _manifest() -> ExportManifest:
    return ExportManifest(
        schema_version="export-manifest/2",
        export_id="00000000-0000-0000-0000-000000000101",
        project_id="00000000-0000-0000-0000-000000000102",
        reviewed_result_id="00000000-0000-0000-0000-000000000103",
        input_pdf_sha256="1" * 64,
        template_id="sip-v1",
        template_version="1",
        template_sha256="2" * 64,
        mapping_version="1",
        font_sha256="3" * 64,
        renderer_version="balloon-pdf/1",
        reviewed_item_count=2,
        balloon_required_count=1,
        balloon_count=1,
        source_page_count=1,
        confidence_policy_versions=("candidate-confidence/1",),
        auto_accepted_item_count=1,
        manual_override_item_count=0,
        artifacts=(
            ArtifactDigest(
                kind="ballooned_pdf",
                filename="drawing-ballooned.pdf",
                sha256="4" * 64,
                size_bytes=41,
                reviewed_result_id="00000000-0000-0000-0000-000000000103",
            ),
            ArtifactDigest(
                kind="sip_excel",
                filename="drawing-sip.xlsx",
                sha256="5" * 64,
                size_bytes=52,
                reviewed_result_id="00000000-0000-0000-0000-000000000103",
            ),
        ),
    )


def test_manifest_is_canonical_and_versioned() -> None:
    """P0-EXP-008 serializes the complete versioned export identity."""
    manifest = _manifest()

    first = manifest.to_bytes()
    second = manifest.to_bytes()
    payload = json.loads(first)

    assert first == second
    assert first.endswith(b"\n")
    assert payload == {
        "artifacts": [
            {
                "filename": "drawing-ballooned.pdf",
                "kind": "ballooned_pdf",
                "reviewed_result_id": manifest.reviewed_result_id,
                "sha256": "4" * 64,
                "size_bytes": 41,
            },
            {
                "filename": "drawing-sip.xlsx",
                "kind": "sip_excel",
                "reviewed_result_id": manifest.reviewed_result_id,
                "sha256": "5" * 64,
                "size_bytes": 52,
            },
        ],
        "balloon_count": 1,
        "balloon_required_count": 1,
        "auto_accepted_item_count": 1,
        "confidence_policy_versions": ["candidate-confidence/1"],
        "export_id": manifest.export_id,
        "font_sha256": "3" * 64,
        "input_pdf_sha256": "1" * 64,
        "mapping_version": "1",
        "manual_override_item_count": 0,
        "project_id": manifest.project_id,
        "renderer_version": "balloon-pdf/1",
        "reviewed_item_count": 2,
        "reviewed_result_id": manifest.reviewed_result_id,
        "schema_version": "export-manifest/2",
        "source_page_count": 1,
        "template_id": "sip-v1",
        "template_sha256": "2" * 64,
        "template_version": "1",
    }


def test_manifest_lists_only_non_recursive_artifact_digests() -> None:
    """P0-EXP-008 keeps the manifest digest in the database, not itself."""
    content = _manifest().to_bytes()
    payload = json.loads(content)

    assert [artifact["kind"] for artifact in payload["artifacts"]] == [
        "ballooned_pdf",
        "sip_excel",
    ]
    assert len(sha256_bytes(content)) == 64
