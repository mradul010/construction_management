import copy
import io
import unittest
from openpyxl import load_workbook
from construction_management.construction_management.report.uae_vat_201_return import gl_view, form_layout
from construction_management.construction_management.report.uae_vat_201_return import uae_vat_201_return as report


class TestGLView(unittest.TestCase):
	def setUp(self):
		self.result = dict(report_view="General Ledger", header=dict(company="Synthetic", from_date="2026-05-01", to_date="2026-07-31"),
			ledger_summary=dict(currency="AED", period_credit=104540.10, period_debit=37274.40, period_net_credit=67265.70,
				opening_debit=535.57, opening_credit=0, closing_debit=0, closing_credit=66730.13),
			filed_comparison={}, ledger_entries=[dict(name="GL-1", posting_date="2026-05-01", voucher_type="Journal Entry", voucher_no="JV-1", account="VAT", debit=10, credit=0)],
			boxes=[dict(box="14", amount=55062.68)])

	def test_cards_use_gl_and_are_independent_of_internal_approvals(self):
		before = copy.deepcopy(self.result)
		self.assertEqual([r['value'] for r in report.summary_cards(self.result)], [104540.10,37274.40,67265.70])
		self.result['boxes'][0]['amount'] = 1
		self.assertEqual(report.summary_cards(self.result), report.summary_cards(before))
		self.assertEqual(gl_view.summary_rows(self.result)[3]['amount'],535.57)

	def test_html_and_excel_share_gl_values_without_claiming_box_14(self):
		content = form_layout.form_html(self.result, interactive=True)
		self.assertIn('67,265.70', content)
		self.assertNotIn('55,062.68', content)
		self.assertIn('/app/journal-entry/JV-1', content)
		book = load_workbook(io.BytesIO(report.workbook_bytes(self.result)))
		self.assertEqual(book.sheetnames, ['VAT per General Ledger','VAT GL Entries'])
		self.assertIn(('Net VAT per Books (credit minus debit)',67265.70,None),list(book.active.values))
		self.assertEqual(book['VAT GL Entries']['F2'].value,10)

	def test_currency_and_missing_totals_are_not_fabricated(self):
		self.result['ledger_summary'] = dict(currency='USD')
		cards = report.summary_cards(self.result)
		self.assertTrue(all(c['currency']=='USD' and c['value']=='Not Available' for c in cards))
		self.result['report_view'] = 'Internal VAT Review'
		self.assertFalse(gl_view.enabled(self.result))
