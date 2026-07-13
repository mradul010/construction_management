from frappe import _


def get_data():
	return {
		"fieldname": "ra_bill",
		"internal_links": {
			"Project": "project",
			"BOQ": "boq",
			"Sales Order": "sales_order",
		},
		"transactions": [
			{"label": _("Contract"), "items": ["Project", "BOQ", "Sales Order"]},
			{"label": _("Billing"), "items": ["Sales Invoice"]},
		],
	}
