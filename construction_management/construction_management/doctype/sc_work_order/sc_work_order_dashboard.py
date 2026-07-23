from frappe import _


def get_data():
	return {
		"fieldname": "sc_work_order",
		"internal_links": {
			"BOQ": "boq",
			"Project": "project",
			"Supplier": "supplier",
		},
		"transactions": [
			{
				"label": _("Contract"),
				"items": ["Project", "Supplier", "BOQ"],
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
