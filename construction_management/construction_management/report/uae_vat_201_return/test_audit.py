import copy
import unittest
from unittest.mock import patch

import frappe

from construction_management.construction_management.report.uae_vat_201_return import calendar, engine, reconciliation, automatic


class TestVATAudit(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe,"get_precision",return_value=2))
		self.settings = {"uae_vat_accounts":[frappe._dict(account="VAT",custom_vat201_side="Both")]}

	def result(self, role="Output", debit=0, credit=50, claim=None, currency="AED"):
		source = dict(voucher_type="Journal Entry",voucher_no="JV",source_row="GL",posting_date="2026-06-01",
			tax_account="VAT",debit=debit,credit=credit,raw_vat=engine.number(debit)-engine.number(credit),
			journal_vat_role=role,base=1000,generated_tax_rows=["TAX"],base_row_references=["BASE"])
		entry = dict(name="GL",voucher_type="Journal Entry",voucher_no="JV",posting_date="2026-06-01",account="VAT",debit=debit,credit=credit)
		events = [] if claim is None else [dict(source,box="9" if role=="Input" else "1f",vat_amount=claim,amount=1000,adjustment=0,tax_date="2026-06-01",aed_exchange_rate=1)]
		details = [] if claim is None else [dict(source,currency="AED",recorded_vat_amount=debit-credit,recoverable_vat_amount=claim)] if role=="Input" else []
		return dict(header=dict(base_currency=currency),ledger_entries=[entry],sources=[source],source_headers={},events=events,details=details,
			reviews=[] if claim is not None else [dict(source,issue="Unresolved source evidence")],excluded=[],warnings=[],boxes=list(engine.aggregate(events).values()),control_movement=debit-credit)

	def test_output_roles_and_raw_gl_signs_do_not_depend_on_allocated_emirate(self):
		for debit, credit, expected in ((0,50,50),(50,0,-50)):
			result = self.result(debit=debit,credit=credit)
			original = copy.deepcopy(result["sources"])
			reconciliation.apply(result,self.settings)
			self.assertEqual(result["sources"],original)
			self.assertEqual(result["reconciliation"][0]["ledger_amount"],expected)
			self.assertEqual(result["reconciliation"][0]["report_amount"],0)
			self.assertEqual(result["audit_rows"][0]["recorded_output"],expected)
			self.assertEqual(result["audit_rows"][0]["raw_movement"],-expected)
			self.assertEqual(result["audit_rows"][0]["source_to_gl_difference"],0)

	def test_partial_and_return_recovery_remain_signed_and_explained(self):
		for debit,credit,claim in ((50,0,20),(0,50,-20)):
			result = self.result(role="Input",debit=debit,credit=credit,claim=claim)
			reconciliation.apply(result,self.settings)
			rec = result["reconciliation"][1]
			self.assertEqual(rec["ledger_amount"],debit-credit)
			self.assertEqual(rec["report_amount"],claim)
			self.assertEqual(result["audit_rows"][0]["known_nonclaimed"],debit-credit-claim)

	def test_control_only_settlement_does_not_become_supply_or_recovery(self):
		result = self.result(role=None)
		result["excluded"] = result["sources"]
		result["reviews"] = []
		reconciliation.apply(result,self.settings)
		self.assertEqual(result["reconciliation"][0]["ledger_amount"],0)
		self.assertEqual(result["reconciliation"][1]["ledger_amount"],0)
		self.assertEqual(result["audit_rows"][0]["control_movement"],-50)
		self.assertIn("settlement/transfer",result["audit_rows"][0]["category"])

	def test_unknown_fx_stays_unavailable_but_zero_side_is_zero(self):
		result = self.result(currency="USD")
		reconciliation.apply(result,self.settings)
		self.assertIsNone(result["reconciliation"][0]["ledger_amount"])
		self.assertEqual(result["reconciliation"][1]["ledger_amount"],0)
		self.assertIsNone(result["audit_rows"][0]["recorded_output"])
		self.assertEqual(result["audit_rows"][0]["recorded_input"],0)

	def test_verified_currency_rate_and_timing_are_separate_from_rounding(self):
		result = self.result(claim=183.5,currency="USD")
		result["events"][0]["aed_exchange_rate"] = 3.67
		result["events"][0]["tax_date"] = "2026-07-01"
		reconciliation.apply(result,self.settings)
		self.assertEqual(result["reconciliation"][0]["difference"],0)
		self.assertIn("timing difference",result["audit_rows"][0]["category"])
		self.assertEqual(result["audit_rows"][0]["source_to_gl_difference"],0)

	def test_duplicate_linked_vat_remains_recorded_but_not_claimed(self):
		result = self.result()
		result["reviews"][0]["journal_duplicate_risk"] = "Linked invoice requires overlap reconciliation"
		reconciliation.apply(result,self.settings)
		self.assertEqual(result["audit_rows"][0]["recorded_output"],50)
		self.assertEqual(result["audit_rows"][0]["claimed_output"],0)
		self.assertIn("overlap",result["audit_rows"][0]["category"])

	def test_foreign_no_vat_is_not_automatically_rc_or_no_obligation(self):
		source = dict(voucher_type="Purchase Invoice",voucher_no="PI",source_row="ITEM",raw_vat=0,tax_account=None,
			potential_reverse_charge=True,reverse_charge="N",base=1000)
		rule,error = automatic.source_rule(source,"AED")
		self.assertIsNone(rule)
		self.assertIn("reverse-charge obligation",error)

	def test_calendar_keeps_user_dates_and_accepts_evidenced_holiday_extension(self):
		header = dict(period_kind="Configured filing period",from_date="2026-05-01",to_date="2026-07-31",filing_frequency="Quarterly",
			quarter_number=2,tax_year_end="2027-01-31",registration_date="2026-05-01",due_date="2026-08-31",due_date_basis="Confirmed")
		issues = calendar.validate(header,{})
		self.assertEqual(header["due_date"],"2026-08-31")
		self.assertEqual(header["nominal_due_date"],"2026-08-28")
		self.assertEqual(header["expected_due_date"],"2026-08-31")
		self.assertIn("FAHR Circular",header["calendar_basis"])
		self.assertEqual(issues,[])
		header["due_date"] = "2026-08-28"
		self.assertTrue(any("checked date 2026-08-31" in issue for issue in calendar.validate(header,{})))

	def test_calendar_flags_bad_cycle_and_overlapping_periods(self):
		header = dict(period_kind="Configured filing period",from_date="2026-05-01",to_date="2026-07-31",filing_frequency="Quarterly",
			quarter_number=1,tax_year_end="2027-01-31",due_date="2026-08-28",due_date_basis="Confirmed")
		settings = {"custom_vat201_periods":[frappe._dict(from_date="2026-07-01",to_date="2026-09-30")]}
		issues = calendar.validate(header,settings)
		self.assertTrue(any("quarter number" in issue for issue in issues))
		self.assertTrue(any("overlap" in issue for issue in issues))

	def test_manually_reviewed_output_role_normalizes_untyped_journal_base(self):
		for debit,credit,base,sign in ((0,50,-1000,1),(50,0,1000,-1)):
			source = dict(voucher_type="Journal Entry",voucher_no="JV",source_row="GL",posting_date="2026-06-01",
				base=base,raw_vat=debit-credit,debit=debit,credit=credit)
			rule = frappe._dict(box="1f",approved_by="Reviewer",reason="Existing reviewed output evidence",
				supporting_reference="REF",tax_date="2026-06-01")
			event,error = engine.apply_rule(source,rule,"AED")
			self.assertIsNone(error)
			self.assertEqual(event["amount"],1000*sign)
			self.assertEqual(event["invoice_taxable_amount"],1000*sign)
			self.assertEqual(event["vat_amount"],50*sign)
			self.assertEqual(event["recorded_vat_amount"],50*sign)
