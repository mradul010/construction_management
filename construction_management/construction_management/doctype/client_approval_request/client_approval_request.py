import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime


APPROVAL_TYPE_BY_SOURCE = {
	"Drawing Approval": "Drawing",
	"Design Change Request": "Design Change",
	"BOQ": "BOQ",
	"RA Bill": "RA Bill",
}

PROJECT_FIELD_BY_SOURCE = {
	"Drawing Approval": "project",
	"Design Change Request": "project",
	"BOQ": "project",
	"RA Bill": "project",
	"Project": "name",
	"Sales Order": "project",
}

CUSTOMER_FIELD_BY_SOURCE = {
	"BOQ": ("customer", "client"),
	"RA Bill": ("customer",),
	"Project": ("customer", "client"),
	"Sales Order": ("customer",),
}


class ClientApprovalRequest(Document):
	def before_validate(self):
		self.set_project_customer()
		self.set_source_title()
		self.set_approval_type_from_source()
		self.set_initial_status()

	def validate(self):
		self.validate_status_transition_guard()
		self.validate_visibility_dates()
		self.validate_source_document()

	def set_project_customer(self):
		if not self.project:
			frappe.throw(_("Project is required."))
		if not frappe.db.exists("Project", self.project):
			frappe.throw(_("Project {0} does not exist.").format(self.project))

		from construction_management.portal_utils import get_project_customer

		project_customer = get_project_customer(self.project)
		if not project_customer:
			frappe.throw(
				_(
					"Selected Project is not linked to a Customer. Please assign a Customer to the Project before creating a Client Approval Request."
				)
			)
		self.customer = project_customer

	def set_source_title(self):
		if not self.source_doctype or not self.source_name:
			self.source_title = None
			return
		if not frappe.db.exists(self.source_doctype, self.source_name):
			frappe.throw(_("Source document {0} {1} does not exist.").format(self.source_doctype, self.source_name))

		try:
			meta = frappe.get_meta(self.source_doctype)
			title_field = meta.title_field
			if title_field and meta.has_field(title_field):
				self.source_title = frappe.db.get_value(self.source_doctype, self.source_name, title_field) or self.source_name
			else:
				self.source_title = self.source_name
		except Exception:
			self.source_title = self.source_name

	def set_approval_type_from_source(self):
		if self.approval_type or not self.source_doctype:
			return
		self.approval_type = APPROVAL_TYPE_BY_SOURCE.get(self.source_doctype) or "General"

	def set_initial_status(self):
		if not self.status:
			self.status = "Draft"
		if self.publish_to_client_portal and self.status == "Draft":
			self.status = "Pending"
			self.requested_by = self.requested_by or frappe.session.user
			self.requested_on = self.requested_on or now_datetime()

	def validate_status_transition_guard(self):
		if self.is_new():
			return
		previous = frappe.db.get_value(self.doctype, self.name, ["status", "response_by", "response_on"], as_dict=True)
		if not previous:
			return
		if previous.status in ("Approved", "Rejected") and self.status != previous.status:
			frappe.throw(_("Responded approval requests cannot be moved back to another status."))
		if previous.status in ("Approved", "Rejected") and (self.response_by != previous.response_by or get_datetime(self.response_on) != get_datetime(previous.response_on)):
			frappe.throw(_("Responded approval request audit fields cannot be changed."))

	def validate_visibility_dates(self):
		if self.visible_from and self.visible_until and getdate(self.visible_until) < getdate(self.visible_from):
			frappe.throw(_("Visible Until cannot be before Visible From."))

	def validate_source_document(self):
		if self.source_doctype and not self.source_name:
			frappe.throw(_("Source Document is required when Source DocType is selected."))
		if self.source_name and not self.source_doctype:
			frappe.throw(_("Source DocType is required when Source Document is selected."))
		if not self.source_doctype and not self.source_name:
			return
		if not frappe.db.exists(self.source_doctype, self.source_name):
			frappe.throw(_("Source document {0} {1} does not exist.").format(self.source_doctype, self.source_name))

		self.validate_source_project()
		self.validate_source_customer()

	def validate_source_project(self):
		fieldname = PROJECT_FIELD_BY_SOURCE.get(self.source_doctype)
		if not fieldname:
			return
		source_project = self.source_name if fieldname == "name" else frappe.db.get_value(self.source_doctype, self.source_name, fieldname)
		if source_project and source_project != self.project:
			frappe.throw(_("Source document belongs to a different Project."))

	def validate_source_customer(self):
		for fieldname in CUSTOMER_FIELD_BY_SOURCE.get(self.source_doctype, ()):
			if frappe.get_meta(self.source_doctype).has_field(fieldname):
				source_customer = frappe.db.get_value(self.source_doctype, self.source_name, fieldname)
				if source_customer and source_customer != self.customer:
					frappe.throw(_("Source document belongs to a different Customer."))
				return
