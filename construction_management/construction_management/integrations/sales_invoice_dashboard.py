from frappe import _


def get_data(data):
	"""Extend the Sales Invoice dashboard data already assembled by Frappe."""
	data.setdefault("non_standard_fieldnames", {}).update(
		{
			"RA Bill": "sales_invoice",
			"Retention Record": "retention_release_invoice",
		}
	)
	data.setdefault("internal_links", {}).update(
		{
			"BOQ": "boq",
			"Project": "project",
			"RA Bill": "ra_bill",
			"Retention Record": "retention_record",
			"Sales Order": "sales_order",
		}
	)

	transactions = data.setdefault("transactions", [])
	construction = next(
		(row for row in transactions if row.get("label") == _("Construction")),
		None,
	)
	if construction:
		for doctype in ("Sales Order", "Project", "BOQ", "RA Bill", "Retention Record"):
			if doctype not in construction.setdefault("items", []):
				construction["items"].append(doctype)
	else:
		transactions.append(
			{
				"label": _("Construction"),
				"items": ["Sales Order", "Project", "BOQ", "RA Bill", "Retention Record"],
			}
		)

	return data
