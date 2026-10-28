import unittest
from unittest.mock import patch

import frappe

from construction_management.construction_management.report.uae_vat_201_return import automatic, engine, journal


class TestJournalVAT(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe, "get_precision", return_value=2))

	def base(self, name="BASE", amount=1042.37, **changes):
		return dict(dict(name=name, account="Expense", custom_vat_account="VAT", custom_vat_rate=5,
			custom_vat_inclusive=0, debit=amount, credit=0, debit_in_account_currency=amount,
			account_currency="AED", exchange_rate=1, project="P1", cost_center="CC", user_remark="Tools"), **changes)

	def tax(self, name="TAX", amount=52.12, **changes):
		return dict(dict(name=name, account="VAT", custom_is_tax_row=1, debit=amount, credit=0,
			project="P1", cost_center="CC", user_remark="Completely unrelated text"), **changes)

	def source(self, name="GL", amount=52.12, **changes):
		return dict(dict(voucher_type="Journal Entry", voucher_no="TEST-JV", source_row=name,
			posting_date="2026-06-30", debit=amount, credit=0, raw_vat=journal.number(amount),
			tax_account="VAT", currency="AED", base=None, project="P1", cost_center="CC"), **changes)

	def match(self, rows, sources=None):
		sources = sources or [self.source()]
		journal.match_journal(dict(accounts=rows), sources, {"Expense"}, "AED")
		return sources

	def test_requested_pair_uses_saved_base_not_remark_or_whole_journal(self):
		source = self.match([self.base(), self.tax(), dict(name="CASH", debit=0, credit=99999)])[0]
		self.assertEqual(source["base"], journal.number("1042.37"))
		self.assertEqual(source["recorded_vat_amount"], 52.12)
		self.assertEqual(source["base_row_references"], ["BASE"])
		self.assertEqual(source["generated_tax_rows"], ["TAX"])
		self.assertIsNone(source["party"])
		self.assertEqual(source["journal_category"], "Recorded purchase VAT")
		rule, error = automatic.source_rule(source, "AED")
		self.assertIsNone(rule)
		self.assertIn("recovery entitlement", error)
		self.assertNotIn("taxable base", error)

	def test_other_requested_pairs_and_half_cent_rounding(self):
		for base, vat in ((96, 4.8), (936.5, 46.82), (300, 15)):
			source = self.match([self.base(amount=base), self.tax(amount=vat)], [self.source(amount=vat)])[0]
			self.assertEqual(float(source["base"]), base)
			self.assertEqual(source["recorded_vat_amount"], vat)

	def test_project_and_cost_center_separate_otherwise_identical_rows(self):
		rows = [self.base("B1"), self.tax("T1"), self.base("B2", project="P2"), self.tax("T2", project="P2")]
		sources = self.match(rows, [self.source("G1"), self.source("G2", project="P2")])
		self.assertEqual([s["base_row_references"] for s in sources], [["B1"], ["B2"]])

	def test_grouped_generated_tax_and_merged_gl_consume_sources_once(self):
		rows = [self.base("B1", 100), self.base("B2", 200), self.tax(amount=15)]
		source = self.match(rows, [self.source(amount=15)])[0]
		self.assertEqual(source["base"], 300)
		self.assertEqual(source["base_row_references"], ["B1", "B2"])
		rows = [self.base("B1", 100), self.base("B2", 200), self.tax("T1", 5), self.tax("T2", 10)]
		source = self.match(rows, [self.source(amount=15)])[0]
		self.assertEqual(source["base"], 300)
		self.assertEqual(set(source["generated_tax_rows"]), {"T1", "T2"})

	def test_ambiguous_matches_are_not_guessed_and_explicit_links_disambiguate(self):
		rows = [self.base("B1", 100), self.base("B2", 100), self.tax("T1", 5), self.tax("T2", 5)]
		sources = [self.source("G1", 5), self.source("G2", 5)]
		self.assertTrue(all(s.get("journal_match_issue") for s in self.match(rows, sources)))
		rows[2]["custom_vat_source_row"], rows[3]["custom_vat_source_row"] = "B1", "B2"
		sources = [self.source("G1", 5, voucher_detail_no="T1"), self.source("G2", 5, voucher_detail_no="T2")]
		self.assertEqual([s["base_row_references"] for s in self.match(rows, sources)], [["B1"], ["B2"]])

	def test_missing_explicit_link_and_bad_gl_cannot_fallback_to_remarks(self):
		for tax, source in ((self.tax(custom_vat_source_row="MISSING"), self.source()),
			(self.tax(), self.source(amount=53)), (self.tax(), self.source(voucher_detail_no="MISSING"))):
			row = self.match([self.base(), tax], [source])[0]
			self.assertIsNone(row["base"])
			self.assertIn("reconcile", row["journal_match_issue"])

	def test_inclusive_uses_saved_split_state_and_preserves_credit_sign(self):
		for sign in (1, -1):
			base = self.base(amount=100, custom_vat_inclusive=1, custom_tax_base_gross=105, custom_tax_last_net=100)
			tax, source = self.tax(amount=5), self.source(amount=5)
			if sign < 0:
				for row in (base, tax, source):
					row["credit"], row["debit"] = row["debit"], 0
				base["credit_in_account_currency"], base["debit_in_account_currency"] = 100, 0
				source["raw_vat"] = journal.number(-5)
			result = self.match([base, tax], [source])[0]
			self.assertEqual(result["base"], 100 * sign)
			self.assertEqual(result["recorded_vat_amount"], 5 * sign)
		base["custom_tax_base_gross"] = 0
		self.assertIsNone(self.match([base, tax], [self.source(amount=5)])[0]["base"])

	def test_foreign_account_requires_saved_company_currency_reconciliation(self):
		base = self.base(amount=367.25, debit_in_account_currency=100, account_currency="USD", exchange_rate=3.6725)
		source = self.match([base, self.tax(amount=18.36)], [self.source(amount=18.36)])[0]
		self.assertEqual(float(source["base"]), 367.25)
		base["debit"] = 100
		source = self.match([base, self.tax(amount=18.36)], [self.source(amount=18.36)])[0]
		self.assertIsNone(source["base"])
		self.assertIn("exchange", source["journal_match_issue"])

	def test_account_transfers_and_invoice_links_do_not_establish_expense_claims(self):
		for base in (self.base(account="Bank"), self.base(reference_type="Purchase Invoice", reference_name="PI")):
			source = self.match([base, self.tax()])[0]
			self.assertEqual(float(source["base"]), 1042.37)
			self.assertIsNone(automatic.source_rule(source, "AED")[0])
			self.assertNotEqual(source["journal_category"], "Recorded purchase VAT")
			rule = frappe._dict(box="9", tax_date="2026-06-30", reason="Existing reviewed evidence", supporting_reference="REF",
				approved_by="MANAGER", recovery_confirmed=1, recovery_percent=100)
			if source.get("journal_invoice_linked"):
				self.assertIn("cannot be claimed again", engine.apply_rule(source, rule, "AED")[1])

	def test_existing_reviewed_partial_recovery_is_preserved_without_new_fields(self):
		source = self.match([self.base(), self.tax()])[0]
		for percent, claim in ((0, 0), (50, 26.06), (100, 52.12)):
			rule = frappe._dict(box="9", tax_date="2026-06-30", reason="Existing reviewed evidence", supporting_reference="REF",
				approved_by="MANAGER", recovery_confirmed=1, recovery_percent=percent)
			event, error = engine.apply_rule(source, rule, "AED")
			self.assertIsNone(error)
			self.assertEqual(event["vat_amount"], claim)
			self.assertEqual(event["invoice_taxable_amount"], 1042.37)
			self.assertEqual(engine.aggregate([event])["13"]["amount"], claim)

	def advance(self, base=455672.60, vat=22783.63, reversal=False, emirate=None, **changes):
		base_row = self.base(account="ADV", debit=0, credit=base, debit_in_account_currency=0,
			credit_in_account_currency=base, party_type="Customer", party="CUSTOMER", is_advance="No")
		tax_row = self.tax(debit=0, credit=vat)
		gross = dict(name="GROSS", account="AR", account_type="Receivable", party_type="Customer", party="CUSTOMER",
			debit=base+vat, credit=0, project="P1")
		source = self.source(debit=0, credit=vat, raw_vat=-journal.number(vat), **changes)
		if reversal:
			for row in (base_row, tax_row, gross, source):
				row["debit"], row["credit"] = row.get("credit", 0), row.get("debit", 0)
			base_row["debit_in_account_currency"], base_row["credit_in_account_currency"] = base, 0
			source["raw_vat"] = journal.number(vat)
		doc = dict(name="TEST-JV", company="TEST", accounts=[base_row, tax_row, gross], vat_emirate=emirate,
			cheque_no="Text that resembles an invoice is NOT a link")
		source["journal_evidence"] = {"document": doc}
		journal.match_journal(doc, [source], {"Expense"}, "AED", {"ADV"})
		return source, doc

	def test_requested_customer_advances_do_not_require_income_or_advance_flag(self):
		for base, vat in ((455672.60, 22783.63), (530642.80, 26532.14)):
			source, doc = self.advance(base, vat)
			journal.link_advance_evidence([source], [])
			self.assertEqual(source["journal_category"], "Customer-advance output VAT")
			self.assertEqual(source["base"], journal.number(base))
			self.assertEqual(source["invoice_taxable_amount"], base)
			self.assertEqual(source["recorded_vat_amount"], vat)
			self.assertEqual(source["raw_vat"], -journal.number(vat))
			self.assertEqual(source["party"], "CUSTOMER")
			rule, error = automatic.source_rule(source, "AED")
			self.assertIsNone(rule)
			self.assertIn("VAT Emirate is missing", error)
			self.assertNotIn("purpose", error)

	def test_output_credit_and_debit_reversal_signs_remain_separate_from_input(self):
		events = []
		for reversal in (False, True):
			source, doc = self.advance(reversal=reversal, emirate="Ras Al Khaimah")
			journal.link_advance_evidence([source], [])
			rule, error = automatic.source_rule(source, "AED")
			self.assertIsNone(error)
			event, error = engine.apply_rule(source, rule, "AED", source_verified=True)
			self.assertIsNone(error)
			sign = -1 if reversal else 1
			self.assertEqual(event["box"], "1f")
			self.assertEqual(event["amount"], 455672.60*sign)
			self.assertEqual(event["vat_amount"], 22783.63*sign)
			self.assertEqual(event["recorded_vat_amount"], 22783.63*sign)
			events.append(event)
		self.assertEqual(engine.aggregate(events)["12"]["amount"], 0)
		purchase = self.match([self.base(), self.tax()])[0]
		self.assertEqual(purchase["recorded_vat_amount"], 52.12)
		self.assertEqual(purchase["journal_vat_role"], "Input")

	def test_advance_requires_configured_account_customer_and_gross_reconciliation(self):
		for change in ("account", "party", "gross"):
			source, doc = self.advance()
			source = self.source(debit=0, credit=22783.63, raw_vat=-journal.number(22783.63))
			if change == "account":
				doc["accounts"][0]["account"] = "Unrelated liability"
			elif change == "party":
				doc["accounts"][0]["party_type"] = "Supplier"
			else:
				doc["accounts"][2]["debit"] += 100
			journal.match_journal(doc, [source], {"Expense"}, "AED", {"ADV"})
			self.assertNotEqual(source["journal_category"], "Customer-advance output VAT")
			self.assertIsNone(automatic.source_rule(source, "AED")[0])

	def test_only_structured_links_resolve_emirate_and_trigger_overlap_review(self):
		source, doc = self.advance()
		invoice = dict(name="SI", company="TEST", customer="CUSTOMER", vat_emirate="Dubai")
		journal.link_advance_evidence([source], [invoice])
		self.assertIsNone(source["source_emirate"])
		self.assertFalse(source.get("journal_duplicate_risk"))
		doc["accounts"][0].update(reference_type="Sales Invoice", reference_name="SI")
		journal.link_advance_evidence([source], [invoice])
		self.assertEqual(source["source_emirate"], "Dubai")
		self.assertIn("overlap reconciliation", automatic.source_rule(source, "AED")[1])
		self.assertIn("SI", source["linked_sales_invoices"])

	def test_inverse_advance_allocations_and_adjustments_do_not_double_count(self):
		for allocations, adjustments in (([dict(parent="SI", reference_type="Journal Entry", reference_name="TEST-JV", allocated_amount=100)], []),
			([], [dict(parent="ADJUSTMENT-JV", reference_name="TEST-JV")])):
			source, _doc = self.advance(emirate="Dubai")
			journal.link_advance_evidence([source], [], allocations, adjustments)
			self.assertIn("overlap reconciliation", automatic.source_rule(source, "AED")[1])
			self.assertEqual(source["recorded_vat_amount"], 22783.63)

	def test_vat_settlement_does_not_become_advance_or_input(self):
		source = self.source(debit=0, credit=50, raw_vat=-journal.number(50))
		journal.match_journal(dict(accounts=[dict(name="BANK", account="Bank", debit=50, credit=0),
			dict(name="TAX", account="VAT", debit=0, credit=50)]), [source], {"Expense"}, "AED", {"ADV"})
		self.assertIsNone(source.get("journal_vat_role"))
		self.assertIsNone(source["base"])
		self.assertIsNone(automatic.source_rule(source, "AED")[0])
		rule = frappe._dict(box="Outside VAT", approved_by="MANAGER", reason="Saved VAT settlement",
			supporting_reference="BANK", tax_date="2026-06-30")
		event, error = engine.apply_rule(source, rule, "AED")
		self.assertIsNone(error)
		self.assertEqual(event["vat_amount"], 0)

	def test_prepared_advance_and_reversal_contribute_to_correct_output_summary(self):
		sources = [self.advance(emirate="Ras Al Khaimah")[0], self.advance(reversal=True, emirate="Ras Al Khaimah", source_row="REVERSAL-GL")[0]]
		result = dict(filters=frappe._dict(company="TEST"), header=dict(base_currency="AED"), events=[], reviews=sources,
			excluded=[], warnings=[], reconciliation=[])
		settings = {"uae_vat_accounts":[frappe._dict(account="VAT", custom_vat201_side="Both")]}
		with patch.object(engine, "build", return_value=result), patch.object(engine, "settings_for", return_value=settings):
			output = automatic.build({"company":"TEST"})
		self.assertFalse(output["reviews"])
		self.assertEqual([e["recorded_vat_amount"] for e in output["events"]], [22783.63, -22783.63])
		self.assertTrue(all(row["treatment"] == "Customer-advance output VAT" for row in output["details"]))
		boxes = {box["box"]:box for box in output["boxes"]}
		self.assertEqual(boxes["1f"]["amount"], 0)
		self.assertEqual(boxes["12"]["amount"], 0)
		self.assertEqual(boxes["13"]["amount"], 0)
