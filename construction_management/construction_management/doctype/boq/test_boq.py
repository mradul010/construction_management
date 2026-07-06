# Copyright (c) 2026, Vigisolvo Private Limited and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestBOQ(IntegrationTestCase):
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
