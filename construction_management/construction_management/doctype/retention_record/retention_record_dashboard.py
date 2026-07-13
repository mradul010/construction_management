from frappe import _


def get_data():
	return {
		"fieldname": "retention_record",
		"non_standard_fieldnames": {
			"Sales Invoice": "retention_record",
		},
		"internal_links": {
			"BOQ": "boq",
			"Project": "project",
			"RA Bill": "ra_bill",
			"Sales Order": "sales_order",
			"Sales Invoice": "sales_invoice",
		},
		"transactions": [
			{
				"label": _("Related Documents"),
				"items": ["Sales Order", "Project", "BOQ", "RA Bill", "Sales Invoice"],
			},
		],
	}
