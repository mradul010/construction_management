from frappe import _


def get_data():
	return {
		"fieldname": "boq",
		"internal_links": {
			"Project": "project",
			"Sales Order": "sales_order",
		},
		"non_standard_fieldnames": {
			"BOQ": "parent_boq",
		},
		"transactions": [
			{
				"label": _("Contract"),
				"items": ["Project", "Sales Order"],
			},
			{
				"label": _("Revisions"),
				"items": ["BOQ"],
			},
			{
				"label": _("Billing"),
				"items": ["RA Bill"],
			},
		],
	}
