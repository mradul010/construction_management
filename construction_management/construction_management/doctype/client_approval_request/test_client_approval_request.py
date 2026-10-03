import frappe
from frappe.tests import UnitTestCase

from construction_management.portal_utils import (
	is_client_approval_visible,
	normalize_client_approval_status_filter,
	sort_client_approvals,
)


class TestClientApprovalRequest(UnitTestCase):
	def test_visibility_requires_public_non_draft_request(self):
		visible = frappe._dict({"publish_to_client_portal": 1, "status": "Pending"})
		self.assertTrue(is_client_approval_visible(visible, reference_date="2026-10-03"))

		unpublished = frappe._dict({"publish_to_client_portal": 0, "status": "Pending"})
		self.assertFalse(is_client_approval_visible(unpublished, reference_date="2026-10-03"))

		draft = frappe._dict({"publish_to_client_portal": 1, "status": "Draft"})
		self.assertFalse(is_client_approval_visible(draft, reference_date="2026-10-03"))

		cancelled = frappe._dict({"publish_to_client_portal": 1, "status": "Cancelled"})
		self.assertFalse(is_client_approval_visible(cancelled, reference_date="2026-10-03"))

	def test_visibility_window(self):
		future = frappe._dict({"publish_to_client_portal": 1, "status": "Pending", "visible_from": "2026-10-04"})
		self.assertFalse(is_client_approval_visible(future, reference_date="2026-10-03"))

		expired = frappe._dict({"publish_to_client_portal": 1, "status": "Pending", "visible_until": "2026-10-02"})
		self.assertFalse(is_client_approval_visible(expired, reference_date="2026-10-03"))

	def test_normalize_status_filter(self):
		self.assertEqual(normalize_client_approval_status_filter(None), "Pending")
		self.assertEqual(normalize_client_approval_status_filter("Approved"), "Approved")
		self.assertEqual(normalize_client_approval_status_filter("Unexpected"), "Pending")

	def test_pending_requests_sort_before_history(self):
		rows = [
			frappe._dict({"status": "Rejected", "response_on": "2026-10-03"}),
			frappe._dict({"status": "Pending", "due_date": "2026-10-05"}),
			frappe._dict({"status": "Approved", "response_on": "2026-10-02"}),
		]
		sorted_rows = sort_client_approvals(rows)
		self.assertEqual(sorted_rows[0].status, "Pending")
