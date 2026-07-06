import frappe

from construction_management.portal_utils import (
	log_portal_access,
	require_portal_customer,
	validate_ra_bill_customer,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	name = frappe.form_dict.get("name")
	validate_ra_bill_customer(name, customer)

	ra_bill = frappe.get_doc("RA Bill", name)
	context.title = ra_bill.name
	context.customer = customer
	context.ra_bill = ra_bill
	context.items = get_ra_bill_items(ra_bill)


def get_ra_bill_items(ra_bill):
	items = []
	for row in ra_bill.get("items") or []:
		item_name = row.get("item_name")
		if not item_name and row.get("boq_item"):
			item_name = frappe.db.get_value("BOQ Item", row.boq_item, "item_name")

		items.append(
			frappe._dict(
				category_name=row.category_name,
				sub_category=row.sub_category,
				item_name=item_name or row.boq_item,
				boq_qty=row.boq_qty,
				uom=row.uom,
				boq_rate=row.boq_rate,
				previous_percent=row.previous_percent,
				work_percent=row.work_percent,
				current_qty=row.current_qty,
				current_amount=row.current_amount,
				remaining_percent=row.remaining_percent,
				cumulative_qty=row.cumulative_qty,
			)
		)
	return items
