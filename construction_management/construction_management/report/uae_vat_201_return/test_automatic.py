import unittest
from unittest.mock import patch

import frappe
from construction_management.construction_management.report.uae_vat_201_return import automatic, engine


class TestAutomaticVAT201(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe, "get_precision", return_value=2))
		self.source = dict(voucher_type="Sales Invoice", voucher_no="FIXTURE-SI", source_row="TAX-ROW",
			posting_date="2026-06-01", base=1000, raw_vat=49.99, tax_rate=5, tax_account="VAT",
			currency="AED", company="TEST", source_emirate="Ras Al Khaimah", vat_rows_count=1)

	def calculate(self, source):
		rule, error = automatic.source_rule(source, "AED")
		self.assertIsNone(error)
		self.assertFalse(rule.get("approved_by"))
		event, error = engine.apply_rule(source, rule, "AED", source_verified=True)
		self.assertIsNone(error)
		return event

	def sales(self, **changes):
		return dict(self.source, supply_verified=1, verified_supply_emirate="Dubai", verification_reference="TEST supply evidence", **changes)

	def purchase(self, **changes):
		return dict(self.source, voucher_type="Purchase Invoice", **changes)

	def test_company_emirate_fetch_is_not_source_evidence(self):
		with patch.object(frappe, "get_meta", return_value=frappe._dict(get_field=lambda _: frappe._dict(fetch_from="company_address.emirate"))):
			rule, error = automatic.source_rule(self.source, "AED")
		self.assertIsNone(rule)
		self.assertIn("company-address", error)

	def test_verified_sales_uses_exact_saved_vat_and_correct_emirate(self):
		event = self.calculate(self.sales())
		self.assertEqual((event["box"], event["vat_amount"]), ("1b", 49.99))
		self.assertNotEqual(event["vat_amount"], 1000 * .05)

	def test_standard_source_emirate_without_company_fetch(self):
		with patch.object(frappe, "get_meta", return_value=frappe._dict(get_field=lambda _: frappe._dict(fetch_from=None))):
			event = self.calculate(self.source)
		self.assertEqual(event["box"], "1f")

	def test_missing_recovery_is_not_zero_entitlement(self):
		for amount in (None, 0):
			rule, error = automatic.source_rule(self.purchase(recovery_source_amount=amount), "AED")
			self.assertIsNone(rule)
			self.assertIn("not established", error)

	def test_saved_recoverable_vat_amount_is_not_an_expense_base(self):
		event = self.calculate(self.purchase(recovery_source_amount=20))
		self.assertEqual((event["box"], event["vat_amount"], event["amount"]), ("9", 20, 1000))

	def test_documented_recovery_including_explicit_zero(self):
		for percent in (0, 40, 100):
			event = self.calculate(self.purchase(recovery_verified=1, verified_recovery_percent=percent, verification_reference="TEST entitlement"))
			self.assertEqual(event["vat_amount"], engine.money(engine.number(49.99) * engine.number(percent) / 100))
			self.assertEqual(event["amount"], 1000 if percent else 0)

	def test_returns_preserve_saved_signs(self):
		for source in (self.sales(base=-1000, raw_vat=-49.99), self.purchase(base=-1000, raw_vat=-49.99, recovery_source_amount=-20)):
			event = self.calculate(source)
			self.assertLess(event["amount"], 0)
			self.assertLess(event["vat_amount"], 0)
		self.assertIsNotNone(automatic.source_rule(self.purchase(raw_vat=-49.99, recovery_source_amount=20), "AED")[1])

	def test_explicit_zero_and_exempt_do_not_require_a_classification(self):
		for treatment, box in (("Zero Rated", "4"), ("Exempt", "5")):
			event = self.calculate(dict(self.source, raw_vat=0, tax_account=None, treatment_hint=treatment))
			self.assertEqual((event["box"], event["vat_amount"]), (box, 0))

	def test_no_purchase_vat_does_not_invent_exemption(self):
		self.assertEqual(automatic.source_rule(self.purchase(raw_vat=0, tax_account=None), "AED"), (None, None))

	def test_journal_direction_and_default_reverse_recovery_are_not_evidence(self):
		for source in (dict(self.source, voucher_type="Journal Entry", debit=50, credit=0), self.purchase(reverse_charge="Y")):
			self.assertIsNone(automatic.source_rule(source, "AED")[0])

	def test_unknown_base_mismatch_and_non_aed_remain_pending(self):
		for source, currency in ((self.sales(base=None), "AED"), (self.sales(invoice_tax_difference=.01), "AED"), (self.sales(), "EUR")):
			self.assertIsNotNone(automatic.source_rule(source, currency)[1])

	def test_documented_reverse_charge_has_two_distinct_events_not_two_scans(self):
		for sign in (1, -1):
			source = self.purchase(base=1000*sign, raw_vat=49.99*sign, reverse_charge="Y", recovery_verified=1,
				verified_recovery_percent=40, verification_reference="TEST reverse charge evidence",
				gl_evidence=[dict(debit=49.99, credit=0), dict(debit=0, credit=49.99)], invoice_tax_difference=49.99*sign)
			result = self.result([source])
			result["reconciliation"] = []
			output = self.run_build(result)
			self.assertFalse(output["reviews"])
			self.assertEqual([e["box"] for e in output["events"]], ["3", "10"])
			self.assertEqual([e["vat_amount"] for e in output["events"]], [49.99*sign, 20*sign])

	def test_reverse_charge_requires_actual_matching_gl_not_a_default(self):
		source = self.purchase(reverse_charge="Y", recovery_verified=1, verified_recovery_percent=100,
			verification_reference="TEST", gl_evidence=[dict(debit=49.99, credit=0)])
		self.assertIn("GL evidence", automatic.source_rule(source, "AED")[1])

	def result(self, sources):
		return dict(filters=frappe._dict(company="TEST"), header=dict(base_currency="AED"), events=[], reviews=sources,
			excluded=[], warnings=["Unapproved sources are NOT included in VAT boxes"],
			reconciliation=[dict(description="Output VAT", ledger_amount=49.99), dict(description="Input VAT", ledger_amount=0)])

	def run_build(self, result):
		with patch.object(engine, "build", return_value=result), patch.object(engine, "settings_for", return_value={"uae_vat_accounts": [frappe._dict(account="VAT", custom_vat201_side="Both")]}):
			return automatic.build({"company": "TEST"})

	def test_automatic_calculation_deduplicates_and_does_not_write_records(self):
		source = self.sales()
		with patch.object(frappe, "get_doc", side_effect=AssertionError("Unexpected document write")):
			result = self.run_build(self.result([source, dict(source)]))
		self.assertEqual(len(result["events"]), 1)
		self.assertFalse(result["reviews"])
		self.assertEqual(result["reconciliation"][0]["difference"], 0)
		self.assertEqual(result["status"], "Prepared - Not Filed")

	def test_conflicting_legacy_decisions_do_not_double_count(self):
		source = self.sales(review="Duplicated source event classification")
		result = self.result([source])
		result["events"] = [self.calculate(source)]
		output = self.run_build(result)
		self.assertFalse(output["events"])
		self.assertEqual(output["status"], automatic.PRELIMINARY)

	def test_verified_history_is_preserved_not_deleted(self):
		result = self.result([])
		result["events"] = [self.calculate(self.sales())]
		output = self.run_build(result)
		self.assertEqual(output["events"], result["events"])

	def test_previous_rejection_or_stale_verification_is_not_silently_bypassed(self):
		for status in ("Rejected", "Needs Review"):
			output = self.run_build(self.result([self.sales(classification_status=status)]))
			self.assertFalse(output["events"])
			self.assertEqual(len(output["reviews"]), 1)
