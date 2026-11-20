import frappe


def execute():
	"""Correct only the known QATRA Aug-Oct 2026 VAT period configuration error."""
	rows = frappe.get_all(
		"VAT 201 Filing Period",
		filters={
			"parent": "QATRA BUILDING CONTG LLC",
			"parenttype": "UAE VAT Settings",
			"from_date": "2026-08-01",
			"to_date": "2026-10-01",
		},
		pluck="name",
	)
	for name in rows:
		frappe.db.set_value(
			"VAT 201 Filing Period",
			name,
			"to_date",
			"2026-10-31",
			update_modified=False,
		)
