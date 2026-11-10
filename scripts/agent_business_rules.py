"""Construction-agent business invariants.

The document payload is untrusted agent output. Approval, authorization, registry
and template facts must be supplied by a trusted client/runtime context, never
copied from the agent payload itself.
"""
from __future__ import annotations

from typing import Any


def _issue(code: str, path: str, message: str, severity: str = "BLOCKER") -> dict[str, str]:
    return {"code": code, "path": path, "message": message, "severity": severity}


def _nonempty_locator(locator: Any) -> bool:
    return isinstance(locator, dict) and any(
        value not in (None, "", [], {}) for value in locator.values()
    )


def _approval_matches(context: dict, *, artifact_id: str, revision: Any, role: str) -> bool:
    record = context.get("approval_record")
    return bool(
        isinstance(record, dict)
        and record.get("decision") == "approved"
        and record.get("artifact_id") == artifact_id
        and record.get("revision") == revision
        and record.get("actor_role") == role
        and record.get("authorized") is True
        and record.get("actor_id")
        and record.get("approval_id")
    )


def validate_gip_result(doc: dict, context: dict | None = None) -> list[dict[str, str]]:
    context = context or {}
    issues: list[dict[str, str]] = []
    sources = {s.get("source_id"): s for s in doc.get("source_documents", [])}
    seen: set[str] = set()

    for index, position in enumerate(doc.get("positions", [])):
        path = f"positions[{index}]"
        pid = position.get("position_id")
        if pid in seen:
            issues.append(_issue("GIP_DUPLICATE_POSITION_ID", path, f"Повторяется position_id: {pid}"))
        seen.add(pid)

        origin = position.get("quantity_origin")
        quantity = position.get("quantity")
        evidence = position.get("evidence", [])
        if origin == "undetermined" and quantity is not None:
            issues.append(_issue("GIP_UNDETERMINED_HAS_QUANTITY", path, "Для undetermined количество должно быть null."))
        if origin in {"extracted", "calculated", "interpreted"} and quantity is None:
            issues.append(_issue("GIP_MISSING_QUANTITY", path, "Для определённого происхождения количества значение обязательно."))
        if origin == "calculated":
            if not position.get("calculation_method") or not position.get("formula"):
                issues.append(_issue("GIP_CALCULATION_BASIS_MISSING", path, "Расчётная позиция требует метода и формулы."))
        expected_relation = {
            "extracted": "extracted_from",
            "calculated": "calculated_from",
            "interpreted": "interpreted_from",
        }.get(origin)
        if expected_relation and not any(e.get("relation") == expected_relation for e in evidence):
            issues.append(_issue("GIP_EVIDENCE_RELATION_MISMATCH", path, f"Нет доказательства с relation={expected_relation}."))
        for ev_index, ev in enumerate(evidence):
            source = sources.get(ev.get("source_id"))
            ev_path = f"{path}.evidence[{ev_index}]"
            if source is None:
                issues.append(_issue("GIP_EVIDENCE_SOURCE_UNKNOWN", ev_path, "Источник позиции отсутствует в source_documents."))
                continue
            if ev.get("revision_id") != source.get("revision_id") or ev.get("document_code") != source.get("document_code"):
                issues.append(_issue("GIP_EVIDENCE_REVISION_MISMATCH", ev_path, "Редакция или шифр доказательства не совпадает с источником."))
            if not _nonempty_locator(ev.get("locator")):
                issues.append(_issue("GIP_EVIDENCE_LOCATOR_EMPTY", ev_path, "Доказательство должно иметь точный локатор."))

    if doc.get("approval_status") == "approved_by_gip":
        blocking = [x for x in doc.get("issues", []) if x.get("severity") in {"critical", "major"}]
        if blocking:
            issues.append(_issue("GIP_APPROVAL_HAS_BLOCKING_ISSUES", "issues", "Нельзя утвердить ВОР при незакрытых CRITICAL/MAJOR замечаниях."))
        if doc.get("open_questions"):
            issues.append(_issue("GIP_APPROVAL_HAS_OPEN_QUESTIONS", "open_questions", "Нельзя утвердить ВОР с открытыми вопросами."))
        for index, position in enumerate(doc.get("positions", [])):
            if position.get("verification_status") != "verified":
                issues.append(_issue("GIP_APPROVAL_POSITION_UNVERIFIED", f"positions[{index}]", "Все позиции утверждаемой ВОР должны иметь статус verified."))
        if not _approval_matches(context, artifact_id=doc.get("boq_id"), revision=doc.get("revision"), role="GIP"):
            issues.append(_issue("GIP_APPROVAL_NOT_AUTHORIZED", "approval_status", "Статус approved_by_gip не подтверждён доверенной записью согласования уполномоченного ГИПа."))
    return issues


def validate_pto_result(doc: dict, context: dict | None = None) -> list[dict[str, str]]:
    context = context or {}
    issues: list[dict[str, str]] = []
    source_ids = {s.get("source_id") for s in doc.get("source_documents", [])}
    for index, field in enumerate(doc.get("fields", [])):
        for source_ref in field.get("source_refs", []):
            if source_ref not in source_ids:
                issues.append(_issue("PTO_FIELD_SOURCE_UNKNOWN", f"fields[{index}].source_refs", f"Неизвестный источник поля: {source_ref}."))

    status = doc.get("document_status")
    if status in {"approved_for_release", "released"}:
        if doc.get("validation", {}).get("passed") is not True or doc.get("validation", {}).get("findings"):
            issues.append(_issue("PTO_RELEASE_VALIDATION_FAILED", "validation", "Нельзя передавать документ к выпуску при проваленной проверке или открытых замечаниях."))
        for index, field in enumerate(doc.get("fields", [])):
            if field.get("value_status") not in {"confirmed", "not_applicable"}:
                issues.append(_issue("PTO_RELEASE_FIELD_UNCONFIRMED", f"fields[{index}]", "Для выпуска обязательны подтверждённые или неприменимые поля."))
        for index, appendix in enumerate(doc.get("appendices", [])):
            if appendix.get("status") not in {"attached", "not_required"}:
                issues.append(_issue("PTO_RELEASE_APPENDIX_INCOMPLETE", f"appendices[{index}]", "Приложение должно быть приложено или обоснованно отмечено как неприменимое."))
        template = context.get("template_registry", {})
        if not (
            template.get("template_id") == doc.get("template", {}).get("template_id")
            and template.get("revision") == doc.get("template", {}).get("revision")
            and template.get("active") is True
        ):
            issues.append(_issue("PTO_TEMPLATE_NOT_AUTHORIZED", "template", "Шаблон/редакция не подтверждены доверенным реестром утверждённых шаблонов."))
    if status == "released":
        if not _approval_matches(context, artifact_id=doc.get("document_id"), revision=context.get("document_revision"), role="PTO_RELEASE_AUTHORITY"):
            issues.append(_issue("PTO_RELEASE_NOT_AUTHORIZED", "document_status", "Выпуск не подтверждён отдельным решением уполномоченного лица."))
    return issues


def validate_estimator_result(doc: dict, context: dict | None = None) -> list[dict[str, str]]:
    context = context or {}
    issues: list[dict[str, str]] = []
    preservation = doc.get("data_preservation_check", {})
    losses = preservation.get("losses_detected", [])
    required_fields = {"norm_code", "norm_name", "unit", "quantity"}
    checked = set(preservation.get("checked_fields", []))
    if losses and preservation.get("passed") is True:
        issues.append(_issue("ESTIMATOR_FALSE_PRESERVATION_PASS", "data_preservation_check", "Нельзя заявлять passed=true при обнаруженных потерях."))
    if doc.get("estimate_status") in {"approved", "exported"}:
        registry = context.get("boq_registry", {})
        source_boq = doc.get("source_boq", {})
        if not (
            registry.get("boq_id") == source_boq.get("boq_id")
            and registry.get("revision") == source_boq.get("revision")
            and registry.get("approval_status") == "approved_by_gip"
            and registry.get("authorized") is True
        ):
            issues.append(_issue("ESTIMATOR_SOURCE_BOQ_NOT_VERIFIED", "source_boq", "Утверждение исходной ВОР не подтверждено доверенным реестром."))
        if losses or preservation.get("passed") is not True or not required_fields.issubset(checked):
            issues.append(_issue("ESTIMATOR_PRESERVATION_GATE_FAILED", "data_preservation_check", "Для утверждения обязательны проверка кодов, наименований, единиц и количеств без потерь."))
        if doc.get("open_questions"):
            issues.append(_issue("ESTIMATOR_OPEN_QUESTIONS", "open_questions", "Нельзя утвердить смету с открытыми вопросами."))
        for index, position in enumerate(doc.get("positions", [])):
            if position.get("mapping_status") != "matched":
                issues.append(_issue("ESTIMATOR_MAPPING_UNRESOLVED", f"positions[{index}]", "Все позиции должны иметь подтверждённое сопоставление нормы."))
    if doc.get("estimate_status") == "exported":
        round_trip = context.get("round_trip_check", {})
        if round_trip.get("performed") is not True or round_trip.get("result") != "identical":
            issues.append(_issue("ESTIMATOR_ROUND_TRIP_NOT_PASSED", "estimate_status", "Экспорт запрещён без успешного обратного сравнения без расхождений."))
        if not _approval_matches(context, artifact_id=doc.get("estimate_id"), revision=context.get("estimate_revision"), role="ESTIMATOR_APPROVER"):
            issues.append(_issue("ESTIMATOR_EXPORT_NOT_AUTHORIZED", "estimate_status", "Экспорт не подтверждён уполномоченным сметчиком/пользователем."))
    return issues


def validate_qa_review_result(doc: dict, context: dict | None = None) -> list[dict[str, str]]:
    context = context or {}
    issues: list[dict[str, str]] = []
    subject = doc.get("subject", {})
    author = subject.get("author_agent_id")
    reviewer = context.get("reviewer_agent_id")
    independent = context.get("reviewer_independent") is True and reviewer and reviewer != author
    status = doc.get("status")
    findings = doc.get("findings", [])
    unresolved = [f for f in findings if f.get("status") not in {"closed", "accepted_risk"}]
    severe = [f for f in unresolved if f.get("severity") in {"BLOCKER", "CRITICAL"}]
    major = [f for f in unresolved if f.get("severity") == "MAJOR"]

    if status == "QA_PASSED":
        if not independent:
            issues.append(_issue("QA_NOT_INDEPENDENT", "status", "QA_PASSED требует независимого проверяющего, отличного от автора результата."))
        if any(c.get("result") not in {"passed", "not_applicable"} for c in doc.get("checks", [])):
            issues.append(_issue("QA_REQUIRED_CHECKS_INCOMPLETE", "checks", "QA_PASSED невозможен при пропущенных, заблокированных или проваленных проверках."))
        if doc.get("unverified_items"):
            issues.append(_issue("QA_UNVERIFIED_ITEMS_REMAIN", "unverified_items", "QA_PASSED невозможен при непроверенных пунктах."))
        if severe or major:
            issues.append(_issue("QA_BLOCKING_FINDINGS_REMAIN", "findings", "QA_PASSED невозможен при незакрытых BLOCKER/CRITICAL/MAJOR замечаниях."))
        minor_open = [f for f in unresolved if f.get("severity") == "MINOR"]
        if minor_open and context.get("minor_risk_policy_approved") is not True:
            issues.append(_issue("QA_MINOR_POLICY_MISSING", "findings", "Открытые MINOR допускаются только по явно утверждённой политике выпуска."))
    if status == "CONDITIONAL_PASS":
        if not independent:
            issues.append(_issue("QA_CONDITIONAL_NOT_INDEPENDENT", "status", "CONDITIONAL_PASS требует независимого проверяющего."))
        if severe:
            issues.append(_issue("QA_CONDITIONAL_HAS_SEVERE_FINDINGS", "findings", "CONDITIONAL_PASS запрещён при незакрытых BLOCKER/CRITICAL замечаниях."))
        risk = context.get("risk_acceptance", {})
        if not (risk.get("approved") is True and risk.get("owner_id") and risk.get("decision_id")):
            issues.append(_issue("QA_RISK_NOT_ACCEPTED", "status", "CONDITIONAL_PASS требует отдельного решения и идентифицированного владельца риска."))
        if not any(f.get("severity") in {"MAJOR", "MINOR"} and f.get("status") not in {"closed", "accepted_risk"} for f in findings):
            issues.append(_issue("QA_CONDITIONAL_WITHOUT_OPEN_RISK", "findings", "CONDITIONAL_PASS должен отражать конкретный открытый риск MAJOR/MINOR."))
    return issues


VALIDATORS = {
    "gip-result": validate_gip_result,
    "pto-result": validate_pto_result,
    "estimator-result": validate_estimator_result,
    "qa-review-result": validate_qa_review_result,
}
