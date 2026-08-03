from frappe import _


def get_data():
	return {
		"fieldname": "ra_bill",
		"internal_links": {
			"Project": "project",
			"Drawing Register": "drawing",
			"BOQ": "boq",
			"Sales Order": "sales_order",
		},
		"transactions": [
			{"label": _("Design"), "items": ["Project", "Drawing Register"]},
			{"label": _("Contract"), "items": ["BOQ", "Sales Order"]},
			{"label": _("Billing"), "items": ["Sales Invoice"]},
		],
	}
