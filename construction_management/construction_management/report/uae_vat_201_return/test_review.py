import unittest
from unittest.mock import Mock, patch

import frappe

from construction_management.construction_management.report.uae_vat_201_return import engine, review
from construction_management.construction_management.report.uae_vat_201_return import uae_vat_201_return as report


class TestVAT201Review(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe,"get_precision",return_value=2))
		self.source = dict(voucher_type="Purchase Invoice",voucher_no="FIXTURE-PI",source_row="TAX",posting_date="2026-06-01",
			base=1000,raw_vat=50,tax_account="VAT",tax_rate=5,company="TEST",currency="AED",invoice_tax_difference=0)

	def test_purchase_suggestion_does_not_assume_entitlement(self):
		box, reason = review.suggest(self.source, {"VAT":"Both"})
		self.assertEqual(box,"9")
		self.assertIn("explicit review",reason)
		self.assertIn("Expenses (AED) is missing",reason)
		self.assertIn("default zero",review.suggest(dict(self.source,recovery_source_amount=0), {"VAT":"Both"})[1])
		self.assertNotIn("recovery_percent",self.source)

	def test_sales_emirate_is_only_a_suggestion_and_not_company_fallback(self):
		source = dict(self.source,voucher_type="Sales Invoice",source_emirate="Dubai")
		self.assertEqual(review.suggest(source,{"VAT":"Both"})[0],"1b")
		self.assertIn("saved invoice VAT Emirate",review.suggest(source,{"VAT":"Both"})[1])
		source["source_emirate"] = None
		self.assertIsNone(review.suggest(source,{"VAT":"Both"})[0])

	def test_sales_return_uses_its_saved_emirate_not_the_original_box(self):
		source = dict(self.source, voucher_type="Sales Invoice", source_emirate="Ras Al Khaimah", is_return=1, return_against="ORIGINAL")
		original = frappe._dict(approved=1, voucher_type="Sales Invoice", voucher_no="ORIGINAL", box="1b")
		self.assertEqual(review.suggest(source, {"VAT": "Both"}, [original])[0], "1f")
		source["source_emirate"] = None
		box, reason = review.suggest(source, {"VAT": "Both"}, [original])
		self.assertIsNone(box)
		self.assertIn("VAT Emirate is missing or invalid", reason)

	def test_zero_tax_without_flags_has_no_box(self):
		source = dict(self.source,raw_vat=0,tax_account=None,voucher_type="Sales Invoice")
		self.assertIsNone(review.suggest(source,{})[0])
		self.assertEqual(review.suggest(dict(source,treatment_hint="Zero Rated"),{})[0],"4")
		self.assertEqual(review.suggest(dict(source,treatment_hint="Exempt"),{})[0],"5")

	def test_journal_is_not_classified_by_debit_credit(self):
		for debit,credit in ((50,0),(0,50)):
			box,reason=review.suggest(dict(self.source,voucher_type="Journal Entry",debit=debit,credit=credit),{"VAT":"Both"})
			self.assertIsNone(box)
			self.assertIn("REVIEW REQUIRED",reason)
			self.assertIn("No structured invoice references",reason)

	def test_control_only_treatments_require_explicit_journal_classification(self):
		for treatment in ("VAT settlement","VAT payment","VAT reclassification"):
			self.assertTrue(review.control_movement_only(dict(voucher_type="Journal Entry"),frappe._dict(journal_treatment=treatment)))
			self.assertFalse(review.control_movement_only(dict(voucher_type="Sales Invoice"),frappe._dict(journal_treatment=treatment)))
		self.assertFalse(review.control_movement_only(dict(voucher_type="Journal Entry"),frappe._dict(journal_treatment="Unresolved")))

	def test_source_gl_mismatch_blocks_suggestion_and_approval(self):
		source=dict(self.source,invoice_tax_difference=1)
		self.assertIsNone(review.suggest(source,{"VAT":"Both"})[0])
		rule=frappe._dict(box="9",approved_by="Reviewer",reason="Fixture",supporting_reference="TEST")
		self.assertIn("does not reconcile",engine.apply_rule(source,rule,"AED")[1])

	def test_fingerprint_ignores_display_fields_but_detects_changed_source(self):
		original=review.fingerprint(self.source)
		self.assertEqual(original,review.fingerprint(dict(self.source,review="new display",suggested_box="9")))
		self.assertNotEqual(original,review.fingerprint(dict(self.source,raw_vat=51)))
		rule=frappe._dict(box="9",approved_by="Reviewer",reason="Fixture",supporting_reference="TEST",source_fingerprint=original)
		self.assertIn("changed since review",engine.apply_rule(dict(self.source,raw_vat=51),rule,"AED")[1])

	def test_rejected_review_is_not_an_exclusion(self):
		rows=[frappe._dict(name="REVIEW",voucher_type="Purchase Invoice",voucher_no="FIXTURE-PI",source_row="TAX",review_status="Rejected",origin="Manual",approved=0)]
		pending=[dict(self.source)]
		review.annotate_reviews(pending,frappe._dict(custom_vat201_classifications=rows),{"VAT":"Both"})
		self.assertEqual(pending[0]["classification_status"],"Rejected")
		self.assertEqual(pending[0]["classification_id"],"REVIEW")
		self.assertEqual(pending[0]["raw_vat"],50)

	def test_approve_action_validates_input_recovery(self):
		row=frappe.get_doc(dict(doctype="VAT 201 Classification",name="REVIEW",voucher_type="Purchase Invoice",voucher_no="FIXTURE-PI",source_row="TAX"))
		doc=frappe._dict(custom_vat201_classifications=[row],uae_vat_accounts=[frappe._dict(account="VAT",custom_vat201_side="Both")],save=Mock())
		with patch.object(review,"manager_access",return_value=doc), patch.object(review,"review_source",return_value={"source":self.source}), patch.object(frappe,"get_cached_value",return_value="AED"):
			with self.assertRaises(frappe.ValidationError):
				review.decide(dict(company="TEST"),"Purchase Invoice","FIXTURE-PI","TAX","Approve",
					dict(box="9",tax_date="2026-06-01",reason="TEST ONLY",supporting_reference="TEST",recovery_confirmed=0),"REVIEW")
		doc.save.assert_not_called()

	def test_reject_requires_reason_and_does_not_save_approval(self):
		row=frappe.get_doc(dict(doctype="VAT 201 Classification",name="REVIEW",voucher_type="Purchase Invoice",voucher_no="FIXTURE-PI",source_row="TAX"))
		doc=frappe._dict(custom_vat201_classifications=[row],save=Mock())
		with patch.object(review,"manager_access",return_value=doc), patch.object(review,"review_source",return_value={"source":self.source}):
			with self.assertRaises(frappe.ValidationError):
				review.decide(dict(company="TEST"),"Purchase Invoice","FIXTURE-PI","TAX","Reject",{},"REVIEW")
			review.decide(dict(company="TEST"),"Purchase Invoice","FIXTURE-PI","TAX","Reject",{"review_remarks":"TEST ONLY - evidence missing"},"REVIEW")
		self.assertEqual((row.review_status,row.approved),("Rejected",0))
		doc.save.assert_called_once()

	def test_sync_preserves_existing_approval_and_rejection(self):
		rows=[frappe._dict(voucher_type="Purchase Invoice",voucher_no="FIXTURE-PI",source_row="TAX",approved=1)]
		doc=frappe._dict(custom_vat201_classifications=rows,save=Mock())
		with patch.object(review,"manager_access",return_value=doc), patch.object(engine,"build",return_value={"reviews":[self.source]}):
			self.assertEqual(review.sync_reviews(dict(company="TEST"))["created"],0)
		doc.save.assert_not_called()
		self.assertEqual(rows[0].approved,1)

	def test_provisional_due_dates_preserve_confirmed_date(self):
		periods=[frappe._dict(to_date="2026-07-31",due_date="2026-08-31",due_date_basis="Confirmed"),
			frappe._dict(to_date="2026-10-31",due_date=None)]
		doc=frappe._dict(custom_vat201_periods=periods,save=Mock())
		with patch.object(review,"manager_access",return_value=doc):
			self.assertEqual(review.fill_provisional_due_dates("TEST")["updated"],1)
		self.assertEqual(periods[0].due_date,"2026-08-31")
		self.assertEqual(str(periods[1].due_date),"2026-11-28")
		self.assertEqual(periods[1].due_date_basis,"Provisional (28 days)")

	def test_filing_period_selection_is_company_scoped(self):
		settings=frappe._dict(custom_vat201_periods=[frappe._dict(from_date="2026-05-01",to_date="2026-07-31")])
		filters=engine.normalize(dict(filing_period="2026-05-01 to 2026-07-31"),settings)
		self.assertEqual(str(filters.from_date),"2026-05-01")
		with self.assertRaises(frappe.ValidationError):
			engine.normalize(dict(filing_period="2025-05-01 to 2025-07-31"),settings)

	def test_net_drilldown_contributions_match_clicked_total(self):
		events=[dict(box="1f",amount=1000,vat_amount=50,adjustment=0),dict(box="9",amount=400,vat_amount=20,adjustment=0)]
		with patch.object(report,"build",return_value={"events":events}):
			self.assertEqual(sum(r["contribution"] for r in report.transactions({},"14","amount")),30)
			self.assertEqual(sum(r["contribution"] for r in report.transactions({},"12","amount")),50)
			self.assertEqual(sum(r["contribution"] for r in report.transactions({},"13","amount")),20)
