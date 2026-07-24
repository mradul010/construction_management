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
	data.setdefault("internal_links", {}).update(
		{
			"Drawing Register": "drawing",
		}
	)

	transactions = data.setdefault("transactions", [])
	_add_items(transactions, _("Design"), ["Drawing Register"])
	_add_items(transactions, _("Execution"), ["BOQ"])
	_add_items(transactions, _("Billing"), ["RA Bill", "Sales Invoice"])
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


def _add_items(transactions, label, items):
	for group in transactions:
		if group.get("label") == label:
			for item in items:
				if item not in group.setdefault("items", []):
					group["items"].append(item)
			return
	transactions.append({"label": label, "items": items})
