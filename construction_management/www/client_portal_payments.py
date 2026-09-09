import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

from construction_management.portal_utils import (
	format_currency_value,
	get_authorized_customer_project,
	get_customer_projects,
	get_primary_customer_project,
	get_project_financial_summary,
	setup_client_portal_context,
)


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "payments")
	context.projects = get_customer_projects(context.customers)
	requested_project = frappe.form_dict.get("project")

	if requested_project:
		context.selected_project = get_authorized_customer_project(requested_project, context.customers)
	else:
		context.selected_project = get_primary_customer_project(context.customers)

	context.financial_summary = (
		get_project_financial_summary(
			context.selected_project.name,
			context.customers,
			project=context.selected_project,
		)
		if context.selected_project
		else None
	)
	context.payment_view = get_payment_view(context.financial_summary)


def get_payment_view(financial_summary):
	if not financial_summary:
		return frappe._dict()

	invoices = sorted(
		financial_summary.invoices or [],
		key=lambda row: (row.posting_date or "", row.creation or "", row.name or ""),
		reverse=True,
	)
	payments = sorted(
		(financial_summary.invoice_payments or []) + (financial_summary.advance_payments or []),
		key=lambda row: (row.posting_date or "", row.creation or "", row.name or ""),
		reverse=True,
	)
	payment_progress = (
		min(flt(financial_summary.total_received) / flt(financial_summary.contract_value) * 100, 100)
		if flt(financial_summary.contract_value)
		else flt(financial_summary.collection_progress)
	)

	return frappe._dict(
		{
			"payment_progress": payment_progress,
			"display_payment_progress": f"{flt(payment_progress, 1)}%",
			"payment_status": get_payment_status(financial_summary),
			"latest_invoice": invoices[0] if invoices else None,
			"latest_payment": payments[0] if payments else None,
			"latest_payment_method": payments[0].mode_of_payment if payments and payments[0].mode_of_payment else _("Not specified"),
			"statement_rows": get_payment_statement_rows(financial_summary),
			"payment_rows": payments,
			"invoice_cards": invoices[:4],
			"receipt_cards": payments[:4],
		}
	)


def get_payment_status(financial_summary):
	if flt(financial_summary.invoice_outstanding) <= 0 and flt(financial_summary.total_invoiced) > 0:
		return _("Paid")
	if flt(financial_summary.total_received) > 0:
		return _("Partially Paid")
	if flt(financial_summary.total_invoiced) > 0:
		return _("Pending")
	return _("No Invoices")


def get_payment_statement_rows(financial_summary):
	rows = []
	running_balance = 0
	for row in financial_summary.statement or []:
		is_invoice = row.type == _("Invoice") or row.type == "Invoice"
		debit = flt(row.amount) if is_invoice else 0
		credit = 0 if is_invoice else flt(row.amount)
		running_balance += debit - credit
		rows.append(
			frappe._dict(
				{
					"posting_date": row.posting_date,
					"display_date": row.display_date or (formatdate(row.posting_date) if row.posting_date else _("Not specified")),
					"document_type": row.type,
					"reference": row.reference,
					"description": row.description,
					"display_debit": format_currency_value(debit, financial_summary.currency) if debit else "-",
					"display_credit": format_currency_value(credit, financial_summary.currency) if credit else "-",
					"display_balance": format_currency_value(running_balance, financial_summary.currency),
					"status": row.status,
				}
			)
		)

	return sorted(rows, key=lambda row: getdate(row.posting_date) if row.posting_date else getdate("1900-01-01"), reverse=True)
