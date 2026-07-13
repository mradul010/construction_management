from frappe import _


def get_data(data):
	"""Extend the Sales Order dashboard data already assembled by Frappe."""
	data.setdefault("non_standard_fieldnames", {}).update(
		{
			"BOQ": "sales_order",
			"RA Bill": "sales_order",
			"Retention Record": "sales_order",
			"Sales Invoice": "sales_order",
		}
	)

	transactions = data.setdefault("transactions", [])
	construction = next(
		(row for row in transactions if row.get("label") == _("Construction")),
		None,
	)
	if construction:
		for doctype in ("BOQ", "RA Bill", "Retention Record"):
			if doctype not in construction.setdefault("items", []):
				construction["items"].append(doctype)
	else:
		transactions.append(
			{"label": _("Construction"), "items": ["BOQ", "RA Bill", "Retention Record"]}
		)

	return data
