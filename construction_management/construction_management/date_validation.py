import frappe
from frappe import _
from frappe.utils import add_days, formatdate, getdate


def has_field(doctype, fieldname):
	try:
		return frappe.get_meta(doctype).has_field(fieldname)
	except Exception:
		return False


def as_date(value):
	return getdate(value) if value else None


def validate_date_range(from_date, to_date, from_label, to_label):
	from_date = as_date(from_date)
	to_date = as_date(to_date)
	if from_date and to_date and from_date > to_date:
		frappe.throw(_("{0} cannot be after {1}.").format(from_label, to_label))


def validate_date_not_before(value, minimum, value_label, minimum_label):
	value = as_date(value)
	minimum = as_date(minimum)
	if value and minimum and value < minimum:
		frappe.throw(_("{0} cannot be before {1}.").format(value_label, minimum_label))


def validate_date_not_after(value, maximum, value_label, maximum_label):
	value = as_date(value)
	maximum = as_date(maximum)
	if value and maximum and value > maximum:
		frappe.throw(_("{0} cannot be after {1}.").format(value_label, maximum_label))


def get_project_dates(project):
	if not project:
		return frappe._dict()

	fields = [
		fieldname
		for fieldname in (
			"expected_start_date",
			"expected_end_date",
			"actual_start_date",
			"actual_end_date",
			"status",
		)
		if has_field("Project", fieldname)
	]
	if not fields:
		return frappe._dict()

	return frappe.db.get_value("Project", project, fields, as_dict=True) or frappe._dict()


def get_project_start(project_dates):
	return project_dates.get("expected_start_date") or project_dates.get("actual_start_date")


def get_project_end(project_dates):
	return project_dates.get("actual_end_date") or project_dates.get("expected_end_date")


def validate_project_dates(doc, method=None):
	validate_date_range(
		doc.get("expected_start_date"),
		doc.get("expected_end_date"),
		_("Project Start Date"),
		_("Expected End Date"),
	)
	validate_date_not_before(
		doc.get("actual_start_date"),
		doc.get("expected_start_date"),
		_("Actual Start Date"),
		_("Project Start Date"),
	)
	validate_date_range(
		doc.get("actual_start_date"),
		doc.get("actual_end_date"),
		_("Actual Start Date"),
		_("Actual End Date"),
	)
	validate_date_not_before(
		doc.get("actual_end_date"),
		doc.get("expected_start_date"),
		_("Actual End Date"),
		_("Project Start Date"),
	)


def get_sales_order_date(sales_order):
	if not sales_order:
		return None
	if not has_field("Sales Order", "transaction_date"):
		return None
	return frappe.db.get_value("Sales Order", sales_order, "transaction_date")


def get_boq_revision_date(boq):
	if not boq:
		return None
	if not has_field("BOQ", "revision_date"):
		return None
	return frappe.db.get_value("BOQ", boq, "revision_date")


def validate_boq_dates(doc):
	revision_date = doc.get("revision_date")
	project_dates = get_project_dates(doc.get("project"))
	project_start = get_project_start(project_dates)
	project_end = get_project_end(project_dates)

	validate_date_range(
		doc.get("active_from_date"),
		doc.get("active_to_date"),
		_("BOQ Active From Date"),
		_("BOQ Active To Date"),
	)
	validate_date_not_before(
		revision_date,
		project_start,
		_("BOQ Date"),
		_("Project Start Date"),
	)
	validate_date_not_after(
		revision_date,
		project_end,
		_("BOQ Date"),
		_("Project End Date"),
	)
	validate_date_not_before(
		revision_date,
		get_sales_order_date(doc.get("sales_order")),
		_("BOQ Date"),
		_("linked Sales Order Date"),
	)
	_validate_boq_revision_date(doc)
	_validate_boq_date_against_existing_ra_bills(doc)


def _validate_boq_revision_date(doc):
	revision_date = doc.get("revision_date")
	if not revision_date:
		return

	if doc.get("original_boq") and doc.get("original_boq") != doc.name:
		original_date = frappe.db.get_value("BOQ", doc.original_boq, "revision_date")
		validate_date_not_before(
			revision_date,
			original_date,
			_("Revision Date"),
			_("original BOQ Date"),
		)

	if doc.get("parent_boq"):
		previous_date = frappe.db.get_value("BOQ", doc.parent_boq, "revision_date")
		validate_date_not_before(
			revision_date,
			previous_date,
			_("Revision Date"),
			_("previous revision date"),
		)


def _validate_boq_date_against_existing_ra_bills(doc):
	if not doc.name or not doc.get("revision_date"):
		return

	earliest = frappe.db.get_value(
		"RA Bill",
		{"boq": doc.name, "docstatus": ["!=", 2]},
		"billing_period_from",
		order_by="billing_period_from asc",
	)
	validate_date_not_after(
		doc.get("revision_date"),
		earliest,
		_("BOQ Date"),
		_("first RA Bill Billing Period From"),
	)


def validate_ra_bill_dates(doc):
	if doc.docstatus == 2:
		return

	validate_date_range(
		doc.get("billing_period_from"),
		doc.get("billing_period_to"),
		_("Billing Period From"),
		_("Billing Period To"),
	)

	project_dates = get_project_dates(doc.get("project"))
	validate_date_not_before(
		doc.get("billing_period_from"),
		get_project_start(project_dates),
		_("RA Bill Billing Period"),
		_("Project Start Date"),
	)
	validate_date_not_after(
		doc.get("billing_period_to"),
		get_project_end(project_dates),
		_("RA Bill Billing Period"),
		_("Project End Date"),
	)
	validate_date_not_before(
		doc.get("billing_period_from"),
		get_boq_revision_date(doc.get("boq")),
		_("RA Bill Date"),
		_("linked BOQ Date"),
	)
	validate_date_not_before(
		doc.get("billing_period_from"),
		get_sales_order_date(doc.get("sales_order")),
		_("RA Bill Billing Period"),
		_("linked Sales Order Date"),
	)
	_validate_ra_bill_payment_schedule_dates(doc)
	validate_ra_bill_period_overlap(doc)


def _validate_ra_bill_payment_schedule_dates(doc):
	posting_date = doc.get("billing_period_to") or doc.get("billing_period_from")
	for row in doc.get("payment_schedule") or []:
		validate_date_not_before(
			row.get("due_date"),
			posting_date,
			_("RA Bill Due Date"),
			_("Posting Date"),
		)


def validate_ra_bill_period_overlap(doc):
	if doc.docstatus == 2 or not doc.get("billing_period_from") or not doc.get("billing_period_to"):
		return

	filters = {
		"name": ["!=", doc.name],
		"project": doc.get("project"),
		"boq": doc.get("boq"),
		"docstatus": 1,
		"billing_period_from": ["<=", doc.get("billing_period_to")],
		"billing_period_to": [">=", doc.get("billing_period_from")],
	}
	if doc.get("sales_order") and has_field("RA Bill", "sales_order"):
		filters["sales_order"] = doc.sales_order

	conflict = frappe.get_all(
		"RA Bill",
		filters=filters,
		fields=["name", "billing_period_from", "billing_period_to"],
		order_by="billing_period_from asc",
		limit=1,
	)
	if conflict:
		row = conflict[0]
		frappe.throw(
			_("Billing Period overlaps with RA Bill {0} ({1} to {2}).").format(
				row.name,
				formatdate(row.billing_period_from),
				formatdate(row.billing_period_to),
			)
		)


def validate_retention_dates(doc):
	if doc.get("status") == "Cancelled":
		return

	ra_bill_date = _get_ra_bill_reference_date(doc.get("ra_bill"))
	validate_date_not_before(
		doc.get("invoice_date"),
		ra_bill_date,
		_("Retention Invoice Date"),
		_("RA Bill Posting Date"),
	)
	validate_date_not_before(
		doc.get("release_date"),
		ra_bill_date,
		_("Retention Release Date"),
		_("RA Bill Posting Date"),
	)
	if doc.get("status") == "Released" and not doc.get("release_date"):
		frappe.throw(_("Released Retention Record requires a Release Date."))

	project_dates = get_project_dates(doc.get("project"))
	project_completion = project_dates.get("actual_end_date")
	if project_completion:
		validate_date_not_before(
			doc.get("release_date"),
			project_completion,
			_("Retention Release Date"),
			_("Project Completion Date"),
		)


def _get_ra_bill_reference_date(ra_bill):
	if not ra_bill:
		return None
	values = frappe.db.get_value(
		"RA Bill",
		ra_bill,
		["billing_period_to", "billing_period_from"],
		as_dict=True,
	)
	if not values:
		return None
	return values.billing_period_to or values.billing_period_from


def validate_retention_sales_invoice_dates(invoice, method=None):
	retention_record = invoice.get("retention_record") if has_field("Sales Invoice", "retention_record") else None
	ra_bill = invoice.get("ra_bill") if has_field("Sales Invoice", "ra_bill") else None
	if not retention_record and not ra_bill:
		return

	validate_date_not_before(
		invoice.get("due_date"),
		invoice.get("posting_date"),
		_("Sales Invoice Due Date"),
		_("Posting Date"),
	)
	validate_date_not_before(
		invoice.get("posting_date"),
		_get_ra_bill_reference_date(ra_bill),
		_("Sales Invoice Posting Date"),
		_("RA Bill Posting Date"),
	)
	if retention_record:
		release_date = frappe.db.get_value("Retention Record", retention_record, "release_date")
		validate_date_not_before(
			invoice.get("posting_date"),
			release_date,
			_("Retention Sales Invoice Posting Date"),
			_("Retention Release Date"),
		)


def get_next_ra_bill_period_start(project, boq):
	if not project or not boq:
		return None
	latest = frappe.db.get_value(
		"RA Bill",
		{"project": project, "boq": boq, "docstatus": 1},
		"billing_period_to",
		order_by="billing_period_to desc",
	)
	return add_days(latest, 1) if latest else None
