from frappe import _


def get_data(data):
	data = data or {}
	data.setdefault("fieldname", "project")
	transactions = data.setdefault("transactions", [])
	_add_items(
		transactions,
		_("Construction"),
		["Daily Progress Report", "BOQ", "RA Bill", "SC Work Order", "SC Bill", "Retention Payable"],
	)
	_add_items(
		transactions,
		_("Design"),
		[
			"Design Package",
			"Design Discipline",
			"Drawing Register",
			"Drawing Review",
			"Drawing Approval",
			"Request For Information",
			"Design Issue",
			"Design Change Request",
			"Design NCR",
			"Drawing Distribution",
			"Drawing Transmittal",
			"BOQ",
		],
	)
	_add_items(transactions, _("Subcontract Management"), ["SC Work Order", "SC Bill", "Retention Payable"])
	_add_items(transactions, _("Advance"), ["Payment Entry"])
	return data


def _add_items(transactions, label, items):
	for group in transactions:
		if group.get("label") == label:
			for item in items:
				if item not in group.setdefault("items", []):
					group["items"].append(item)
			return

	transactions.append({"label": label, "items": items})
