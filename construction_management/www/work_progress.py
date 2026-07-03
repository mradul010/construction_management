import frappe
from frappe.utils import flt

from construction_management.portal_utils import (
	get_boq_customer_field,
	log_portal_access,
	require_portal_customer,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	context.title = "Work Progress"
	context.customer = customer
	context.rows = get_work_progress(customer)


def get_work_progress(customer):
	boq_customer_field = get_boq_customer_field()
	if has_ra_bill_transaction_rows(customer, boq_customer_field):
		return get_work_progress_from_transactions(customer, boq_customer_field)

	return get_work_progress_from_ra_bill_items(customer, boq_customer_field)


def has_ra_bill_transaction_rows(customer, boq_customer_field):
	try:
		if not frappe.db.table_exists("RA Bill Transaction"):
			return False
	except Exception:
		return False

	return bool(
		frappe.db.sql(
			"""
			SELECT t.name
			FROM `tabRA Bill Transaction` t
			JOIN `tabRA Bill` rb ON rb.name = t.ra_bill
			JOIN `tabBOQ` b ON b.name = t.boq
			WHERE rb.customer = %s
			  AND b.`{boq_customer_field}` = %s
			  AND rb.docstatus = 1
			LIMIT 1
			""".format(boq_customer_field=boq_customer_field),
			(customer, customer),
		)
	)


def get_work_progress_from_transactions(customer, boq_customer_field):
	rows = frappe.db.sql(
		"""
		SELECT
			t.boq,
			t.boq_item,
			MAX(t.category_name) AS category_name,
			MAX(t.sub_category) AS sub_category,
			MAX(t.item_name) AS item_name,
			MAX(t.boq_qty) AS boq_qty,
			SUM(t.current_qty) AS completed_qty,
			SUM(t.current_amount) AS completed_amount
		FROM `tabRA Bill Transaction` t
		JOIN `tabRA Bill` rb ON rb.name = t.ra_bill
		JOIN `tabBOQ` b ON b.name = t.boq
		WHERE rb.customer = %s
		  AND b.`{boq_customer_field}` = %s
		  AND rb.docstatus = 1
		GROUP BY t.boq, t.boq_item
		ORDER BY t.boq, category_name, sub_category, item_name
		""".format(boq_customer_field=boq_customer_field),
		(customer, customer),
		as_dict=True,
	)
	return add_progress_values(rows)


def get_work_progress_from_ra_bill_items(customer, boq_customer_field):
	rows = frappe.db.sql(
		"""
		SELECT
			rb.boq,
			rbi.boq_item,
			MAX(rbi.category_name) AS category_name,
			MAX(rbi.sub_category) AS sub_category,
			MAX(bi.item_name) AS item_name,
			MAX(COALESCE(NULLIF(rbi.boq_qty, 0), bi.qty, 0)) AS boq_qty,
			SUM(
				CASE
					WHEN COALESCE(rbi.current_qty, 0) > 0 THEN rbi.current_qty
					ELSE COALESCE(NULLIF(rbi.boq_qty, 0), bi.qty, 0)
						* COALESCE(rbi.work_percent, 0) / 100
				END
			) AS completed_qty,
			SUM(
				CASE
					WHEN COALESCE(rbi.current_amount, 0) > 0 THEN rbi.current_amount
					ELSE (
						CASE
							WHEN COALESCE(rbi.current_qty, 0) > 0 THEN rbi.current_qty
							ELSE COALESCE(NULLIF(rbi.boq_qty, 0), bi.qty, 0)
								* COALESCE(rbi.work_percent, 0) / 100
						END
					) * COALESCE(rbi.boq_rate, bi.unit_rate, 0)
				END
			) AS completed_amount
		FROM `tabRA Bill Item` rbi
		JOIN `tabRA Bill` rb ON rb.name = rbi.parent
		JOIN `tabBOQ` b ON b.name = rb.boq
		LEFT JOIN `tabBOQ Item` bi ON bi.name = rbi.boq_item
		WHERE rb.customer = %s
		  AND b.`{boq_customer_field}` = %s
		  AND rb.docstatus = 1
		GROUP BY rb.boq, rbi.boq_item
		ORDER BY rb.boq, category_name, sub_category, item_name
		""".format(boq_customer_field=boq_customer_field),
		(customer, customer),
		as_dict=True,
	)
	return add_progress_values(rows)


def add_progress_values(rows):
	for row in rows:
		row.boq_qty = flt(row.boq_qty)
		row.completed_qty = flt(row.completed_qty)
		row.completed_amount = flt(row.completed_amount)
		row.remaining_qty = row.boq_qty - row.completed_qty
		row.progress_percent = (row.completed_qty / row.boq_qty * 100) if row.boq_qty else 0
	return rows
