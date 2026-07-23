from frappe import _


def get_data(data):
	"""Extend the Purchase Invoice dashboard with subcontract bill references."""
	data = data or {}
	data.setdefault("non_standard_fieldnames", {}).update(
		{
			"SC Bill": "purchase_invoice",
			"Retention Payable": "purchase_invoice",
			"Payment Entry": "purchase_invoice",
		}
	)
	data.setdefault("internal_links", {}).update(
		{
			"Project": "project",
			"Supplier": "supplier",
		}
	)

	transactions = data.setdefault("transactions", [])
	_add_items(transactions, _("Subcontract Management"), ["SC Bill", "Retention Payable", "Project"])
	return data


def _add_items(transactions, label, items):
	for group in transactions:
		if group.get("label") == label:
			for item in items:
				if item not in group.setdefault("items", []):
					group["items"].append(item)
			return

	transactions.append({"label": label, "items": items})
