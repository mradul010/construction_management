from frappe import _


def get_data(data):
	"""Extend the Supplier dashboard with subcontract work and billing links."""
	data = data or {}
	data.setdefault("fieldname", "supplier")

	transactions = data.setdefault("transactions", [])
	_add_items(
		transactions,
		_("Subcontract Management"),
		["SC Work Order", "SC Bill", "Retention Payable", "Purchase Invoice"],
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
