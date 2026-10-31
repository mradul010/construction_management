import copy
import unittest
from unittest.mock import patch

import frappe
from construction_management.construction_management.report.uae_vat_201_return import engine, reconciliation, automatic, review
from construction_management.construction_management.report.uae_vat_201_return import test_audit


class TestRecordedBridge(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe, 'get_precision', return_value=2))
		self.settings = {'uae_vat_accounts': [frappe._dict(account='VAT', custom_vat201_side='Both')]}

	def fixture(self, **kwargs):
		return test_audit.TestVATAudit().result(**kwargs)

	def test_pending_output_normalizes_credit_and_reversal(self):
		for debit, credit, expected in ((0,50,50),(50,0,-50)):
			r = self.fixture(debit=debit,credit=credit)
			reconciliation.apply(r,self.settings)
			self.assertEqual(r['tax_measures']['pending_output'],expected)
			self.assertEqual(r['tax_measures']['recorded_net_movement'],expected)
			self.assertEqual(r['tax_measures']['residual_output'],0)

	def test_verified_full_partial_zero_and_returns_partition_once(self):
		for debit,credit,claim in ((50,0,50),(50,0,20),(50,0,0),(0,50,-20)):
			r = self.fixture(role='Input',debit=debit,credit=credit,claim=claim)
			reconciliation.apply(r,self.settings)
			m = r['tax_measures']
			self.assertEqual(m['recorded_input'],debit-credit)
			self.assertEqual(m['claimed_input'],claim)
			self.assertEqual(m['known_nonclaimed'],debit-credit-claim)
			self.assertEqual(m['pending_input'],0)
			self.assertEqual(m['residual_input'],0)

	def test_pending_is_not_a_zero_approval_and_duplicate_source_does_not_double_pending(self):
		r = self.fixture(role='Input',debit=50,credit=0)
		r['sources'].append(copy.deepcopy(r['sources'][0]))
		reconciliation.apply(r,self.settings)
		self.assertEqual(r['tax_measures']['pending_input'],50)
		self.assertEqual(r['tax_measures']['known_nonclaimed'],0)
		self.assertEqual(r['tax_measures']['residual_input'],0)

	def test_opening_and_period_are_separate(self):
		r = self.fixture()
		r['opening_entries'] = [dict(debit=10,credit=0)]
		reconciliation.apply(r,self.settings)
		self.assertEqual(r['ledger_summary'],dict(currency='AED',opening_debit=10,opening_credit=0,
			period_debit=0,period_credit=50,period_net_credit=50,closing_debit=0,closing_credit=40))

	def test_unsupported_residual_is_visible(self):
		r = self.fixture(role='Input',debit=50,credit=0,claim=20)
		r['details'] = []
		reconciliation.apply(r,self.settings)
		self.assertEqual(r['tax_measures']['residual_input'],30)
		self.assertTrue(any('residual' in w for w in r['warnings']))

	def test_new_fingerprint_binds_recovery_and_amended_identity(self):
		s = dict(voucher_type='Purchase Invoice',voucher_no='PI',source_row='TAX',recovery_source_amount=0)
		self.assertNotEqual(review.decision_fingerprint(s),review.decision_fingerprint(dict(s,recovery_source_amount=10)))
		self.assertNotEqual(review.decision_fingerprint(s),review.decision_fingerprint(dict(s,voucher_no='PI-1')))

	def test_default_zero_remains_pending_in_actual_pipeline(self):
		s = dict(voucher_type='Purchase Invoice',voucher_no='PI',source_row='TAX',posting_date='2026-06-01',
			tax_account='VAT',base=1000,raw_vat=50,recovery_source_amount=0,vat_rows_count=1)
		r = dict(filters=frappe._dict(company='TEST'),header=dict(base_currency='AED'),events=[],reviews=[s],excluded=[],warnings=[],reconciliation=[])
		with patch.object(engine,'build',return_value=r), patch.object(engine,'settings_for',return_value=self.settings):
			output = automatic.build({'company':'TEST'})
		self.assertEqual(output['details'][0]['recovery_status'],'Pending verification')
		self.assertIn('pending accountant approval',output['details'][0]['issue'])
		self.assertFalse(output['events'])

	def test_authorized_review_preserves_zero_approval_without_invoice_change(self):
		s = dict(voucher_type='Purchase Invoice',voucher_no='PI',source_row='TAX',posting_date='2026-06-01',
			tax_account='VAT',base=1000,raw_vat=50,recovery_source_amount=0,vat_rows_count=1)
		for percent, status in ((0,'Verified non-recoverable'),(40,'Verified partially recoverable'),(100,'Verified fully recoverable')):
			rule = frappe._dict(box='9',tax_date='2026-06-01',reason='Reviewed original invoice',supporting_reference='TEST',
				approved_by='Reviewer',recovery_confirmed=1,recovery_percent=percent)
			event, error = engine.apply_rule(s,rule,'AED')
			self.assertIsNone(error)
			r = dict(filters=frappe._dict(company='TEST'),header=dict(base_currency='AED'),events=[event],reviews=[],excluded=[],warnings=[],reconciliation=[])
			with patch.object(engine,'build',return_value=r), patch.object(engine,'settings_for',return_value=self.settings):
				output = automatic.build({'company':'TEST'})
			self.assertEqual(output['details'][0]['recovery_status'],status)
			self.assertEqual(output['details'][0]['recoverable_vat_amount'],percent / 2)
			self.assertEqual(s['recovery_source_amount'],0)
			if percent == 0:
				self.assertEqual(output['details'][0]['vat_box'],'')

	def test_conflicting_nonzero_saved_amount_requires_review(self):
		s = dict(voucher_type='Purchase Invoice',voucher_no='PI',source_row='TAX',posting_date='2026-06-01',
			tax_account='VAT',base=1000,raw_vat=50,recovery_source_amount=20,vat_rows_count=1)
		rule = frappe._dict(box='9',tax_date='2026-06-01',reason='TEST',supporting_reference='TEST',approved_by='Reviewer',
			recovery_confirmed=1,recovery_percent=100)
		self.assertIn('conflicts',engine.apply_rule(s,rule,'AED')[1])
		rule.recovery_percent = 40
		self.assertIsNone(engine.apply_rule(s,rule,'AED')[1])

	def test_unauthorized_update_fails_before_source_query(self):
		with patch.object(review,'manager_access',side_effect=frappe.PermissionError), patch.object(review,'review_source') as source:
			with self.assertRaises(frappe.PermissionError):
				review.decide({'company':'TEST'},'Purchase Invoice','PI','TAX','Approve')
			source.assert_not_called()

	def test_stale_dialog_cannot_approve_changed_source(self):
		with patch.object(review,'manager_access',return_value=frappe._dict()), patch.object(review,'review_source',return_value={'source':{'voucher_no':'Changed'}}):
			with self.assertRaises(frappe.ValidationError):
				review.decide({'company':'TEST'},'Purchase Invoice','PI','TAX','Approve',expected_fingerprint='old')

	def test_approved_tax_date_outside_period_explains_difference(self):
		r = self.fixture(claim=50)
		r['timing_events'] = r['events']
		r['timing_events'][0]['tax_date'] = '2026-08-01'
		r['events'] = []
		r['boxes'] = list(engine.aggregate([]).values())
		reconciliation.apply(r,self.settings)
		self.assertEqual(r['tax_measures']['claimed_output'],0)
		self.assertEqual(r['tax_measures']['pending_output'],0)
		self.assertEqual(r['tax_measures']['timing_output'],50)
		self.assertEqual(r['tax_measures']['residual_output'],0)
