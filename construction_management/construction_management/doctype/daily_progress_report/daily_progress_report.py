import frappe
from frappe import _
from frappe.model.document import Document

from construction_management.portal_utils import get_project_customer


class DailyProgressReport(Document):
	def validate(self):
		self._set_project_customer()
		self._set_defaults()
		self._validate_task_rows()

	def before_submit(self):
		self._set_project_customer()
		self.status = "Published" if self.publish_to_portal else "Submitted"

	def on_submit(self):
		status = "Published" if self.publish_to_portal else "Submitted"
		self.db_set("status", status, update_modified=False)

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)

	def _set_project_customer(self):
		if not self.project:
			frappe.throw(_("Project is required."))

		if not frappe.db.exists("Project", self.project):
			frappe.throw(_("Project {0} does not exist.").format(self.project))

		project_customer = get_project_customer(self.project)
		if self.customer and project_customer and self.customer != project_customer:
			frappe.throw(_("Customer must match the selected Project customer."))

		self.customer = project_customer

	def _set_defaults(self):
		if not self.prepared_by:
			self.prepared_by = frappe.session.user

		if not self.title:
			self.title = _("Daily Progress - {0} - {1}").format(
				self.project,
				self.dpr_date or "",
			)

		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			self.status = "Published" if self.publish_to_portal else "Submitted"

	def _validate_task_rows(self):
		for row in self.get("tasks_completed") or []:
			if row.task_title:
				continue

			has_other_values = any(
				row.get(fieldname)
				for fieldname in ("description", "quantity", "uom", "location", "notes", "photo")
			)
			if has_other_values:
				frappe.throw(_("Task Completed is required in row {0}.").format(row.idx))


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if _has_internal_access(user):
		return None

	try:
		from construction_management.portal_utils import get_customer_for_portal_user

		customer = get_customer_for_portal_user(user)
	except Exception:
		return "1 = 0"

	customer = frappe.db.escape(customer)
	return (
		f"`tabDaily Progress Report`.`customer` = {customer} "
		"AND `tabDaily Progress Report`.`docstatus` = 1 "
		"AND `tabDaily Progress Report`.`publish_to_portal` = 1"
	)


def has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if _has_internal_access(user):
		return True

	if doc.docstatus != 1 or not doc.publish_to_portal or doc.status == "Cancelled":
		return False

	try:
		from construction_management.portal_utils import get_customer_for_portal_user

		return doc.customer == get_customer_for_portal_user(user)
	except Exception:
		return False


def _has_internal_access(user):
	if user == "Administrator":
		return True

	roles = set(frappe.get_roles(user))
	return bool(
		roles
		& {
			"System Manager",
			"Construction Manager",
			"Projects Manager",
			"Projects User",
			"Accounts User",
		}
	)
