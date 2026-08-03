from frappe import _


def get_data(data=None):
	return {
		"fieldname": "purchase_order",
		"internal_links": {
			"Drawing Register": "drawing",
			"SC Work Order": "sc_work_order",
			"Project": "project",
			"Supplier": "supplier",
			"BOQ": "boq",
		},
		"transactions": [
			{
				"label": _("Design"),
				"items": ["Project", "Drawing Register", "BOQ"],
			},
			{
				"label": _("Subcontract"),
				"items": ["SC Work Order", "Supplier"],
			},
			{
				"label": _("Billing"),
				"items": ["SC Bill", "Purchase Invoice", "Payment Entry", "Retention Payable"],
			},
		],
	}
