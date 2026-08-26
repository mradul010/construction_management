from frappe import _


def get_data():
	return {
		"internal_links": {
			"Stock Entry": "stock_entry",
		},
		"transactions": [
			{
				"label": _("Reference"),
				"items": ["Stock Entry"],
			},
		],
	}
