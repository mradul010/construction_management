import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


STAGE_SEQUENCE = ["Unloading", "Assembly", "Erection", "Alignment"]
PREVIOUS_STAGE = {"Assembly": "Unloading", "Erection": "Assembly", "Alignment": "Erection"}
NEXT_STAGE = {"Unloading": "Assembly", "Assembly": "Erection", "Erection": "Alignment"}
REFERENCE_FIELD = {
	"Assembly": "unloading_reference",
	"Erection": "assembly_reference",
	"Alignment": "erection_reference",
}


class ConstructionActivity(Document):
	stage = None

	def before_validate(self):
		self.set_defaults()

	def validate(self):
		self.validate_items()
		self.validate_stage_sequence()

	def on_cancel(self):
		self.validate_downstream_cancellation()

	def set_defaults(self):
		if not self.activity_date:
			self.activity_date = nowdate()
		if self.project and not self.company:
			self.company = frappe.db.get_value("Project", self.project, "company")

		for row in self.get("items") or []:
			if row.mark_no and not flt(row.unit_weight):
				row.unit_weight = get_item_unit_weight(row.mark_no)
			row.total_weight = flt(row.qty) * flt(row.unit_weight)

	def validate_items(self):
		if not self.get("items"):
			frappe.throw(_("At least one item row is required."))

		for row in self.items:
			row.total_weight = flt(row.qty) * flt(row.unit_weight)
			if not row.mark_no:
				frappe.throw(_("Mark No. is required in row {0}.").format(row.idx))
			if flt(row.qty) <= 0:
				frappe.throw(_("Qty must be greater than zero in row {0}.").format(row.idx))
			if flt(row.unit_weight) < 0:
				frappe.throw(_("Unit Weight cannot be negative in row {0}.").format(row.idx))

	def validate_stage_sequence(self):
		if self.stage == "Unloading":
			return

		previous_stage = PREVIOUS_STAGE[self.stage]
		for row in self.items:
			previous_qty = get_stage_item_qty(previous_stage, self.project, self.building_number, row.mark_no)
			if previous_qty <= 0:
				frappe.throw(
					_("{0} is allowed only after submitted {1} for Mark {2}, Project {3}, Building {4}.").format(
						self.stage,
						previous_stage,
						row.mark_no,
						self.project,
						self.building_number,
					)
				)

			current_qty = (
				get_stage_item_qty(self.stage, self.project, self.building_number, row.mark_no, exclude_parent=self.name)
				+ flt(row.qty)
			)
			if current_qty > previous_qty:
				frappe.throw(
					_("{0} Qty {1} exceeds submitted {2} Qty {3} for Mark {4}, Project {5}, Building {6}.").format(
						self.stage,
						current_qty,
						previous_stage,
						previous_qty,
						row.mark_no,
						self.project,
						self.building_number,
					)
				)

	def validate_downstream_cancellation(self):
		next_stage = NEXT_STAGE.get(self.stage)
		if not next_stage:
			return

		for row in self.items:
			remaining_current = get_stage_item_qty(
				self.stage,
				self.project,
				self.building_number,
				row.mark_no,
				exclude_parent=self.name,
			)
			downstream_qty = get_stage_item_qty(next_stage, self.project, self.building_number, row.mark_no)
			if downstream_qty > remaining_current:
				frappe.throw(
					_("Cannot cancel {0}. Submitted {1} Qty {2} would exceed remaining {0} Qty {3} for Mark {4}.").format(
						self.stage,
						next_stage,
						downstream_qty,
						remaining_current,
						row.mark_no,
					)
				)


def get_stage_item_qty(stage, project, building_number, mark_no, exclude_parent=None):
	if stage not in STAGE_SEQUENCE or not project or not building_number or not mark_no:
		return 0

	conditions = [
		"parent.docstatus = 1",
		"parent.project = %(project)s",
		"parent.building_number = %(building_number)s",
		"item.mark_no = %(mark_no)s",
	]
	values = {"project": project, "building_number": building_number, "mark_no": mark_no}
	if exclude_parent:
		conditions.append("parent.name != %(exclude_parent)s")
		values["exclude_parent"] = exclude_parent

	result = frappe.db.sql(
		f"""
		select sum(item.qty)
		from `tab{stage}` parent
		inner join `tabConstruction Activity Item` item on item.parent = parent.name
		where {" and ".join(conditions)}
		""",
		values,
	)
	return flt(result[0][0] if result else 0)


def get_item_unit_weight(mark_no):
	if not mark_no:
		return 0
	return flt(frappe.db.get_value("Item", mark_no, "weight_per_unit") or 0)


def get_existing_downstream(target_stage, reference_field, source_name, draft_only=False):
	filters = {reference_field: source_name, "docstatus": 0 if draft_only else ["!=", 2]}
	return frappe.db.get_value(target_stage, filters, "name", order_by="creation desc")


def get_remaining_items(source, target_stage):
	rows_by_mark = {}
	for row in source.items:
		if row.mark_no:
			rows_by_mark[row.mark_no] = row

	remaining = []
	for mark_no, source_row in rows_by_mark.items():
		source_qty = get_stage_item_qty(source.doctype, source.project, source.building_number, mark_no)
		target_qty = get_stage_item_qty(target_stage, source.project, source.building_number, mark_no)
		remaining_qty = source_qty - target_qty
		if remaining_qty > 0:
			remaining.append(
				{
					"mark_no": mark_no,
					"qty": remaining_qty,
					"unit_weight": flt(source_row.unit_weight),
					"total_weight": remaining_qty * flt(source_row.unit_weight),
				}
			)
	return remaining


def make_next_stage(source_name, source_stage, target_stage):
	source = frappe.get_doc(source_stage, source_name)
	if source.docstatus != 1:
		frappe.throw(_("{0} must be submitted before creating {1}.").format(source_stage, target_stage))

	reference_field = REFERENCE_FIELD[target_stage]
	existing_draft = get_existing_downstream(target_stage, reference_field, source.name, draft_only=True)
	if existing_draft:
		return frappe.get_doc(target_stage, existing_draft)

	items = get_remaining_items(source, target_stage)
	if not items:
		existing = get_existing_downstream(target_stage, reference_field, source.name)
		if existing:
			return frappe.get_doc(target_stage, existing)
		frappe.throw(_("No remaining quantity is available for {0}.").format(target_stage))

	doc = frappe.new_doc(target_stage)
	doc.company = source.company
	doc.project = source.project
	doc.building_number = source.building_number
	doc.set(reference_field, source.name)
	for row in items:
		doc.append("items", row)

	doc.run_method("set_defaults")
	return doc


@frappe.whitelist()
def make_assembly(source_name):
	return make_next_stage(source_name, "Unloading", "Assembly")


@frappe.whitelist()
def make_erection(source_name):
	return make_next_stage(source_name, "Assembly", "Erection")


@frappe.whitelist()
def make_alignment(source_name):
	return make_next_stage(source_name, "Erection", "Alignment")
