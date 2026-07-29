from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from construction_management.design_management.design_management import (
	DrawingRevision,
	get_next_revision_number,
	validate_design_references,
)


class TestDrawingRevision(UnitTestCase):
	def test_ifc_status_sets_ifc_flags(self):
		revision = DrawingRevision(
			{
				"doctype": "Drawing Revision",
				"drawing": "DRAW-TEST",
				"revision_number": "REV0",
				"revision_date": "2026-07-24",
				"status": "Issued For Construction",
			}
		)

		revision._validate_ifc_status()

		self.assertEqual(revision.ifc, 1)
		self.assertTrue(revision.ifc_date)

	def test_cancelled_status_clears_ifc_flags(self):
		revision = DrawingRevision(
			{
				"doctype": "Drawing Revision",
				"drawing": "DRAW-TEST",
				"revision_number": "REV0",
				"revision_date": "2026-07-24",
				"status": "Cancelled",
				"ifc": 1,
				"ifc_date": "2026-07-24",
			}
		)

		revision._validate_ifc_status()

		self.assertEqual(revision.ifc, 0)
		self.assertIsNone(revision.ifc_date)

	@patch("frappe.db.get_value")
	def test_execution_reference_rejects_non_ifc_revision(self, get_value):
		get_value.side_effect = ["DRAW-TEST", ("Approved", 0)]
		doc = frappe.get_doc(
			{
				"doctype": "BOQ",
				"items": [
					{
						"doctype": "BOQ Item",
						"drawing": "DRAW-TEST",
						"drawing_revision": "DREV-TEST",
					}
				],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			validate_design_references(doc)

	@patch("frappe.db.get_value")
	def test_execution_reference_accepts_ifc_revision(self, get_value):
		get_value.side_effect = ["DRAW-TEST", ("Issued For Construction", 1)]
		doc = frappe.get_doc(
			{
				"doctype": "BOQ",
				"items": [
					{
						"doctype": "BOQ Item",
						"drawing": "DRAW-TEST",
						"drawing_revision": "DREV-TEST",
					}
				],
			}
		)

		validate_design_references(doc)

		self.assertEqual(doc.items[0].ifc_revision, "DREV-TEST")

	@patch("frappe.get_all")
	def test_next_revision_number_increments_latest_suffix(self, get_all):
		get_all.return_value = ["REV0", "REV1", "REV9"]

		self.assertEqual(get_next_revision_number("DRAW-TEST"), "REV10")
