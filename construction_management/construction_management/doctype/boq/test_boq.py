# Copyright (c) 2026, Vigisolvo Private Limited and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.construction_management.doctype.boq.boq import (
	unlink_non_revision_duplicate_boqs,
)


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

	def test_boq_item_category_is_optional_for_totals(self):
		boq = frappe.get_doc({
			"doctype": "BOQ",
			"currency": "AED",
			"items": [
				{
					"doctype": "BOQ Item",
					"item_name": "Root Item",
					"qty": 2,
					"unit_cost": 100,
					"margin_percent": 10,
				},
				{
					"doctype": "BOQ Item",
					"item_name": "Category Item",
					"boq_category": "BOQ-CAT-TEST",
					"qty": 3,
					"unit_cost": 50,
					"margin_percent": 20,
				},
			],
		})

		boq._calculate_totals()

		self.assertAlmostEqual(boq.total_cost, 350)
		self.assertAlmostEqual(boq.grand_total, 400)

	@patch("frappe.db.get_value")
	def test_parent_category_is_cleared_for_root_items(self, get_value):
		boq = frappe.get_doc({
			"doctype": "BOQ",
			"items": [
				{
					"doctype": "BOQ Item",
					"item_name": "Root Item",
					"boq_parent_category": "Old Category",
					"qty": 1,
					"unit_cost": 100,
				},
			],
		})

		boq._fill_parent_categories()

		get_value.assert_not_called()
		self.assertEqual(boq.items[0].boq_parent_category, "")

	@patch("frappe.db.get_value")
	def test_parent_category_supports_direct_category_items(self, get_value):
		def category_value(doctype, name, fieldname):
			values = {
				("BOQ-CAT-TEST", "parent_node"): None,
				("BOQ-CAT-TEST", "category_name"): "Civil Work",
			}
			return values.get((name, fieldname))

		get_value.side_effect = category_value
		boq = frappe.get_doc({
			"doctype": "BOQ",
			"items": [
				{
					"doctype": "BOQ Item",
					"item_name": "Category Item",
					"boq_category": "BOQ-CAT-TEST",
					"qty": 1,
					"unit_cost": 100,
				},
			],
		})

		boq._fill_parent_categories()

		self.assertEqual(boq.items[0].boq_parent_category, "Civil Work")

	def test_standard_duplicate_is_decoupled_from_source_boq(self):
		boq = frappe.get_doc(
			{
				"doctype": "BOQ",
				"original_boq": "BOQ-SOURCE",
				"parent_boq": "BOQ-SOURCE",
				"superseded_by": "BOQ-NEXT",
				"is_revision": 1,
				"is_active_revision": 1,
				"revision_no": 3,
				"revision_status": "Active",
				"status": "Active",
				"active_from_date": "2026-09-04",
				"active_to_date": "2026-09-05",
			}
		)

		boq._sanitize_standard_duplicate_references()

		self.assertIsNone(boq.original_boq)
		self.assertIsNone(boq.parent_boq)
		self.assertIsNone(boq.superseded_by)
		self.assertEqual(boq.is_revision, 0)
		self.assertEqual(boq.is_active_revision, 0)
		self.assertEqual(boq.revision_no, 0)
		self.assertEqual(boq.revision_status, "Draft")
		self.assertEqual(boq.status, "Draft")
		self.assertIsNone(boq.active_from_date)
		self.assertIsNone(boq.active_to_date)

	def test_revision_copy_keeps_revision_links(self):
		boq = frappe.get_doc(
			{
				"doctype": "BOQ",
				"original_boq": "BOQ-SOURCE",
				"parent_boq": "BOQ-PARENT",
				"is_revision": 1,
				"revision_no": 3,
			}
		)
		boq.flags.from_boq_revision = True

		boq._sanitize_standard_duplicate_references()

		self.assertEqual(boq.original_boq, "BOQ-SOURCE")
		self.assertEqual(boq.parent_boq, "BOQ-PARENT")
		self.assertEqual(boq.is_revision, 1)
		self.assertEqual(boq.revision_no, 3)

	@patch("frappe.clear_cache")
	@patch("frappe.db.set_value")
	@patch("frappe.db.sql")
	def test_unlink_non_revision_duplicate_boqs_keeps_real_revisions(
		self, db_sql, set_value, clear_cache
	):
		db_sql.return_value = ["BOQ-DUPLICATE"]

		unlink_non_revision_duplicate_boqs("BOQ-SOURCE")

		query, params = db_sql.call_args[0]
		self.assertIn("original_boq = %(source_boq)s", query)
		self.assertIn("COALESCE(is_revision, 0) = 0", query)
		self.assertIn("parent_boq IS NULL OR parent_boq = ''", query)
		self.assertEqual(params["source_boq"], "BOQ-SOURCE")
		self.assertTrue(db_sql.call_args.kwargs["pluck"])
		set_value.assert_called_once_with(
			"BOQ",
			"BOQ-DUPLICATE",
			{
				"original_boq": "BOQ-DUPLICATE",
				"parent_boq": None,
				"superseded_by": None,
				"is_revision": 0,
				"is_active_revision": 0,
			},
			update_modified=False,
		)
		clear_cache.assert_called_once_with(doctype="BOQ")

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
