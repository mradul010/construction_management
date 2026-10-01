import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".dwg", ".dxf", ".zip", ".rvt", ".ifc"}
GALLERY_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ProjectPortalFile(Document):
	def before_validate(self):
		self.set_project_customer()

	def validate(self):
		self.set_file_metadata()
		self.set_category_defaults()
		self.validate_category()
		self.validate_visibility_dates()
		self.validate_file_privacy()
		self.set_published_on()

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
					"Selected Project is not linked to a Customer. Please assign a Customer to the Project before publishing a portal file."
				)
			)
		self.customer = project_customer

	def set_file_metadata(self):
		if not self.file:
			frappe.throw(_("File is required."))

		file_doc = get_file_doc(self.file)
		if not file_doc:
			frappe.throw(_("File {0} was not found.").format(self.file))

		self.file_url = file_doc.file_url or self.file
		self.file_name = file_doc.file_name or os.path.basename(self.file_url or self.file)
		self.file_size = file_doc.file_size
		self.uploaded_by = file_doc.owner
		self.file_extension = get_file_extension(self.file_name or self.file_url)
		self.is_image = 1 if self.file_extension in GALLERY_EXTENSIONS else 0
		if not self.portal_title:
			self.portal_title = self.file_name

	def set_category_defaults(self):
		if self.category:
			return
		self.category = "Gallery" if self.is_image else "Document"

	def validate_category(self):
		if self.category == "Gallery" and self.file_extension not in GALLERY_EXTENSIONS:
			frappe.throw(_("Gallery files must be JPG, JPEG, PNG, or WEBP images."))
		if self.category == "Document" and self.file_extension not in DOCUMENT_EXTENSIONS:
			frappe.throw(_("Document files must use one of the approved document extensions."))

	def validate_visibility_dates(self):
		if self.visible_from and self.visible_until and getdate(self.visible_until) < getdate(self.visible_from):
			frappe.throw(_("Visible Until cannot be before Visible From."))

	def validate_file_privacy(self):
		if not self.publish_to_client_portal:
			return
		file_doc = get_file_doc(self.file)
		if file_doc and file_doc.is_private:
			frappe.throw(_("Only public File records can currently be published to the Client Portal."))

	def set_published_on(self):
		if not self.publish_to_client_portal:
			return
		previous = None
		if not self.is_new():
			previous = frappe.db.get_value(self.doctype, self.name, "publish_to_client_portal")
		if not self.published_on and not previous:
			self.published_on = now_datetime()


def get_file_doc(file_value):
	if not file_value:
		return None

	fields = ["name", "file_name", "file_url", "file_size", "is_private", "owner"]
	if frappe.db.exists("File", file_value):
		return frappe.get_cached_doc("File", file_value)

	rows = frappe.get_all("File", filters={"file_url": file_value}, fields=fields, limit_page_length=1, ignore_permissions=True)
	if rows:
		return frappe._dict(rows[0])

	rows = frappe.get_all("File", filters={"file_name": file_value}, fields=fields, limit_page_length=1, ignore_permissions=True)
	return frappe._dict(rows[0]) if rows else None


def get_file_extension(value):
	if not value:
		return ""
	path = str(value).split("?", 1)[0]
	return os.path.splitext(path)[1].lower()
