from frappe import _


def get_data():
	return {
		"fieldname": "boq",
		"internal_links": {
			"Project": "project",
			"Sales Order": "sales_order",
		},
		"non_standard_fieldnames": {
			"Project": "current_boq",
			"BOQ": "parent_boq",
			"Sales Order": "boq",
			"RA Bill": "boq",
			"SC Work Order": "boq",
			"SC Bill": "boq",
			"Purchase Order": "boq",
		},
		"transactions": [
			{
				"label": _("Design"),
				"items": ["Project"],
			},
			{
				"label": _("Contract"),
				"items": ["Sales Order"],
			},
			{
				"label": _("Revisions"),
				"items": ["BOQ"],
			},
			{
				"label": _("Billing"),
				"items": ["RA Bill"],
			},
			{
				"label": _("Subcontracting"),
				"items": ["SC Work Order", "Purchase Order", "SC Bill"],
			},
		],
	}
