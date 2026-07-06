from frappe import _


def get_data():
	return {
		"fieldname": "boq",
		"non_standard_fieldnames": {
			"BOQ": "parent_boq",
		},
		"transactions": [
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
