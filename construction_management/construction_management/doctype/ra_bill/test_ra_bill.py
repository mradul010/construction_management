# Copyright (c) 2026, Vigisolvo Private Limited and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.construction_management.overrides.sales_invoice import (
	apply_ra_bill_deduction_taxes_to_sales_invoice,
	get_ra_bill_vat_config,
	validate_ra_bill_advance_recovery_balance,
)
from construction_management.construction_management.doctype.ra_bill.ra_bill import (
	calculate_ra_bill_taxes,
)
from construction_management.construction_management.ra_bill_dates import (
	apply_ra_bill_dates_to_sales_invoice,
	set_default_ra_bill_invoice_dates,
	validate_ra_bill_invoice_dates,
)
from construction_management.construction_management.advance_management import (
	get_ra_bill_advance_recovery_target,
	update_ra_bill_advance_fields,
)


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class _FakeMeta:
	def has_field(self, fieldname):
		return True


class _FakeRow(frappe._dict):
	meta = _FakeMeta()

	def as_dict(self):
		return dict(self)


class _FakeDoc(frappe._dict):
	meta = _FakeMeta()

	def is_new(self):
		return bool(self.get("__islocal"))

	def set(self, fieldname, value):
		self[fieldname] = value

	def append(self, fieldname, value):
		row = _FakeRow(value)
		row.idx = len(self.setdefault(fieldname, [])) + 1
		self[fieldname].append(row)
		return row


def _fake_sales_invoice():
	return _FakeDoc(
		{
			"doctype": "Sales Invoice",
			"company": "QBC",
			"customer": "CUSTOMER-TEST",
			"project": "PROJECT-TEST",
			"cost_center": "Main - QBC",
			"posting_date": "2026-08-12",
			"taxes": [],
			"advances": [_FakeRow({"allocated_amount": 990})],
			"items": [
				_FakeRow(
					{
						"item_code": "RA Bill Services",
						"item_tax_template": "VAT Template",
						"item_tax_rate": '{"VAT 5% - QBC": 5}',
					}
				)
			],
		}
	)


def _fake_ra_bill(**values):
	defaults = {
		"name": "RA-BILL-TEST",
		"customer": "CUSTOMER-TEST",
		"project": "PROJECT-TEST",
		"retention_amount": 990,
		"tax_category": None,
		"sales_taxes_and_charges_template": None,
		"taxes": [],
	}
	defaults.update(values)
	return _FakeDoc(defaults)


def _fake_advance_sources():
	return [
		frappe._dict(
			{
				"reference_type": "Journal Entry",
				"reference_name": "JE-TEST",
				"advance_amount": 1000,
				"remarks": "Journal advance",
				"difference_posting_date": "2026-08-12",
			}
		),
		frappe._dict(
			{
				"reference_type": "Payment Entry",
				"reference_name": "PE-TEST",
				"advance_amount": 1000,
				"remarks": "Payment advance",
				"difference_posting_date": "2026-08-12",
			}
		),
	]


class IntegrationTestRABill(UnitTestCase):
	"""
	Integration tests for RABill.
	Use this class for testing interactions between multiple components.
	"""

	def test_boq_populates_sales_order_and_contract_fields(self):
		ra_bill = frappe.get_doc({"doctype": "RA Bill", "boq": "BOQ-TEST"})

		def get_value(doctype, *args, **kwargs):
			if doctype == "BOQ":
				return frappe._dict(
				name="BOQ-TEST",
					project="PROJECT-TEST",
					client="CUSTOMER-TEST",
					company="COMPANY-TEST",
					currency="AED",
				sales_order="SO-TEST",
				)
			if doctype == "Sales Order":
				return frappe._dict(
					customer="CUSTOMER-TEST",
					project="PROJECT-TEST",
					company="COMPANY-TEST",
					currency="AED",
				)
			return None

		with patch("frappe.db.get_value", side_effect=get_value):
			ra_bill._sync_and_validate_boq_contract()

		self.assertEqual(ra_bill.sales_order, "SO-TEST")
		self.assertEqual(ra_bill.project, "PROJECT-TEST")
		self.assertEqual(ra_bill.customer, "CUSTOMER-TEST")
		self.assertEqual(ra_bill.currency, "AED")

	def test_rejects_sales_order_mismatch(self):
		boq = frappe._dict(
			name="BOQ-TEST",
			project="PROJECT-TEST",
			client="CUSTOMER-TEST",
			company="COMPANY-TEST",
			currency="AED",
			sales_order="SO-TEST",
		)
		ra_bill = frappe.get_doc(
			{"doctype": "RA Bill", "boq": "BOQ-TEST", "sales_order": "SO-OTHER"}
		)

		with patch("frappe.db.get_value", return_value=boq):
			with self.assertRaises(frappe.ValidationError):
				ra_bill._sync_and_validate_boq_contract()

	def test_amended_ra_bill_clears_generated_invoice_state_before_link_validation(self):
		ra_bill = frappe.get_doc(
			{
				"doctype": "RA Bill",
				"amended_from": "RA-BILL-OLD",
				"sales_invoice": "ACC-SINV-CANCELLED",
				"status": "Invoiced",
			}
		)

		with patch("frappe.model.document.Document._validate_links") as validate_links:
			ra_bill._validate_links()

		validate_links.assert_called_once()
		self.assertIsNone(ra_bill.sales_invoice)
		self.assertEqual(ra_bill.status, "Draft")

	def test_ra_bill_invoice_deduction_tax_rows_are_ordered_before_vat(self):
		si = _fake_sales_invoice()
		ra_bill = _fake_ra_bill()

		def account_for(_company, account_key, **_kwargs):
			return {
				"retention_receivable": "Retention Receivable - QBC",
				"customer_advance": "Customer Advances - QBC",
			}[account_key]

		with (
			patch(
				"construction_management.construction_management.overrides.sales_invoice.get_construction_account",
				side_effect=account_for,
			),
			patch(
				"construction_management.construction_management.overrides.sales_invoice.get_ra_bill_project_cost_center",
				return_value="Main - QBC",
			),
			patch(
				"construction_management.construction_management.overrides.sales_invoice.get_ra_bill_vat_config",
				return_value=frappe._dict(
					{
						"account_head": "VAT 5% - QBC",
						"description": "VAT 5%",
						"rate": 5,
					}
				),
			),
		):
			apply_ra_bill_deduction_taxes_to_sales_invoice(si, ra_bill, advance_native=990)

		self.assertEqual([row.description for row in si.taxes], ["Retention Deduction", "Advance Recovery", "VAT 5%"])
		self.assertEqual(si.taxes[0].charge_type, "Actual")
		self.assertEqual(si.taxes[0].tax_amount, -990)
		self.assertEqual(si.taxes[0].account_head, "Retention Receivable - QBC")
		self.assertEqual(si.taxes[1].charge_type, "Actual")
		self.assertEqual(si.taxes[1].tax_amount, -990)
		self.assertEqual(si.taxes[1].account_head, "Customer Advances - QBC")
		self.assertEqual(si.taxes[2].charge_type, "On Previous Row Total")
		self.assertEqual(si.taxes[2].row_id, 2)
		self.assertEqual(si.taxes[2].rate, 5)
		self.assertEqual(si.advances, [])
		self.assertIsNone(si["items"][0].item_tax_template)
		self.assertEqual(si["items"][0].item_tax_rate, "{}")

	def test_ra_bill_invoice_vat_uses_net_total_when_there_are_no_deductions(self):
		si = _fake_sales_invoice()
		ra_bill = _fake_ra_bill(retention_amount=0)

		with (
			patch(
				"construction_management.construction_management.overrides.sales_invoice.get_ra_bill_project_cost_center",
				return_value="Main - QBC",
			),
			patch(
				"construction_management.construction_management.overrides.sales_invoice.get_ra_bill_vat_config",
				return_value=frappe._dict(
					{
						"account_head": "VAT 5% - QBC",
						"description": "VAT 5%",
						"rate": 5,
					}
				),
			),
		):
			apply_ra_bill_deduction_taxes_to_sales_invoice(si, ra_bill, advance_native=0)

		self.assertEqual(len(si.taxes), 1)
		self.assertEqual(si.taxes[0].charge_type, "On Net Total")
		self.assertFalse(si.taxes[0].get("row_id"))

	def test_zero_rated_or_exempt_ra_bill_without_template_does_not_add_vat(self):
		si = _fake_sales_invoice()
		ra_bill = _fake_ra_bill(retention_amount=0, tax_category="Zero Rated")

		with (
			patch(
				"construction_management.construction_management.overrides.sales_invoice.get_taxes_and_charges",
				return_value=[],
			),
			patch(
				"construction_management.construction_management.overrides.sales_invoice.frappe.db.get_value",
				return_value=None,
			),
		):
			self.assertIsNone(get_ra_bill_vat_config(si, ra_bill))

	def test_ra_bill_advance_recovery_validates_against_remaining_sales_order_balance(self):
		si = _fake_sales_invoice()
		si.sales_order = "SO-TEST"
		si.name = "SI-TEST"

		with patch(
			"construction_management.construction_management.advance_management.get_sales_order_advance_summary",
			return_value=frappe._dict(
				{
					"sales_order": "SO-TEST",
					"total_advance_received": 2000,
					"total_advance_recovered": 0,
					"remaining_advance_balance": 2000,
				}
			),
		):
			validate_ra_bill_advance_recovery_balance(si, 2000)
			with self.assertRaises(frappe.ValidationError):
				validate_ra_bill_advance_recovery_balance(si, 2000.01)

	def test_ra_bill_advance_recovery_percent_uses_gross_amount_and_caps_actual(self):
		ra_bill = _fake_ra_bill(
			name="RA-BILL-TEST",
			sales_order="SO-TEST",
			gross_amount=68800,
			grand_total=68800,
			advance_recovery_percent=10,
			advances=[
				_FakeRow({"idx": 1, "advance_amount": 1000, "allocated_amount": 1000}),
				_FakeRow({"idx": 2, "advance_amount": 1000, "allocated_amount": 1000}),
			],
		)

		with (
			patch(
				"construction_management.construction_management.advance_management.get_ra_bill_sales_order",
				return_value="SO-TEST",
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_summary",
				return_value=frappe._dict(
					{
						"sales_order": "SO-TEST",
						"total_advance_received": 2000,
						"total_advance_recovered": 0,
						"remaining_advance_balance": 2000,
					}
				),
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_reference_rows",
				return_value=_fake_advance_sources(),
			),
		):
			values = update_ra_bill_advance_fields(ra_bill)

		self.assertEqual(values.proposed_advance_recovery, 6880)
		self.assertEqual(values.actual_advance_recovered, 2000)
		self.assertEqual(values.remaining_advance_after_current_bill, 0)
		self.assertEqual([row.allocated_amount for row in ra_bill.advances], [1000, 1000])

	def test_ra_bill_advance_recovery_percent_recovers_calculated_amount_when_advance_is_available(self):
		ra_bill = _fake_ra_bill(
			name="RA-BILL-TEST",
			sales_order="SO-TEST",
			gross_amount=10000,
			grand_total=10000,
			advance_recovery_percent=10,
			advances=[
				_FakeRow({"idx": 1, "advance_amount": 1000, "allocated_amount": 1000}),
				_FakeRow({"idx": 2, "advance_amount": 1000, "allocated_amount": 1000}),
			],
		)

		with (
			patch(
				"construction_management.construction_management.advance_management.get_ra_bill_sales_order",
				return_value="SO-TEST",
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_summary",
				return_value=frappe._dict(
					{
						"sales_order": "SO-TEST",
						"total_advance_received": 5000,
						"total_advance_recovered": 0,
						"remaining_advance_balance": 5000,
					}
				),
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_reference_rows",
				return_value=_fake_advance_sources(),
			),
		):
			values = update_ra_bill_advance_fields(ra_bill)

		self.assertEqual(values.proposed_advance_recovery, 1000)
		self.assertEqual(values.actual_advance_recovered, 1000)
		self.assertEqual(values.remaining_advance_after_current_bill, 4000)
		self.assertEqual([row.allocated_amount for row in ra_bill.advances], [1000, 0])

	def test_ra_bill_advance_recovery_percent_caps_actual_by_remaining_balance(self):
		ra_bill = _fake_ra_bill(
			name="RA-BILL-TEST",
			sales_order="SO-TEST",
			gross_amount=68800,
			grand_total=68800,
			advance_recovery_percent=10,
			advances=[_FakeRow({"idx": 1, "advance_amount": 1000, "allocated_amount": 1000})],
		)

		with (
			patch(
				"construction_management.construction_management.advance_management.get_ra_bill_sales_order",
				return_value="SO-TEST",
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_summary",
				return_value=frappe._dict(
					{
						"sales_order": "SO-TEST",
						"total_advance_received": 2000,
						"total_advance_recovered": 1850,
						"remaining_advance_balance": 150,
					}
				),
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_reference_rows",
				return_value=_fake_advance_sources(),
			),
		):
			values = update_ra_bill_advance_fields(ra_bill)

		self.assertEqual(values.proposed_advance_recovery, 6880)
		self.assertEqual(values.actual_advance_recovered, 150)
		self.assertEqual(values.remaining_advance_after_current_bill, 0)
		self.assertEqual([row.allocated_amount for row in ra_bill.advances], [0, 150])

	def test_ra_bill_advance_recovery_percent_uses_zero_when_no_remaining_balance(self):
		ra_bill = _fake_ra_bill(
			name="RA-BILL-TEST",
			sales_order="SO-TEST",
			gross_amount=68800,
			grand_total=68800,
			advance_recovery_percent=10,
			advances=[_FakeRow({"idx": 1, "advance_amount": 1000, "allocated_amount": 1000})],
		)

		with (
			patch(
				"construction_management.construction_management.advance_management.get_ra_bill_sales_order",
				return_value="SO-TEST",
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_summary",
				return_value=frappe._dict(
					{
						"sales_order": "SO-TEST",
						"total_advance_received": 2000,
						"total_advance_recovered": 2000,
						"remaining_advance_balance": 0,
					}
				),
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_reference_rows",
				return_value=_fake_advance_sources(),
			),
		):
			values = update_ra_bill_advance_fields(ra_bill)

		self.assertEqual(values.proposed_advance_recovery, 6880)
		self.assertEqual(values.actual_advance_recovered, 0)
		self.assertEqual(values.remaining_advance_after_current_bill, 0)
		self.assertEqual([row.allocated_amount for row in ra_bill.advances], [0, 0])

		with patch(
			"construction_management.construction_management.advance_management.update_ra_bill_advance_fields",
			return_value=values,
		):
			self.assertEqual(get_ra_bill_advance_recovery_target(ra_bill), 0)

	def test_ra_bill_advance_recovery_percent_zero_and_full_recovery(self):
		ra_bill = _fake_ra_bill(
			name="RA-BILL-TEST",
			sales_order="SO-TEST",
			gross_amount=68800,
			grand_total=68800,
			advance_recovery_percent=0,
			advances=[_FakeRow({"idx": 1, "advance_amount": 1000, "allocated_amount": 0})],
		)

		def summary(_sales_order, **_kwargs):
			return frappe._dict(
				{
					"sales_order": "SO-TEST",
					"total_advance_received": 2000,
					"total_advance_recovered": 0,
					"remaining_advance_balance": 2000,
				}
			)

		with (
			patch(
				"construction_management.construction_management.advance_management.get_ra_bill_sales_order",
				return_value="SO-TEST",
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_summary",
				side_effect=summary,
			),
			patch(
				"construction_management.construction_management.advance_management.get_sales_order_advance_reference_rows",
				return_value=_fake_advance_sources(),
			),
		):
			values = update_ra_bill_advance_fields(ra_bill)
			self.assertEqual(values.actual_advance_recovered, 0)

			ra_bill.advance_recovery_percent = 100
			values = update_ra_bill_advance_fields(ra_bill)
			self.assertEqual(values.proposed_advance_recovery, 68800)
			self.assertEqual(values.actual_advance_recovered, 2000)
			self.assertEqual(values.remaining_advance_after_current_bill, 0)
			self.assertEqual([row.allocated_amount for row in ra_bill.advances], [1000, 1000])

	def test_ra_bill_tax_calculation_keeps_negative_actual_amount(self):
		ra_bill = _fake_ra_bill(
			gross_amount=10000,
			taxes=[
				_FakeRow(
					{
						"idx": 1,
						"charge_type": "Actual",
						"tax_amount": -1000,
					}
				)
			],
		)

		calculate_ra_bill_taxes(ra_bill)

		self.assertEqual(ra_bill.net_total, 10000)
		self.assertEqual(ra_bill.taxes[0].tax_amount, -1000)
		self.assertEqual(ra_bill.taxes[0].total, 9000)
		self.assertEqual(ra_bill.total_taxes_and_charges, -1000)
		self.assertEqual(ra_bill.grand_total, 9000)

	def test_ra_bill_tax_calculation_supports_previous_row_total(self):
		ra_bill = _fake_ra_bill(
			gross_amount=10000,
			taxes=[
				_FakeRow(
					{
						"idx": 1,
						"charge_type": "Actual",
						"tax_amount": -1000,
					}
				),
				_FakeRow(
					{
						"idx": 2,
						"charge_type": "Actual",
						"tax_amount": -1000,
					}
				),
				_FakeRow(
					{
						"idx": 3,
						"charge_type": "On Previous Row Total",
						"row_id": 2,
						"rate": 5,
					}
				),
			],
		)

		calculate_ra_bill_taxes(ra_bill)

		self.assertEqual(ra_bill.taxes[0].total, 9000)
		self.assertEqual(ra_bill.taxes[1].total, 8000)
		self.assertEqual(ra_bill.taxes[2].tax_amount, 400)
		self.assertEqual(ra_bill.taxes[2].total, 8400)
		self.assertEqual(ra_bill.total_taxes_and_charges, -1600)
		self.assertEqual(ra_bill.grand_total, 8400)

	def test_adjustment_row_reduces_cumulative_progress(self):
		ra_bill = frappe.get_doc(
			{
				"doctype": "RA Bill",
				"boq": "BOQ-TEST",
				"items": [
					{
						"boq_item": "BOQ-ITEM-TEST",
						"item_name": "Site Management and Supervision",
						"boq_qty": 100,
						"boq_rate": 900,
						"progress_type": "Adjustment",
						"work_percent": -50,
					}
				],
			}
		)

		with patch(
			"construction_management.construction_management.doctype.ra_bill.ra_bill._get_boq_item_billing_summary",
			return_value={
				"previous_qty": 100,
				"previous_percent": 100,
				"remaining_qty": 0,
				"remaining_percent": 0,
			},
		):
			ra_bill.validate_item_values()
			ra_bill._calculate_row_totals()
			ra_bill._validate_not_overbilling()

		row = ra_bill.items[0]
		self.assertEqual(row.current_qty, -50)
		self.assertEqual(row.current_amount, -45000)
		self.assertEqual(row.cumulative_qty, 50)

	def test_progress_after_adjustment_uses_corrected_baseline(self):
		ra_bill = frappe.get_doc(
			{
				"doctype": "RA Bill",
				"boq": "BOQ-TEST",
				"items": [
					{
						"boq_item": "BOQ-ITEM-TEST",
						"item_name": "Site Management and Supervision",
						"boq_qty": 100,
						"boq_rate": 900,
						"progress_type": "Progress",
						"work_percent": 10,
					}
				],
			}
		)

		with patch(
			"construction_management.construction_management.doctype.ra_bill.ra_bill._get_boq_item_billing_summary",
			return_value={
				"previous_qty": 50,
				"previous_percent": 50,
				"remaining_qty": 50,
				"remaining_percent": 50,
			},
		):
			ra_bill.validate_item_values()
			ra_bill._calculate_row_totals()
			ra_bill._validate_not_overbilling()

		row = ra_bill.items[0]
		self.assertEqual(row.current_qty, 10)
		self.assertEqual(row.current_amount, 9000)
		self.assertEqual(row.cumulative_qty, 60)

	def test_adjustment_row_cannot_reduce_cumulative_below_zero(self):
		ra_bill = frappe.get_doc(
			{
				"doctype": "RA Bill",
				"boq": "BOQ-TEST",
				"items": [
					{
						"boq_item": "BOQ-ITEM-TEST",
						"item_name": "Site Management and Supervision",
						"boq_qty": 100,
						"boq_rate": 900,
						"progress_type": "Adjustment",
						"work_percent": -40,
					}
				],
			}
		)

		with patch(
			"construction_management.construction_management.doctype.ra_bill.ra_bill._get_boq_item_billing_summary",
			return_value={
				"previous_qty": 30,
				"previous_percent": 30,
				"remaining_qty": 70,
				"remaining_percent": 70,
			},
		):
			ra_bill.validate_item_values()
			ra_bill._calculate_row_totals()
			with self.assertRaises(frappe.ValidationError):
				ra_bill._validate_not_overbilling()

	def test_cancelled_ra_bill_delete_clears_cancelled_sales_invoice_back_reference(self):
		ra_bill = frappe.get_doc(
			{
				"doctype": "RA Bill",
				"name": "RA-BILL-CANCELLED",
				"docstatus": 2,
				"sales_invoice": "SI-CANCELLED",
			}
		)

		with (
			patch(
				"frappe.db.get_value",
				return_value=frappe._dict(
					{
						"name": "SI-CANCELLED",
						"docstatus": 2,
						"ra_bill": "RA-BILL-CANCELLED",
					}
				),
			),
			patch("frappe.db.set_value") as set_value,
		):
			ra_bill.on_trash()

		set_value.assert_called_once_with(
			"Sales Invoice",
			"SI-CANCELLED",
			"ra_bill",
			None,
			update_modified=False,
		)

	def test_cancelled_ra_bill_delete_blocks_active_sales_invoice_unlink(self):
		ra_bill = frappe.get_doc(
			{
				"doctype": "RA Bill",
				"name": "RA-BILL-CANCELLED",
				"docstatus": 2,
				"sales_invoice": "SI-SUBMITTED",
			}
		)

		with patch(
			"frappe.db.get_value",
			return_value=frappe._dict(
				{
					"name": "SI-SUBMITTED",
					"docstatus": 1,
					"ra_bill": "RA-BILL-CANCELLED",
				}
			),
		):
			with self.assertRaises(frappe.ValidationError):
				ra_bill.on_trash()

	def test_cancelled_sales_invoice_delete_clears_cancelled_ra_bill_reference(self):
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"name": "SI-CANCELLED",
				"docstatus": 2,
				"ra_bill": "RA-BILL-CANCELLED",
			}
		)

		with (
			patch(
				"frappe.db.get_value",
				return_value=frappe._dict(
					{
						"name": "RA-BILL-CANCELLED",
						"docstatus": 2,
						"sales_invoice": "SI-CANCELLED",
					}
				),
			),
			patch("frappe.db.set_value") as set_value,
		):
			invoice.unlink_cancelled_ra_bill_for_delete()

		set_value.assert_called_once_with(
			"RA Bill",
			"RA-BILL-CANCELLED",
			"sales_invoice",
			None,
			update_modified=False,
		)

	def test_cancelled_sales_invoice_delete_blocks_active_ra_bill_unlink(self):
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"name": "SI-CANCELLED",
				"docstatus": 2,
				"ra_bill": "RA-BILL-SUBMITTED",
			}
		)

		with patch(
			"frappe.db.get_value",
			return_value=frappe._dict(
				{
					"name": "RA-BILL-SUBMITTED",
					"docstatus": 1,
					"sales_invoice": "SI-CANCELLED",
				}
			),
		):
			with self.assertRaises(frappe.ValidationError):
				invoice.unlink_cancelled_ra_bill_for_delete()

	def test_ra_bill_invoice_date_defaults_use_billing_period_and_schedule(self):
		ra_bill = _fake_ra_bill(
			billing_period_to="2026-05-31",
			payment_schedule=[_FakeRow({"due_date": "2026-06-30"})],
		)

		with patch(
			"construction_management.construction_management.ra_bill_dates.get_customer_due_date",
			return_value=None,
		):
			set_default_ra_bill_invoice_dates(ra_bill)

		self.assertEqual(ra_bill.posting_date, "2026-05-31")
		self.assertEqual(ra_bill.due_date, "2026-06-30")

	def test_ra_bill_rejects_due_date_before_posting_date(self):
		ra_bill = _fake_ra_bill(
			posting_date="2026-06-01",
			due_date="2026-05-31",
		)

		with self.assertRaises(frappe.ValidationError):
			validate_ra_bill_invoice_dates(ra_bill)

	def test_ra_bill_dates_are_applied_to_sales_invoice_and_schedule(self):
		si = _fake_sales_invoice()
		si.payment_schedule = [_FakeRow({"due_date": "2026-09-30", "invoice_portion": 100})]
		ra_bill = _fake_ra_bill(
			posting_date="2026-05-31",
			due_date="2026-06-30",
		)

		apply_ra_bill_dates_to_sales_invoice(si, ra_bill)

		self.assertEqual(si.posting_date, "2026-05-31")
		self.assertEqual(si.due_date, "2026-06-30")
		self.assertEqual(si.payment_schedule[0].due_date, "2026-06-30")
		self.assertEqual(si.set_posting_time, 1)
