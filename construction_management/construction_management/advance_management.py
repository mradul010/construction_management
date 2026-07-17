import frappe
from frappe import _
from frappe.utils import flt


ADVANCE_TOLERANCE = 0.0001
SALES_ORDER_ADVANCE_SUMMARY_FIELDS = (
	"total_advance_received",
	"total_advance_recovered",
	"remaining_advance_balance",
)
PROJECT_ADVANCE_SUMMARY_FIELDS = (
	"total_sales_order_value",
	"total_customer_advance_received",
	"total_advance_recovered",
	"remaining_advance_balance",
	"advance_recovery_percent",
	"sales_orders_with_advance",
	"last_advance_receipt_date",
	"last_advance_recovery_date",
	"advance_status",
)


def has_field(doctype, fieldname):
	try:
		return frappe.get_meta(doctype).has_field(fieldname)
	except Exception:
		return False


def get_ra_bill_sales_order(ra_bill):
	if not ra_bill:
		return None

	if isinstance(ra_bill, str):
		values = frappe.db.get_value("RA Bill", ra_bill, ["sales_order", "boq"], as_dict=True)
	else:
		values = frappe._dict({"sales_order": ra_bill.get("sales_order"), "boq": ra_bill.get("boq")})

	if values and values.get("sales_order"):
		return values.sales_order
	if values and values.get("boq") and has_field("BOQ", "sales_order"):
		return frappe.db.get_value("BOQ", values.boq, "sales_order")
	return None


def get_ra_bill_sales_invoice_receivable_account(customer, company, currency):
	"""
	Use ERPNext's normal Customer receivable account when it can carry this
	invoice currency. Standard advance lookup filters Payment Entries by the
	Sales Invoice party account, so a custom RA Bill receivable account can hide
	valid Sales Order advances.
	"""
	if not company:
		return None

	from erpnext.accounts.party import get_party_account

	party_account = get_party_account("Customer", customer, company) if customer else None
	if party_account:
		account_currency = frappe.get_cached_value("Account", party_account, "account_currency")
		if account_currency == currency:
			return party_account

	from construction_management.construction_management.setup import (
		get_or_create_ra_bill_receivable_account,
	)

	return get_or_create_ra_bill_receivable_account(company, currency)


def get_sales_order_advance_received(sales_order):
	if not sales_order:
		return 0

	if has_field("Sales Order", "advance_paid"):
		return flt(frappe.db.get_value("Sales Order", sales_order, "advance_paid"))

	return flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(per.`allocated_amount`), 0)
			FROM `tabPayment Entry Reference` per
			INNER JOIN `tabPayment Entry` pe ON pe.`name` = per.`parent`
			WHERE pe.`docstatus` = 1
				AND pe.`payment_type` = 'Receive'
				AND per.`reference_doctype` = 'Sales Order'
				AND per.`reference_name` = %s
			""",
			sales_order,
		)[0][0]
	)


def get_sales_order_advance_recovered(sales_order, exclude_invoice=None, exclude_ra_bill=None):
	if not sales_order:
		return 0

	header_condition = "0=1"
	if has_field("Sales Invoice", "sales_order"):
		header_condition = "si.`sales_order` = %(sales_order)s"

	ra_bill_condition = ""
	if exclude_ra_bill and has_field("Sales Invoice", "ra_bill"):
		ra_bill_condition = "AND COALESCE(si.`ra_bill`, '') != %(exclude_ra_bill)s"

	exclude_invoice_condition = ""
	if exclude_invoice:
		exclude_invoice_condition = "AND si.`name` != %(exclude_invoice)s"

	return flt(
		frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(sia.`allocated_amount`), 0)
			FROM `tabSales Invoice Advance` sia
			INNER JOIN `tabSales Invoice` si ON si.`name` = sia.`parent`
			WHERE si.`docstatus` = 1
				{exclude_invoice_condition}
				{ra_bill_condition}
				AND (
					{header_condition}
					OR EXISTS (
						SELECT 1
						FROM `tabSales Invoice Item` sii
						WHERE sii.`parent` = si.`name`
							AND sii.`sales_order` = %(sales_order)s
					)
				)
			""",
			{
				"sales_order": sales_order,
				"exclude_invoice": exclude_invoice,
				"exclude_ra_bill": exclude_ra_bill,
			},
		)[0][0]
	)


def get_sales_order_last_advance_receipt_date(sales_order):
	if not sales_order:
		return None

	return frappe.db.sql(
		"""
		SELECT MAX(pe.`posting_date`)
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.`name` = per.`parent`
		WHERE pe.`docstatus` = 1
			AND pe.`payment_type` = 'Receive'
			AND per.`reference_doctype` = 'Sales Order'
			AND per.`reference_name` = %s
		""",
		sales_order,
	)[0][0]


def get_sales_order_last_advance_recovery_date(sales_order):
	if not sales_order:
		return None

	header_condition = "0=1"
	if has_field("Sales Invoice", "sales_order"):
		header_condition = "si.`sales_order` = %(sales_order)s"

	return frappe.db.sql(
		f"""
		SELECT MAX(si.`posting_date`)
		FROM `tabSales Invoice Advance` sia
		INNER JOIN `tabSales Invoice` si ON si.`name` = sia.`parent`
		WHERE si.`docstatus` = 1
			AND sia.`allocated_amount` > 0
			AND (
				{header_condition}
				OR EXISTS (
					SELECT 1
					FROM `tabSales Invoice Item` sii
					WHERE sii.`parent` = si.`name`
						AND sii.`sales_order` = %(sales_order)s
				)
			)
		""",
		{"sales_order": sales_order},
	)[0][0]


def get_sales_order_advance_summary(sales_order, exclude_invoice=None, exclude_ra_bill=None):
	received = get_sales_order_advance_received(sales_order)
	recovered = get_sales_order_advance_recovered(
		sales_order,
		exclude_invoice=exclude_invoice,
		exclude_ra_bill=exclude_ra_bill,
	)
	return frappe._dict(
		{
			"sales_order": sales_order,
			"total_advance_received": received,
			"total_advance_recovered": recovered,
			"remaining_advance_balance": max(received - recovered, 0),
		}
	)


def get_sales_order_project(sales_order):
	if not sales_order:
		return None
	return frappe.db.get_value("Sales Order", sales_order, "project")


def update_sales_order_and_project_advance_summary(sales_order):
	if not sales_order:
		return
	update_sales_order_advance_summary(sales_order)
	recalculate_project_advance_summary(get_sales_order_project(sales_order))


def update_sales_order_advance_summary(sales_order):
	if not sales_order:
		return

	summary = get_sales_order_advance_summary(sales_order)
	updates = {}
	for fieldname in SALES_ORDER_ADVANCE_SUMMARY_FIELDS:
		if has_field("Sales Order", fieldname):
			updates[fieldname] = summary.get(fieldname)

	if updates:
		frappe.db.set_value("Sales Order", sales_order, updates, update_modified=False)


def sync_sales_order_summaries_from_doc(doc):
	for sales_order in get_sales_orders_from_doc(doc):
		update_sales_order_and_project_advance_summary(sales_order)


def get_sales_orders_from_doc(doc):
	sales_orders = set()
	if not doc:
		return sales_orders

	if doc.doctype == "Payment Entry":
		for row in doc.get("references") or []:
			if row.reference_doctype == "Sales Order" and row.reference_name:
				sales_orders.add(row.reference_name)
		return sales_orders

	if doc.doctype == "Sales Invoice":
		if has_field("Sales Invoice", "sales_order") and doc.get("sales_order"):
			sales_orders.add(doc.sales_order)
		for row in doc.get("items") or []:
			if row.get("sales_order"):
				sales_orders.add(row.sales_order)
		if has_field("Sales Invoice", "ra_bill") and doc.get("ra_bill"):
			sales_order = get_ra_bill_sales_order(doc.ra_bill)
			if sales_order:
				sales_orders.add(sales_order)
	return sales_orders


def get_project_sales_orders(project_name):
	if not project_name:
		return []

	return frappe.get_all(
		"Sales Order",
		filters={"project": project_name, "docstatus": 1},
		fields=[
			"name",
			"grand_total",
			"base_grand_total",
			"currency",
			"conversion_rate",
			"status",
		],
		order_by="transaction_date asc, name asc",
	)


def get_project_advance_status(received, recovered, remaining):
	if flt(received) <= 0:
		return "No Advance"
	if flt(recovered) <= 0:
		return "Advance Available"
	if flt(remaining) > ADVANCE_TOLERANCE:
		return "Partially Recovered"
	return "Fully Recovered"


def get_project_advance_summary(project_name):
	sales_orders = get_project_sales_orders(project_name)
	if not sales_orders:
		return frappe._dict(
			{
				"project": project_name,
				"currency": None,
				"total_sales_order_value": 0,
				"total_customer_advance_received": 0,
				"total_advance_recovered": 0,
				"remaining_advance_balance": 0,
				"advance_recovery_percent": 0,
				"sales_orders_with_advance": 0,
				"last_advance_receipt_date": None,
				"last_advance_recovery_date": None,
				"advance_status": "No Advance",
			}
		)

	currencies = {row.currency for row in sales_orders if row.get("currency")}
	use_base_currency = len(currencies) > 1
	project_company = frappe.db.get_value("Project", project_name, "company")
	display_currency = None
	if use_base_currency and project_company:
		display_currency = frappe.get_cached_value("Company", project_company, "default_currency")
	elif currencies:
		display_currency = next(iter(currencies))
	total_sales_order_value = 0
	total_received = 0
	total_recovered = 0
	sales_orders_with_advance = 0
	last_receipt_date = None
	last_recovery_date = None

	for row in sales_orders:
		total_sales_order_value += flt(
			row.get("base_grand_total") if use_base_currency else row.get("grand_total")
		)
		summary = get_sales_order_advance_summary(row.name)
		received = flt(summary.total_advance_received)
		recovered = flt(summary.total_advance_recovered)
		if use_base_currency:
			conversion_rate = flt(row.get("conversion_rate") or 1)
			received *= conversion_rate
			recovered *= conversion_rate

		total_received += received
		total_recovered += recovered
		if received > ADVANCE_TOLERANCE:
			sales_orders_with_advance += 1

		receipt_date = get_sales_order_last_advance_receipt_date(row.name)
		recovery_date = get_sales_order_last_advance_recovery_date(row.name)
		if receipt_date and (not last_receipt_date or receipt_date > last_receipt_date):
			last_receipt_date = receipt_date
		if recovery_date and (not last_recovery_date or recovery_date > last_recovery_date):
			last_recovery_date = recovery_date

	remaining = max(total_received - total_recovered, 0)
	recovery_percent = (total_recovered / total_received * 100) if total_received else 0
	return frappe._dict(
		{
			"project": project_name,
			"currency": display_currency,
			"total_sales_order_value": total_sales_order_value,
			"total_customer_advance_received": total_received,
			"total_advance_recovered": total_recovered,
			"remaining_advance_balance": remaining,
			"advance_recovery_percent": recovery_percent,
			"sales_orders_with_advance": sales_orders_with_advance,
			"last_advance_receipt_date": last_receipt_date,
			"last_advance_recovery_date": last_recovery_date,
			"advance_status": get_project_advance_status(total_received, total_recovered, remaining),
		}
	)


def recalculate_project_advance_summary(project_name):
	if not project_name or not frappe.db.exists("Project", project_name):
		return

	summary = get_project_advance_summary(project_name)
	updates = {}
	for fieldname in PROJECT_ADVANCE_SUMMARY_FIELDS:
		if has_field("Project", fieldname):
			updates[fieldname] = summary.get(fieldname)

	if updates:
		frappe.db.set_value("Project", project_name, updates, update_modified=False)


def set_item_sales_order(invoice_items, sales_order):
	if not sales_order or not has_field("Sales Invoice Item", "sales_order"):
		return

	for row in invoice_items:
		if flt(row.get("qty")) * flt(row.get("rate")) > 0:
			row["sales_order"] = sales_order


def update_ra_bill_advance_fields(ra_bill):
	sales_order = get_ra_bill_sales_order(ra_bill)
	if not sales_order:
		return frappe._dict()

	summary = get_sales_order_advance_summary(
		sales_order,
		exclude_invoice=ra_bill.get("sales_invoice"),
		exclude_ra_bill=ra_bill.get("name"),
	)
	remaining_before = summary.remaining_advance_balance
	proposed = 0
	if flt(ra_bill.get("advance_recovery_percent")) > 0:
		proposed = flt(ra_bill.get("gross_amount")) * flt(ra_bill.get("advance_recovery_percent")) / 100
		proposed = min(proposed, remaining_before, flt(ra_bill.get("grand_total")))

	allocated_from_rows = sum(flt(row.allocated_amount) for row in ra_bill.get("advances") or [])
	actual = proposed if flt(ra_bill.get("advance_recovery_percent")) > 0 else allocated_from_rows
	values = frappe._dict(
		{
			"sales_order": sales_order,
			"total_advance_received": summary.total_advance_received,
			"previously_recovered_advance": summary.total_advance_recovered,
			"remaining_advance_before_current_bill": remaining_before,
			"proposed_advance_recovery": proposed,
			"actual_advance_recovered": actual,
			"remaining_advance_after_current_bill": max(remaining_before - actual, 0),
		}
	)

	for fieldname, value in values.items():
		if ra_bill.meta.has_field(fieldname):
			ra_bill.set(fieldname, value)
	return values


def validate_ra_bill_advance_recovery(ra_bill):
	values = update_ra_bill_advance_fields(ra_bill)
	if not values:
		return

	actual = flt(values.actual_advance_recovered)
	if actual < -ADVANCE_TOLERANCE:
		frappe.throw(_("Advance recovered cannot be negative."))

	if actual > flt(values.remaining_advance_before_current_bill) + ADVANCE_TOLERANCE:
		frappe.throw(
			_(
				"Advance recovered in this RA Bill cannot exceed the remaining advance balance "
				"for Sales Order {0}."
			).format(values.sales_order)
		)

	if actual > flt(ra_bill.get("grand_total")) + ADVANCE_TOLERANCE:
		frappe.throw(_("Advance recovered cannot exceed the RA Bill Grand Total."))


def get_ra_bill_advance_recovery_target(ra_bill):
	if not ra_bill:
		return 0

	values = update_ra_bill_advance_fields(ra_bill)
	if values and flt(values.get("actual_advance_recovered")) > 0:
		return flt(values.actual_advance_recovered)

	return flt(ra_bill.get("total_advance")) or flt(ra_bill.get("proposed_advance_recovery"))


def apply_standard_advances_to_sales_invoice(si, target_amount=None):
	if not si.meta.has_field("advances") or not hasattr(si, "set_advances"):
		return 0

	si.only_include_allocated_payments = 1
	si.set_advances()
	target = flt(target_amount)
	if target <= 0:
		target = flt(si.get("grand_total"))

	allocated = 0
	kept_rows = []
	for row in si.get("advances") or []:
		remaining = max(target - allocated, 0)
		if remaining <= ADVANCE_TOLERANCE:
			continue
		next_allocated = min(flt(row.allocated_amount), remaining)
		if next_allocated <= ADVANCE_TOLERANCE:
			continue
		row.allocated_amount = next_allocated
		allocated += next_allocated
		kept_rows.append(row)

	si.set("advances", [row.as_dict() for row in kept_rows])
	if si.meta.has_field("total_advance"):
		si.total_advance = allocated
	return allocated


def apply_ra_bill_advances_to_sales_invoice(si, ra_bill):
	target = get_ra_bill_advance_recovery_target(ra_bill)
	if target <= ADVANCE_TOLERANCE and not ra_bill.get("allocate_advances_automatically"):
		return 0

	allocated = apply_standard_advances_to_sales_invoice(si, target)
	if target > ADVANCE_TOLERANCE and allocated + ADVANCE_TOLERANCE < target:
		frappe.throw(
			_(
				"Could not allocate the requested advance recovery of {0}. "
				"Only {1} is available through standard Sales Invoice advances for this Sales Order."
			).format(
				frappe.format_value(target, {"fieldtype": "Currency"}),
				frappe.format_value(allocated, {"fieldtype": "Currency"}),
			)
		)

	if ra_bill.meta.has_field("actual_advance_recovered"):
		ra_bill.actual_advance_recovered = allocated
	if ra_bill.meta.has_field("total_advance"):
		ra_bill.total_advance = allocated
	if ra_bill.meta.has_field("outstanding_amount"):
		ra_bill.outstanding_amount = flt(ra_bill.get("grand_total")) - allocated
	if ra_bill.meta.has_field("remaining_advance_after_current_bill"):
		before = flt(ra_bill.get("remaining_advance_before_current_bill"))
		ra_bill.remaining_advance_after_current_bill = max(before - allocated, 0)
	return allocated


def validate_sales_invoice_advance_consistency(si, method=None):
	if si.doctype != "Sales Invoice":
		return

	ra_bill = si.get("ra_bill") if has_field("Sales Invoice", "ra_bill") else None
	if not ra_bill:
		return

	sales_order = si.get("sales_order") if has_field("Sales Invoice", "sales_order") else None
	if not sales_order and ra_bill:
		sales_order = get_ra_bill_sales_order(ra_bill)
	if not sales_order:
		return

	if ra_bill:
		ra_bill_sales_order = get_ra_bill_sales_order(ra_bill)
		if ra_bill_sales_order and sales_order != ra_bill_sales_order:
			frappe.throw(
				_(
					"Sales Invoice Sales Order must match the Sales Order linked to the originating RA Bill."
				)
			)

	allocated = sum(flt(row.allocated_amount) for row in si.get("advances") or [])
	if allocated <= 0:
		return

	remaining = get_sales_order_advance_summary(
		sales_order,
		exclude_invoice=si.name if not si.is_new() else None,
		exclude_ra_bill=ra_bill,
	).remaining_advance_balance
	if allocated > remaining + ADVANCE_TOLERANCE:
		frappe.throw(
			_(
				"Sales Invoice advance allocation cannot exceed the remaining advance balance "
				"for Sales Order {0}."
			).format(sales_order)
		)


def on_sales_invoice_advance_change(doc, method=None):
	sync_sales_order_summaries_from_doc(doc)


def on_payment_entry_advance_change(doc, method=None):
	sync_sales_order_summaries_from_doc(doc)


def on_sales_order_advance_context_change(doc, method=None):
	project_names = set()
	if doc.get("project"):
		project_names.add(doc.project)

	previous = doc.get_doc_before_save()
	if previous and previous.get("project"):
		project_names.add(previous.project)

	if doc.docstatus == 1:
		update_sales_order_advance_summary(doc.name)

	for project_name in project_names:
		recalculate_project_advance_summary(project_name)
