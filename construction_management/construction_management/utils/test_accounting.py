from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.construction_management.utils.accounting import (
	apply_construction_accounts_to_purchase_invoice,
)


class _FakeMeta:
	def has_field(self, fieldname):
		return True


class _FakeDoc(frappe._dict):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not self.get("meta"):
			self.meta = _FakeMeta()

	def set(self, fieldname, value):
		self[fieldname] = value


class UnitTestConstructionPurchaseInvoiceAccounting(UnitTestCase):
	def test_purchase_invoice_item_project_and_cost_center_are_not_overwritten(self):
		invoice = _FakeDoc(
			{
				"name": "PINV-TEST",
				"company": "QBC",
				"project": "PROJ-HEADER",
				"currency": "QAR",
				"credit_to": None,
				"party_account_currency": None,
				"meta": _FakeMeta(),
				"items": [
					_FakeDoc(
						{
							"item_code": "Cement",
							"project": "PROJ-001",
							"cost_center": "Civil Works - QBC",
							"expense_account": None,
						}
					),
					_FakeDoc(
						{
							"item_code": "Steel",
							"project": "PROJ-002",
							"cost_center": "Electrical - QBC",
							"expense_account": "Existing Expense - QBC",
						}
					),
					_FakeDoc(
						{
							"item_code": "Transport Charges",
							"project": None,
							"cost_center": None,
							"expense_account": None,
						}
					),
				],
			}
		)

		with (
			patch(
				"construction_management.construction_management.utils.accounting._is_construction_purchase_invoice",
				return_value=True,
			),
			patch(
				"construction_management.construction_management.utils.accounting.get_construction_account",
				side_effect=lambda _company, account_key, **_kwargs: {
					"subcontractor_payable": "Trade Payable - QBC",
					"subcontract_expense": "Cost Of Construction Projects - QBC",
				}[account_key],
			),
			patch(
				"construction_management.construction_management.utils.accounting._get_construction_cost_center",
				return_value="Header Cost Center - QBC",
			),
			patch(
				"construction_management.construction_management.utils.accounting.frappe.get_cached_value",
				return_value="QAR",
			),
		):
			apply_construction_accounts_to_purchase_invoice(invoice)

		rows = invoice.get("items")
		self.assertEqual(rows[0].project, "PROJ-001")
		self.assertEqual(rows[0].cost_center, "Civil Works - QBC")
		self.assertEqual(rows[1].project, "PROJ-002")
		self.assertEqual(rows[1].cost_center, "Electrical - QBC")
		self.assertIsNone(rows[2].project)
		self.assertIsNone(rows[2].cost_center)
		self.assertEqual(rows[0].expense_account, "Cost Of Construction Projects - QBC")
		self.assertEqual(rows[1].expense_account, "Existing Expense - QBC")
		self.assertEqual(rows[2].expense_account, "Cost Of Construction Projects - QBC")
