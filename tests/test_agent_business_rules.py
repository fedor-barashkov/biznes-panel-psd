from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.agent_business_rules import (
    validate_estimator_result,
    validate_gip_result,
    validate_pto_result,
    validate_qa_review_result,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "docs" / "AGENTS" / "contracts" / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class GIPBusinessRulesTests(unittest.TestCase):
    def setUp(self):
        self.doc = fixture("gip-result.valid.json")

    def test_draft_fixture_has_no_business_rule_violations(self):
        self.assertEqual([], validate_gip_result(self.doc))

    def test_approved_boq_requires_trusted_approval_and_verified_positions(self):
        doc = copy.deepcopy(self.doc)
        doc["approval_status"] = "approved_by_gip"
        doc["open_questions"] = []
        doc["positions"][0]["verification_status"] = "verified"
        context = {"approval_record": {
            "approval_id": "APR-1", "artifact_id": "BOQ-001", "revision": 1,
            "decision": "approved", "actor_id": "user-1", "actor_type": "human", "actor_role": "GIP",
            "authorized": True,
        }}
        self.assertEqual([], validate_gip_result(doc, context))

    def test_agent_or_service_cannot_self_approve_boq(self):
        doc = copy.deepcopy(self.doc)
        doc["approval_status"] = "approved_by_gip"
        doc["open_questions"] = []
        doc["positions"][0]["verification_status"] = "verified"
        context = {"approval_record": {
            "approval_id": "APR-SVC-1", "artifact_id": "BOQ-001", "revision": 1,
            "decision": "approved", "actor_id": "service-agent", "actor_type": "service",
            "actor_role": "GIP", "authorized": True,
        }}
        self.assertIn("GIP_APPROVAL_NOT_AUTHORIZED",
                      {x["code"] for x in validate_gip_result(doc, context)})

    def test_approved_boq_without_approval_is_blocked(self):
        doc = copy.deepcopy(self.doc)
        doc["approval_status"] = "approved_by_gip"
        self.assertIn("GIP_APPROVAL_NOT_AUTHORIZED",
                      {x["code"] for x in validate_gip_result(doc)})

    def test_approved_boq_is_blocked_with_open_major_issue(self):
        doc = copy.deepcopy(self.doc)
        doc["approval_status"] = "approved_by_gip"
        doc["open_questions"] = []
        doc["positions"][0]["verification_status"] = "verified"
        doc["issues"] = [{"issue_id": "I-1", "severity": "major",
                          "description": "Конфликт отметок", "source_refs": []}]
        context = {"approval_record": {
            "approval_id": "APR-1", "artifact_id": "BOQ-001", "revision": 1,
            "decision": "approved", "actor_id": "user-1", "actor_type": "human", "actor_role": "GIP",
            "authorized": True,
        }}
        self.assertIn("GIP_APPROVAL_HAS_BLOCKING_ISSUES",
                      {x["code"] for x in validate_gip_result(doc, context)})

    def test_evidence_must_reference_known_source_and_nonempty_locator(self):
        doc = copy.deepcopy(self.doc)
        doc["positions"][0]["evidence"][0]["source_id"] = "UNKNOWN"
        codes = {x["code"] for x in validate_gip_result(doc)}
        self.assertIn("GIP_EVIDENCE_SOURCE_UNKNOWN", codes)

    def test_evidence_without_locator_is_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["positions"][0]["evidence"][0]["locator"] = {}
        self.assertIn("GIP_EVIDENCE_LOCATOR_EMPTY",
                      {x["code"] for x in validate_gip_result(doc)})

    def test_calculated_quantity_requires_formula_and_calculation_evidence(self):
        doc = copy.deepcopy(self.doc)
        p = doc["positions"][0]
        p["quantity_origin"] = "calculated"
        p["calculation_method"] = "Геометрический расчёт"
        p["formula"] = "2 × 3"
        self.assertIn("GIP_EVIDENCE_RELATION_MISMATCH",
                      {x["code"] for x in validate_gip_result(doc)})


class PTOBusinessRulesTests(unittest.TestCase):
    def setUp(self):
        self.doc = fixture("pto-result.valid.json")
        self.context = {
            "template_registry": {
                "template_id": "USER-AOSR-TEMPLATE", "revision": "1.0", "active": True
            }
        }

    def _make_release_ready(self):
        self.doc["document_status"] = "released"
        self.doc["fields"][0]["value_status"] = "confirmed"
        self.doc["validation"] = {"passed": True, "findings": []}
        self.doc["appendices"][0]["status"] = "attached"
        self.context["approval_record"] = {
            "approval_id": "APR-PTO-1", "artifact_id": "ACT-001",
            "revision": "1", "decision": "approved", "actor_id": "user-2",
            "actor_type": "human",
            "actor_role": "PTO_RELEASE_AUTHORITY", "authorized": True,
        }
        self.context["document_revision"] = "1"

    def test_draft_fixture_has_no_business_rule_violations(self):
        self.assertEqual([], validate_pto_result(self.doc))

    def test_release_requires_complete_fields_validation_template_and_approval(self):
        self._make_release_ready()
        self.assertEqual([], validate_pto_result(self.doc, self.context))

    def test_release_is_blocked_when_field_is_unverified(self):
        self._make_release_ready()
        self.doc["fields"][0]["value_status"] = "extracted_unverified"
        self.assertIn("PTO_RELEASE_FIELD_UNCONFIRMED",
                      {x["code"] for x in validate_pto_result(self.doc, self.context)})

    def test_release_is_blocked_when_template_not_in_trusted_registry(self):
        self._make_release_ready()
        self.context["template_registry"]["active"] = False
        self.assertIn("PTO_TEMPLATE_NOT_AUTHORIZED",
                      {x["code"] for x in validate_pto_result(self.doc, self.context)})

    def test_release_is_blocked_when_required_appendix_is_missing(self):
        self._make_release_ready()
        self.doc["appendices"][0]["status"] = "missing"
        self.assertIn("PTO_RELEASE_APPENDIX_INCOMPLETE",
                      {x["code"] for x in validate_pto_result(self.doc, self.context)})

    def test_agent_payload_cannot_supply_its_own_template_authority(self):
        self._make_release_ready()
        self.context.pop("template_registry")
        self.doc["template"]["active"] = True
        self.assertIn("PTO_TEMPLATE_NOT_AUTHORIZED",
                      {x["code"] for x in validate_pto_result(self.doc, self.context)})


class EstimatorBusinessRulesTests(unittest.TestCase):
    def setUp(self):
        self.doc = fixture("estimator-result.valid.json")
        self.context = {
            "boq_registry": {
                "boq_id": "BOQ-001", "revision": 2,
                "approval_status": "approved_by_gip", "authorized": True,
                "position_ids": ["BOQ-POS-001"],
            }
        }

    def _make_approved(self):
        self.doc["estimate_status"] = "approved"
        self.doc["positions"][0]["mapping_status"] = "matched"
        self.doc["open_questions"] = []
        self.context["estimate_revision"] = "1"
        self.context["approval_record"] = {
            "approval_id": "APR-EST-1", "artifact_id": "EST-001",
            "revision": "1", "decision": "approved", "actor_id": "user-3",
            "actor_type": "human",
            "actor_role": "ESTIMATOR_APPROVER", "authorized": True,
        }

    def test_draft_allows_unresolved_mapping(self):
        self.assertEqual([], validate_estimator_result(self.doc))

    def test_approval_requires_trusted_boq_and_full_preservation(self):
        self._make_approved()
        self.assertEqual([], validate_estimator_result(self.doc, self.context))

    def test_approval_is_blocked_for_unresolved_mapping(self):
        self.doc["estimate_status"] = "approved"
        self.doc["open_questions"] = []
        self.assertIn("ESTIMATOR_MAPPING_UNRESOLVED",
                      {x["code"] for x in validate_estimator_result(self.doc, self.context)})

    def test_export_requires_identical_round_trip_and_approval(self):
        self._make_approved()
        self.doc["estimate_status"] = "exported"
        self.context["round_trip_check"] = {"performed": True, "result": "identical"}
        self.assertIn("ESTIMATOR_EXPORT_NOT_AUTHORIZED",
                      {x["code"] for x in validate_estimator_result(self.doc, self.context)})
        self.context["export_authorization"] = {
            "authorized": True, "artifact_id": "EST-001", "revision": "1",
            "operation": "grand_smeta.export", "actor_id": "user-3",
            "actor_type": "human",
            "decision_id": "EXPORT-1",
        }
        self.assertEqual([], validate_estimator_result(self.doc, self.context))
        self.context["round_trip_check"]["result"] = "differences"
        self.assertIn("ESTIMATOR_ROUND_TRIP_NOT_PASSED",
                      {x["code"] for x in validate_estimator_result(self.doc, self.context)})

    def test_approval_requires_position_code_in_preservation_scope(self):
        self._make_approved()
        self.doc["data_preservation_check"]["checked_fields"].remove("position_code")
        codes = {x["code"] for x in validate_estimator_result(self.doc, self.context)}
        self.assertIn("ESTIMATOR_PRESERVATION_GATE_FAILED", codes)

    def test_approval_requires_source_position_in_trusted_boq_revision(self):
        self._make_approved()
        self.context["boq_registry"]["position_ids"] = ["OTHER-POSITION"]
        codes = {x["code"] for x in validate_estimator_result(self.doc, self.context)}
        self.assertIn("ESTIMATOR_SOURCE_POSITION_UNKNOWN", codes)

    def test_resources_and_coefficients_must_be_in_preservation_scope(self):
        self._make_approved()
        self.doc["positions"][0]["resource_codes"] = ["RES-01"]
        self.doc["positions"][0]["coefficients"] = [{"code": "K-1", "value": 1.1}]
        codes = {x["code"] for x in validate_estimator_result(self.doc, self.context)}
        self.assertIn("ESTIMATOR_PRESERVATION_SCOPE_INCOMPLETE", codes)

    def test_export_requires_separate_export_authorization(self):
        self._make_approved()
        self.doc["estimate_status"] = "exported"
        self.context["round_trip_check"] = {"performed": True, "result": "identical"}
        self.context["export_authorization"] = {
            "authorized": True, "artifact_id": "EST-001", "revision": "other",
            "operation": "grand_smeta.export", "actor_id": "user-3",
            "actor_type": "human",
            "decision_id": "EXPORT-1",
        }
        self.assertIn("ESTIMATOR_EXPORT_NOT_AUTHORIZED",
                      {x["code"] for x in validate_estimator_result(self.doc, self.context)})


class QABusinessRulesTests(unittest.TestCase):
    def setUp(self):
        self.doc = fixture("qa-review-result.valid.json")
        self.doc["status"] = "QA_PASSED"
        self.doc["unverified_items"] = []
        self.context = {"reviewer_agent_id": "construction.qa.2", "reviewer_independent": True}

    def test_qa_passed_requires_complete_independent_review(self):
        self.assertEqual([], validate_qa_review_result(self.doc, self.context))

    def test_qa_passed_is_blocked_for_open_critical_finding(self):
        self.doc["findings"].append({
            "finding_id": "F-1", "severity": "CRITICAL",
            "description": "Не устранена критическая ошибка",
            "status": "open", "evidence_refs": ["EV-1"],
        })
        self.assertIn("QA_BLOCKING_FINDINGS_REMAIN",
                      {x["code"] for x in validate_qa_review_result(self.doc, self.context)})

    def test_qa_passed_is_blocked_when_reviewer_is_author(self):
        self.context["reviewer_agent_id"] = "construction.gip"
        self.assertIn("QA_NOT_INDEPENDENT",
                      {x["code"] for x in validate_qa_review_result(self.doc, self.context)})

    def test_conditional_pass_requires_every_open_risk_to_be_in_decision(self):
        self.doc["status"] = "CONDITIONAL_PASS"
        self.doc["findings"].append({
            "finding_id": "F-3", "severity": "MAJOR",
            "description": "Риск не включён в решение",
            "status": "open", "evidence_refs": ["EV-3"],
        })
        self.context["risk_acceptance"] = {
            "approved": True, "owner_id": "risk-owner-1", "actor_id": "risk-owner-1", "actor_type": "human", "decision_id": "RISK-1",
            "finding_ids": ["F-2"],
        }
        self.assertIn("QA_RISK_SCOPE_MISMATCH",
                      {x["code"] for x in validate_qa_review_result(self.doc, self.context)})

    def test_conditional_pass_is_blocked_for_unverified_checks(self):
        self.doc["status"] = "CONDITIONAL_PASS"
        self.doc["unverified_items"] = ["Непроверенный пункт"]
        self.doc["findings"].append({
            "finding_id": "F-2", "severity": "MAJOR",
            "description": "Остаточный риск",
            "status": "open", "evidence_refs": ["EV-2"],
        })
        self.context["risk_acceptance"] = {
            "approved": True, "owner_id": "risk-owner-1", "actor_id": "risk-owner-1", "actor_type": "human", "decision_id": "RISK-1",
            "finding_ids": ["F-2"],
        }
        self.assertIn("QA_CONDITIONAL_NOT_VERIFIED",
                      {x["code"] for x in validate_qa_review_result(self.doc, self.context)})

    def test_conditional_pass_requires_risk_owner_and_decision(self):
        self.doc["status"] = "CONDITIONAL_PASS"
        self.doc["findings"].append({
            "finding_id": "F-2", "severity": "MAJOR",
            "description": "Остаточный риск",
            "status": "open", "evidence_refs": ["EV-2"],
        })
        self.context["risk_acceptance"] = {
            "approved": True, "owner_id": "risk-owner-1", "actor_id": "risk-owner-1", "actor_type": "human", "decision_id": "RISK-1",
            "finding_ids": ["F-2"],
        }
        self.assertEqual([], validate_qa_review_result(self.doc, self.context))

    def test_conditional_pass_rejects_unverified_accepted_risk(self):
        self.doc["status"] = "CONDITIONAL_PASS"
        self.doc["findings"].append({
            "finding_id": "F-7", "severity": "MINOR",
            "description": "Риск отмечен принятым без решения",
            "status": "accepted_risk", "evidence_refs": ["EV-7"],
        })
        self.doc["findings"].append({
            "finding_id": "F-8", "severity": "MAJOR",
            "description": "Открытый риск",
            "status": "open", "evidence_refs": ["EV-8"],
        })
        self.context["risk_acceptance"] = {
            "approved": True, "owner_id": "risk-owner-1", "actor_id": "risk-owner-1", "actor_type": "human", "decision_id": "RISK-3",
            "finding_ids": ["F-8"],
        }
        self.assertIn("QA_ACCEPTED_RISK_UNVERIFIED",
                      {x["code"] for x in validate_qa_review_result(self.doc, self.context)})

    def test_qa_passed_rejects_unverified_accepted_risk(self):
        self.doc["findings"].append({
            "finding_id": "F-5", "severity": "MINOR",
            "description": "Риск без подтверждённого решения",
            "status": "accepted_risk", "evidence_refs": ["EV-5"],
        })
        self.assertIn("QA_ACCEPTED_RISK_UNVERIFIED",
                      {x["code"] for x in validate_qa_review_result(self.doc, self.context)})

    def test_qa_passed_accepts_only_explicitly_scoped_minor_risk(self):
        self.doc["findings"].append({
            "finding_id": "F-6", "severity": "MINOR",
            "description": "Открытое малозначительное замечание",
            "status": "open", "evidence_refs": ["EV-6"],
        })
        self.context["risk_acceptance"] = {
            "approved": True, "owner_id": "risk-owner-1", "actor_id": "risk-owner-1", "actor_type": "human", "decision_id": "RISK-2",
            "finding_ids": ["F-6"],
        }
        self.assertEqual([], validate_qa_review_result(self.doc, self.context))


if __name__ == "__main__":
    unittest.main(verbosity=2)
