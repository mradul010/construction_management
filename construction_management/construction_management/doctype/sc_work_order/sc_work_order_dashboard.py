from frappe import _


def get_data():
	return {
		"fieldname": "sc_work_order",
		"internal_links": {
			"Drawing Register": "drawing",
			"BOQ": "boq",
			"Project": "project",
			"Supplier": "supplier",
		},
		"non_standard_fieldnames": {
			"Purchase Order": "sc_work_order",
			"SC Bill": "sc_work_order",
			"Purchase Invoice": "sc_work_order",
		},
		"transactions": [
			{
				"label": _("Design"),
				"items": ["Project", "Drawing Register", "BOQ"],
			},
			{
				"label": _("Contract"),
				"items": ["Supplier"],
			},
			{
				"label": _("Subcontract Ordering"),
				"items": ["Purchase Order", "SC Bill"],
			},
			{
				"label": _("Accounting"),
				"items": ["Purchase Invoice", "Payment Entry", "Retention Payable"],
			},
		],
	}
