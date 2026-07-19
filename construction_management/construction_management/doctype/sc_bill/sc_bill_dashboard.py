from frappe import _


def get_data():
	return {
		"fieldname": "sc_bill",
		"internal_links": {
			"SC Work Order": "sc_work_order",
			"Project": "project",
			"Supplier": "supplier",
			"BOQ": "boq",
			"Purchase Invoice": "purchase_invoice",
		},
		"transactions": [
			{
				"label": _("Subcontract"),
				"items": ["SC Work Order", "Project", "Supplier", "BOQ"],
			},
			{
				"label": _("Accounting"),
				"items": ["Purchase Invoice"],
			},
		],
	}
