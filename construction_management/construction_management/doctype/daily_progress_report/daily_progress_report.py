import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from construction_management.portal_utils import get_project_customer

WORKER_FIELDS = (
	"fitter",
	"welder",
	"gas_cutter",
	"rigger",
	"grinder",
	"helper",
	"khalasi",
	"electrician",
	"foreman",
)


class DailyProgressReport(Document):
	def validate(self):
		self._set_project_customer()
		self._set_defaults()
		self._update_task_rows()
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
			if row.todays_work_activity:
				pass

			has_other_values = any(
				row.get(fieldname)
				for fieldname in (
					"work_location",
					"todays_work_activity",
					"target_mark_no",
					"work_completed",
					"completed_mark_no",
					"remarks_constraints",
					"description",
					"quantity",
					"uom",
					"location",
					"notes",
					"photo",
					"contractor",
					"gang_name",
					"mark_no",
					"target_quantity",
					"completed_quantity",
				)
			)
			if not row.todays_work_activity and has_other_values:
				frappe.throw(_("Task Completed is required in row {0}.").format(row.idx))

			row_label = _("Row {0}").format(row.idx)
			for fieldname in WORKER_FIELDS:
				if cint(row.get(fieldname)) < 0:
					frappe.throw(_("{0}: {1} cannot be negative.").format(row_label, frappe.unscrub(fieldname)))

			if flt(row.target_quantity) < 0:
				frappe.throw(_("{0}: Target Quantity cannot be negative.").format(row_label))
			if flt(row.completed_quantity) < 0:
				frappe.throw(_("{0}: Completed Quantity cannot be negative.").format(row_label))
			if flt(row.completed_quantity) > flt(row.target_quantity):
				frappe.throw(_("{0}: Completed Quantity cannot exceed Target Quantity.").format(row_label))

	def _update_task_rows(self):
		for row in self.get("tasks_completed") or []:
			if not row.work_location and row.location:
				row.work_location = row.location
			if not row.todays_work_activity and row.task_title:
				row.todays_work_activity = row.task_title
			if not row.work_completed and row.description:
				row.work_completed = row.description
			if not row.remarks_constraints and row.notes:
				row.remarks_constraints = row.notes
			if not row.target_mark_no:
				row.target_mark_no = (row.mark_no or row.item_code or row.item_name or "").strip()
			if not row.completed_mark_no:
				row.completed_mark_no = (row.mark_no or row.item_code or row.item_name or "").strip()

			if flt(row.quantity) and not flt(row.target_quantity) and not flt(row.completed_quantity):
				row.target_quantity = flt(row.quantity)
				row.completed_quantity = flt(row.quantity)

			row.total_workers = sum(cint(row.get(fieldname)) for fieldname in WORKER_FIELDS)
			row.balance_quantity = flt(row.target_quantity) - flt(row.completed_quantity)


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
