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
		return dict(dict(self.source, source_emirate="Dubai"), **changes)

	def purchase(self, **changes):
		return dict(self.source, voucher_type="Purchase Invoice", **changes)

	def test_saved_emirate_does_not_depend_on_field_fetch_or_verification(self):
		with patch.object(frappe, "get_meta", side_effect=AssertionError("Emirate must not depend on fetch metadata")):
			rule, error = automatic.source_rule(self.source, "AED")
		self.assertIsNone(error)
		self.assertEqual(rule.box, "1f")

	def test_saved_sales_emirate_uses_exact_saved_vat(self):
		event = self.calculate(self.sales())
		self.assertEqual((event["box"], event["vat_amount"]), ("1b", 49.99))
		self.assertNotEqual(event["vat_amount"], 1000 * .05)

	def test_all_valid_saved_emirates(self):
		for index, emirate in enumerate(engine.get_emirates()):
			event = self.calculate(self.sales(source_emirate=emirate))
			self.assertEqual(event["box"], "1" + chr(97 + index))

	def test_missing_or_invalid_emirate_warns_only_when_required(self):
		for emirate in (None, "", "Not an Emirate"):
			rule, error = automatic.source_rule(self.sales(source_emirate=emirate), "AED")
			self.assertIsNone(rule)
			self.assertEqual(error, "VAT Emirate is missing or invalid")
			for hint, box in (("Zero Rated", "4"), ("Exempt", "5")):
				event = self.calculate(self.sales(source_emirate=emirate, raw_vat=0, tax_account=None, treatment_hint=hint))
				self.assertEqual(event["box"], box)

	def test_requested_ras_al_khaimah_invoice_values(self):
		event = self.calculate(self.sales(voucher_no="ACC-SINV-2026-00050-2", source_emirate="Ras Al Khaimah", base=952.38, raw_vat=47.62))
		self.assertEqual((event["box"], event["amount"], event["vat_amount"]), ("1f", 952.38, 47.62))

	def test_missing_recovery_is_not_zero_entitlement(self):
		for amount in (None, ""):
			rule, error = automatic.source_rule(self.purchase(recovery_source_amount=amount), "AED")
			self.assertIsNone(rule)
			self.assertIn("amount is missing", error)
		rule, error = automatic.source_rule(self.purchase(recovery_source_amount=0), "AED")
		self.assertIsNone(rule)
		self.assertIn("default zero", error)

	def test_saved_recoverable_vat_amount_is_not_an_expense_base(self):
		event = self.calculate(self.purchase(recovery_source_amount=20))
		self.assertEqual((event["box"], event["vat_amount"], event["amount"]), ("9", 20, 1000))

	def test_saved_recovery_amount_including_explicit_zero(self):
		for amount in (0, 20, 49.99):
			event = self.calculate(self.purchase(recovery_source_amount=amount, recovery_source_reference="TEST source Version" if amount == 0 else None))
			self.assertEqual(event["vat_amount"], amount)
			self.assertEqual(event["amount"], 1000 if amount else 0)

	def test_requested_purchase_full_recovery_is_an_amount_not_a_checkbox(self):
		for amount in (1, 20, 77.88):
			source = self.purchase(voucher_no="ACC-PINV-2026-00293-1", base=1557.50, raw_vat=77.88, recovery_source_amount=amount)
			event = self.calculate(source)
			self.assertEqual((event["box"], event["amount"], event["vat_amount"]), ("9", 1557.50, amount))
			result = self.result([source])
			result["reconciliation"] = []
			output = self.run_build(result)
			self.assertFalse(output["reviews"])
			self.assertEqual(output["events"][0]["vat_amount"], amount)

	def test_invalid_or_excessive_recovery_is_not_claimed(self):
		for value in ("not a number", "NaN", "Infinity", 50, -1):
			self.assertIsNotNone(automatic.source_rule(self.purchase(recovery_source_amount=value), "AED")[1])
		self.assertIn("allocation", automatic.source_rule(self.purchase(recovery_source_amount=20, vat_rows_count=2), "AED")[1])

	def test_zero_recovery_history_is_read_only_and_scoped_to_permitted_invoices(self):
		invoice = frappe._dict(name="PERMITTED-PI", recoverable_standard_rated_expenses=0, reverse_charge="N")
		version = frappe._dict(name="VERSION-ZERO", docname=invoice.name, data={"changed": [["recoverable_standard_rated_expenses", 20, 0]]})
		with patch.object(frappe, "get_all", return_value=[version]) as reader:
			references = engine.recovery_source_references([invoice])
		self.assertIn((invoice.name, "recoverable_standard_rated_expenses"), references)
		self.assertEqual(reader.call_args.kwargs["filters"]["docname"], ["in", [invoice.name]])
		self.assertEqual(reader.call_args.args[0], "Version")

	def test_default_zero_is_not_made_explicit_by_unrelated_or_stale_history(self):
		invoice = frappe._dict(name="PI", recoverable_standard_rated_expenses=0, reverse_charge="N")
		field = "recoverable_standard_rated_expenses"
		for changes in ([], [["remarks", "old", "new"]], [[field, None, 0]], [[field, 0, 20]]):
			version = frappe._dict(name="VERSION", docname=invoice.name, data={"changed": changes})
			with patch.object(frappe, "get_all", return_value=[version]):
				self.assertFalse(engine.recovery_source_references([invoice]))
		versions = [frappe._dict(name="LATEST", docname=invoice.name, data={"changed": [[field, 0, 20]]}),
			frappe._dict(name="OLD", docname=invoice.name, data={"changed": [[field, 20, 0]]})]
		with patch.object(frappe, "get_all", return_value=versions):
			self.assertFalse(engine.recovery_source_references([invoice]))

	def test_positive_recovery_needs_no_history_scan(self):
		invoice = frappe._dict(name="PI", recoverable_standard_rated_expenses=20, reverse_charge="N")
		with patch.object(frappe, "get_all") as reader:
			self.assertFalse(engine.recovery_source_references([invoice]))
		reader.assert_not_called()

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
			source = self.purchase(base=1000*sign, raw_vat=49.99*sign, reverse_charge="Y", reverse_recovery_percent=40,
				gl_evidence=[dict(debit=49.99, credit=0), dict(debit=0, credit=49.99)], invoice_tax_difference=49.99*sign)
			result = self.result([source])
			result["reconciliation"] = []
			output = self.run_build(result)
			self.assertFalse(output["reviews"])
			self.assertEqual([e["box"] for e in output["events"]], ["3", "10"])
			self.assertEqual([e["vat_amount"] for e in output["events"]], [49.99*sign, 20*sign])

	def test_reverse_charge_requires_actual_matching_gl_not_a_default(self):
		source = self.purchase(reverse_charge="Y", reverse_recovery_percent=100,
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

	def test_saved_emirate_is_authoritative_for_retained_standard_rated_history(self):
		for emirate in ("Ras Al Khaimah", None, "Not an Emirate"):
			event = self.calculate(self.sales())
			event["source_emirate"] = emirate
			result = self.result([])
			result["events"] = [event]
			output = self.run_build(result)
			if emirate == "Ras Al Khaimah":
				self.assertEqual(output["events"][0]["box"], "1f")
				self.assertFalse(output["reviews"])
				continue
			self.assertFalse(output["events"])
			self.assertEqual(output["reviews"][0]["issue"], "VAT Emirate is missing or invalid")

	def test_previous_rejection_or_stale_verification_is_not_silently_bypassed(self):
		for status in ("Rejected", "Needs Review"):
			output = self.run_build(self.result([self.sales(classification_status=status)]))
			self.assertFalse(output["events"])
			self.assertEqual(len(output["reviews"]), 1)
