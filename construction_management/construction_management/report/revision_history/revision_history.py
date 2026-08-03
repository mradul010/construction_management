import frappe
from frappe import _
from frappe.utils import date_diff, nowdate

REF_DOCTYPE = 'Drawing Register'
REPORT_FIELDS = ['name', 'project', 'drawing_number', 'drawing_title', 'revision_number', 'revision_date', 'revision_description', 'current_status', 'ifc_status', 'ifc_date', 'approved_by']
BASE_FILTERS = {}

def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data, None, None, get_report_summary(data)

def get_columns():
	columns = []
	meta = frappe.get_meta(REF_DOCTYPE)
	for fieldname in REPORT_FIELDS:
		df = meta.get_field(fieldname)
		if df:
			columns.append({"label": _(df.label or fieldname.replace('_', ' ').title()), "fieldname": fieldname, "fieldtype": df.fieldtype, "options": df.options, "width": 150})
		else:
			columns.append({"label": _(fieldname.replace('_', ' ').title()), "fieldname": fieldname, "fieldtype": "Data", "width": 150})
	if 'Revision History' == "Drawing Aging":
		columns.append({"label": _("Age Days"), "fieldname": "age_days", "fieldtype": "Int", "width": 90})
	if 'Revision History' in ("Drawings by Discipline", "Drawings by Package", "Design Dashboard"):
		columns.append({"label": _("Drawing Count"), "fieldname": "drawing_count", "fieldtype": "Int", "width": 110})
	return columns

def get_data(filters):
	db_filters = dict(BASE_FILTERS)
	for key in ("project", "design_package", "discipline", "current_status", "status"):
		if filters.get(key):
			db_filters[key] = filters.get(key)
	if 'Revision History' == "Design Dashboard":
		return get_dashboard_data(db_filters)
	if 'Revision History' == "Drawings by Discipline":
		return grouped_data(db_filters, ["project", "design_package", "discipline", "current_status"])
	if 'Revision History' == "Drawings by Package":
		return grouped_data(db_filters, ["project", "design_package", "current_status"])
	rows = frappe.get_all(REF_DOCTYPE, filters=db_filters, fields=REPORT_FIELDS, order_by="modified desc", limit_page_length=500)
	if 'Revision History' == "Drawing Aging":
		for row in rows:
			row["age_days"] = date_diff(nowdate(), row.get("modified")) if row.get("modified") else 0
	return rows

def grouped_data(filters, group_fields):
	fields = group_fields + ["count(name) as drawing_count"]
	return frappe.get_all("Drawing Register", filters=filters, fields=fields, group_by=", ".join(group_fields), order_by=", ".join(group_fields), limit_page_length=500)

def get_dashboard_data(filters):
	return grouped_data(filters, ["project", "design_package", "discipline", "current_status"])

def get_report_summary(data):
	return [{"label": _("Rows"), "value": len(data), "indicator": "Blue"}]
