import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class ConstructionBOM(Document):
	def before_insert(self):
		if not self.posting_date:
			self.posting_date = today()

	def validate(self):
		self.validate_project_and_boq()
		self.validate_items()
		self.update_item_values()

	def before_submit(self):
		self.validate_project_and_boq()
		self.validate_items()

	def validate_project_and_boq(self):
		if not self.project:
			frappe.throw(_("Project is required."))
		if not frappe.db.exists("Project", self.project):
			frappe.throw(_("Project {0} does not exist.").format(frappe.bold(self.project)))

		if not self.boq:
			return

		boq_project = frappe.db.get_value("BOQ", self.boq, "project")
		if not boq_project:
			if not frappe.db.exists("BOQ", self.boq):
				frappe.throw(_("BOQ {0} does not exist.").format(frappe.bold(self.boq)))
			return

		if boq_project != self.project:
			frappe.throw(
				_("BOQ {0} belongs to Project {1}, not Project {2}.").format(
					frappe.bold(self.boq),
					frappe.bold(boq_project),
					frappe.bold(self.project),
				)
			)

	def validate_items(self):
		if not self.get("items"):
			frappe.throw(_("At least one Construction BOM Item is required."))

		for row in self.items:
			row_label = _("Row {0}").format(row.idx)
			if not row.mark_no:
				frappe.throw(_("{0}: Mark No. is required.").format(row_label))
			if not frappe.db.exists("Item", row.mark_no):
				frappe.throw(_("{0}: Mark No. {1} is not a valid Item.").format(row_label, frappe.bold(row.mark_no)))
			if flt(row.qty) < 0:
				frappe.throw(_("{0}: Qty cannot be negative.").format(row_label))
			if flt(row.unit_weight) < 0:
				frappe.throw(_("{0}: Unit Weight cannot be negative.").format(row_label))

	def update_item_values(self):
		for row in self.items:
			row.serial_no = row.idx
			row.total_weight = flt(row.qty) * flt(row.unit_weight)
			row.total_wt_mt = flt(row.total_weight) / 1000
