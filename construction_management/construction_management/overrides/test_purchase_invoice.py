from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.construction_management.overrides.purchase_invoice import (
	ConstructionPurchaseInvoice,
)


class _FakeMeta:
	def __init__(self, fields=None):
		self.fields = set(fields or [])

	def has_field(self, fieldname):
		return fieldname in self.fields


class _FakeRow(frappe._dict):
	def __init__(self, *args, fields=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.meta = _FakeMeta(fields)


class UnitTestPurchaseInvoiceSiteMaterialConsumption(UnitTestCase):
	def test_non_project_row_requires_consumption_account(self):
		invoice = frappe._dict(company="QBC")
		row = _FakeRow(
			{"idx": 1, "item_code": "Concrete C20/20"},
			fields={"consumption_account"},
		)

		with self.assertRaises(frappe.ValidationError):
			ConstructionPurchaseInvoice.get_site_material_consumption_expense_account(invoice, row, None)

	def test_row_consumption_account_is_used_for_non_project_row(self):
		invoice = frappe._dict(company="QBC")
		row = _FakeRow(
			{
				"idx": 1,
				"item_code": "Concrete C20/20",
				"consumption_account": "Cost of Other Jobs - QBC",
			},
			fields={"consumption_account"},
		)

		with patch(
			"construction_management.construction_management.doctype.site_material_consumption.site_material_consumption.validate_expense_account"
		) as validate_expense_account:
			account = ConstructionPurchaseInvoice.get_site_material_consumption_expense_account(
				invoice, row, None
			)

		self.assertEqual(account, "Cost of Other Jobs - QBC")
		validate_expense_account.assert_called_once_with("Cost of Other Jobs - QBC", "QBC", 1)

	def test_project_row_keeps_existing_default_consumption_account(self):
		invoice = frappe._dict(company="QBC")
		row = _FakeRow(
			{"idx": 1, "item_code": "Concrete C20/20"},
			fields={"consumption_account"},
		)

		with patch(
			"construction_management.construction_management.doctype.site_material_consumption.site_material_consumption.get_default_expense_account",
			return_value="Cost of Construction - QBC",
		):
			account = ConstructionPurchaseInvoice.get_site_material_consumption_expense_account(
				invoice, row, "PROJ-0016"
			)

		self.assertEqual(account, "Cost of Construction - QBC")

	def test_mixed_project_and_non_project_rows_do_not_set_parent_project(self):
		invoice = frappe._dict()
		rows = [
			frappe._dict(project="PROJ-0016"),
			frappe._dict(project=None),
		]

		project = ConstructionPurchaseInvoice.get_common_site_material_consumption_value(
			invoice, rows, "project"
		)

		self.assertIsNone(project)

	def test_same_project_rows_set_parent_project(self):
		invoice = frappe._dict()
		rows = [
			frappe._dict(project="PROJ-0016"),
			frappe._dict(project="PROJ-0016"),
		]

		project = ConstructionPurchaseInvoice.get_common_site_material_consumption_value(
			invoice, rows, "project"
		)

		self.assertEqual(project, "PROJ-0016")
