import frappe
from frappe.utils import flt

from construction_management.portal_utils import (
	get_boq_customer_field,
	get_request_filters,
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	setup_portal_context(
		context,
		"Work Progress",
		description="Review completed quantity, remaining quantity and progress against BOQ items.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "Work Progress", "route": "/work-progress"},
		],
	)
	context.customer = customer
	context.filters = get_request_filters("search", "project", "completion")
	all_rows = get_work_progress(customer)
	context.projects = sorted({row.project for row in all_rows if row.project})
	context.rows = filter_work_progress_rows(all_rows, context.filters)


def get_work_progress(customer):
	boq_customer_field = get_boq_customer_field()
	if has_ra_bill_transaction_table():
		return get_work_progress_from_transactions(customer, boq_customer_field)

	return get_work_progress_from_ra_bill_items(customer, boq_customer_field)


def has_ra_bill_transaction_table():
	try:
		return (
			frappe.db.table_exists("RA Bill Transaction")
			and frappe.get_meta("RA Bill Transaction").has_field("original_boq")
			and frappe.get_meta("RA Bill Transaction").has_field("boq_item_key")
		)
	except Exception:
		return False


def get_work_progress_from_transactions(customer, boq_customer_field):
	rows = frappe.db.sql(
		"""
		SELECT
			b.name AS boq,
			b.project AS project,
			bi.name AS boq_item,
			bi.boq_parent_category AS category_name,
			bi.boq_category AS sub_category,
			bi.item_name AS item_name,
			bi.qty AS boq_qty,
			COALESCE(tx.completed_qty, 0) AS completed_qty,
			COALESCE(tx.completed_amount, 0) AS completed_amount
		FROM `tabBOQ` b
		JOIN `tabBOQ Item` bi
		  ON bi.parent = b.name
		 AND bi.parenttype = 'BOQ'
		 AND bi.parentfield = 'items'
		LEFT JOIN (
			SELECT
				COALESCE(NULLIF(t.original_boq, ''), NULLIF(tb.original_boq, ''), t.boq)
					AS original_boq,
				COALESCE(
					NULLIF(t.boq_item_key, ''),
					NULLIF(tbi.boq_item_key, ''),
					NULLIF(tbi.component_key, ''),
					t.boq_item
				) AS boq_item_key,
				SUM(t.current_qty) AS completed_qty,
				SUM(t.current_amount) AS completed_amount
			FROM `tabRA Bill Transaction` t
			JOIN `tabRA Bill` rb ON rb.name = t.ra_bill
			LEFT JOIN `tabBOQ` tb
			  ON tb.name = COALESCE(NULLIF(t.boq_revision, ''), NULLIF(t.boq, ''))
			LEFT JOIN `tabBOQ Item` tbi ON tbi.name = t.boq_item
			WHERE rb.customer = %s
			  AND rb.docstatus = 1
			GROUP BY original_boq, boq_item_key
		) tx
		  ON tx.original_boq = COALESCE(NULLIF(b.original_boq, ''), b.name)
		 AND tx.boq_item_key = COALESCE(
				NULLIF(bi.boq_item_key, ''),
				NULLIF(bi.component_key, ''),
				bi.name
			)
		WHERE b.`{boq_customer_field}` = %s
		  AND b.is_active_revision = 1
		  AND b.docstatus != 2
		  AND COALESCE(bi.is_deleted_in_revision, 0) = 0
		ORDER BY b.name, category_name, sub_category, item_name
		""".format(boq_customer_field=boq_customer_field),
		(customer, customer),
		as_dict=True,
	)
	return add_progress_values(rows)


def get_work_progress_from_ra_bill_items(customer, boq_customer_field):
	rows = frappe.db.sql(
		"""
		SELECT
			b.name AS boq,
			b.project AS project,
			bi.name AS boq_item,
			bi.boq_parent_category AS category_name,
			bi.boq_category AS sub_category,
			bi.item_name AS item_name,
			bi.qty AS boq_qty,
			COALESCE(tx.completed_qty, 0) AS completed_qty,
			COALESCE(tx.completed_amount, 0) AS completed_amount
		FROM `tabBOQ` b
		JOIN `tabBOQ Item` bi
		  ON bi.parent = b.name
		 AND bi.parenttype = 'BOQ'
		 AND bi.parentfield = 'items'
		LEFT JOIN (
			SELECT
				COALESCE(NULLIF(rbi.original_boq, ''), NULLIF(rbq.original_boq, ''), rb.boq)
					AS original_boq,
				COALESCE(
					NULLIF(rbi.boq_item_key, ''),
					NULLIF(rbi_boq_item.boq_item_key, ''),
					NULLIF(rbi_boq_item.component_key, ''),
					rbi.boq_item
				) AS boq_item_key,
				SUM(
					CASE
						WHEN COALESCE(rbi.current_qty, 0) > 0 THEN rbi.current_qty
						ELSE COALESCE(NULLIF(rbi.boq_qty, 0), rbi_boq_item.qty, 0)
							* COALESCE(rbi.work_percent, 0) / 100
					END
				) AS completed_qty,
				SUM(
					CASE
						WHEN COALESCE(rbi.current_amount, 0) > 0 THEN rbi.current_amount
						ELSE (
							CASE
								WHEN COALESCE(rbi.current_qty, 0) > 0 THEN rbi.current_qty
								ELSE COALESCE(NULLIF(rbi.boq_qty, 0), rbi_boq_item.qty, 0)
									* COALESCE(rbi.work_percent, 0) / 100
							END
						) * COALESCE(rbi.boq_rate, rbi_boq_item.unit_rate, 0)
					END
				) AS completed_amount
			FROM `tabRA Bill Item` rbi
			JOIN `tabRA Bill` rb ON rb.name = rbi.parent
			LEFT JOIN `tabBOQ` rbq ON rbq.name = COALESCE(NULLIF(rbi.boq_revision, ''), rb.boq)
			LEFT JOIN `tabBOQ Item` rbi_boq_item ON rbi_boq_item.name = rbi.boq_item
			WHERE rb.customer = %s
			  AND rb.docstatus = 1
			GROUP BY original_boq, boq_item_key
		) tx
		  ON tx.original_boq = COALESCE(NULLIF(b.original_boq, ''), b.name)
		 AND tx.boq_item_key = COALESCE(
				NULLIF(bi.boq_item_key, ''),
				NULLIF(bi.component_key, ''),
				bi.name
			)
		WHERE b.`{boq_customer_field}` = %s
		  AND b.is_active_revision = 1
		  AND b.docstatus != 2
		  AND COALESCE(bi.is_deleted_in_revision, 0) = 0
		ORDER BY b.name, category_name, sub_category, item_name
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
		row.remaining_qty = max(0, row.boq_qty - row.completed_qty)
		row.progress_percent = (row.completed_qty / row.boq_qty * 100) if row.boq_qty else 0
	return rows


def filter_work_progress_rows(rows, request_filters):
	search = (request_filters.search or "").lower()
	filtered_rows = []
	for row in rows:
		if request_filters.project and row.project != request_filters.project:
			continue
		if search and not any(
			search in str(value or "").lower()
			for value in (row.project, row.boq, row.category_name, row.sub_category, row.item_name)
		):
			continue
		if request_filters.completion == "complete" and flt(row.progress_percent) < 100:
			continue
		if request_filters.completion == "in_progress" and not (0 < flt(row.progress_percent) < 100):
			continue
		if request_filters.completion == "not_started" and flt(row.progress_percent) > 0:
			continue
		filtered_rows.append(row)

	return filtered_rows
