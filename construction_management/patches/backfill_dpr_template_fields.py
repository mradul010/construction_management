import frappe
from frappe.utils import cint, flt


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


def execute():
	if not frappe.db.table_exists("DPR Task Completed"):
		return

	_create_buildings_from_existing_sources()
	_backfill_dpr_task_rows()


def _create_buildings_from_existing_sources():
	if not frappe.db.exists("DocType", "Building"):
		return

	existing_locations = frappe.db.sql(
		"""
		SELECT DISTINCT child.location, parent.project
		FROM `tabDPR Task Completed` child
		INNER JOIN `tabDaily Progress Report` parent ON parent.name = child.parent
		WHERE child.parenttype = 'Daily Progress Report'
		  AND child.location IS NOT NULL
		  AND child.location != ''
		""",
		as_dict=True,
	)
	for row in existing_locations:
		_ensure_building(row.location, row.project)

	if frappe.db.table_exists("Construction BOM"):
		for row in frappe.db.sql(
			"""
			SELECT DISTINCT building_number, project
			FROM `tabConstruction BOM`
			WHERE building_number IS NOT NULL
			  AND building_number != ''
			""",
			as_dict=True,
		):
			_ensure_building(row.building_number, row.project)


def _ensure_building(building_name, project=None):
	building_name = (building_name or "").strip()
	if not building_name or frappe.db.exists("Building", building_name):
		return

	doc = frappe.new_doc("Building")
	doc.building_name = building_name
	doc.project = project
	doc.insert(ignore_permissions=True)


def _backfill_dpr_task_rows():
	rows = frappe.db.sql(
		"""
		SELECT
			child.name,
			child.location,
			child.work_location,
			child.task_title,
			child.todays_work_activity,
			child.mark_no,
			child.target_mark_no,
			child.completed_mark_no,
			child.item_code,
			child.item_name,
			child.description,
			child.work_completed,
			child.notes,
			child.remarks_constraints,
			child.quantity,
			child.target_quantity,
			child.completed_quantity,
			child.fitter,
			child.welder,
			child.gas_cutter,
			child.rigger,
			child.grinder,
			child.helper,
			child.khalasi,
			child.electrician,
			child.foreman
		FROM `tabDPR Task Completed` child
		WHERE child.parenttype = 'Daily Progress Report'
		  AND child.parentfield = 'tasks_completed'
		""",
		as_dict=True,
	)

	for row in rows:
		values = {}
		if not row.work_location and row.location and frappe.db.exists("Building", row.location):
			values["work_location"] = row.location
		if not row.todays_work_activity and row.task_title:
			values["todays_work_activity"] = row.task_title
		if not row.work_completed and row.description:
			values["work_completed"] = row.description
		if not row.remarks_constraints and row.notes:
			values["remarks_constraints"] = row.notes

		legacy_mark_no = (row.mark_no or row.item_code or row.item_name or "").strip()
		if legacy_mark_no:
			if not row.target_mark_no:
				values["target_mark_no"] = legacy_mark_no
			if not row.completed_mark_no:
				values["completed_mark_no"] = legacy_mark_no

		target_quantity = flt(row.target_quantity)
		completed_quantity = flt(row.completed_quantity)
		if flt(row.quantity) and not target_quantity and not completed_quantity:
			target_quantity = completed_quantity = flt(row.quantity)
			values["target_quantity"] = target_quantity
			values["completed_quantity"] = completed_quantity

		values["total_workers"] = sum(cint(row.get(fieldname)) for fieldname in WORKER_FIELDS)
		values["balance_quantity"] = target_quantity - completed_quantity

		if values:
			frappe.db.set_value("DPR Task Completed", row.name, values, update_modified=False)
