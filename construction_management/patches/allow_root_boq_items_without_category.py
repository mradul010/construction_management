import frappe


def execute():
	"""Keep BOQ Item category optional for root-level BOQ rows."""
	frappe.db.delete(
		"Property Setter",
		{
			"doc_type": "BOQ Item",
			"field_name": "boq_category",
			"property": "reqd",
		},
	)

	frappe.db.set_value(
		"DocField",
		{"parent": "BOQ Item", "fieldname": "boq_category"},
		"reqd",
		0,
	)

	frappe.clear_cache(doctype="BOQ Item")
