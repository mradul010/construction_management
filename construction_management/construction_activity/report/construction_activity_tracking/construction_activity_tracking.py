from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


STAGES = ["Unloading", "Assembly", "Erection", "Alignment"]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	activity = {stage: get_activity_rows(stage, filters) for stage in STAGES}
	rows = build_rows(activity)
	return columns, rows


def get_columns():
	return [
		{"label": _("Building Number"), "fieldname": "building_number", "fieldtype": "Link", "options": "Building Number", "width": 150},
		{"label": _("Mark"), "fieldname": "mark_no", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("Unit Weight"), "fieldname": "unit_weight", "fieldtype": "Float", "width": 110},
		{"label": _("Total Weight"), "fieldname": "total_weight", "fieldtype": "Float", "width": 120},
		{"label": _("Vehicle No"), "fieldname": "vehicle_no", "fieldtype": "Data", "width": 130},
		{"label": _("Unloading"), "fieldname": "unloading", "fieldtype": "Date", "width": 110},
		{"label": _("Assembly"), "fieldname": "assembly", "fieldtype": "Date", "width": 110},
		{"label": _("Erection"), "fieldname": "erection", "fieldtype": "Date", "width": 110},
		{"label": _("Alignment"), "fieldname": "alignment", "fieldtype": "Date", "width": 110},
	]


def get_activity_rows(stage, filters):
	conditions = ["parent.docstatus = 1"]
	values = {}
	add_filter(conditions, values, "parent.company", "company", filters)
	add_filter(conditions, values, "parent.project", "project", filters)
	add_filter(conditions, values, "parent.building_number", "building_number", filters)
	add_filter(conditions, values, "item.mark_no", "mark_no", filters)
	add_filter(conditions, values, "parent.activity_date", "from_date", filters, ">=")
	add_filter(conditions, values, "parent.activity_date", "to_date", filters, "<=")

	fields = """
		parent.name,
		parent.company,
		parent.project,
		parent.building_number,
		item.mark_no,
		item.qty,
		item.unit_weight,
		item.total_weight,
		parent.activity_date
	"""
	if stage == "Unloading":
		fields += ", parent.vehicle_no"

	return frappe.db.sql(
		f"""
		select {fields}
		from `tab{stage}` parent
		inner join `tabConstruction Activity Item` item on item.parent = parent.name
		where {" and ".join(conditions)}
		order by parent.project, parent.building_number, item.mark_no, parent.activity_date, parent.creation
		""",
		values,
		as_dict=True,
	)


def build_rows(activity):
	keys = set()
	for stage_rows in activity.values():
		keys.update(row_key(row) for row in stage_rows)

	stage_rows_by_key = {
		stage: group_rows_by_key(rows)
		for stage, rows in activity.items()
	}

	rows = []
	for key in sorted(keys, key=lambda value: (value[1] or "", value[2] or "", value[3] or "")):
		unloading_rows = stage_rows_by_key["Unloading"].get(key, [])
		tracking_qty = get_tracking_qty(stage_rows_by_key, key)
		unit_weight = get_first_value(stage_rows_by_key, key, "unit_weight")
		total_weight = tracking_qty * unit_weight

		rows.append(
			{
				"building_number": key[2],
				"mark_no": key[3],
				"qty": tracking_qty,
				"unit_weight": unit_weight,
				"total_weight": total_weight,
				"vehicle_no": get_latest_value(unloading_rows, "vehicle_no"),
				"unloading": get_latest_value(unloading_rows, "activity_date"),
				"assembly": get_latest_value(stage_rows_by_key["Assembly"].get(key, []), "activity_date"),
				"erection": get_latest_value(stage_rows_by_key["Erection"].get(key, []), "activity_date"),
				"alignment": get_latest_value(stage_rows_by_key["Alignment"].get(key, []), "activity_date"),
			}
		)
	return rows


def get_tracking_qty(stage_rows_by_key, key):
	for stage in STAGES:
		qty = sum(flt(row.qty) for row in stage_rows_by_key[stage].get(key, []))
		if qty:
			return qty
	return 0


def get_latest_value(rows, fieldname):
	value = None
	for row in rows:
		if row.get(fieldname):
			value = row.get(fieldname)
	return value


def get_first_value(stage_rows_by_key, key, fieldname):
	for stage in STAGES:
		for row in stage_rows_by_key[stage].get(key, []):
			if flt(row.get(fieldname)):
				return flt(row.get(fieldname))
	return 0


def group_rows_by_key(rows):
	grouped = defaultdict(list)
	for row in rows:
		grouped[row_key(row)].append(row)
	return grouped


def row_key(row):
	return (row.get("company"), row.get("project"), row.get("building_number"), row.get("mark_no"))


def add_filter(conditions, values, db_field, filter_name, filters, operator="="):
	if filters.get(filter_name):
		conditions.append(f"{db_field} {operator} %({filter_name})s")
		values[filter_name] = filters.get(filter_name)
