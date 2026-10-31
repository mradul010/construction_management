import io
import unittest
from unittest.mock import patch

import frappe
from openpyxl import load_workbook

from construction_management.construction_management.report.uae_vat_201_return import automatic, completeness, engine
from construction_management.construction_management.report.uae_vat_201_return import uae_vat_201_return as report


class TestVATCompleteness(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe, "get_precision", return_value=2))
		self.settings = {"uae_vat_accounts":[frappe._dict(account="VAT",custom_vat201_side="Both")]}

	def source(self, **changes):
		return dict(dict(voucher_type="Journal Entry",voucher_no="JV",source_row="GL",posting_date="2026-06-01",
			base=1042.37,raw_vat=engine.number(52.12),tax_account="VAT",currency="AED",debit=52.12,credit=0,
			journal_category="Recorded purchase VAT",journal_vat_role="Input",invoice_taxable_amount=1042.37,
			recorded_vat_amount=52.12), **changes)

	def build(self, sources=(), **changes):
		result = dict(filters=frappe._dict(company="TEST"),header=dict(company="TEST",base_currency="AED"),
			events=[],reviews=list(sources),excluded=[],warnings=[],reconciliation=[],observed=dict(sales_vat=0,purchases_vat=0))
		result.update(changes)
		with patch.object(engine,"build",return_value=result), patch.object(engine,"settings_for",return_value=self.settings):
			return automatic.build({"company":"TEST"})

	def state(self, result, box, component="amount"):
		return next(row for row in result["boxes"] if row["box"] == box)["completeness"][component]["provisional"]

	def test_complete_no_activity_is_numeric_zero_without_pending(self):
		result = self.build()
		for box in result["boxes"]:
			for component in completeness.COMPONENTS:
				self.assertEqual(box[component], 0)
				self.assertFalse(self.state(result,box["box"],component))
		self.assertTrue(all(not card["provisional"] for card in report.summary_cards(result)))

	def test_missing_advance_emirate_affects_only_output_allocations_and_totals(self):
		source = self.source(journal_category="Customer-advance output VAT",journal_vat_role="Output",base=455672.6,
			raw_vat=engine.number(-22783.63),debit=0,credit=22783.63,invoice_taxable_amount=455672.6,recorded_vat_amount=22783.63)
		result = self.build([source])
		for box in engine.OUTPUT[:7] + ["8","12","14"]:
			self.assertTrue(self.state(result,box))
		for box in ["2","3","4","5","6","7","9","10","11","13"]:
			self.assertFalse(self.state(result,box))
		self.assertTrue(all(not self.state(result,box["box"],"adjustment") for box in result["boxes"]))
		self.assertEqual(result["unallocated_output"][0]["recorded_vat"],22783.63)
		self.assertFalse(result["events"])

	def test_purchase_journal_recovery_affects_only_input_and_net(self):
		result = self.build([self.source()])
		for box in ["9","11","13","14"]:
			self.assertTrue(self.state(result,box))
		for box in engine.OUTPUT + ["8","10","12"]:
			self.assertFalse(self.state(result,box))
		self.assertFalse(self.state(result,"9","adjustment"))
		cards = report.summary_cards(result)
		claim = next(c for c in cards if c["label"].startswith("Recoverable Purchase"))
		self.assertEqual(claim["value"],0)
		self.assertTrue(claim["provisional"])
		adjustment = next(c for c in cards if c["label"].startswith("VAT Adjustments"))
		self.assertEqual((adjustment["value"],adjustment["provisional"]),(0,False))

	def test_default_purchase_zero_requires_approval_without_a_box_claim(self):
		source = self.source(voucher_type="Purchase Invoice",journal_category=None,journal_vat_role=None,
			recovery_source_amount=0,vat_rows_count=1)
		result = self.build([source])
		self.assertTrue(result["reviews"])
		self.assertTrue(self.state(result,"9"))
		self.assertIsNone(result["details"][0]["vat_box"])
		self.assertEqual(result["details"][0]["recorded_vat_amount"],52.12)

	def test_only_actual_adjustments_propagate_to_adjustment_components(self):
		source = self.source(is_adjustment=1,box="9")
		result = self.build([source])
		for box in ["9","11"]:
			self.assertTrue(self.state(result,box,"adjustment"))
			self.assertFalse(self.state(result,box,"vat_amount"))
		self.assertTrue(self.state(result,"13"))
		self.assertTrue(self.state(result,"14"))
		self.assertFalse(self.state(result,"8","adjustment"))
		self.assertTrue(next(c for c in report.summary_cards(result) if c["label"].startswith("VAT Adjustments"))["provisional"])

	def test_saved_adjustment_rule_is_used_without_adding_source_fields(self):
		self.settings["custom_vat201_classifications"] = [frappe._dict(voucher_type="Journal Entry",voucher_no="JV",source_row="GL",box="9",is_adjustment=1)]
		result = self.build([self.source()])
		self.assertTrue(self.state(result,"9","adjustment"))
		self.assertFalse(self.state(result,"9","vat_amount"))

	def test_reverse_charge_recovery_does_not_mark_ordinary_emirate_boxes(self):
		result = self.build([self.source(voucher_type="Purchase Invoice",journal_category=None,journal_vat_role=None,reverse_charge="Y")])
		for box in ["3","10","8","11","12","13","14"]:
			self.assertTrue(self.state(result,box))
		for box in engine.OUTPUT[:7]+["9"]:
			self.assertFalse(self.state(result,box))

	def test_unknown_journal_can_affect_imports_but_not_arbitrary_adjustments(self):
		result = self.build([self.source(journal_category="Unresolved",journal_vat_role=None,base=None)])
		for box in ["2","3","6","7","9","10"]:
			self.assertTrue(self.state(result,box))
		for box in ["4","5"]:
			self.assertFalse(self.state(result,box))
		self.assertFalse(self.state(result,"8","adjustment"))

	def test_ledger_difference_and_header_warnings_do_not_mask_box_completeness(self):
		result = self.build(warnings=["TRN: Not Configured"],reconciliation=[dict(description="Output VAT",ledger_amount=100)])
		self.assertEqual(result["status"],automatic.PRELIMINARY)
		self.assertTrue(all(not self.state(result,box["box"],field) for box in result["boxes"] for field in completeness.COMPONENTS))
		self.assertFalse(next(c for c in report.summary_cards(result) if c["label"].startswith("Net VAT"))["provisional"])

	def test_inaccessible_scope_cannot_claim_confirmed_no_activity(self):
		result = self.build(scope_incomplete=True)
		for box in engine.OUTPUT+engine.INPUT:
			for field in completeness.COMPONENTS:
				self.assertTrue(self.state(result,box,field))
		self.assertTrue(self.state(result,"14"))

	def test_known_numeric_screen_totals_equal_excel_even_while_provisional(self):
		event = dict(voucher_type="Sales Invoice",voucher_no="SI",source_row="SI-TAX",box="1f",amount=1101253.46,
			vat_amount=55062.68,adjustment=0,source_emirate="Ras Al Khaimah")
		result = self.build([self.source()],events=[event],observed=dict(sales_vat=55062.68))
		with patch.object(report,"build",return_value=result):
			screen = report.execute({})
		book = load_workbook(io.BytesIO(report.workbook_bytes(result)))
		rows = list(book.active.values)
		for box, row in zip(screen[1], rows[7:]):
			self.assertEqual(list(row[2:5]),[box[field] for field in completeness.COMPONENTS])
			self.assertTrue(all(isinstance(value,(int,float)) for value in row[2:5]))
		net = next(c for c in screen[4] if c["label"].startswith("Net VAT"))
		self.assertEqual(net["value"],55062.68)
		self.assertIn("Provisional",net["label"])
		self.assertTrue(all(isinstance(v,(int,float)) for row in rows[7:7+len(result["boxes"])] for v in row[2:5]))

	def test_role_normalized_warning_and_export_keep_raw_gl_separate(self):
		source = self.source(journal_category="Customer-advance output VAT",journal_vat_role="Output",base=455672.6,
			raw_vat=engine.number(-22783.63),debit=0,credit=22783.63,invoice_taxable_amount=455672.6,recorded_vat_amount=22783.63)
		result = self.build([source])
		rows = report.export_rows(result)
		start = next(i for i,row in enumerate(rows) if row[0] == "Needs Attention")
		self.assertEqual(rows[start+2][4],22783.63)
		self.assertEqual(rows[start+2][6],-22783.63)
		self.assertTrue(any("recorded output VAT AED 22783.63" in warning for warning in result["warnings"]))

	def test_default_zero_does_not_become_confirmed_exclusion(self):
		source = self.source(voucher_type="Purchase Invoice",journal_category=None,journal_vat_role=None,
			recovery_source_amount=0,vat_rows_count=1)
		result = self.build([source],reconciliation=[dict(description="Input VAT",ledger_amount=52.12)])
		self.assertTrue(self.state(result,"13"))
		self.assertEqual(result["reconciliation"][0]["difference"],-52.12)
		self.assertIn("recovery exclusions: AED 0.0",result["reconciliation"][0]["explanation"])

	def test_unallocated_output_reversal_remains_negative_in_warnings(self):
		source = self.source(journal_category="Customer-advance output VAT",journal_vat_role="Output",base=-455672.6,
			raw_vat=engine.number(22783.63),debit=22783.63,credit=0,invoice_taxable_amount=-455672.6,recorded_vat_amount=-22783.63)
		result = self.build([source])
		self.assertTrue(any("recorded output VAT AED -22783.63" in warning for warning in result["warnings"]))

	def test_foreign_untaxed_purchase_affects_potential_supply_import_boxes_only(self):
		source = self.source(voucher_type="Purchase Invoice",journal_category=None,journal_vat_role=None,
			raw_vat=0,tax_account=None,potential_reverse_charge=True,recovery_source_amount=0,recorded_vat_amount=0)
		result = self.build([source])
		for box in ("3","6","10","8","11","12","13","14"):
			self.assertTrue(self.state(result,box))
		for box in engine.OUTPUT[:7]+["2","4","5","7","9"]:
			self.assertFalse(self.state(result,box))
		self.assertTrue(all(not self.state(result,box["box"],"adjustment") for box in result["boxes"]))
		self.assertEqual(result["details"][0]["recorded_vat_amount"],0)
		self.assertFalse(result["events"])
