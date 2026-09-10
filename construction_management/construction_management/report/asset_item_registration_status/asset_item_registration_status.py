import frappe
from frappe import _
from frappe.utils import cint

from construction_management.construction_management.report.report_utils import parse_filters


REPORT_ROLES = {
	"System Manager",
	"Construction Manager",
	"Stock Manager",
	"Accounts Manager",
	"Projects Manager",
	"Projects User",
}


def execute(filters=None):
	filters = parse_filters(filters)
	ensure_access()
	data = get_data(filters)
	return get_columns(), data, None, None, get_report_summary(data)


def ensure_access():
	if frappe.session.user == "Administrator":
		return
	if set(frappe.get_roles()) & REPORT_ROLES:
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def get_columns():
	return [
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 160},
		{
			"label": _("Asset Category"),
			"fieldname": "asset_category",
			"fieldtype": "Link",
			"options": "Asset Category",
			"width": 170,
		},
		{"label": _("Is Fixed Asset"), "fieldname": "is_fixed_asset", "fieldtype": "Data", "width": 120},
		{"label": _("Asset Registered"), "fieldname": "asset_registered", "fieldtype": "Data", "width": 135},
		{"label": _("Number of Asset Records"), "fieldname": "asset_count", "fieldtype": "Int", "width": 175},
		{"label": _("Asset IDs / Asset Names"), "fieldname": "asset_names", "fieldtype": "Data", "width": 320},
	]


def get_data(filters):
	item_conditions = ["i.`is_fixed_asset` = 1"]
	asset_conditions = ["a.`docstatus` < 2"]
	params = {}

	if filters.get("company"):
		asset_conditions.append("a.`company` = %(company)s")
		params["company"] = filters.company
	if filters.get("item_group"):
		item_conditions.append("i.`item_group` = %(item_group)s")
		params["item_group"] = filters.item_group
	if filters.get("asset_category"):
		item_conditions.append("i.`asset_category` = %(asset_category)s")
		params["asset_category"] = filters.asset_category

	registration_status = filters.get("registration_status")
	if registration_status == "Registered":
		item_conditions.append("IFNULL(asset_summary.`asset_count`, 0) > 0")
	elif registration_status == "Not Registered":
		item_conditions.append("IFNULL(asset_summary.`asset_count`, 0) = 0")

	rows = frappe.db.sql(
		f"""
		SELECT
			i.`name` AS item_code,
			i.`item_name`,
			i.`item_group`,
			i.`asset_category`,
			CASE WHEN i.`is_fixed_asset` = 1 THEN 'Yes' ELSE 'No' END AS is_fixed_asset,
			CASE
				WHEN IFNULL(asset_summary.`asset_count`, 0) > 0 THEN 'Yes'
				ELSE 'No'
			END AS asset_registered,
			IFNULL(asset_summary.`asset_count`, 0) AS asset_count,
			IFNULL(asset_summary.`asset_names`, '') AS asset_names
		FROM `tabItem` i
		LEFT JOIN (
			SELECT
				a.`item_code`,
				COUNT(a.`name`) AS asset_count,
				GROUP_CONCAT(a.`name` ORDER BY a.`name` SEPARATOR ', ') AS asset_names
			FROM `tabAsset` a
			WHERE {" AND ".join(asset_conditions)}
			GROUP BY a.`item_code`
		) asset_summary ON asset_summary.`item_code` = i.`name`
		WHERE {" AND ".join(item_conditions)}
		ORDER BY i.`item_group`, i.`asset_category`, i.`name`
		""",
		params,
		as_dict=True,
	)

	for row in rows:
		row.asset_count = cint(row.asset_count)

	return rows


def get_report_summary(data):
	registered = sum(1 for row in data if cint(row.get("asset_count")) > 0)
	not_registered = len(data) - registered

	return [
		{
			"value": len(data),
			"label": _("Asset Items"),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"value": registered,
			"label": _("Registered"),
			"datatype": "Int",
			"indicator": "Green",
		},
		{
			"value": not_registered,
			"label": _("Not Registered"),
			"datatype": "Int",
			"indicator": "Red" if not_registered else "Green",
		},
	]
