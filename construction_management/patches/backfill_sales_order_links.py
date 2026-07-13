from collections import defaultdict

import frappe


INVALID_SALES_ORDER_STATUSES = ("Cancelled", "Closed", "On Hold")


def execute():
	"""Backfill only explicit or revision-chain Sales Order relationships."""
	frappe.clear_cache()
	if not _has_field("BOQ", "sales_order") or not _has_field("RA Bill", "sales_order"):
		return

	logger = frappe.logger("construction_management.sales_order_backfill")
	_backfill_boq_from_legacy_sales_order_link(logger)
	_backfill_boq_revision_chains(logger)
	_backfill_ra_bills_and_invoices(logger)


def _has_field(doctype, fieldname):
	try:
		return frappe.get_meta(doctype).has_field(fieldname)
	except Exception:
		return False


def _backfill_boq_from_legacy_sales_order_link(logger):
	if not _has_field("Sales Order", "boq"):
		return

	links_by_boq = defaultdict(list)
	for row in frappe.get_all(
		"Sales Order",
		filters={
			"boq": ["is", "set"],
			"docstatus": 1,
			"status": ["not in", INVALID_SALES_ORDER_STATUSES],
		},
		fields=["name", "boq"],
	):
		if frappe.db.exists("BOQ", row.boq):
			links_by_boq[row.boq].append(row.name)

	for boq, sales_orders in links_by_boq.items():
		if len(sales_orders) != 1:
			logger.warning("Skipped ambiguous BOQ %s; Sales Orders: %s", boq, sales_orders)
			continue

		current = frappe.db.get_value("BOQ", boq, "sales_order")
		if not current:
			frappe.db.set_value("BOQ", boq, "sales_order", sales_orders[0], update_modified=False)
		elif current != sales_orders[0]:
			logger.warning(
				"Kept existing BOQ %s Sales Order %s; legacy link points to %s",
				boq,
				current,
				sales_orders[0],
			)


def _backfill_boq_revision_chains(logger):
	chains = defaultdict(list)
	for row in frappe.get_all(
		"BOQ",
		fields=["name", "original_boq", "sales_order"],
	):
		chains[row.original_boq or row.name].append(row)

	for root, rows in chains.items():
		sales_orders = {row.sales_order for row in rows if row.sales_order}
		if len(sales_orders) > 1:
			logger.warning(
				"Skipped ambiguous BOQ revision chain %s; Sales Orders: %s",
				root,
				sorted(sales_orders),
			)
			continue
		if not sales_orders:
			continue

		sales_order = next(iter(sales_orders))
		for row in rows:
			if not row.sales_order:
				frappe.db.set_value("BOQ", row.name, "sales_order", sales_order, update_modified=False)


def _backfill_ra_bills_and_invoices(logger):
	for row in frappe.get_all(
		"RA Bill",
		fields=["name", "boq", "sales_order", "sales_invoice"],
	):
		boq_sales_order = (
			frappe.db.get_value("BOQ", row.boq, "sales_order") if row.boq else None
		)
		if not boq_sales_order:
			continue

		if not row.sales_order:
			frappe.db.set_value(
				"RA Bill", row.name, "sales_order", boq_sales_order, update_modified=False
			)
		elif row.sales_order != boq_sales_order:
			logger.warning(
				"Kept mismatched RA Bill %s Sales Order %s; BOQ %s points to %s",
				row.name,
				row.sales_order,
				row.boq,
				boq_sales_order,
			)
			continue

		if (
			row.sales_invoice
			and _has_field("Sales Invoice", "sales_order")
			and frappe.db.exists("Sales Invoice", row.sales_invoice)
		):
			invoice_sales_order = frappe.db.get_value(
				"Sales Invoice", row.sales_invoice, "sales_order"
			)
			if not invoice_sales_order:
				frappe.db.set_value(
					"Sales Invoice",
					row.sales_invoice,
					"sales_order",
					boq_sales_order,
					update_modified=False,
				)
