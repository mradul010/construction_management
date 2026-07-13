# Copyright (c) 2026, Vigisolvo Private Limited and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestBOQ(UnitTestCase):
	"""
	Integration tests for BOQ.
	Use this class for testing interactions between multiple components.
	"""

	def test_amount_is_base_cost_and_after_margin_is_selling_amount(self):
		boq = frappe.get_doc({
			"doctype": "BOQ",
			"currency": "AED",
			"built_up_area": 10,
			"items": [
				{
					"doctype": "BOQ Item",
					"qty": 2,
					"unit_cost": 100,
					"margin_percent": 25,
				},
			],
		})

		boq._calculate_totals()

		row = boq.items[0]
		self.assertAlmostEqual(row.unit_rate, 125)
		self.assertAlmostEqual(row.amount, 200)
		self.assertAlmostEqual(row.amount_after_margin, 250)
		self.assertAlmostEqual(boq.total_cost, 200)
		self.assertAlmostEqual(boq.grand_total, 250)
		self.assertAlmostEqual(boq.total_margin, 50)
		self.assertAlmostEqual(boq.margin_percent, 20)
		self.assertAlmostEqual(boq.rate_per_bua, 25)

	def test_cost_breakdown_matches_amount(self):
		boq = self._make_boq_with_cost_breakdown(1000)

		boq.validate_cost_breakdown_matches_amount()

	def test_cost_breakdown_rejects_unit_cost_total(self):
		boq = self._make_boq_with_cost_breakdown(100)

		with self.assertRaises(frappe.ValidationError):
			boq.validate_cost_breakdown_matches_amount()

	@patch("frappe.db.get_value")
	def test_sales_order_populates_empty_contract_fields(self, get_value):
		get_value.return_value = frappe._dict(
			name="SO-TEST",
			customer="CUSTOMER-TEST",
			project="PROJECT-TEST",
			company="COMPANY-TEST",
			currency="AED",
			docstatus=1,
			status="To Bill",
		)
		boq = frappe.get_doc({"doctype": "BOQ", "sales_order": "SO-TEST"})

		boq._sync_and_validate_sales_order()

		self.assertEqual(boq.client, "CUSTOMER-TEST")
		self.assertEqual(boq.project, "PROJECT-TEST")
		self.assertEqual(boq.company, "COMPANY-TEST")
		self.assertEqual(boq.currency, "AED")

	@patch("frappe.db.get_value")
	def test_sales_order_rejects_customer_mismatch(self, get_value):
		get_value.return_value = frappe._dict(
			name="SO-TEST",
			customer="CUSTOMER-TEST",
			project="PROJECT-TEST",
			company="COMPANY-TEST",
			currency="AED",
			docstatus=1,
			status="To Bill",
		)
		boq = frappe.get_doc(
			{"doctype": "BOQ", "sales_order": "SO-TEST", "client": "OTHER-CUSTOMER"}
		)

		with self.assertRaises(frappe.ValidationError):
			boq._sync_and_validate_sales_order()

	def _make_boq_with_cost_breakdown(self, breakdown_amount):
		boq = frappe.get_doc({
			"doctype": "BOQ",
			"currency": "AED",
			"items": [
				{
					"doctype": "BOQ Item",
					"component_key": "test-boq-item",
					"qty": 10,
					"unit_cost": 100,
					"margin_percent": 25,
				},
			],
			"cost_components": [
				{
					"doctype": "BOQ Cost Component",
					"boq_item": "test-boq-item",
					"component_type": "Labour",
					"description": "Labour",
					"amount": breakdown_amount,
				},
			],
		})
		boq._calculate_totals()
		return boq
