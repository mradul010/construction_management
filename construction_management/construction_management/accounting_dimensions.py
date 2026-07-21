import frappe
from frappe import _


def get_ra_bill_project_cost_center(ra_bill=None, project=None, company=None):
	ra_bill_values = _get_ra_bill_values(ra_bill)
	project = project or ra_bill_values.get("project")
	company = company or _get_ra_bill_company(ra_bill_values) or _get_project_company(project)

	cost_center = _get_first_value(
		ra_bill_values,
		("custom_cost_center", "cost_center"),
	)
	if _is_valid_cost_center(cost_center, company):
		return cost_center

	cost_center = _get_project_cost_center(project)
	if _is_valid_cost_center(cost_center, company):
		return cost_center

	cost_center = _get_construction_settings_cost_center()
	if _is_valid_cost_center(cost_center, company):
		return cost_center

	cost_center = _get_company_cost_center(company)
	if _is_valid_cost_center(cost_center, company):
		return cost_center

	if company:
		frappe.throw(_("Please set a default Cost Center for company {0}.").format(company))

	return None


def apply_ra_bill_cost_center_to_sales_invoice(invoice, method=None):
	if not invoice or not invoice.meta.has_field("ra_bill") or not invoice.get("ra_bill"):
		return

	ra_bill_values = _get_ra_bill_values(invoice.ra_bill)
	project = invoice.get("project") or ra_bill_values.get("project")
	if project and invoice.meta.has_field("project") and not invoice.get("project"):
		invoice.project = project

	company = invoice.get("company") or _get_ra_bill_company(ra_bill_values) or _get_project_company(project)
	cost_center = get_ra_bill_project_cost_center(invoice.ra_bill, project=project, company=company)
	if not cost_center:
		return

	_set_if_empty(invoice, "cost_center", cost_center)
	for row in invoice.get("items") or []:
		_set_if_empty(row, "cost_center", cost_center)


def apply_ra_bill_cost_center_to_payment_entry(payment_entry, retention_account=None):
	context = get_payment_entry_ra_bill_context(payment_entry)
	if not context:
		return

	cost_center = get_ra_bill_project_cost_center(
		context.ra_bill,
		project=context.project,
		company=context.company,
	)
	if not cost_center:
		return

	if payment_entry.meta.has_field("project") and context.project and not payment_entry.get("project"):
		payment_entry.project = context.project

	if not retention_account:
		from construction_management.construction_management.utils.accounting import (
			get_construction_account,
		)

		retention_account = get_construction_account(
			context.company,
			"retention_receivable",
			project=context.project,
			transaction=payment_entry,
		)

	for row in payment_entry.get("deductions") or []:
		if row.account == retention_account:
			row.cost_center = cost_center


def get_payment_entry_ra_bill_context(payment_entry):
	if not payment_entry:
		return None

	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue

		invoice_fields = ["name", "company", "project"]
		invoice_meta = frappe.get_meta("Sales Invoice")
		if invoice_meta.has_field("ra_bill"):
			invoice_fields.append("ra_bill")
		if invoice_meta.has_field("retention_record"):
			invoice_fields.append("retention_record")

		invoice_values = frappe.db.get_value(
			"Sales Invoice",
			reference.reference_name,
			invoice_fields,
			as_dict=True,
		)
		if not invoice_values or not invoice_values.get("ra_bill"):
			continue
		if invoice_values.get("retention_record"):
			continue

		ra_bill_values = _get_ra_bill_values(invoice_values.ra_bill)
		project = invoice_values.get("project") or ra_bill_values.get("project")
		return frappe._dict(
			{
				"company": invoice_values.company or _get_ra_bill_company(ra_bill_values),
				"project": project,
				"ra_bill": invoice_values.ra_bill,
				"sales_invoice": invoice_values.name,
				"allocated_amount": reference.allocated_amount,
			}
		)

	return None


def _get_ra_bill_values(ra_bill):
	if not ra_bill:
		return frappe._dict()

	fields = ["name", "project", "boq", "sales_order"]
	meta = frappe.get_meta("RA Bill")
	for fieldname in ("custom_cost_center", "cost_center", "company"):
		if meta.has_field(fieldname):
			fields.append(fieldname)

	return frappe.db.get_value("RA Bill", ra_bill, fields, as_dict=True) or frappe._dict()


def _get_ra_bill_company(ra_bill_values):
	if not ra_bill_values:
		return None

	if ra_bill_values.get("company"):
		return ra_bill_values.company

	for doctype, fieldname in (("BOQ", "boq"), ("Sales Order", "sales_order")):
		document_name = ra_bill_values.get(fieldname)
		if document_name and frappe.get_meta(doctype).has_field("company"):
			company = frappe.db.get_value(doctype, document_name, "company")
			if company:
				return company

	return _get_project_company(ra_bill_values.get("project"))


def _get_first_value(values, fieldnames):
	for fieldname in fieldnames:
		value = values.get(fieldname)
		if value:
			return value

	return None


def _get_project_company(project):
	if not project or not frappe.get_meta("Project").has_field("company"):
		return None

	return frappe.db.get_value("Project", project, "company")


def _get_project_cost_center(project):
	if not project or not frappe.get_meta("Project").has_field("cost_center"):
		return None

	return frappe.db.get_value("Project", project, "cost_center")


def _get_construction_settings_cost_center():
	if not frappe.db.exists("DocType", "Construction Settings"):
		return None

	meta = frappe.get_meta("Construction Settings")
	for fieldname in ("default_project_cost_center", "project_cost_center", "default_cost_center"):
		if meta.has_field(fieldname):
			return frappe.db.get_single_value("Construction Settings", fieldname)

	return None


def _get_company_cost_center(company):
	if not company:
		return None

	if frappe.get_meta("Company").has_field("default_project_cost_center"):
		cost_center = frappe.db.get_value("Company", company, "default_project_cost_center")
		if cost_center:
			return cost_center

	return frappe.db.get_value("Company", company, "cost_center")


def _is_valid_cost_center(cost_center, company=None):
	if not cost_center:
		return False

	filters = {"name": cost_center, "is_group": 0, "disabled": 0}
	if company:
		filters["company"] = company

	return bool(frappe.db.exists("Cost Center", filters))


def _set_if_empty(doc, fieldname, value):
	if doc.meta.has_field(fieldname) and value and not doc.get(fieldname):
		doc.set(fieldname, value)
