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
