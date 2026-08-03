from frappe import _


def get_data():
	return {
		"fieldname": "retention_payable",
		"non_standard_fieldnames": {
			"Purchase Invoice": "retention_payable",
		},
		"internal_links": {
			"Project": "project",
			"Supplier": "supplier",
			"SC Bill": "sc_bill",
			"SC Work Order": "sc_work_order",
			"Purchase Invoice": "purchase_invoice",
		},
		"transactions": [
			{
				"label": _("Related Documents"),
				"items": ["Project", "Supplier", "SC Work Order", "SC Bill", "Purchase Invoice", "Payment Entry"],
			},
		],
	}
