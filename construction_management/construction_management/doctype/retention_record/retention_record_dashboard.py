from frappe import _


def get_data():
	return {
		"fieldname": "retention_record",
		"non_standard_fieldnames": {
			"Sales Invoice": "retention_record",
		},
		"transactions": [
			{
				"label": _("Related Documents"),
				"items": ["Sales Invoice"],
			},
		],
	}
