import frappe
from frappe import _
from frappe.utils import cstr, flt


ITEM_GROUP_SETTING = "default_construction_activity_item_group"
STOCK_UOM_SETTING = "default_construction_activity_stock_uom"
HSN_CODE_SETTING = "default_construction_activity_hsn_code"


def normalize_mark_no(mark_no):
	return cstr(mark_no).strip()


def item_response(item_name, created=False):
	item = frappe.db.get_value("Item", item_name, ["name", "item_code", "item_name"], as_dict=True)
	if not item:
		return None
	return {
		"item": item.name,
		"item_code": item.item_code,
		"item_name": item.item_name,
		"created": bool(created),
	}


def _settings_field_value(fieldname):
	if not frappe.get_meta("Construction Settings").has_field(fieldname):
		return None
	return frappe.db.get_single_value("Construction Settings", fieldname)


def get_default_activity_item_group():
	configured_item_group = _settings_field_value(ITEM_GROUP_SETTING)
	if configured_item_group and frappe.db.exists("Item Group", {"name": configured_item_group, "is_group": 0}):
		return configured_item_group

	for item_group in ("Construction Material", "Construction Materials", "Raw Material", "Raw Materials", "Products"):
		if frappe.db.exists("Item Group", {"name": item_group, "is_group": 0}):
			return item_group

	frappe.throw(
		_(
			"Unable to create Item because no valid Item Group is configured for Construction Activities. "
			"Set Default Construction Activity Item Group in Construction Settings."
		)
	)


def get_default_activity_stock_uom(uom=None):
	if uom and frappe.db.exists("UOM", {"name": uom, "enabled": 1}):
		return uom

	configured_uom = _settings_field_value(STOCK_UOM_SETTING)
	if configured_uom and frappe.db.exists("UOM", {"name": configured_uom, "enabled": 1}):
		return configured_uom

	for stock_uom in ("Nos", "Unit", "Kg"):
		if frappe.db.exists("UOM", {"name": stock_uom, "enabled": 1}):
			return stock_uom

	frappe.throw(
		_(
			"Unable to create Item because no valid Stock UOM is configured for Construction Activities. "
			"Set Default Construction Activity Stock UOM in Construction Settings."
		)
	)


def get_default_activity_hsn_code(item_group=None, stock_uom=None):
	if not frappe.get_meta("Item").has_field("gst_hsn_code"):
		return None

	configured_hsn_code = _settings_field_value(HSN_CODE_SETTING)
	if configured_hsn_code and frappe.db.exists("GST HSN Code", configured_hsn_code):
		return configured_hsn_code

	filters = {"gst_hsn_code": ["is", "set"]}
	if item_group:
		filters["item_group"] = item_group
	if stock_uom:
		filters["stock_uom"] = stock_uom

	hsn_code = frappe.db.get_value("Item", filters, "gst_hsn_code", order_by="modified desc")
	if hsn_code:
		return hsn_code

	hsn_code = frappe.db.get_value("Item", {"gst_hsn_code": ["is", "set"]}, "gst_hsn_code", order_by="modified desc")
	if hsn_code:
		return hsn_code

	frappe.throw(
		_(
			"Unable to create Item because no valid HSN/SAC Code is configured for Construction Activities. "
			"Set Default Construction Activity HSN/SAC Code in Construction Settings."
		)
	)


@frappe.whitelist()
def ensure_item_for_mark(mark_no, unit_weight=None, uom=None):
	mark_no = normalize_mark_no(mark_no)
	if not mark_no:
		return None

	if frappe.db.exists("Item", mark_no):
		return item_response(mark_no, created=False)

	item_group = get_default_activity_item_group()
	stock_uom = get_default_activity_stock_uom(uom)

	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": mark_no,
			"item_name": mark_no,
			"item_group": item_group,
			"stock_uom": stock_uom,
			"is_stock_item": 1,
		}
	)

	if flt(unit_weight) and frappe.get_meta("Item").has_field("weight_per_unit"):
		item.weight_per_unit = flt(unit_weight)

	hsn_code = get_default_activity_hsn_code(item_group=item_group, stock_uom=stock_uom)
	if hsn_code:
		item.gst_hsn_code = hsn_code

	try:
		item.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		return item_response(mark_no, created=False)
	except Exception:
		frappe.log_error(frappe.get_traceback(), _("Activity Item Auto Creation"))
		frappe.throw(
			_(
				"Unable to create Item {0}. Please check Construction Activity Item Group, Stock UOM, and HSN/SAC settings."
			).format(frappe.bold(mark_no))
		)

	return item_response(item.name, created=True)
