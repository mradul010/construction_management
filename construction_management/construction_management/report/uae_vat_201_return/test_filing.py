import copy
import unittest
from unittest.mock import Mock, patch

import frappe

from construction_management.construction_management.report.uae_vat_201_return import engine, filing


class TestFiledComparison(unittest.TestCase):
	def setUp(self):
		self.result = dict(header=dict(base_currency="AED"), boxes=list(engine.aggregate([
			dict(box="1f", amount=1101253.46, vat_amount=55062.68, adjustment=0),
			dict(box="1f", amount=986315.4, vat_amount=49315.77, adjustment=0),
			dict(box="9", amount=730309.57, vat_amount=36515.54, adjustment=0),
			dict(box="9", amount=11944.2, vat_amount=597.21, adjustment=0),
		]).values()), ledger_summary=dict(currency="AED", period_net_credit=67265.7))
		# Hypothetical approved scenario. Bases for journals are synthetic test data.
		self.filed = dict(name="TEST-FILING", filed_liability_known=1, filed_liability=66609.25,
			amount_due_known=1, amount_due=66609.25, fta_reference="230011401626",
			submission_date="2026-08-27", filed_values=[])

	def test_actual_difference_stays_unexplained_without_source_evidence(self):
		r = filing.compare(self.result, self.filed)
		self.assertEqual(r["gl_less_filed"], 656.45)
		self.assertEqual(r["calculated_less_filed"], 656.45)
		self.assertEqual(r["unexplained_difference"], 656.45)
		self.assertEqual(r["difference_status"], "Unexplained filed-return difference")
		self.assertEqual(r["explained_difference"], 0)

	def test_acknowledgment_is_not_payment(self):
		r = filing.compare(self.result, self.filed)
		self.assertEqual(r["filing_status"], "Submitted")
		self.assertEqual(r["payment_status"], "Unknown / Not Verified")
		self.assertIsNone(r["payment_amount"])
		self.assertIsNone(r["outstanding_balance"])

	def test_unknown_boxes_are_not_reverse_engineered(self):
		r = filing.compare(self.result, self.filed)
		self.assertTrue(all(v["filed"] is None for v in r["known_values"] if v["box"] != "14"))
		self.assertEqual(next(v["filed"] for v in r["known_values"] if (v["box"], v["component"]) == ("14", "amount")), 66609.25)

	def test_known_zero_and_unknown_remain_distinct(self):
		self.filed["filed_values"] = [dict(box="9", component="vat_amount", value=0)]
		values = {(v["box"], v["component"]): v for v in filing.compare(self.result, self.filed)["known_values"]}
		self.assertEqual(values[("9", "vat_amount")]["filed"], 0)
		self.assertIsNone(values[("9", "amount")]["filed"])

	def test_recalculation_does_not_overwrite_filed_history(self):
		original = copy.deepcopy(self.filed)
		self.result["boxes"] = list(engine.aggregate([]).values())
		r = filing.compare(self.result, self.filed)
		self.assertEqual(r["filed_liability"], 66609.25)
		self.assertEqual(r["calculated_liability"], 0)
		self.assertEqual(self.filed, original)

	def test_partial_full_and_overpayment_require_payment_rows(self):
		for amount, status, balance in ((100, "Partially Paid", 66509.25), (66609.25, "Paid", 0), (66610.25, "Overpaid", -1)):
			r = filing.compare(self.result, self.filed, [dict(payment_amount=amount)])
			self.assertEqual((r["payment_status"], r["outstanding_balance"]), (status, balance))

	def test_unknown_due_is_not_paid_by_inference(self):
		self.filed["amount_due_known"] = 0
		r = filing.compare(self.result, self.filed, [dict(payment_amount=66609.25)])
		self.assertIsNone(r["outstanding_balance"])
		self.assertEqual(r["payment_status"], "Payment evidenced; amount due unknown")

	def test_documented_explanations_do_not_change_boxes(self):
		original = copy.deepcopy(self.result)
		r = filing.compare(self.result, self.filed, explanations=[dict(difference=100, gl_entry="TEST-GL", reason="Synthetic supported timing item")])
		self.assertEqual(r["unexplained_difference"], 556.45)
		self.assertEqual(self.result, original)

	def test_no_filing_never_invents_fixture(self):
		r = filing.compare(self.result)
		self.assertIsNone(r["filed_liability"])
		self.assertIsNone(r["gl_less_filed"])

	def test_non_aed_gl_cannot_be_compared_directly(self):
		self.result["header"]["base_currency"] = "USD"
		self.assertIsNone(filing.compare(self.result, self.filed)["gl_less_filed"])

	def test_snapshot_exposes_changes_since_recording(self):
		self.filed["calculation_snapshot"] = frappe.as_json(dict(boxes=[dict(box="14", amount=55062.68)]))
		self.assertEqual(filing.compare(self.result, self.filed)["calculation_change_since_recording"], 12203.02)

	def test_scenario_a_and_supplier_return_signs(self):
		boxes = {r["box"]: r for r in self.result["boxes"]}
		self.assertEqual(boxes["8"]["vat_amount"], 104378.45)
		self.assertEqual(boxes["11"]["vat_amount"], 37112.75)
		self.assertEqual(boxes["14"]["amount"], 67265.70)
		returns = sum(map(engine.number, [52.26, 13, 1.39, 9, 86]))
		self.assertEqual(engine.money(returns), 161.65)
		self.assertEqual(engine.money(engine.number(36677.19) - returns), 36515.54)

	def test_scenario_b_separately_explains_excluded_output(self):
		result = engine.aggregate([dict(box="1f",amount=1101253.46,vat_amount=55062.68,adjustment=0),
			dict(box="9",amount=742253.77,vat_amount=37112.75,adjustment=0)])
		self.assertEqual(result["14"]["amount"], 17949.93)
		self.assertEqual(engine.money(engine.number(result["14"]["amount"])+engine.number(49315.77)),67265.70)

	def test_accounting_identity_excludes_opening_from_movement(self):
		self.assertEqual(engine.money(engine.number(104540.10)-engine.number(37274.40)), 67265.70)
		self.assertEqual(engine.money(engine.number(67265.70)-engine.number(535.57)), 66730.13)

	def test_unauthorized_filing_is_blocked(self):
		with patch.object(engine, "access"), patch.object(frappe, "get_roles", return_value=["Accounts User"]):
			with self.assertRaises(frappe.PermissionError):
				filing.manager("TEST")

	def test_submitted_record_cannot_be_changed_or_cancelled(self):
		doc = frappe._dict(company="TEST", get_doc_before_save=lambda: frappe._dict(docstatus=1))
		with patch.object(filing, "manager"):
			with self.assertRaises(frappe.ValidationError):
				filing.EvidenceRecord.validate(doc)
		with self.assertRaises(frappe.ValidationError):
			filing.EvidenceRecord.before_cancel(doc)

	def test_company_isolation_for_related_records(self):
		doc = frappe._dict(company="OTHER", filing="FILING")
		parent = frappe._dict(company="TEST", docstatus=1, check_permission=Mock())
		with patch.object(frappe, "get_doc", return_value=parent):
			with self.assertRaises(frappe.ValidationError):
				filing.linked_filing(doc)

	def test_nan_and_infinity_are_rejected(self):
		for value in ("NaN", "Infinity", "bad"):
			with self.assertRaises(frappe.ValidationError):
				filing.decimal_value(value)

	def test_export_preserves_unknown_and_unexplained_amount(self):
		from construction_management.construction_management.report.uae_vat_201_return.uae_vat_201_return import export_rows
		result = dict(self.result, status="Needs Review", events=[], details=[], reviews=[], warnings=[], reconciliation=[])
		result["filed_comparison"] = filing.compare(result, self.filed)
		rows = export_rows(result)
		self.assertIn(["Unexplained Difference", 656.45], rows)
		self.assertTrue(any(row[:2] == ["9", "amount"] and row[3] == "Unknown" for row in rows))


	def test_correction_preserves_payments_against_prior_filing(self):
		self.result["header"].update(company="SYNTHETIC", from_date="2026-05-01", to_date="2026-07-31")
		current = dict(self.filed, name="CORRECTED")
		doc = frappe._dict(name="CORRECTED", check_permission=Mock(), as_dict=lambda: current)
		def get_list(dt, **kwargs):
			if dt == "VAT 201 Filing":
				return [frappe._dict(name="ORIGINAL"), frappe._dict(name="CORRECTED", correction_of="ORIGINAL")]
			if dt == "VAT 201 Payment":
				self.assertEqual(kwargs["filters"]["filing"], ["in", ["CORRECTED", "ORIGINAL"]])
				return [dict(payment_amount=100)]
			return []
		with patch.object(frappe.db, "exists", return_value=True), patch.object(frappe, "has_permission", return_value=True), patch.object(frappe, "get_list", side_effect=get_list), patch.object(frappe, "get_doc", return_value=doc):
			filing.attach_comparison(self.result)
		self.assertEqual(self.result["filed_comparison"]["payment_amount"], 100)


class TestFilingDocumentValidation(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(filing, "manager"))
		original = frappe.get_list
		self.enterContext(patch.object(frappe, "get_list", side_effect=lambda dt, *args, **kwargs: [frappe._dict(name="TEST-EVIDENCE")] if dt == "File" else original(dt, *args, **kwargs)))

	def make_filing(self, **changes):
		values = dict(doctype="VAT 201 Filing", company="SYNTHETIC", from_date="2026-05-01", to_date="2026-07-31",
			submission_date="2026-08-27", fta_reference="SYNTHETIC", filed_liability_known=1, filed_liability=0,
			amount_due_known=0, supporting_evidence="/private/files/test-only.pdf", reason="Synthetic fixture")
		values.update(changes)
		return frappe.get_doc(values)

	def test_frappe_factory_preserves_known_nil_filing(self):
		doc = self.make_filing()
		doc.validate()
		self.assertEqual(doc.filed_liability, 0)
		self.assertFalse(doc.amount_due_known)
		self.assertFalse(doc.approved_by)

	def test_missing_liability_is_not_a_nil_filing(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_filing(filed_liability_known=0).validate()

	def test_conflicting_and_duplicate_components_fail(self):
		for rows in ([dict(box="14", component="amount", value=1, evidence_reference="TEST")],
			[dict(box="9", component="vat_amount", value=0, evidence_reference="TEST")]*2):
			with self.assertRaises(frappe.ValidationError):
				self.make_filing(filed_values=rows).validate()

	def test_invoice_and_filing_dates_have_separate_validation(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_filing(submission_date="2026-07-01").validate()

	def test_snapshot_cannot_be_supplied_by_client(self):
		doc = self.make_filing(calculation_snapshot='{"boxes": []}', approved_by="forged@example.com")
		doc.validate()
		self.assertIsNone(doc.calculation_snapshot)
		self.assertIsNone(doc.approved_by)

	def test_missing_evidence_is_rejected(self):
		with patch.object(frappe, "get_list", return_value=[]):
			with self.assertRaises(frappe.ValidationError):
				self.make_filing().validate()


class TestDocumentaryTax(unittest.TestCase):
	def test_customs_and_imported_services_use_distinct_output_boxes(self):
		from construction_management.construction_management.report.uae_vat_201_return.tax_evidence import events_for
		for supply, box in (("Customs import", "6"), ("Imported services reverse charge", "3"), ("Import adjustment", "7")):
			doc = dict(name="SYNTHETIC-CUSTOMS", company="SYNTHETIC", tax_date="2026-06-01", supply_type=supply,
				taxable_base=1000, vat_amount=50, recovery_confirmed=1, recovery_percent=40, source_reference="SYNTHETIC-DECLARATION",
				approved_by="Reviewer", approved_on="2026-06-15", reason="Documented supply", supporting_evidence="TEST", overlap_basis="Synthetic no-overlap check")
			events = events_for(doc)
			self.assertEqual([e["box"] for e in events], [box, "10"])
			self.assertEqual([e["vat_amount"] for e in events], [50,20])
			self.assertTrue(all(e["recorded_in_gl"] is False for e in events))

	def test_source_rate_is_configurable_without_recalculating_recorded_tax(self):
		from construction_management.construction_management.report.uae_vat_201_return.automatic import source_rule
		source = dict(voucher_type="Sales Invoice", voucher_no="TEST", source_row="TEST-TAX", posting_date="2026-06-01",
			base=1000, raw_vat=70, tax_rate=7, tax_account="TEST-VAT", source_emirate="Dubai")
		rule, error = source_rule(source, "AED", standard_rate=7)
		self.assertIsNone(error)
		event, error = engine.apply_rule(source, rule, "AED", source_verified=True)
		self.assertEqual(event["vat_amount"], 70)
		self.assertIsNotNone(source_rule(source, "AED", standard_rate=5)[1])

	def test_advance_overlap_approval_is_bound_to_current_allocation(self):
		from construction_management.construction_management.report.uae_vat_201_return.review import decision_fingerprint
		source = dict(voucher_type="Journal Entry", voucher_no="TEST-JV", source_row="TEST-GL", posting_date="2026-06-01",
			base=1000, raw_vat=-50, debit=0, credit=50, journal_vat_role="Output", journal_duplicate_risk="Invoice overlap needs reconciliation",
			advance_allocation_evidence=[dict(parent="TEST-SI", allocated_amount=1050)])
		rule = frappe._dict(box="1f", tax_date="2026-06-01", approved_by="Reviewer", reason="Documented no duplicate VAT",
			supporting_reference="TEST-TAX-INVOICE", overlap_reviewed=1, overlap_reference="TEST-OVERLAP-SCHEDULE",
			source_fingerprint=decision_fingerprint(source))
		self.assertIsNone(engine.apply_rule(source, rule, "AED")[1])
		source["advance_allocation_evidence"][0]["allocated_amount"] = 1100
		self.assertIn("changed since review", engine.apply_rule(source, rule, "AED")[1])
