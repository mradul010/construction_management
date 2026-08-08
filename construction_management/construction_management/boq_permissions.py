import frappe
from frappe import _


def get_authorized_boq(boq, permission_type="read"):
	if not boq:
		frappe.throw(_("BOQ is required."))

	if not frappe.db.exists("BOQ", boq):
		frappe.throw(_("BOQ {0} does not exist.").format(boq))

	doc = frappe.get_doc("BOQ", boq)
	try:
		doc.check_permission(permission_type)
	except frappe.PermissionError:
		frappe.throw(
			_("You do not have permission to access BOQ {0}.").format(boq),
			frappe.PermissionError,
		)

	return doc


def get_authorized_boq_item(boq_item, boq=None, permission_type="read", fields=None):
	if not boq_item:
		frappe.throw(_("BOQ Item is required."))

	fields = list(dict.fromkeys(["name", "parent", "parenttype", "parentfield"] + (fields or [])))
	row = frappe.db.get_value("BOQ Item", boq_item, fields, as_dict=True)
	if not row or row.parenttype != "BOQ":
		frappe.throw(_("Invalid BOQ Item {0}.").format(boq_item))

	if boq and row.parent != boq:
		frappe.throw(
			_("BOQ Item {0} does not belong to BOQ {1}.").format(boq_item, boq)
		)

	boq_doc = get_authorized_boq(row.parent, permission_type)
	return row, boq_doc


def get_authorized_boq_items(boq, fields=None, filters=None, order_by="idx asc", limit=None):
	get_authorized_boq(boq)

	child_filters = {
		"parent": boq,
		"parenttype": "BOQ",
		"parentfield": "items",
	}
	child_filters.update(filters or {})

	args = {
		"filters": child_filters,
		"fields": fields or ["name"],
		"order_by": order_by,
	}
	if limit:
		args["limit_page_length"] = limit

	return frappe.get_all("BOQ Item", **args)
