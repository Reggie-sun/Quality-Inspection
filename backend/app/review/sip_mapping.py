from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RULE_VERSION = "sip-auto-map/1"

METHOD_BY_TYPE = {
    "linear_dimension": "游标卡尺",
    "diameter_dimension": "游标卡尺",
    "thread": "螺纹规",
    "radius": "半径规",
    "angle": "万能角度尺",
    "general_requirement": "目视",
    "roughness": "粗糙度仪",
}

ITEM_LABEL_BY_TYPE = {
    "linear_dimension": "线性尺寸",
    "diameter_dimension": "直径尺寸",
    "thread": "螺纹",
    "radius": "半径",
    "angle": "角度",
    "general_requirement": "通用要求",
    "roughness": "粗糙度",
}


@dataclass(frozen=True)
class SipMappingResult:
    fields: dict[str, object]
    provenance: dict[str, str]
    exceptions: tuple[str, ...]


def map_sip_item(
    item: dict[str, Any],
    *,
    inspection_role: str,
) -> SipMappingResult:
    item_type = item.get("item_type") or item.get("coarse_type")
    provenance = _provenance(item)
    fields: dict[str, object] = {}
    exceptions: list[str] = []

    inspection_item = _preserved_text(item, provenance, "inspection_item")
    if inspection_item is None:
        label = ITEM_LABEL_BY_TYPE.get(item_type, "检验项目")
        text = _text(item.get("normalized_text")) or _text(item.get("raw_text"))
        inspection_item = f"{label}：{text}" if text else label
        quantity = item.get("quantity")
        if isinstance(quantity, int) and not isinstance(quantity, bool) and quantity >= 1:
            inspection_item = f"{inspection_item}（{quantity}处）"
        provenance["inspection_item"] = RULE_VERSION
    fields["inspection_item"] = inspection_item

    inspection_standard = _preserved_text(
        item,
        provenance,
        "inspection_standard",
    )
    if inspection_standard is None:
        inspection_standard = "图纸要求"
        provenance["inspection_standard"] = RULE_VERSION
    fields["inspection_standard"] = inspection_standard

    inspection_method = _preserved_text(
        item,
        provenance,
        "inspection_method",
    )
    if inspection_method is None:
        inspection_method = METHOD_BY_TYPE.get(item_type)
        if item_type == "composite":
            exceptions.append("composite_method_required")
        elif inspection_method is None:
            exceptions.append("unsupported_item_type")
        else:
            provenance["inspection_method"] = RULE_VERSION
    if inspection_method is not None:
        fields["inspection_method"] = inspection_method

    key_dimension = _preserved_text(item, provenance, "key_dimension")
    if key_dimension is None:
        key_dimension = (
            "是"
            if item.get("critical") is True or item.get("is_critical") is True
            else "否"
        )
        provenance["key_dimension"] = RULE_VERSION
    fields["key_dimension"] = key_dimension

    resolved_role = _preserved_text(item, provenance, "inspection_role")
    if resolved_role is None:
        resolved_role = inspection_role.strip()
        if resolved_role:
            provenance["inspection_role"] = RULE_VERSION
        else:
            exceptions.append("missing_inspection_role")
    if resolved_role:
        fields["inspection_role"] = resolved_role

    source_page = _preserved_page(item, provenance)
    if source_page is None:
        page_index = item.get("page_index")
        if (
            isinstance(page_index, int)
            and not isinstance(page_index, bool)
            and page_index >= 0
        ):
            source_page = page_index + 1
            provenance["source_page"] = RULE_VERSION
        else:
            exceptions.append("missing_source_page")
    if source_page is not None:
        fields["source_page"] = source_page

    remarks = item.get("remarks")
    if not isinstance(remarks, str) or provenance.get("remarks") == RULE_VERSION:
        remarks = ""
        provenance["remarks"] = RULE_VERSION
    fields["remarks"] = remarks

    return SipMappingResult(
        fields=fields,
        provenance=provenance,
        exceptions=tuple(exceptions),
    )


def _provenance(item: dict[str, Any]) -> dict[str, str]:
    value = item.get("sip_suggestion_provenance")
    if not isinstance(value, dict):
        return {}
    return {
        str(field): source
        for field, source in value.items()
        if isinstance(source, str) and source
    }


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _preserved_text(
    item: dict[str, Any],
    provenance: dict[str, str],
    field: str,
) -> str | None:
    if provenance.get(field) == RULE_VERSION:
        provenance.pop(field, None)
        return None
    return _text(item.get(field))


def _preserved_page(
    item: dict[str, Any],
    provenance: dict[str, str],
) -> int | None:
    if provenance.get("source_page") == RULE_VERSION:
        provenance.pop("source_page", None)
        return None
    value = item.get("source_page")
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 1
    ):
        return value
    return None
