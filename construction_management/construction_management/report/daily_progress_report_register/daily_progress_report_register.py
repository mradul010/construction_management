import frappe
from frappe import _
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


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data, None, None, get_report_summary(data)


def get_columns():
	return [
		{"label": _("DPR"), "fieldname": "dpr", "fieldtype": "Link", "options": "Daily Progress Report", "width": 160},
		{"label": _("DPR Date"), "fieldname": "dpr_date", "fieldtype": "Date", "width": 100},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("S. No."), "fieldname": "serial_no", "fieldtype": "Int", "width": 70},
		{"label": _("Work Location / Building"), "fieldname": "work_location", "fieldtype": "Link", "options": "Building", "width": 170},
		{"label": _("Contractor"), "fieldname": "contractor", "fieldtype": "Link", "options": "Supplier", "width": 170},
		{"label": _("Gang Name"), "fieldname": "gang_name", "fieldtype": "Data", "width": 130},
		{"label": _("Fitter"), "fieldname": "fitter", "fieldtype": "Int", "width": 80},
		{"label": _("Welder"), "fieldname": "welder", "fieldtype": "Int", "width": 80},
		{"label": _("Gas Cutter"), "fieldname": "gas_cutter", "fieldtype": "Int", "width": 90},
		{"label": _("Rigger"), "fieldname": "rigger", "fieldtype": "Int", "width": 80},
		{"label": _("Grinder"), "fieldname": "grinder", "fieldtype": "Int", "width": 80},
		{"label": _("Helper"), "fieldname": "helper", "fieldtype": "Int", "width": 80},
		{"label": _("Khalasi"), "fieldname": "khalasi", "fieldtype": "Int", "width": 80},
		{"label": _("Electrician"), "fieldname": "electrician", "fieldtype": "Int", "width": 90},
		{"label": _("Foreman"), "fieldname": "foreman", "fieldtype": "Int", "width": 80},
		{"label": _("Total Workers"), "fieldname": "total_workers", "fieldtype": "Int", "width": 100},
		{"label": _("Today's Work / Activity"), "fieldname": "todays_work_activity", "fieldtype": "Data", "width": 220},
		{"label": _("Mark No"), "fieldname": "target_mark_no", "fieldtype": "Data", "width": 130},
		{"label": _("Target Quantity"), "fieldname": "target_quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Work Completed"), "fieldname": "work_completed", "fieldtype": "Data", "width": 220},
		{"label": _("Mark No"), "fieldname": "completed_mark_no", "fieldtype": "Data", "width": 130},
		{"label": _("Completed Quantity"), "fieldname": "completed_quantity", "fieldtype": "Float", "width": 130},
		{"label": _("Balance Quantity"), "fieldname": "balance_quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Remarks / Constraints"), "fieldname": "remarks_constraints", "fieldtype": "Data", "width": 220},
	]


def get_data(filters):
	parent_names = _get_permitted_dprs(filters)
	if not parent_names:
		return []

	conditions = [
		"task.parent IN %(parents)s",
		"task.parenttype = 'Daily Progress Report'",
		"task.parentfield = 'tasks_completed'",
	]
	values = {"parents": tuple(parent_names)}

	if filters.get("contractor"):
		conditions.append("task.contractor = %(contractor)s")
		values["contractor"] = filters.contractor
	if filters.get("work_location"):
		conditions.append("(task.work_location = %(work_location)s OR task.location = %(work_location)s)")
		values["work_location"] = filters.work_location
	if filters.get("gang_name"):
		conditions.append("task.gang_name LIKE %(gang_name)s")
		values["gang_name"] = f"%{filters.gang_name}%"
	if filters.get("mark_no"):
		conditions.append(
			"(task.target_mark_no LIKE %(mark_no)s OR task.completed_mark_no LIKE %(mark_no)s OR task.mark_no LIKE %(mark_no)s)"
		)
		values["mark_no"] = f"%{filters.mark_no}%"

	rows = frappe.db.sql(
		f"""
		SELECT
			dpr.name AS dpr,
			dpr.dpr_date,
			dpr.project,
			task.idx AS serial_no,
			task.work_location,
			task.location,
			task.contractor,
			task.gang_name,
			task.fitter,
			task.welder,
			task.gas_cutter,
			task.rigger,
			task.grinder,
			task.helper,
			task.khalasi,
			task.electrician,
			task.foreman,
			task.total_workers,
			task.todays_work_activity,
			task.task_title,
			task.target_mark_no,
			task.completed_mark_no,
			task.mark_no,
			task.target_quantity,
			task.work_completed,
			task.description,
			task.completed_quantity,
			task.quantity,
			task.balance_quantity,
			task.remarks_constraints,
			task.notes
		FROM `tabDPR Task Completed` task
		INNER JOIN `tabDaily Progress Report` dpr ON dpr.name = task.parent
		WHERE {" AND ".join(conditions)}
		ORDER BY dpr.dpr_date DESC, dpr.name DESC, task.idx ASC
		""",
		values,
		as_dict=True,
	)

	return [_normalise_row(row) for row in rows]


def _get_permitted_dprs(filters):
	parent_filters = {}
	if filters.get("project"):
		parent_filters["project"] = filters.project
	if filters.get("from_date") or filters.get("to_date"):
		parent_filters["dpr_date"] = ["between", [filters.get("from_date") or "1900-01-01", filters.get("to_date") or "2999-12-31"]]

	return frappe.get_list(
		"Daily Progress Report",
		filters=parent_filters,
		pluck="name",
		order_by="dpr_date desc, name desc",
		limit_page_length=0,
	)


def _normalise_row(row):
	for fieldname in WORKER_FIELDS:
		row[fieldname] = cint(row.get(fieldname))

	row.work_location = row.work_location or row.location
	row.total_workers = sum(row[fieldname] for fieldname in WORKER_FIELDS)
	row.todays_work_activity = row.todays_work_activity or row.task_title
	row.target_mark_no = row.target_mark_no or row.mark_no
	row.completed_mark_no = row.completed_mark_no or row.mark_no
	row.work_completed = row.work_completed or row.description
	row.completed_quantity = flt(row.completed_quantity) if row.completed_quantity is not None else flt(row.quantity)
	row.target_quantity = flt(row.target_quantity)
	row.balance_quantity = flt(row.balance_quantity)
	if row.balance_quantity == 0 and (row.target_quantity or row.completed_quantity):
		row.balance_quantity = row.target_quantity - row.completed_quantity
	row.remarks_constraints = row.remarks_constraints or row.notes
	return row


def get_report_summary(data):
	return [
		{"value": len(data), "label": _("Task Rows"), "datatype": "Int", "indicator": "Blue"},
		{
			"value": sum(cint(row.total_workers) for row in data),
			"label": _("Total Workers"),
			"datatype": "Int",
			"indicator": "Green",
		},
		{
			"value": sum(flt(row.target_quantity) for row in data),
			"label": _("Target Quantity"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": sum(flt(row.completed_quantity) for row in data),
			"label": _("Completed Quantity"),
			"datatype": "Float",
			"indicator": "Green",
		},
		{
			"value": sum(flt(row.balance_quantity) for row in data),
			"label": _("Balance Quantity"),
			"datatype": "Float",
			"indicator": "Orange",
		},
	]
