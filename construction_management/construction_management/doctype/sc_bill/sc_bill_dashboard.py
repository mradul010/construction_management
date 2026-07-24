from frappe import _


def get_data():
	return {
		"fieldname": "sc_bill",
		"internal_links": {
			"Drawing Register": "drawing",
			"SC Work Order": "sc_work_order",
			"Project": "project",
			"Supplier": "supplier",
			"BOQ": "boq",
			"Purchase Order": "purchase_order",
			"Purchase Invoice": "purchase_invoice",
		},
		"transactions": [
			{
				"label": _("Design"),
				"items": ["Project", "Drawing Register", "BOQ"],
			},
			{
				"label": _("Subcontract"),
				"items": ["SC Work Order", "Purchase Order", "Supplier"],
			},
			{
				"label": _("Accounting"),
				"items": ["Purchase Invoice", "Payment Entry", "Retention Payable"],
			},
		],
	}
