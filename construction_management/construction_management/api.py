import json
import frappe

from construction_management.construction_management.boq_permissions import get_authorized_boq


@frappe.whitelist()
def get_item_default_cost_components(item):
	"""
	Fetch the default cost breakdown stored on the Item master,
	keyed by Item code. Returns [] if item is blank or doesn't
	exist as a valid Item document (e.g. legacy/manual BOQ rows
	where "item" holds a free-text description instead of a
	real Item code).
	"""
	if not item:
		return []

	if not frappe.db.exists("Item", item):
		return []

	doc = frappe.get_doc("Item", item)
	components = []
	for row in doc.get("default_cost_components") or []:
		components.append({
			"component_type": row.component_type,
			"description": row.description,
			"amount": row.amount
		})
	return components


@frappe.whitelist()
def save_item_default_cost_components(item, components):
	"""
	Save/overwrite the default cost breakdown on the Item master.
	Silently does nothing if item is blank or not a valid Item
	document, instead of throwing — so the BOQ dialog flow never
	breaks for legacy rows with bad item links.
	components: JSON string or list of dicts with
	            component_type, description, amount
	"""
	if not item or not frappe.db.exists("Item", item):
		return {"status": "skipped", "reason": "invalid or missing item link"}

	if isinstance(components, str):
		components = json.loads(components)

	doc = frappe.get_doc("Item", item)
	doc.set("default_cost_components", [])
	for c in components:
		doc.append("default_cost_components", {
			"component_type": c.get("component_type"),
			"description": c.get("description"),
			"amount": c.get("amount") or 0
		})
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def boq_item_search(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	"""
	Search BOQ Item links by their human-readable item_name while
	returning doc.name as the stored Link value.
	"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	parent = filters.get("parent") or filters.get("boq")

	if not parent:
		return []

	get_authorized_boq(parent)

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"

	return frappe.db.sql(
		"""
		SELECT name, item_name
		FROM `tabBOQ Item`
		WHERE parent = %(parent)s
		  AND (%(txt)s = '' OR item_name LIKE %(like_txt)s OR name LIKE %(like_txt)s)
		ORDER BY
		  CASE
		    WHEN item_name LIKE %(prefix_txt)s THEN 0
		    WHEN item_name LIKE %(like_txt)s THEN 1
		    WHEN name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		  END,
		  item_name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"parent": parent,
			"txt": txt,
			"like_txt": like_txt,
			"prefix_txt": prefix_txt,
			"start": start,
			"page_len": page_len,
		},
	)
 
 
 
