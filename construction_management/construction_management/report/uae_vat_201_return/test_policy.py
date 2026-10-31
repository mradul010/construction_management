import copy
import unittest
from unittest.mock import patch

import frappe

from construction_management.construction_management.report.uae_vat_201_return import api, automatic, engine, policy
from construction_management.construction_management.report.uae_vat_201_return import uae_vat_201_return as report


class TestRecoveryPolicy(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe, "get_precision", return_value=2))
		self.row = frappe._dict(name="POLICY-ROW", policy_name="Approved taxable construction costs", enabled=1,
			approved=1, approved_by="MANAGER", approval_time="2026-10-31 10:00:00", applies_to="Purchase Invoice",
			expense_account="Expense", tax_category="Taxable Business", valid_from="2026-05-01", recovery_percent=100,
			payment_condition="Paid invoices only", basis="Business use for taxable supplies under documented company policy",
			supporting_reference="POLICY-REFERENCE")
		self.settings = frappe._dict(company="TEST", uae_vat_accounts=[frappe._dict(account="VAT", custom_vat201_side="Both")],
			custom_vat201_recovery_policies=[self.row])
		self.source = dict(voucher_type="Purchase Invoice", voucher_no="PI", source_row="TAX", posting_date="2026-06-01",
			base=1557.50, raw_vat=77.88, tax_account="VAT", tax_rate=5, recovery_source_amount=0, vat_rows_count=1,
			tax_category="Taxable Business", purchase_country="United Arab Emirates", bill_no="SUPPLIER-BILL", bill_date="2026-06-01",
			source_tax_id="100000000000001", outstanding_amount=0,
			item_evidence=[dict(name="ITEM", item_code="CODE", expense_account="Expense", project="P", cost_center="CC", base_net_amount=1557.50)])

	def build(self, source=None, events=()):
		source = copy.deepcopy(self.source if source is None else source)
		initial = dict(filters=frappe._dict(company="TEST", from_date="2026-05-01", to_date="2026-07-31"), header=dict(base_currency="AED"),
			events=list(events), sources=[source], reviews=[] if events else [source], excluded=[], warnings=[], reconciliation=[])
		with patch.object(engine, "build", return_value=initial), patch.object(engine, "settings_for", return_value=self.settings):
			return automatic.build({"company": "TEST"})

	def test_saved_zero_does_not_get_replaced_by_full_policy(self):
		before = copy.deepcopy((self.source, self.settings))
		with patch.object(frappe, "get_doc", side_effect=AssertionError("No source writes")):
			result = self.build()
		self.assertFalse(result["reviews"])
		self.assertFalse(result["events"])
		self.assertEqual(result["details"][0]["recovery_status"], "Saved source zero")
		self.assertEqual((self.source, self.settings), before)

	def test_saved_partial_zero_full_and_returns_ignore_policy(self):
		for percent in (0, 40, 100):
			self.row.recovery_percent = percent
			for sign in (1, -1):
				source = dict(self.source, base=1557.5*sign, raw_vat=77.88*sign, is_return=sign < 0,
					recovery_source_amount=engine.money(77.88*sign*percent/100))
				result = self.build(source)
				self.assertFalse(result["reviews"])
				row = result["details"][0]
				self.assertEqual(row["recorded_vat_amount"], 77.88*sign)
				self.assertEqual(row["invoice_taxable_amount"], 1557.5*sign)
				self.assertEqual(row["recoverable_vat_amount"], engine.money(77.88*sign*percent/100))
				if not percent:
					self.assertIsNone(row["vat_box"])
					self.assertFalse(result["events"])

	def test_saved_zero_takes_precedence_over_old_report_approval(self):
		rule = frappe._dict(box="9", tax_date="2026-06-01", reason="Explicit private use exclusion", supporting_reference="OVERRIDE",
			approved_by="REVIEWER", recovery_confirmed=1, recovery_percent=0)
		event, error = engine.apply_rule(self.source, rule, "AED")
		self.assertIsNone(error)
		result = self.build(events=[event])
		self.assertEqual(result["details"][0]["recoverable_vat_amount"], 0)
		self.assertEqual(result["details"][0]["recovery_status"], "Saved source zero")
		self.assertFalse(result["events"])
		self.assertIsNone(result["details"][0]["vat_box"])

	def test_current_invoice_amount_supersedes_historical_report_override(self):
		for previous in (0, 77.88):
			old_source = dict(self.source, recovery_source_amount=0)
			rule = frappe._dict(box="9", tax_date="2026-06-01", reason="Historical decision", supporting_reference="OLD",
				approved_by="OLD-REVIEWER", recovery_confirmed=1, recovery_percent=previous/77.88*100)
			event, error = engine.apply_rule(old_source, rule, "AED")
			self.assertIsNone(error)
			result = self.build(dict(self.source, recovery_source_amount=10, custom_vat201_recovery_verified=0,
				custom_vat201_recovery_percent=0), events=[event])
			self.assertFalse(result["reviews"])
			self.assertEqual(result["events"][0]["vat_amount"], 10)
			self.assertIsNone(result["events"][0]["approved_by"])

	def test_foreign_invoice_saved_amount_is_already_aed(self):
		result = self.build(dict(self.source, currency="USD", conversion_rate=3.6725, recovery_source_amount=10))
		row = result["details"][0]
		self.assertEqual((row["invoice_taxable_amount"], row["recorded_vat_amount"], row["recoverable_vat_amount"]), (1557.5,77.88,10))

	def test_structured_bill_date_wins_without_parsing_remarks(self):
		result = self.build(dict(self.source, recovery_source_amount=10, bill_no="16937", bill_date="2026-07-16",
			remarks="Supplier invoice date 16-09-2026"))
		remarks = result["details"][0]["display_remarks"]
		self.assertIn("16937; Bill date: 2026-07-16", remarks)
		self.assertNotIn("16-09-2026", remarks)

	def test_multi_tax_rows_allocate_saved_amount_once_at_currency_precision(self):
		for sign in (1, -1):
			rows = [dict(self.source, source_row=str(i), raw_vat=vat*sign, base=vat*20*sign,
				recovery_source_amount=10*sign, vat_rows_count=3) for i,vat in enumerate((10,20,47.88))]
			rows.append(dict(rows[0]))
			initial = dict(filters=frappe._dict(company="TEST", from_date="2026-05-01", to_date="2026-07-31"),
				header=dict(base_currency="AED"), sources=rows, events=[], reviews=rows, excluded=[], warnings=[], reconciliation=[])
			with patch.object(engine,"build",return_value=initial), patch.object(engine,"settings_for",return_value=self.settings):
				result = automatic.build({"company":"TEST"})
			self.assertFalse(result["reviews"])
			self.assertEqual(len(result["events"]),3)
			self.assertEqual(engine.aggregate(result["events"])["9"]["vat_amount"], 10*sign)

	def test_missing_invalid_and_excessive_saved_recovery_remain_data_errors(self):
		for amount in (None,"", "invalid","NaN","Infinity",78,-10):
			result = self.build(dict(self.source, recovery_source_amount=amount))
			self.assertTrue(result["reviews"])
			self.assertFalse(result["events"])

	def test_missing_or_conflicting_policy_does_not_gate_saved_recovery(self):
		self.settings[policy.FIELD] = []
		self.assertFalse(self.build()["reviews"])
		self.settings[policy.FIELD] = [self.row, frappe._dict(self.row, name="DUPLICATE")]
		self.assertFalse(self.build(dict(self.source, recovery_source_amount=10))["reviews"])

	def test_saved_recovery_does_not_require_matching_policy_scope(self):
		for change in (dict(tax_category="Other"), dict(item_evidence=[dict(expense_account="Other")] ), dict(posting_date="2026-04-30")):
			self.assertFalse(self.build(dict(self.source, recovery_source_amount=10, **change))["reviews"])
		self.row.approved = 0
		self.assertFalse(self.build()["reviews"])

	def test_source_quality_is_not_a_saved_amount_recovery_gate(self):
		for change in (dict(bill_no=None), dict(bill_date=None), dict(source_tax_id=None), dict(outstanding_amount=5), dict(purchase_country="India")):
			result = self.build(dict(self.source, recovery_source_amount=10, **change))
			self.assertFalse(result["reviews"])
			self.assertEqual(result["events"][0]["vat_amount"], 10)

	def test_no_policy_saved_nonzero_and_zero_resolve(self):
		self.settings[policy.FIELD] = []
		result = self.build(dict(self.source, recovery_source_amount=20))
		self.assertFalse(result["reviews"])
		self.assertEqual(result["events"][0]["vat_amount"], 20)
		self.assertEqual(result["events"][0]["treatment_source"], "Saved source recovery amount")
		self.assertFalse(self.build()["reviews"])

	def test_saved_partial_owns_recovery_regardless_of_policy_percentage(self):
		self.assertEqual(self.build(dict(self.source, recovery_source_amount=20))["events"][0]["vat_amount"], 20)
		self.row.recovery_percent = 20 / 77.88 * 100
		self.assertFalse(self.build(dict(self.source, recovery_source_amount=20))["reviews"])

	def test_saved_recovery_does_not_require_expense_policy_match(self):
		self.row.project = "Different"
		self.assertFalse(self.build()["reviews"])
		self.row.project = "P"
		self.row.cost_center = "CC"
		self.assertFalse(self.build()["reviews"])
		items = self.source["item_evidence"] + [dict(expense_account="Private", project="P", cost_center="CC")]
		self.assertFalse(self.build(dict(self.source, item_evidence=items))["reviews"])

	def test_reverse_charge_and_missing_gl_base_fx_stay_specific(self):
		for changes in (dict(reverse_charge="Y"), dict(invoice_tax_difference=1)):
			self.assertTrue(self.build(dict(self.source, **changes))["reviews"])
		self.assertTrue(self.build(dict(self.source, base=None, recovery_source_amount=10))["reviews"])
		self.assertIn("AED", policy.resolve(self.source, self.settings, "USD")[1])

	def test_reverse_charge_build_preserves_existing_path_without_a_policy(self):
		self.settings[policy.FIELD] = []
		for sign in (1, -1):
			for percent in (0, 40, 100):
				source = dict(self.source, base=1557.5*sign, raw_vat=77.88*sign, recovery_source_amount=0,
					reverse_charge="Y", reverse_recovery_percent=percent,
					gl_evidence=[dict(debit=77.88, credit=0), dict(debit=0, credit=77.88)])
				result = self.build(source)
				self.assertFalse(result["reviews"])
				boxes = engine.aggregate(result["events"])
				self.assertEqual(boxes["3"]["vat_amount"], 77.88*sign)
				self.assertEqual(boxes["10"]["vat_amount"], engine.money(77.88*sign*percent/100))

	def test_journal_uses_approved_rule_without_reentering_header_bill_or_attachment(self):
		self.row.applies_to = "Expense Journal"
		self.row.tax_category = None
		self.row.payment_condition = "Paid or intended within required time"
		s = dict(voucher_type="Journal Entry", voucher_no="JV", source_row="GL", posting_date="2026-06-01", tax_account="VAT",
			base=1042.37, raw_vat=52.12, debit=52.12, credit=0, journal_category="Recorded purchase VAT", journal_vat_role="Input",
			base_row_references=["BASE"], journal_evidence=dict(document=dict(bill_no="BILL", bill_date="2026-06-01",
				accounts=[dict(name="BASE", account="Expense")]), attachments=[dict(name="ATTACHMENT")]))
		result = self.build(s)
		self.assertFalse(result["reviews"])
		self.assertEqual(result["events"][0]["vat_amount"], 52.12)
		self.assertTrue(self.build(dict(s, journal_invoice_linked=True))["reviews"])
		document = dict(accounts=s["journal_evidence"]["document"]["accounts"])
		self.assertFalse(self.build(dict(s, journal_evidence=dict(document=document, attachments=[])))["reviews"])
		for sign in (1,-1):
			for percent,claim in ((0,0),(50,26.06),(100,52.12)):
				self.row.recovery_percent = percent
				result = self.build(dict(s,base=1042.37*sign,raw_vat=52.12*sign,debit=52.12 if sign>0 else 0,credit=52.12 if sign<0 else 0))
				self.assertFalse(result["reviews"])
				row = result["details"][0]
				self.assertEqual(row["recorded_vat_amount"],52.12*sign)
				self.assertEqual(row["recoverable_vat_amount"],claim*sign)
				self.assertIsNone(row.get("approved_by"))
				self.assertEqual(row["policy_id"],self.row.name)
				if not percent:
					self.assertEqual(row["vat_box"],"")

	def test_unauthorized_policy_changes_and_removal_fail(self):
		doc = frappe._dict(company="TEST", custom_vat201_recovery_policies=[self.row])
		with patch.object(frappe, "get_roles", return_value=["Accounts User"]):
			with self.assertRaises(frappe.PermissionError):
				policy.validate(doc)
			with self.assertRaises(frappe.PermissionError):
				policy.validate(frappe._dict(custom_vat201_recovery_policies=[]), doc)

	def test_journal_manual_restriction_and_stale_decision_precede_full_rule(self):
		self.row.applies_to="Expense Journal"
		self.row.tax_category=None
		self.row.payment_condition="Paid or intended within required time"
		source=dict(voucher_type="Journal Entry",voucher_no="JV",source_row="GL",posting_date="2026-06-01",tax_account="VAT",
			base=1042.37,raw_vat=52.12,debit=52.12,credit=0,journal_category="Recorded purchase VAT",journal_vat_role="Input",
			base_row_references=["BASE"],journal_evidence=dict(document=dict(accounts=[dict(name="BASE",account="Expense")])))
		for percent in (0,50):
			rule=frappe._dict(box="9",tax_date="2026-06-01",reason="Explicit source restriction",supporting_reference="RESTRICTION",
				approved_by="REVIEWER",recovery_confirmed=1,recovery_percent=percent)
			event,error=engine.apply_rule(source,rule,"AED")
			self.assertIsNone(error)
			result=self.build(source,events=[event])
			self.assertEqual(result["details"][0]["recoverable_vat_amount"],engine.money(52.12*percent/100))
			self.assertNotIn("policy_id",result["details"][0])
		for restriction in (dict(requires_review=True),dict(classification_status="Rejected")):
			result=self.build(dict(source,**restriction))
			self.assertTrue(result["reviews"])
			self.assertFalse(result["events"])

	def test_missing_journal_recovery_is_a_factual_source_gap_not_zero_entitlement(self):
		self.settings[policy.FIELD]=[]
		source=dict(voucher_type="Journal Entry",voucher_no="JV",source_row="GL",posting_date="2026-06-01",tax_account="VAT",
			base=1042.37,raw_vat=52.12,debit=52.12,credit=0,journal_category="Recorded purchase VAT",journal_vat_role="Input",
			base_row_references=["BASE"],journal_evidence=dict(document=dict(accounts=[dict(name="BASE",account="Expense")])))
		result=self.build(source)
		row=result["details"][0]
		self.assertEqual(row["issue"],"Recovery not specified in source.")
		self.assertEqual(row["treatment"],"Recorded expense JV VAT")
		self.assertEqual((row["base"],row["raw_vat"]),(1042.37,52.12))
		self.assertIsNone(row.get("recoverable_vat_amount"))
		self.assertFalse(result["return_complete"])
		self.assertEqual(result["calculation_description"],"Calculated from saved ERPNext records")
		self.assertTrue(next(b for b in result["boxes"] if b["box"]=="13")["completeness"]["amount"]["provisional"])

	def test_manager_approval_is_stamped_and_cannot_use_tax_account_only(self):
		self.row.tax_category = None
		doc = frappe._dict(company="TEST", custom_vat201_recovery_policies=[self.row])
		with patch.object(frappe, "get_roles", return_value=["Accounts Manager"]), patch.object(frappe, "get_cached_doc", return_value=frappe._dict(company="TEST", root_type="Expense", is_group=0)):
			with self.assertRaises(frappe.ValidationError):
				policy.validate(doc)
			self.row.tax_category = "Taxable Business"
			policy.validate(doc)
			self.assertEqual(self.row.approved_by, frappe.session.user)
			self.assertTrue(self.row.approval_time)

	def test_item_wise_saved_tax_allocation_never_divides_rounded_vat(self):
		tax = dict(charge_type="On Net Total", item_wise_tax_detail='{"CODE":[5,77.88],"EXEMPT":[0,0]}', base_tax_amount_after_discount_amount=77.88)
		items = self.source["item_evidence"] + [dict(item_code="EXEMPT", base_net_amount=10, is_exempt=1)]
		base, selected = engine.item_tax_base(tax, items, 1)
		self.assertEqual(float(base), 1557.5)
		self.assertEqual(len(selected), 1)
		self.assertIsNone(engine.item_tax_base(dict(tax, base_tax_amount_after_discount_amount=99), items, 1)[0])
		self.assertIsNone(engine.item_tax_base(dict(tax, charge_type="On Previous Row Total"), items, 1)[0])


class TestLiveVATAPI(unittest.TestCase):
	def test_other_reports_delegate_without_changed_arguments(self):
		from frappe.desk import query_report
		with patch.object(query_report, "run", return_value={"result": []}) as run:
			api.run("Other", filters={"company":"TEST"}, ignore_prepared_report=False)
			self.assertFalse(run.call_args.kwargs["ignore_prepared_report"])
			self.assertEqual(run.call_args.kwargs["report_name"], "Other")

	def test_vat_refresh_ignores_prepared_and_context_reuses_exact_result(self):
		from frappe.desk import query_report
		result = dict(marker=object())
		def execute(**kwargs):
			self.assertTrue(kwargs["ignore_prepared_report"])
			self.assertNotIn("prepared_report_name", kwargs["filters"])
			frappe.local.vat201_current_result = result
			return dict(result=[])
		with patch.object(query_report, "run", side_effect=execute), patch.object(report, "context_for", return_value={"fresh":True}) as context:
			response = api.run(api.REPORT, filters={"prepared_report_name":"OLD"})
			self.assertIs(context.call_args.args[0], result)
			self.assertTrue(response["vat201_context"]["fresh"])

	def test_standard_excel_and_custom_download_use_same_live_builder(self):
		previous = frappe.local.form_dict
		try:
			frappe.local.form_dict = frappe._dict(report_name=api.REPORT, file_format_type="Excel", filters='{"company":"TEST"}')
			with patch.object(report, "download") as download:
				api.export_query()
				download.assert_called_once_with('{"company":"TEST"}', "xlsx")
		finally:
			frappe.local.form_dict = previous

	def test_non_vat_export_is_untouched(self):
		from frappe.desk import query_report
		previous = frappe.local.form_dict
		try:
			frappe.local.form_dict = frappe._dict(report_name="Other")
			with patch.object(query_report, "export_query", return_value="NATIVE"):
				self.assertEqual(api.export_query(), "NATIVE")
		finally:
			frappe.local.form_dict = previous
