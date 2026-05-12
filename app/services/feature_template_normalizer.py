"""기능템플릿 LLM/fallback dict → FeatureTemplateData용 안전 구조 보정."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.schemas.feature_template import FeatureTemplateGenerateRequest

__all__ = [
    "FeatureTemplateNormalizer",
    "normalize_feature_template_payload",
]

logger = logging.getLogger(__name__)

_PRIORITY_NUMBER_MAP: dict[int, str] = {
    1: "HIGH",
    2: "MEDIUM",
    3: "LOW",
}

_TOP_LEVEL_STRING_FIELDS: dict[str, tuple[str, ...]] = {
    "overview": ("featureName", "purpose", "resultDescription"),
    "flow.layers": ("layer", "role"),
    "requirements": (
        "requirementId",
        "name",
        "description",
        "inputValue",
        "processCondition",
        "successResult",
        "failureResult",
        "priority",
        "relatedScreenOrApi",
    ),
    "apiSpec": ("apiName", "method", "endpoint", "description"),
    "codeFiles": ("fileName", "role", "language", "content"),
    "basicQuestions": (
        "questionId",
        "type",
        "question",
        "answer",
        "explanation",
        "relatedSection",
        "difficulty",
    ),
    "missions": ("missionId", "title", "description", "missionType", "difficulty"),
    "interviewQuestions": ("questionId", "question", "sampleAnswer", "relatedSection"),
    "nextRecommendations": ("featureName", "reason", "expectedLearning"),
}

_STRING_LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "overview": ("useCases", "techStack", "learningGoals"),
    "flow": ("steps",),
    "basicQuestions": ("choices",),
    "missions": ("requirements", "successCriteria", "relatedRequirements"),
    "interviewQuestions": ("keyPoints",),
}

_TOP_LEVEL_ALIASES: dict[str, str] = {
    "api_spec": "apiSpec",
    "basic_questions": "basicQuestions",
    "interview": "interviewQuestions",
    "interview_questions": "interviewQuestions",
    "next_recommendations": "nextRecommendations",
}


def _coerce_to_string(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _normalize_string_fields(
    item: dict,
    fields: tuple[str, ...],
    path_prefix: str,
    changed_fields: list[str],
) -> dict:
    normalized_item = dict(item)
    for field in fields:
        if field not in normalized_item:
            continue
        value = normalized_item[field]
        if value is None and field in {"filePath", "relatedSection"}:
            continue
        if not isinstance(value, str):
            normalized_item[field] = _coerce_to_string(value)
            changed_fields.append(f"{path_prefix}.{field}")
    return normalized_item


def _normalize_string_list_field(
    item: dict,
    field: str,
    path_prefix: str,
    changed_fields: list[str],
) -> dict:
    if field not in item:
        return item

    normalized_item = dict(item)
    values = normalized_item[field]
    if values is None and field == "choices":
        return normalized_item
    if not isinstance(values, list):
        normalized_item[field] = [_coerce_to_string(values)]
        changed_fields.append(f"{path_prefix}.{field}")
        return normalized_item

    normalized_values = []
    changed = False
    for value in values:
        if isinstance(value, str):
            normalized_values.append(value)
        else:
            normalized_values.append(_coerce_to_string(value))
            changed = True
    if changed:
        normalized_item[field] = normalized_values
        changed_fields.append(f"{path_prefix}.{field}")
    return normalized_item


def normalize_feature_template_payload(payload: dict) -> dict:
    """LLM 응답에서 자주 흔들리는 타입만 Pydantic 검증 전에 보정한다."""
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    changed_fields: list[str] = []

    requirements = normalized.get("requirements")
    if isinstance(requirements, list):
        normalized_requirements = []
        for index, item in enumerate(requirements):
            if not isinstance(item, dict):
                continue

            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS["requirements"],
                f"requirements[{index}]",
                changed_fields,
            )
            priority = normalized_item.get("priority")
            if isinstance(priority, int):
                normalized_item["priority"] = _PRIORITY_NUMBER_MAP.get(
                    priority,
                    str(priority),
                )
                changed_fields.append(f"requirements[{index}].priority")
            elif isinstance(priority, str) and priority.strip().isdigit():
                normalized_item["priority"] = _PRIORITY_NUMBER_MAP.get(
                    int(priority.strip()),
                    priority,
                )
                changed_fields.append(f"requirements[{index}].priority")
            elif priority is not None and not isinstance(priority, str):
                normalized_item["priority"] = str(priority)
                changed_fields.append(f"requirements[{index}].priority")
            normalized_requirements.append(normalized_item)
        normalized["requirements"] = normalized_requirements

    api_specs = normalized.get("apiSpec")
    if isinstance(api_specs, list):
        normalized_api_specs = []
        for index, item in enumerate(api_specs):
            if not isinstance(item, dict):
                continue

            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS["apiSpec"],
                f"apiSpec[{index}]",
                changed_fields,
            )
            status = normalized_item.get("status")
            if isinstance(status, str):
                match = re.search(r"\d{3}", status)
                if match:
                    normalized_item["status"] = int(match.group())
                    changed_fields.append(f"apiSpec[{index}].status")
                else:
                    logger.warning(
                        "Feature template normalization skipped: field=apiSpec[%s].status reason=unparseable",
                        index,
                    )
            normalized_api_specs.append(normalized_item)
        normalized["apiSpec"] = normalized_api_specs

    flow = normalized.get("flow")
    if isinstance(flow, dict):
        normalized_flow = dict(flow)
        normalized_flow = _normalize_string_list_field(
            normalized_flow,
            "steps",
            "flow",
            changed_fields,
        )
        layers = normalized_flow.get("layers")
        if isinstance(layers, list):
            normalized_layers = []
            for index, item in enumerate(layers):
                if isinstance(item, dict):
                    normalized_layers.append(
                        _normalize_string_fields(
                            item,
                            _TOP_LEVEL_STRING_FIELDS["flow.layers"],
                            f"flow.layers[{index}]",
                            changed_fields,
                        )
                    )
            normalized_flow["layers"] = normalized_layers
        normalized["flow"] = normalized_flow

    missions = normalized.get("missions")
    if isinstance(missions, list):
        normalized_missions = []
        for index, item in enumerate(missions):
            if not isinstance(item, dict):
                continue

            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS["missions"],
                f"missions[{index}]",
                changed_fields,
            )
            for field in _STRING_LIST_FIELDS["missions"]:
                normalized_item = _normalize_string_list_field(
                    normalized_item,
                    field,
                    f"missions[{index}]",
                    changed_fields,
                )
            mission_type = normalized_item.get("missionType")
            if mission_type is None:
                normalized_item["missionType"] = "implementation"
                changed_fields.append(f"missions[{index}].missionType")
            elif not isinstance(mission_type, str):
                normalized_item["missionType"] = str(mission_type)
                changed_fields.append(f"missions[{index}].missionType")
            normalized_missions.append(normalized_item)
        normalized["missions"] = normalized_missions

    overview = normalized.get("overview")
    if isinstance(overview, dict):
        normalized_overview = _normalize_string_fields(
            overview,
            _TOP_LEVEL_STRING_FIELDS["overview"],
            "overview",
            changed_fields,
        )
        for field in _STRING_LIST_FIELDS["overview"]:
            normalized_overview = _normalize_string_list_field(
                normalized_overview,
                field,
                "overview",
                changed_fields,
            )
        normalized["overview"] = normalized_overview

    for section in ("codeFiles", "basicQuestions", "interviewQuestions", "nextRecommendations"):
        items = normalized.get(section)
        if not isinstance(items, list):
            continue
        normalized_items = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS[section],
                f"{section}[{index}]",
                changed_fields,
            )
            for field in _STRING_LIST_FIELDS.get(section, ()):
                normalized_item = _normalize_string_list_field(
                    normalized_item,
                    field,
                    f"{section}[{index}]",
                    changed_fields,
                )
            normalized_items.append(normalized_item)
        normalized[section] = normalized_items

    if changed_fields:
        logger.info(
            "Feature template LLM payload normalized: fields=%s",
            ",".join(changed_fields),
        )

    return normalized


def _default_overview(request: FeatureTemplateGenerateRequest | None) -> dict[str, Any]:
    name = ""
    if request is not None:
        name = (request.featureName or "").strip()
    return {
        "featureName": name,
        "purpose": "",
        "useCases": [],
        "resultDescription": "",
        "techStack": [],
        "learningGoals": [],
    }


def _ensure_list_of_dicts(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, dict)]


def _ensure_flow(value: object) -> dict[str, Any]:
    if isinstance(value, list):
        return {"steps": [_coerce_to_string(x) for x in value], "layers": []}
    if not isinstance(value, dict):
        return {"steps": [], "layers": []}
    raw = dict(value)
    steps = raw.get("steps", [])
    if not isinstance(steps, list):
        steps = [_coerce_to_string(steps)] if steps is not None else []
    else:
        steps = [_coerce_to_string(s) for s in steps]
    layers = raw.get("layers", [])
    if not isinstance(layers, list):
        layers = []
    clean_layers: list[dict[str, Any]] = []
    for item in layers:
        if isinstance(item, dict):
            clean_layers.append(item)
    return {"steps": steps, "layers": clean_layers}


def _remap_top_level_keys(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in data.items():
        if key == "code_view":
            continue
        canon = _TOP_LEVEL_ALIASES.get(key, key)
        out[canon] = val
    if "code_view" in data and "codeFiles" not in out:
        cv = data["code_view"]
        if isinstance(cv, dict) and isinstance(cv.get("files"), list):
            out["codeFiles"] = _ensure_list_of_dicts(cv["files"])
        elif isinstance(cv, list):
            out["codeFiles"] = _ensure_list_of_dicts(cv)
        elif isinstance(cv, dict):
            out["codeFiles"] = []
    return out


class FeatureTemplateNormalizer:
    """9개 top-level 섹션을 항상 채운 뒤 타입 보정까지 수행한다."""

    @staticmethod
    def normalize(
        raw: object,
        request: FeatureTemplateGenerateRequest | None = None,
    ) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raw_dict: dict[str, Any] = {}
        else:
            raw_dict = dict(raw)

        remapped = _remap_top_level_keys(raw_dict)

        overview_base = _default_overview(request)
        overview_src = remapped.get("overview")
        overview: dict[str, Any]
        if isinstance(overview_src, dict):
            overview = {**overview_base, **overview_src}
        else:
            overview = dict(overview_base)

        requirements = _ensure_list_of_dicts(remapped.get("requirements"))
        flow = _ensure_flow(remapped.get("flow"))
        api_spec = _ensure_list_of_dicts(remapped.get("apiSpec"))
        code_files = _ensure_list_of_dicts(remapped.get("codeFiles"))
        basic_questions = _ensure_list_of_dicts(remapped.get("basicQuestions"))
        missions = _ensure_list_of_dicts(remapped.get("missions"))
        interview_questions = _ensure_list_of_dicts(remapped.get("interviewQuestions"))
        next_recommendations = _ensure_list_of_dicts(remapped.get("nextRecommendations"))

        if request is not None:
            if not request.includeCode:
                code_files = []
            if not request.includeMissions:
                missions = []
            if not request.includeInterview:
                interview_questions = []

        merged: dict[str, Any] = {
            "overview": overview,
            "requirements": requirements,
            "flow": flow,
            "apiSpec": api_spec,
            "codeFiles": code_files,
            "basicQuestions": basic_questions,
            "missions": missions,
            "interviewQuestions": interview_questions,
            "nextRecommendations": next_recommendations,
        }
        return normalize_feature_template_payload(merged)
