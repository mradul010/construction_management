from frappe import _


def get_data(data=None):
	return {
		"fieldname": "purchase_order",
		"internal_links": {
			"SC Work Order": "sc_work_order",
			"Project": "project",
			"Supplier": "supplier",
			"BOQ": "boq",
		},
		"transactions": [
			{
				"label": _("Subcontract"),
				"items": ["SC Work Order", "Project", "Supplier", "BOQ"],
			},
			{
				"label": _("Billing"),
				"items": ["SC Bill", "Purchase Invoice", "Payment Entry", "Retention Payable"],
			},
		],
	}
