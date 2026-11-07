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
			sources=[dict(voucher_type="Journal Entry", voucher_no="JV-1", source_row="GL-1", journal_category="Recorded purchase VAT", base=200)],
			boxes=[dict(box="14", amount=55062.68)])

	def test_cards_use_gl_and_are_independent_of_internal_approvals(self):
		before = copy.deepcopy(self.result)
		self.assertEqual([r['value'] for r in report.summary_cards(self.result)], [0,0,200,10,-10])
		self.result['boxes'][0]['amount'] = 1
		self.assertEqual(report.summary_cards(self.result), report.summary_cards(before))
		self.assertEqual(gl_view.summary_rows(self.result)[3]['amount'],535.57)

	def test_html_and_excel_share_gl_values_without_claiming_box_14(self):
		content = form_layout.form_html(self.result, interactive=True)
		self.assertIn('67,265.70', content)
		self.assertNotIn('55,062.68', content)
		self.assertIn('/app/journal-entry/JV-1', content)
		book = load_workbook(io.BytesIO(report.workbook_bytes(self.result)))
		self.assertEqual(book.sheetnames[:2], ['VAT per General Ledger','VAT GL Entries'])
		self.assertIn('VAT Opening Entries', book.sheetnames)
		self.assertIn(('Net VAT per Books (credit minus debit)',67265.70,None),list(book.active.values))
		self.assertEqual(book['VAT GL Entries']['F2'].value,10)

	def test_currency_and_missing_totals_are_not_fabricated(self):
		self.result['ledger_summary'] = dict(currency='USD')
		cards = report.summary_cards(self.result)
		self.assertTrue(all(c['currency']=='USD' for c in cards))
		self.assertTrue(all(r['amount'] is None for r in gl_view.summary_rows(self.result)))
		self.result['report_view'] = 'Internal VAT Review'
		self.assertFalse(gl_view.enabled(self.result))

	def test_returns_reduce_their_category_and_every_gl_row_reconciles(self):
		def entry(name, dt, debit, credit, date="2026-05-02"):
			return dict(name=name, voucher_type=dt, voucher_no=name, posting_date=date, account="VAT", debit=debit, credit=credit)
		self.result['ledger_entries'] = [entry("P-return", "Purchase Invoice", 0, 5), entry("S", "Sales Invoice", 0, 50), entry("P", "Purchase Invoice", 20, 0), entry("S-return", "Sales Invoice", 10, 0), entry("A", "Journal Entry", 0, 30), entry("U", "Payment Entry", 7, 0)]
		self.result['sources'] = [dict(voucher_type=e['voucher_type'],voucher_no=e['voucher_no'],source_row=e['name'],tax_account="VAT",base=base,journal_category="Customer-advance output VAT" if e['name']=="A" else None) for e,base in zip(self.result['ledger_entries'],[-100,1000,400,-200,600,None])]
		b=gl_view.business_summary(self.result)
		self.assertEqual((b['sales']['base'],b['sales']['vat']),(1400,70))
		self.assertEqual((b['purchases']['base'],b['purchases']['vat']),(300,15))
		self.assertEqual(next(r for r in b['sales']['rows'] if r['voucher_no']=='A')['category'],'Customer advance')
		self.assertEqual(b['other']['vat'],-7)
		self.assertEqual(gl_view.net_payable(self.result),55)
		self.assertEqual(len(gl_view.drilldown(self.result,'sales','base')['rows']),3)
		self.assertEqual(len(gl_view.drilldown(self.result,'net_payable')['rows']),5)
		content = form_layout.form_html(self.result, interactive=True)
		self.assertIn('Net VAT Payable',content)
		self.assertNotIn('Other VAT movements',content)
		self.assertNotIn('data-group="advances"',content)
		self.assertNotIn('data-group="other"',content)
		self.assertIn('outside sales and purchases',content)
		book = load_workbook(io.BytesIO(report.workbook_bytes(self.result)))
		self.assertNotIn('VAT Advances',book.sheetnames)
		self.assertEqual(book['VAT Sales'].max_row,4)
		self.assertIn(('Net VAT Payable / Refundable',55,None),list(book.active.values))

		self.assertEqual(sum(len(d['entries']) for d in b.values()),6)
		self.assertEqual(b['sales']['vat']-b['purchases']['vat']+b['other']['vat'],48)

	def test_split_gl_does_not_duplicate_source_base_and_approval_is_irrelevant(self):
		self.result['ledger_entries'].append(dict(self.result['ledger_entries'][0], name="GL-2", debit=5))
		self.result['sources'][0]['journal_group_gl_rows'] = ['GL-1','GL-2']
		b=gl_view.business_summary(self.result)
		self.assertEqual(b['purchases']['base'],200)
		self.assertEqual(b['purchases']['vat'],15)
		self.result['events'] = [dict(box='9', amount=9999, vat_amount=999)]
		self.assertEqual(gl_view.business_summary(self.result), b)

	def test_missing_base_stays_unknown_and_opening_is_separate_sorted(self):
		self.result['sources'][0]['base'] = None
		self.assertIsNone(gl_view.business_summary(self.result)['purchases']['base'])
		self.result['opening_entries'] = [dict(self.result['ledger_entries'][0],name='older', posting_date='2026-04-30',debit=535.57)]
		self.assertEqual(gl_view.drilldown(self.result,'opening_debit')['rows'][0]['name'],'older')
		self.assertEqual([r['name'] for r in gl_view.drilldown(self.result,'closing_credit')['rows']],['older','GL-1'])
		self.assertEqual(len(gl_view.drilldown(self.result,'period_net_credit')['rows']),1)
		self.assertEqual(gl_view.drilldown(self.result,'purchases','base')['kind'],'sources')

	def test_screen_pagination_does_not_limit_print_or_excel(self):
		from lxml import html
		self.result['ledger_entries'] = [dict(self.result['ledger_entries'][0],name=f'GL-{i:03}') for i in range(62)]
		screen = html.fromstring(form_layout.form_html(self.result,interactive=True))
		rows = screen.xpath('//div[contains(@class,"vat201-paged-table")]//tbody/tr')
		self.assertEqual(len(rows),62)
		self.assertEqual(len([r for r in rows if 'display:none' not in r.get('style','')]),25)
		printed = html.fromstring(form_layout.form_html(self.result))
		self.assertFalse(printed.xpath('//tr[contains(@style,"display:none")]'))
		self.assertEqual(len(printed.xpath('//div[contains(@class,"gl-scroll")]//tbody/tr')),62)
		book = load_workbook(io.BytesIO(report.workbook_bytes(self.result)))
		self.assertEqual(book['VAT GL Entries'].max_row,63)
