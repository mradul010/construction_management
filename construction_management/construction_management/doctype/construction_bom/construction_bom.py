import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from construction_management.construction_activity.item_sync import ensure_item_for_mark

TOTAL_WEIGHT_PRECISION = 2
TOTAL_WT_MT_PRECISION = 4


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

		seen = set()
		for row in self.items:
			row_label = _("Row {0}").format(row.idx)
			if not row.mark_no:
				frappe.throw(_("{0}: Mark No. is required.").format(row_label))
			row_key = ((row.mark_no or "").strip(), (row.mark_item or "").strip())
			if row_key in seen:
				frappe.throw(
					_("{0}: Duplicate Construction BOM row for Mark No. {1} and Mark Item {2}.").format(
						row_label,
						frappe.bold(row.mark_no),
						frappe.bold(row.mark_item or "-"),
					)
				)
			seen.add(row_key)
			if row.mark_no and not row.item_code:
				item = ensure_item_for_mark(row.mark_no, unit_weight=row.unit_weight)
				row.item_code = item.get("item") if item else None
			if row.mark_item and not row.mark_item_item_code:
				item = ensure_item_for_mark(row.mark_item, unit_weight=row.unit_weight)
				row.mark_item_item_code = item.get("item") if item else None
			if flt(row.qty) < 0:
				frappe.throw(_("{0}: Qty cannot be negative.").format(row_label))
			if flt(row.unit_weight) < 0:
				frappe.throw(_("{0}: Unit Weight cannot be negative.").format(row_label))

	def update_item_values(self):
		for row in self.items:
			row.serial_no = row.idx
			row.total_weight, row.total_wt_mt = get_weight_values(row.qty, row.unit_weight)


def get_weight_values(qty, unit_weight):
	total_weight = flt(flt(qty) * flt(unit_weight), TOTAL_WEIGHT_PRECISION)
	total_wt_mt = flt(total_weight / 1000, TOTAL_WT_MT_PRECISION)
	return total_weight, total_wt_mt
