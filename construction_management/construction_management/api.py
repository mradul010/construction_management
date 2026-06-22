import json
import frappe


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
