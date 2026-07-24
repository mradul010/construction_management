from frappe import _


def get_data():
	return {
		"fieldname": "boq",
		"internal_links": {
			"Project": "project",
			"Drawing Register": "drawing",
			"Sales Order": "sales_order",
		},
		"non_standard_fieldnames": {
			"BOQ": "parent_boq",
			"RA Bill": "boq",
			"SC Work Order": "boq",
			"SC Bill": "boq",
			"Purchase Order": "boq",
			"Purchase Invoice": "boq",
		},
		"transactions": [
			{
				"label": _("Design"),
				"items": ["Project", "Drawing Register"],
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
				"items": ["SC Work Order", "Purchase Order", "SC Bill", "Purchase Invoice"],
			},
		],
	}
