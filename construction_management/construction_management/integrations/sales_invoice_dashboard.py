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
			"Drawing Register": "drawing",
			"BOQ": "boq",
			"Project": "project",
			"RA Bill": "ra_bill",
			"Retention Record": "retention_record",
			"Sales Order": "sales_order",
		}
	)

	transactions = data.setdefault("transactions", [])
	_add_items(transactions, _("Design"), ["Project", "Drawing Register", "BOQ"])
	_add_items(transactions, _("Billing"), ["Sales Order", "RA Bill"])
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


def _add_items(transactions, label, items):
	for group in transactions:
		if group.get("label") == label:
			for item in items:
				if item not in group.setdefault("items", []):
					group["items"].append(item)
			return
	transactions.append({"label": label, "items": items})
