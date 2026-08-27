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


def _fake_purchase_invoice(**values):
	invoice = object.__new__(ConstructionPurchaseInvoice)
	for fieldname, value in values.items():
		setattr(invoice, fieldname, value)
	return invoice


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

	def test_site_material_consumption_rows_keep_item_project_and_cost_center(self):
		invoice = frappe._dict(
			{
				"name": "PINV-TEST",
				"company": "QBC",
				"project": "PROJ-HEADER",
				"cost_center": "Header Cost Center - QBC",
				"items": [
					_FakeRow(
						{
							"idx": 1,
							"name": "pi-item-1",
							"item_code": "Cement",
							"item_name": "Cement",
							"description": "Cement",
							"qty": 5,
							"uom": "Nos",
							"stock_uom": "Nos",
							"conversion_factor": 1,
							"warehouse": "Stores - QBC",
							"project": "PROJ-001",
							"cost_center": "Civil Works - QBC",
						}
					),
					_FakeRow(
						{
							"idx": 2,
							"name": "pi-item-2",
							"item_code": "Steel",
							"item_name": "Steel",
							"description": "Steel",
							"qty": 3,
							"uom": "Nos",
							"stock_uom": "Nos",
							"conversion_factor": 1,
							"warehouse": "Stores - QBC",
							"project": "PROJ-002",
							"cost_center": "Electrical - QBC",
						}
					),
					_FakeRow(
						{
							"idx": 3,
							"name": "pi-item-3",
							"item_code": "Transport",
							"item_name": "Transport",
							"description": "Transport",
							"qty": 1,
							"uom": "Nos",
							"stock_uom": "Nos",
							"conversion_factor": 1,
							"warehouse": "Stores - QBC",
							"project": None,
							"cost_center": None,
						}
					),
				],
			}
		)
		invoice.get_site_material_consumption_expense_account = (
			lambda _row, _project: "Cost Of Construction Projects - QBC"
		)

		def item_values(_doctype, item_code, *_args, **_kwargs):
			return frappe._dict(
				{
					"is_stock_item": 0 if item_code == "Transport" else 1,
					"disabled": 0,
				}
			)

		with patch(
			"construction_management.construction_management.overrides.purchase_invoice.frappe.db.get_value",
			side_effect=item_values,
		):
			rows = ConstructionPurchaseInvoice.get_site_material_consumption_rows(invoice)

		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0].project, "PROJ-001")
		self.assertEqual(rows[0].cost_center, "Civil Works - QBC")
		self.assertEqual(rows[1].project, "PROJ-002")
		self.assertEqual(rows[1].cost_center, "Electrical - QBC")
		self.assertEqual(rows[0].purchase_invoice, "PINV-TEST")
		self.assertEqual(rows[1].purchase_invoice_item, "pi-item-2")

	def test_accounting_only_return_fallback_does_not_match_smc_by_idx(self):
		invoice = _fake_purchase_invoice(return_against="ACC-PINV-2026-00076")
		original_values = frappe._dict(
			{
				"name": "3t2m9o014u",
				"idx": 30,
				"item_code": 'PVC TEE GREY 2" ATLAS',
				"project": "PROJ-0015",
				"cost_center": "Tools & Consumables - QBC",
				"warehouse": "Stores - QBC",
				"qty": 6,
				"uom": "Nos",
				"stock_uom": "Nos",
				"conversion_factor": 1,
			}
		)
		get_all_calls = []

		def get_meta(doctype):
			if doctype == "Purchase Invoice":
				return _FakeMeta({"site_material_consumption"})
			if doctype == "Site Material Consumption Item":
				return _FakeMeta({"purchase_invoice_item"})
			return _FakeMeta()

		def db_get_value(doctype, name, *args, **kwargs):
			if doctype == "Purchase Invoice":
				return "SMC-2026-0053"
			return None

		def get_all(doctype, filters=None, **kwargs):
			get_all_calls.append(filters)
			if filters.get("purchase_invoice_item") == "3t2m9o014u":
				return []
			if filters.get("item_code") == 'PVC TEE GREY 2" ATLAS':
				return [
					frappe._dict(
						{
							"name": "7tatv9oq55",
							"idx": 29,
							"item_code": 'PVC TEE GREY 2" ATLAS',
							"qty": 6,
							"uom": "Nos",
							"stock_uom": "Nos",
							"conversion_factor": 1,
							"expense_account": "Cost Of Construction Projects - QBC",
							"project": "PROJ-0015",
							"cost_center": "Tools & Consumables - QBC",
						}
					)
				]
			return []

		with (
			patch("construction_management.construction_management.overrides.purchase_invoice.frappe.get_meta", side_effect=get_meta),
			patch("construction_management.construction_management.overrides.purchase_invoice.frappe.db.get_value", side_effect=db_get_value),
			patch("construction_management.construction_management.overrides.purchase_invoice.frappe.db.exists", return_value=True),
			patch("construction_management.construction_management.overrides.purchase_invoice.frappe.get_all", side_effect=get_all),
		):
			account = ConstructionPurchaseInvoice.get_site_material_consumption_account_for_original_item(
				invoice,
				"3t2m9o014u",
				original_values=original_values,
			)

		self.assertEqual(account, "Cost Of Construction Projects - QBC")
		self.assertFalse(any(filters.get("idx") for filters in get_all_calls))

	def test_accounting_only_return_non_stock_row_uses_original_expense_account(self):
		invoice = _fake_purchase_invoice(return_against="ACC-PINV-2026-00076")
		item = _FakeRow(
			{
				"idx": 23,
				"item_code": "Transport Charges",
				"purchase_invoice_item": "3t2m4ikdj3",
			},
			fields={"original_consumption_account"},
		)

		with (
			patch.object(
				ConstructionPurchaseInvoice,
				"get_original_purchase_invoice_item_values",
				return_value=frappe._dict(
					{
						"name": "3t2m4ikdj3",
						"item_code": "Transport Charges",
						"expense_account": "Freight and Forwarding Charges - QBC",
					}
				),
			),
			patch.object(ConstructionPurchaseInvoice, "is_stock_item", return_value=False),
			patch.object(
				ConstructionPurchaseInvoice,
				"validate_accounting_only_return_expense_account",
				side_effect=lambda account, _item: account,
			) as validate_account,
			patch.object(ConstructionPurchaseInvoice, "get_site_material_consumption_account_for_original_item") as smc_lookup,
		):
			account = ConstructionPurchaseInvoice.get_original_consumption_account_for_return_item(
				invoice, item
			)

		self.assertEqual(account, "Freight and Forwarding Charges - QBC")
		validate_account.assert_called_once_with("Freight and Forwarding Charges - QBC", item)
		smc_lookup.assert_not_called()

	def test_accounting_only_return_ambiguous_smc_fallback_is_blocked(self):
		invoice = _fake_purchase_invoice()
		rows = [
			frappe._dict(idx=29, expense_account="Cost Of Construction Projects - QBC"),
			frappe._dict(idx=30, expense_account="Cost Of Other Jobs - QBC"),
		]

		with self.assertRaises(frappe.ValidationError):
			ConstructionPurchaseInvoice.get_unique_site_material_consumption_match(
				invoice,
				rows,
				"3t2m9o014u",
				match_context="test fallback",
			)
