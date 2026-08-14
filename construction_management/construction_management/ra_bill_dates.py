import frappe
from frappe import _
from frappe.utils import getdate, today

from erpnext.accounts.party import get_due_date as get_party_due_date
from erpnext.controllers.accounts_controller import (
	get_due_date as get_payment_term_due_date,
	get_payment_terms,
)


def get_ra_bill_posting_date(ra_bill):
	return ra_bill.get("posting_date") or ra_bill.get("billing_period_to") or today()


def get_ra_bill_due_date(ra_bill, posting_date=None, company=None):
	posting_date = posting_date or get_ra_bill_posting_date(ra_bill)
	due_date = ra_bill.get("due_date") or get_ra_bill_payment_schedule_due_date(
		ra_bill,
		posting_date,
		company=company,
	)

	if not due_date:
		due_date = posting_date

	if getdate(due_date) < getdate(posting_date):
		if ra_bill.get("due_date"):
			frappe.throw(_("Due Date cannot be before Posting Date."))
		due_date = posting_date

	return due_date


def set_default_ra_bill_invoice_dates(ra_bill, company=None):
	if not ra_bill.get("posting_date"):
		ra_bill.posting_date = get_ra_bill_posting_date(ra_bill)

	if not ra_bill.get("due_date"):
		ra_bill.due_date = get_ra_bill_due_date(
			ra_bill,
			posting_date=ra_bill.posting_date,
			company=company,
		)


def validate_ra_bill_invoice_dates(ra_bill):
	if ra_bill.get("posting_date") and ra_bill.get("due_date"):
		if getdate(ra_bill.due_date) < getdate(ra_bill.posting_date):
			frappe.throw(_("Due Date cannot be before Posting Date."))


def apply_ra_bill_dates_to_sales_invoice(si, ra_bill, company=None):
	posting_date = get_ra_bill_posting_date(ra_bill)
	due_date = get_ra_bill_due_date(ra_bill, posting_date=posting_date, company=company)

	si.posting_date = posting_date
	si.due_date = due_date

	if si.meta.has_field("set_posting_time") and getdate(posting_date) != getdate(today()):
		si.set_posting_time = 1

	sync_sales_invoice_payment_schedule_due_date(si, due_date)


def sync_sales_invoice_payment_schedule_due_date(si, due_date):
	if not si.meta.has_field("payment_schedule"):
		return

	if not si.get("payment_schedule"):
		si.append(
			"payment_schedule",
			{
				"due_date": due_date,
				"invoice_portion": 100,
			},
		)
		return

	for row in si.get("payment_schedule"):
		row.due_date = due_date
		if row.get("discount_date") and getdate(row.discount_date) > getdate(due_date):
			row.discount_date = None


def get_ra_bill_payment_schedule_due_date(ra_bill, posting_date, company=None):
	due_dates = [
		row.due_date for row in ra_bill.get("payment_schedule") or [] if row.get("due_date")
	]
	if due_dates:
		return max(due_dates, key=getdate)

	sales_order_due_dates = get_sales_order_due_dates(ra_bill, posting_date)
	if sales_order_due_dates:
		return max(sales_order_due_dates, key=getdate)

	template_due_dates = get_template_due_dates(
		ra_bill.get("payment_terms_template"),
		posting_date,
	)
	if template_due_dates:
		return max(template_due_dates, key=getdate)

	party_due_date = get_customer_due_date(ra_bill, posting_date, company=company)
	if party_due_date:
		return party_due_date

	return None


def get_sales_order_due_dates(ra_bill, posting_date):
	if not ra_bill.get("sales_order"):
		return []

	schedule_rows = frappe.get_all(
		"Payment Schedule",
		filters={
			"parenttype": "Sales Order",
			"parent": ra_bill.sales_order,
		},
		fields=[
			"payment_term",
			"due_date",
			"due_date_based_on",
			"credit_days",
			"credit_months",
		],
		order_by="idx asc",
	)

	due_dates = []
	for row in schedule_rows:
		due_date = get_schedule_row_due_date(row, posting_date)
		if due_date:
			due_dates.append(due_date)

	if due_dates:
		return due_dates

	template = frappe.db.get_value("Sales Order", ra_bill.sales_order, "payment_terms_template")
	return get_template_due_dates(template, posting_date)


def get_schedule_row_due_date(row, posting_date):
	due_date = None
	if row.get("due_date_based_on"):
		due_date = get_payment_term_due_date(row, posting_date)
	elif row.get("due_date"):
		due_date = row.due_date

	if due_date and getdate(due_date) < getdate(posting_date):
		return posting_date

	return due_date


def get_template_due_dates(template, posting_date):
	if not template:
		return []

	return [
		row.get("due_date")
		for row in get_payment_terms(template, posting_date) or []
		if row.get("due_date")
	]


def get_customer_due_date(ra_bill, posting_date, company=None):
	if not ra_bill.get("customer"):
		return None

	return get_party_due_date(
		posting_date=posting_date,
		party_type="Customer",
		party=ra_bill.customer,
		company=company,
		template_name=ra_bill.get("payment_terms_template"),
	)
