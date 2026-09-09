import re
from html import unescape
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, fmt_money, formatdate, get_datetime, getdate, today


CONSTRUCTION_PORTAL_ITEMS = [
	{"title": _("Dashboard"), "route": "/construction-portal"},
	{"title": _("Projects"), "route": "/construction-projects"},
	{"title": _("BOQ"), "route": "/boq"},
	{"title": _("RA Bills"), "route": "/ra-bill"},
	{"title": _("Work Progress"), "route": "/work-progress"},
	{"title": _("Daily Progress Reports"), "route": "/dprs"},
	{"title": _("Logout"), "route": "/?cmd=web_logout"},
]

QATRA_CLIENT_PORTAL_FALLBACK_LOGO = "/assets/construction_management/images/qatra-logo.svg"
QATRA_CLIENT_PORTAL_ASSET_VERSION = "20260909-login-error"

QATRA_CLIENT_PORTAL_ITEMS = [
	{"key": "dashboard", "title": _("Dashboard"), "route": "/client-portal/dashboard"},
	{"key": "projects", "title": _("Projects"), "route": "/client-portal/projects"},
	{"key": "reports", "title": _("Reports"), "route": "/client-portal/reports"},
	{"key": "documents", "title": _("Documents"), "route": "/client-portal/documents"},
	{"key": "gallery", "title": _("Gallery"), "route": "/client-portal/gallery"},
	{"key": "approvals", "title": _("Approvals"), "route": "/client-portal/approvals"},
	{"key": "payments", "title": _("Payments"), "route": "/client-portal/payments"},
]

QATRA_CLIENT_PORTAL_PAGES = {
	"dashboard": {
		"kicker": _("QATRA Client Portal"),
		"title": _("Dashboard"),
		"subtitle": _("Dashboard implementation coming next."),
	},
	"projects": {
		"kicker": _("Project Portfolio"),
		"title": _("Projects"),
		"subtitle": _("Track all projects linked to your client account."),
	},
	"reports": {
		"kicker": _("Published Updates"),
		"title": _("Reports"),
		"subtitle": _("View published project reports and updates."),
	},
	"documents": {
		"kicker": _("Shared Files"),
		"title": _("Documents"),
		"subtitle": _("Access approved project documents and shared files."),
	},
	"gallery": {
		"kicker": _("Progress Photos"),
		"title": _("Gallery"),
		"subtitle": _("View project progress photos and visual updates."),
	},
	"approvals": {
		"kicker": _("Pending Reviews"),
		"title": _("Approvals"),
		"subtitle": _("Review requests that require your approval."),
	},
	"payments": {
		"kicker": _("Account Activity"),
		"title": _("Payments"),
		"subtitle": _("Review invoices, receipts, and outstanding balances."),
	},
}

CLIENT_PORTAL_REPORT_TYPES = (
	{
		"key": "weekly-site-summary-report",
		"label": _("Weekly Site Summary Report"),
		"description": _("Published daily updates, tasks, and photos for the selected week."),
		"internal_route": "/app/query-report/Weekly Site Summary Report",
	},
	{
		"key": "daily-progress-report",
		"label": _("Daily Progress Report"),
		"description": _("Published day-by-day site progress updates."),
		"internal_route": "/app/daily-progress-report",
	},
	{
		"key": "material-status-report",
		"label": _("Material Status Report"),
		"description": _("Project material received and consumed status."),
		"internal_route": "/app/query-report/Material Status Report",
	},
	{
		"key": "monthly-project-performance-report",
		"label": _("Monthly Project Performance Report"),
		"description": _("Monthly billing, collection, and progress performance."),
		"internal_route": "/app/query-report/Monthly Project Performance Report",
	},
)


def redirect_to_client_portal_login():
	frappe.local.flags.redirect_location = "/client-portal"
	raise frappe.Redirect


def get_client_portal_access(user=None):
	user = user or frappe.session.user
	access = frappe._dict({"allowed": False, "customer": None, "customers": [], "reason": None})

	if user == "Guest":
		access.reason = _("Please sign in to continue.")
		return access

	user_type = frappe.db.get_value("User", user, "user_type")
	if user_type != "Website User":
		access.reason = _("This portal is reserved for client website users.")
		return access

	try:
		access.customers = get_customers_for_portal_user(user)
	except Exception:
		access.reason = _("This account is not linked to a QATRA client record.")
		return access

	if not access.customers:
		access.reason = _("This account is not linked to a QATRA client record.")
		return access

	# Future client-to-project eligibility rules should be added here once the
	# client portal gets its own customer/project visibility matrix.
	access.customer = access.customers[0]
	access.allowed = True
	return access


def require_client_portal_user():
	if frappe.session.user == "Guest":
		redirect_to_client_portal_login()

	access = get_client_portal_access()
	if not access.allowed:
		frappe.throw(access.reason or _("Not permitted."), frappe.PermissionError)

	return access


def setup_client_portal_context(context, active_page):
	access = require_client_portal_user()
	page = frappe._dict(QATRA_CLIENT_PORTAL_PAGES.get(active_page) or {})
	if not page:
		frappe.throw(_("Page not found."), frappe.DoesNotExistError)

	context.no_header = True
	context.no_breadcrumbs = True
	context.show_sidebar = False
	context.hide_login = True
	context.full_width = True
	context.body_class = "qatra-client-portal"
	context.qatra_logo = get_client_portal_logo()
	context.qatra_fallback_logo = QATRA_CLIENT_PORTAL_FALLBACK_LOGO
	context.qatra_company_name = get_client_portal_company_name()
	context.qatra_client_portal_asset_version = QATRA_CLIENT_PORTAL_ASSET_VERSION
	context.qatra_portal_nav_items = QATRA_CLIENT_PORTAL_ITEMS
	context.active_page = active_page
	context.customer = access.customer
	context.customers = access.customers
	context.customer_name = get_client_portal_customer_name(access.customer)
	context.customer_names = get_client_portal_customer_names(access.customers)
	context.full_name = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
	context.page_kicker = page.kicker
	context.page_title = page.title
	context.page_subtitle = page.subtitle
	context.title = page.title


def get_client_portal_logo():
	company = get_default_client_portal_company()
	if company:
		try:
			return frappe.db.get_value("Company", company, "company_logo") or QATRA_CLIENT_PORTAL_FALLBACK_LOGO
		except Exception:
			return QATRA_CLIENT_PORTAL_FALLBACK_LOGO

	return QATRA_CLIENT_PORTAL_FALLBACK_LOGO


def get_client_portal_company_name():
	return get_default_client_portal_company() or _("QATRA Building Contracting")


def get_default_client_portal_company():
	return (
		frappe.defaults.get_global_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)


def get_client_portal_customer_name(customer):
	if not customer:
		return _("Client Portal")

	try:
		return frappe.db.get_value("Customer", customer, "customer_name") or customer
	except Exception:
		return customer or _("Client Portal")


def get_client_portal_customer_names(customers):
	return [get_client_portal_customer_name(customer) for customer in customers or []]


def get_customers_for_portal_user(user=None):
	user = user or frappe.session.user
	if user == "Guest":
		return []

	customers = []
	user_ids = get_portal_user_ids(user)

	for user_id in user_ids:
		customers.extend(get_customers_from_contact_user(user_id))
		customers.extend(get_customers_from_contact_email(user_id))
		customers.extend(get_customers_from_contact(user_id))
		customers.extend(get_customers_from_portal_user(user_id))

	customer = get_default_customer_from_erpnext(user)
	if customer:
		customers.append(customer)

	return list(dict.fromkeys(customer for customer in customers if customer))


def get_customer_projects(customers, limit_page_length=None):
	customers = [customer for customer in (customers or []) if customer]
	customer_field = get_project_customer_field()
	if not customers or not customer_field:
		return []

	project_meta = frappe.get_meta("Project")
	fields = get_client_portal_project_fields(project_meta, customer_field)
	filters = {customer_field: ["in", customers]}
	projects = frappe.get_all(
		"Project",
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit_page_length=limit_page_length,
		ignore_permissions=True,
	)

	manager_map = get_project_manager_map([project.name for project in projects])
	for project in projects:
		set_client_portal_project_display_fields(project, project_meta, customer_field, manager_map)

	frappe.logger("construction_management.portal").info(
		"Client portal user %s resolved to customers %s and %s projects",
		frappe.session.user,
		", ".join(customers),
		len(projects),
	)
	return projects


def get_primary_customer_project(customers):
	projects = get_customer_projects(customers)
	for project in projects:
		if project.status in ("Open", "In Progress", "Active"):
			return project

	return projects[0] if projects else None


def get_authorized_customer_project(project_name, customers):
	customers = [customer for customer in (customers or []) if customer]
	customer_field = get_project_customer_field()
	if not project_name or not customers or not customer_field:
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	project_meta = frappe.get_meta("Project")
	fields = get_client_portal_project_fields(project_meta, customer_field)
	project = frappe.db.get_value("Project", project_name, fields, as_dict=True)
	if not project or project.get(customer_field) not in customers:
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	manager_map = get_project_manager_map([project.name])
	set_client_portal_project_display_fields(project, project_meta, customer_field, manager_map)
	return project


def get_client_portal_project_fields(project_meta, customer_field):
	fields = [
		"name",
		"project_name",
		"status",
		customer_field,
		"percent_complete",
		"expected_start_date",
		"expected_end_date",
		"modified",
	]

	for fieldname in ("project_type", "sales_order", "company"):
		if project_meta.has_field(fieldname):
			fields.append(fieldname)

	location_field = get_project_location_field(project_meta)
	if location_field:
		fields.append(location_field)

	stage_field = get_project_stage_field(project_meta)
	if stage_field:
		fields.append(stage_field)

	return list(dict.fromkeys(fields))


def get_project_location_field(project_meta=None):
	project_meta = project_meta or frappe.get_meta("Project")
	for fieldname in ("project_location", "location", "site_location"):
		if project_meta.has_field(fieldname):
			return fieldname

	return None


def get_project_manager_map(projects):
	projects = [project for project in (projects or []) if project]
	if not projects:
		return {}

	users = frappe.get_all(
		"Project User",
		filters={"parent": ["in", projects]},
		fields=["parent", "user", "full_name"],
		order_by="idx asc",
		ignore_permissions=True,
	)
	manager_map = {}
	for row in users:
		if row.parent not in manager_map:
			manager_map[row.parent] = row.full_name or row.user

	return manager_map


def set_client_portal_project_display_fields(project, project_meta, customer_field, manager_map):
	location_field = get_project_location_field(project_meta)
	project.customer = project.get(customer_field)
	project.customer_name = get_client_portal_customer_name(project.customer)
	project.display_name = project.project_name or project.name
	project.display_status = project.status or _("Not specified")
	project.progress_summary = get_project_progress_summary(project.name, [project.customer], project=project)
	project.display_percent_complete = project.progress_summary.physical_progress
	project.display_progress_source = project.progress_summary.physical_progress_source
	project.display_location = project.get(location_field) if location_field else None
	project.display_location = project.display_location or _("Not specified")
	project.display_manager = manager_map.get(project.name) or _("Not specified")
	project.display_start_date = formatdate(project.expected_start_date) if project.expected_start_date else _("Not specified")
	project.display_end_date = formatdate(project.expected_end_date) if project.expected_end_date else _("Not specified")
	project.detail_route = f"/client-portal/project/{quote(project.name, safe='')}"


def get_client_portal_project_counts(project_name, customers):
	customers = [customer for customer in (customers or []) if customer]
	if not project_name or not customers:
		return frappe._dict({"boqs": 0, "ra_bills": 0, "dprs": 0})

	counts = frappe._dict({"boqs": 0, "ra_bills": 0, "dprs": 0})
	boq_customer_field = get_boq_customer_field()
	counts.boqs = frappe.db.count(
		"BOQ",
		{
			boq_customer_field: ["in", customers],
			"project": project_name,
			"docstatus": ["!=", 2],
		},
	)
	counts.ra_bills = frappe.db.count(
		"RA Bill",
		{
			"customer": ["in", customers],
			"project": project_name,
			"docstatus": 1,
			"status": ["!=", "Cancelled"],
		},
	)
	if frappe.db.exists("DocType", "Daily Progress Report"):
		counts.dprs = frappe.db.count(
			"Daily Progress Report",
			{
				"customer": ["in", customers],
				"project": project_name,
				"docstatus": 1,
				"publish_to_portal": 1,
				"status": ["!=", "Cancelled"],
			},
		)

	return counts


def get_client_dashboard_data(project_name=None, customers=None):
	access = None
	if customers is None:
		access = require_client_portal_user()
		customers = access.customers

	customers = [customer for customer in (customers or []) if customer]
	projects = get_dashboard_projects(customers)
	financials_by_project = get_dashboard_financials_for_projects(
		[project.name for project in projects],
		customers,
	)
	counts_by_project = get_dashboard_counts_for_projects([project.name for project in projects], customers)

	for project in projects:
		financials = financials_by_project.get(project.name) or get_empty_dashboard_financials(project.name)
		project.dashboard_route = f"/client-portal/dashboard?project={quote(project.name, safe='')}"
		project.detail_route = f"/client-portal/project/{quote(project.name, safe='')}"
		project.display_percent_complete = financials.physical_progress
		project.display_billing_progress = financials.display_billing_progress
		project.display_collection_progress = financials.display_collection_progress
		project.display_contract_value = financials.display_contract_value
		project.counts = counts_by_project.get(project.name) or get_empty_project_counts()
		project.timeline = get_project_timeline(project)

	selected_project = get_dashboard_selected_project(projects, project_name)
	selected_financials = None
	selected_counts = get_empty_project_counts()
	next_milestone = None
	current_stage = _("Stage not specified")
	journey = []
	recent_activity = []
	recent_financial_activity = []

	if selected_project:
		selected_financials = get_project_financial_summary(
			selected_project.name,
			customers,
			project=selected_project,
		)
		selected_counts = counts_by_project.get(selected_project.name) or get_empty_project_counts()
		next_milestone = get_next_project_milestone(selected_project.name, customers)
		current_stage = get_project_current_stage(selected_project)
		journey = get_project_journey(selected_project)
		recent_activity = get_dashboard_recent_activity(
			selected_project.name,
			customers,
			selected_financials,
			limit=8,
		)
		recent_financial_activity = get_project_recent_financial_activity(
			selected_project.name,
			customers,
			selected_financials,
			limit=8,
		)

	return frappe._dict(
		{
			"customer": get_dashboard_customer_summary(customers),
			"project_summary": get_dashboard_project_summary(projects),
			"financial_summary": get_dashboard_client_financial_summary(financials_by_project),
			"projects": projects,
			"selected_project": selected_project,
			"selected_project_financials": selected_financials,
			"counts": selected_counts,
			"journey": journey,
			"current_stage": current_stage,
			"next_milestone": next_milestone,
			"recent_activity": recent_activity,
			"recent_financial_activity": recent_financial_activity,
		}
	)


def get_dashboard_projects(customers):
	customers = [customer for customer in (customers or []) if customer]
	customer_field = get_project_customer_field()
	if not customers or not customer_field:
		return []

	project_meta = frappe.get_meta("Project")
	fields = get_client_portal_project_fields(project_meta, customer_field)
	projects = frappe.get_all(
		"Project",
		filters={customer_field: ["in", customers]},
		fields=fields,
		order_by="modified desc",
		ignore_permissions=True,
	)
	manager_map = get_project_manager_map([project.name for project in projects])
	location_field = get_project_location_field(project_meta)
	for project in projects:
		project.customer = project.get(customer_field)
		project.customer_name = get_client_portal_customer_name(project.customer)
		project.display_name = project.project_name or project.name
		project.display_status = project.status or _("Not specified")
		project.display_location = project.get(location_field) if location_field else None
		project.display_location = project.display_location or _("Not specified")
		project.display_manager = manager_map.get(project.name) or _("Not specified")
		project.display_start_date = formatdate(project.expected_start_date) if project.expected_start_date else _("Not specified")
		project.display_end_date = formatdate(project.expected_end_date) if project.expected_end_date else _("Not specified")

	return projects


def get_dashboard_selected_project(projects, project_name=None):
	if not projects:
		return None

	if project_name:
		for project in projects:
			if project.name == project_name:
				return project
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	for project in projects:
		if project.status in ("Open", "In Progress", "Active"):
			return project

	return projects[0]


def get_dashboard_project_summary(projects):
	active_statuses = {"Open", "In Progress", "Active"}
	completed_statuses = {"Completed", "Closed"}
	on_hold_statuses = {"On Hold", "Hold"}
	return frappe._dict(
		{
			"total_projects": len(projects or []),
			"active_projects": len([project for project in projects or [] if project.status in active_statuses]),
			"completed_projects": len(
				[project for project in projects or [] if project.status in completed_statuses]
			),
			"on_hold_projects": len([project for project in projects or [] if project.status in on_hold_statuses]),
		}
	)


def get_dashboard_customer_summary(customers):
	return frappe._dict(
		{
			"name": ", ".join(get_client_portal_customer_names(customers)) or _("Client"),
			"customers": customers,
		}
	)


def get_dashboard_financials_for_projects(project_names, customers):
	project_names = [project for project in (project_names or []) if project]
	customers = [customer for customer in (customers or []) if customer]
	if not project_names or not customers:
		return {}

	sales_orders = frappe.get_all(
		"Sales Order",
		filters={
			"project": ["in", project_names],
			"customer": ["in", customers],
			"docstatus": 1,
		},
		fields=[
			"name",
			"project",
			"customer",
			"currency",
			"net_total",
			"grand_total",
			"base_net_total",
			"base_grand_total",
			"advance_paid",
			"transaction_date",
			"status",
		],
		ignore_permissions=True,
	)
	ra_bills = frappe.get_all(
		"RA Bill",
		filters={
			"project": ["in", project_names],
			"customer": ["in", customers],
			"docstatus": 1,
			"status": ["!=", "Cancelled"],
		},
		fields=[
			"name",
			"project",
			"customer",
			"gross_amount",
			"currency",
			"sales_invoice",
			"sales_order",
			"posting_date",
			"creation",
			"status",
		],
		ignore_permissions=True,
	)
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"project": ["in", project_names],
			"customer": ["in", customers],
			"docstatus": 1,
		},
		fields=[
			"name",
			"project",
			"customer",
			"currency",
			"net_total",
			"grand_total",
			"rounded_total",
			"outstanding_amount",
			"is_return",
			"return_against",
			"posting_date",
			"creation",
			"status",
		],
		ignore_permissions=True,
	)
	invoices_by_name = {invoice.name: invoice for invoice in invoices}
	sales_orders_by_name = {sales_order.name: sales_order for sales_order in sales_orders}
	payment_refs = get_dashboard_payment_references(invoices_by_name, sales_orders_by_name, customers)

	financials_by_project = {}
	for project_name in project_names:
		project_sales_orders = [row for row in sales_orders if row.project == project_name]
		project_ra_bills = [row for row in ra_bills if row.project == project_name]
		project_invoices = [row for row in invoices if row.project == project_name]
		project_payment_refs = [row for row in payment_refs if row.project == project_name]
		financials_by_project[project_name] = build_dashboard_financials(
			project_name,
			project_sales_orders,
			project_ra_bills,
			project_invoices,
			project_payment_refs,
		)

	return financials_by_project


def get_dashboard_payment_references(invoices_by_name, sales_orders_by_name, customers):
	reference_filters = []
	if invoices_by_name:
		reference_filters.append(
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": ["in", list(invoices_by_name)],
			}
		)
	if sales_orders_by_name:
		reference_filters.append(
			{
				"reference_doctype": "Sales Order",
				"reference_name": ["in", list(sales_orders_by_name)],
			}
		)
	if not reference_filters:
		return []

	references = []
	for reference_filter in reference_filters:
		references.extend(
			frappe.get_all(
				"Payment Entry Reference",
				filters=reference_filter,
				fields=["parent", "reference_doctype", "reference_name", "allocated_amount"],
				ignore_permissions=True,
			)
		)
	payment_names = list(dict.fromkeys(row.parent for row in references if row.parent))
	if not payment_names:
		return []

	payments = frappe.get_all(
		"Payment Entry",
		filters={
			"name": ["in", payment_names],
			"party": ["in", customers],
			"payment_type": "Receive",
			"docstatus": 1,
		},
		fields=["name"],
		ignore_permissions=True,
	)
	allowed_payments = {payment.name for payment in payments}
	rows = []
	for reference in references:
		if reference.parent not in allowed_payments:
			continue

		if reference.reference_doctype == "Sales Invoice":
			source = invoices_by_name.get(reference.reference_name)
			transaction_type = "Invoice Payment"
		else:
			source = sales_orders_by_name.get(reference.reference_name)
			transaction_type = "Advance Receipt"

		if not source:
			continue

		reference.project = source.project
		reference.transaction_type = transaction_type
		rows.append(reference)

	return rows


def build_dashboard_financials(project_name, sales_orders, ra_bills, invoices, payment_refs):
	currency = get_financial_currency(sales_orders, ra_bills, invoices)
	mixed_currency = has_mixed_currency(sales_orders, ra_bills, invoices)
	contract_value = sum(flt(row.base_net_total if mixed_currency else row.net_total) for row in sales_orders)
	certified_work_value = sum(flt(row.gross_amount) for row in ra_bills)
	total_invoiced = sum(get_signed_amount(row, "net_total") for row in invoices)
	total_invoice_receivable = sum(get_invoice_receivable_amount(row) for row in invoices)
	invoice_outstanding = sum(get_signed_amount(row, "outstanding_amount") for row in invoices)
	received_against_invoices = sum(
		flt(row.allocated_amount) for row in payment_refs if row.transaction_type == "Invoice Payment"
	)
	advance_received = sum(
		flt(row.allocated_amount) for row in payment_refs if row.transaction_type == "Advance Receipt"
	)
	total_received = received_against_invoices + advance_received
	financials = frappe._dict(
		{
			"project": project_name,
			"currency": currency,
			"mixed_currency": mixed_currency,
			"contract_value": contract_value,
			"certified_work_value": certified_work_value,
			"total_invoiced": total_invoiced,
			"total_invoice_receivable": total_invoice_receivable,
			"received_against_invoices": received_against_invoices,
			"advance_received": advance_received,
			"total_received": total_received,
			"invoice_outstanding": invoice_outstanding,
			"remaining_contract_value": max(contract_value - total_invoiced, 0),
			"physical_progress": clamp_percent(certified_work_value / contract_value * 100)
			if certified_work_value and contract_value
			else 0,
			"billing_progress": clamp_percent(total_invoiced / contract_value * 100)
			if total_invoiced and contract_value
			else 0,
			"collection_progress": clamp_percent(received_against_invoices / total_invoice_receivable * 100)
			if received_against_invoices and total_invoice_receivable
			else 0,
		}
	)
	add_financial_display_values(financials)
	return financials


def get_empty_dashboard_financials(project_name=None):
	financials = frappe._dict(
		{
			"project": project_name,
			"currency": frappe.defaults.get_global_default("currency"),
			"mixed_currency": False,
			"contract_value": 0,
			"certified_work_value": 0,
			"total_invoiced": 0,
			"total_invoice_receivable": 0,
			"received_against_invoices": 0,
			"advance_received": 0,
			"total_received": 0,
			"invoice_outstanding": 0,
			"remaining_contract_value": 0,
			"physical_progress": 0,
			"billing_progress": 0,
			"collection_progress": 0,
		}
	)
	add_financial_display_values(financials)
	return financials


def get_dashboard_client_financial_summary(financials_by_project):
	financials_by_project = financials_by_project or {}
	currency = get_financial_currency(financials_by_project.values())
	summary = frappe._dict(
		{
			"currency": currency,
			"contract_value": sum(flt(row.contract_value) for row in financials_by_project.values()),
			"certified_work_value": sum(flt(row.certified_work_value) for row in financials_by_project.values()),
			"total_invoiced": sum(flt(row.total_invoiced) for row in financials_by_project.values()),
			"total_invoice_receivable": sum(
				flt(row.total_invoice_receivable) for row in financials_by_project.values()
			),
			"received_against_invoices": sum(
				flt(row.received_against_invoices) for row in financials_by_project.values()
			),
			"advance_received": sum(flt(row.advance_received) for row in financials_by_project.values()),
			"total_received": sum(flt(row.total_received) for row in financials_by_project.values()),
			"invoice_outstanding": sum(flt(row.invoice_outstanding) for row in financials_by_project.values()),
		}
	)
	summary.remaining_contract_value = max(summary.contract_value - summary.total_invoiced, 0)
	summary.physical_progress = (
		clamp_percent(summary.certified_work_value / summary.contract_value * 100)
		if summary.certified_work_value and summary.contract_value
		else 0
	)
	summary.billing_progress = (
		clamp_percent(summary.total_invoiced / summary.contract_value * 100)
		if summary.total_invoiced and summary.contract_value
		else 0
	)
	summary.collection_progress = (
		clamp_percent(summary.received_against_invoices / summary.total_invoice_receivable * 100)
		if summary.received_against_invoices and summary.total_invoice_receivable
		else 0
	)
	add_financial_display_values(summary)
	return summary


def get_dashboard_counts_for_projects(project_names, customers):
	project_names = [project for project in (project_names or []) if project]
	customers = [customer for customer in (customers or []) if customer]
	counts = {project_name: get_empty_project_counts() for project_name in project_names}
	if not project_names or not customers:
		return counts

	if frappe.db.exists("DocType", "Daily Progress Report"):
		report_rows = frappe.get_all(
			"Daily Progress Report",
			filters={
				"project": ["in", project_names],
				"customer": ["in", customers],
				"docstatus": 1,
				"publish_to_portal": 1,
				"status": ["!=", "Cancelled"],
			},
			fields=["project"],
			ignore_permissions=True,
		)
		for row in report_rows:
			if row.project in counts:
				counts[row.project].reports += 1

	# Documents and approvals remain zero until explicit client visibility flags
	# or portal publication rules exist for those internal doctypes.
	return counts


def get_empty_project_counts():
	return frappe._dict({"reports": 0, "documents": 0, "pending_approvals": 0})


def get_client_portal_report_types():
	return [frappe._dict(row.copy()) for row in CLIENT_PORTAL_REPORT_TYPES]


def get_client_portal_report_type_map():
	report_type_map = {}
	for report_type in get_client_portal_report_types():
		report_type_map[report_type.key] = report_type
		report_type_map[report_type.label] = report_type
	return report_type_map


def get_client_portal_report_type_key(report_type):
	if not report_type:
		return None

	report_type_info = get_client_portal_report_type_map().get(report_type)
	return report_type_info.key if report_type_info else "__unknown__"


def get_client_portal_reports(customers, filters=None):
	customers = [customer for customer in (customers or []) if customer]
	filters = frappe._dict(filters or {})
	if not customers:
		return []

	project_filter = filters.get("project")
	authorized_projects = get_dashboard_projects(customers)
	authorized_project_names = {project.name for project in authorized_projects}
	if project_filter:
		if project_filter not in authorized_project_names:
			frappe.throw(_("Not permitted."), frappe.PermissionError)
		authorized_projects = [project for project in authorized_projects if project.name == project_filter]

	report_type_key = get_client_portal_report_type_key(filters.get("type"))
	if report_type_key == "__unknown__":
		return []

	anchor_date = get_client_report_anchor_date(filters)
	search_text = (filters.get("search") or "").strip().lower()
	cards = []
	for project in authorized_projects:
		for report_type in get_client_portal_report_types():
			if report_type_key and report_type.key != report_type_key:
				continue

			card = build_client_report_card(project, customers, report_type, anchor_date, filters)
			if search_text and not client_report_matches_search(card, search_text):
				continue
			cards.append(card)

	return cards


def get_client_report_anchor_date(filters=None):
	filters = filters or {}
	return getdate(filters.get("date") or today())


def client_report_matches_search(report, search_text):
	values = (
		report.get("report_type"),
		report.get("display_title"),
		report.get("display_summary"),
		report.get("project"),
		report.get("project_display_name"),
		report.get("display_status"),
	)
	return search_text in " ".join([str(value or "") for value in values]).lower()


def build_client_report_card(project, customers, report_type, anchor_date, filters=None):
	if report_type.key == "weekly-site-summary-report":
		return build_weekly_site_summary_card(project, customers, report_type, anchor_date)
	if report_type.key == "daily-progress-report":
		return build_daily_progress_report_card(project, customers, report_type, anchor_date, filters)
	if report_type.key == "material-status-report":
		return build_material_status_report_card(project, report_type, anchor_date)
	if report_type.key == "monthly-project-performance-report":
		return build_monthly_project_performance_card(project, customers, report_type, anchor_date)

	frappe.throw(_("Unknown report type."), frappe.PermissionError)


def get_client_report_route(report_key, project_name, anchor_date=None):
	route = f"/client-portal/report/{quote(report_key, safe='')}?project={quote(project_name, safe='')}"
	if anchor_date:
		route += f"&date={quote(str(anchor_date), safe='')}"
	return route


def build_base_client_report_card(project, report_type, anchor_date):
	return frappe._dict(
		{
			"name": report_type.key,
			"report_key": report_type.key,
			"report_type": report_type.label,
			"description": report_type.description,
			"internal_route": report_type.internal_route,
			"project": project.name,
			"project_display_name": project.display_name,
			"project_route": f"/client-portal/project/{quote(project.name, safe='')}",
			"detail_route": get_client_report_route(report_type.key, project.name, anchor_date),
			"is_virtual": True,
			"sort_date": anchor_date,
			"period_label": formatdate(anchor_date),
			"task_count": 0,
			"photo_count": 0,
			"primary_metric_label": _("Items"),
			"primary_metric_value": 0,
			"secondary_metric_label": _("Updates"),
			"secondary_metric_value": 0,
			"daily_updates": [],
		}
	)


def build_weekly_site_summary_card(project, customers, report_type, anchor_date):
	week_start = add_days(anchor_date, -6)
	rows = get_published_client_dpr_rows(customers, [project.name], from_date=week_start, to_date=anchor_date)
	child_counts = get_client_report_child_counts([row.name for row in rows])
	task_count = sum(child_counts.tasks.get(row.name, 0) for row in rows)
	photo_count = sum(child_counts.photos.get(row.name, 0) for row in rows)
	card = build_base_client_report_card(project, report_type, anchor_date)
	card.display_title = _("Weekly Site Summary - {0}").format(project.display_name)
	card.display_date = _("{0} to {1}").format(formatdate(week_start), formatdate(anchor_date))
	card.display_status = _("Available") if rows else _("No Published Updates")
	card.display_summary = (
		_("{0} published daily updates with {1} task entries and {2} photos for this week.").format(
			len(rows), task_count, photo_count
		)
		if rows
		else _("No published daily updates were found for this project in the selected week.")
	)
	card.task_count = task_count
	card.photo_count = photo_count
	card.primary_metric_label = _("Updates")
	card.primary_metric_value = len(rows)
	card.secondary_metric_label = _("Photos")
	card.secondary_metric_value = photo_count
	card.period_label = card.display_date
	return card


def build_daily_progress_report_card(project, customers, report_type, anchor_date, filters=None):
	filters = filters or {}
	if filters.get("date"):
		rows = get_published_client_dpr_rows(customers, [project.name], exact_date=anchor_date)
	else:
		rows = get_published_client_dpr_rows(customers, [project.name])

	child_counts = get_client_report_child_counts([row.name for row in rows])
	task_count = sum(child_counts.tasks.get(row.name, 0) for row in rows)
	photo_count = sum(child_counts.photos.get(row.name, 0) for row in rows)
	latest = rows[0] if rows else None
	card = build_base_client_report_card(project, report_type, anchor_date)
	if not filters.get("date"):
		card.detail_route = get_client_report_route(report_type.key, project.name)
	card.display_title = _("Daily Progress Report - {0}").format(project.display_name)
	card.display_date = formatdate(latest.dpr_date) if latest and latest.dpr_date else formatdate(anchor_date)
	card.display_status = _("Published") if rows else _("No Published Updates")
	card.display_summary = (
		_("{0} published daily updates are available. Latest update: {1}.").format(
			len(rows), latest.title or latest.name
		)
		if rows and latest
		else _("No submitted DPR has been published to the client portal for this project yet.")
	)
	card.task_count = task_count
	card.photo_count = photo_count
	card.primary_metric_label = _("Updates")
	card.primary_metric_value = len(rows)
	card.secondary_metric_label = _("Tasks")
	card.secondary_metric_value = task_count
	return card


def build_material_status_report_card(project, report_type, anchor_date):
	material_data = get_project_material_status_data(project.name, to_date=anchor_date, limit=5)
	card = build_base_client_report_card(project, report_type, anchor_date)
	card.display_title = _("Material Status Report - {0}").format(project.display_name)
	card.display_date = _("As of {0}").format(formatdate(anchor_date))
	card.display_status = _("Available") if material_data.rows else _("No Material Movement")
	card.display_summary = (
		_("{0} material item rows are tracked from project receipts and site consumption.").format(
			material_data.item_count
		)
		if material_data.rows
		else _("No project-tagged material receipts or site consumption entries were found.")
	)
	card.task_count = material_data.item_count
	card.photo_count = material_data.consumption_entry_count
	card.primary_metric_label = _("Items")
	card.primary_metric_value = material_data.item_count
	card.secondary_metric_label = _("Consumptions")
	card.secondary_metric_value = material_data.consumption_entry_count
	return card


def build_monthly_project_performance_card(project, customers, report_type, anchor_date):
	performance = get_project_monthly_performance_data(project, customers, anchor_date)
	card = build_base_client_report_card(project, report_type, anchor_date)
	card.display_title = _("Monthly Project Performance - {0}").format(project.display_name)
	card.display_date = performance.period_label
	card.display_status = _("Available")
	card.display_summary = _(
		"Current progress is {0}, billing is {1}, and collection is {2} for the selected month view."
	).format(
		performance.financials.display_physical_progress,
		performance.financials.display_billing_progress,
		performance.financials.display_collection_progress,
	)
	card.task_count = performance.monthly_ra_bill_count
	card.photo_count = performance.monthly_invoice_count
	card.primary_metric_label = _("Progress")
	card.primary_metric_value = performance.financials.display_physical_progress
	card.secondary_metric_label = _("Invoices")
	card.secondary_metric_value = performance.monthly_invoice_count
	return card


def get_published_client_dpr_rows(customers, project_names, from_date=None, to_date=None, exact_date=None):
	customers = [customer for customer in (customers or []) if customer]
	project_names = [project for project in (project_names or []) if project]
	if not customers or not project_names or not frappe.db.exists("DocType", "Daily Progress Report"):
		return []

	filters = {
		"customer": ["in", customers],
		"project": ["in", project_names],
		"docstatus": 1,
		"publish_to_portal": 1,
		"status": ["!=", "Cancelled"],
	}
	if exact_date:
		filters["dpr_date"] = exact_date
	else:
		if from_date:
			filters["dpr_date"] = [">=", from_date]
		if to_date:
			if from_date:
				filters["dpr_date"] = ["between", [from_date, to_date]]
			else:
				filters["dpr_date"] = ["<=", to_date]

	rows = frappe.get_all(
		"Daily Progress Report",
		filters=filters,
		fields=[
			"name",
			"dpr_date",
			"project",
			"title",
			"summary",
			"notes",
			"status",
			"prepared_by",
			"modified",
			"creation",
		],
		order_by="dpr_date desc, modified desc, name desc",
		ignore_permissions=True,
	)
	for row in rows:
		row.display_title = row.title or row.name
		row.display_date = formatdate(row.dpr_date) if row.dpr_date else _("Date not specified")
		row.display_summary = get_portal_plain_text(row.summary, _("No summary provided."))
	return rows


def get_client_report_child_counts(report_names):
	counts = frappe._dict({"tasks": {}, "photos": {}})
	report_names = [name for name in (report_names or []) if name]
	if not report_names:
		return counts

	for key, doctype, parentfield in (
		("tasks", "DPR Task Completed", "tasks_completed"),
		("photos", "DPR Photo", "photos"),
	):
		if not frappe.db.exists("DocType", doctype):
			continue
		for row in frappe.db.sql(
			f"""
			SELECT parent, COUNT(*) AS total
			FROM `tab{doctype}`
			WHERE parent IN %(parents)s
			  AND parenttype = 'Daily Progress Report'
			  AND parentfield = %(parentfield)s
			GROUP BY parent
			""",
			{"parents": tuple(report_names), "parentfield": parentfield},
			as_dict=True,
		):
			counts[key][row.parent] = row.total

	return counts


def get_client_report_summary(reports, projects=None):
	reports = reports or []
	projects = projects or []
	latest_report = reports[0] if reports else None
	projects_with_reports = len({row.project for row in reports if row.project})
	available_types = len({row.report_key for row in reports if row.get("report_key")})
	return frappe._dict(
		{
			"total": len(reports),
			"projects_with_reports": projects_with_reports,
			"total_projects": len(projects),
			"available_types": available_types,
			"latest": latest_report,
			"latest_title": latest_report.display_title if latest_report else _("No reports available"),
			"latest_date": latest_report.display_date if latest_report else _("Not available"),
			"visibility": _("Client Portal"),
		}
	)


def get_authorized_client_report(report_name, customers, filters=None):
	customers = [customer for customer in (customers or []) if customer]
	filters = frappe._dict(filters or {})
	report_type_key = get_client_portal_report_type_key(report_name)
	if report_type_key and report_type_key != "__unknown__":
		return get_authorized_virtual_client_report(report_type_key, customers, filters)

	if not report_name or not customers or not frappe.db.exists("DocType", "Daily Progress Report"):
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	report = frappe.db.get_value(
		"Daily Progress Report",
		report_name,
		[
			"name",
			"customer",
			"project",
			"dpr_date",
			"title",
			"summary",
			"notes",
			"status",
			"prepared_by",
			"docstatus",
			"publish_to_portal",
		],
		as_dict=True,
	)
	if (
		not report
		or report.customer not in customers
		or report.docstatus != 1
		or not report.publish_to_portal
		or report.status == "Cancelled"
	):
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	validate_project_in_customers(report.project, customers)
	report_doc = frappe.get_doc("Daily Progress Report", report.name)
	project = get_authorized_customer_project(report.project, customers)
	tasks = get_client_dpr_tasks(report_doc)
	photos = get_client_dpr_photos(report_doc)
	report_doc.display_title = report_doc.title or report_doc.name
	report_doc.display_date = formatdate(report_doc.dpr_date) if report_doc.dpr_date else _("Date not specified")
	report_doc.display_status = report_doc.status or _("Published")
	report_doc.project_display_name = project.display_name
	report_doc.project_route = project.detail_route
	report_doc.detail_route = f"/client-portal/report/{quote(report_doc.name, safe='')}"
	report_doc.display_summary = get_portal_plain_text(report_doc.summary, _("No summary provided."))
	report_doc.display_notes = get_portal_plain_text(report_doc.notes, _("No notes provided."))
	report_doc.daily_updates = [
		get_client_dpr_update_payload(report_doc, project, tasks=tasks, photos=photos)
	]

	return frappe._dict(
		{
			"report": report_doc,
			"project": project,
			"tasks": tasks,
			"photos": photos,
			"attachments": get_client_report_attachments(report_doc.name),
		}
	)


def get_client_dpr_update_details(dpr_rows, project):
	updates = []
	for row in dpr_rows or []:
		try:
			report_doc = frappe.get_doc("Daily Progress Report", row.name)
		except Exception:
			continue

		updates.append(get_client_dpr_update_payload(report_doc, project))

	return updates


def get_client_dpr_update_payload(report_doc, project, tasks=None, photos=None):
	tasks = tasks if tasks is not None else get_client_dpr_tasks(report_doc)
	photos = photos if photos is not None else get_client_dpr_photos(report_doc)
	update = frappe._dict(
		{
			"name": report_doc.name,
			"title": report_doc.title or report_doc.name,
			"display_date": formatdate(report_doc.dpr_date) if report_doc.dpr_date else _("Date not specified"),
			"display_status": report_doc.status or _("Published"),
			"prepared_by": report_doc.prepared_by or _("Not specified"),
			"summary": get_portal_plain_text(report_doc.summary, _("No summary provided.")),
			"notes": get_portal_plain_text(report_doc.notes),
			"project_display_name": project.display_name if project else report_doc.project,
			"detail_route": f"/client-portal/report/{quote(report_doc.name, safe='')}",
			"tasks": tasks,
			"photos": photos,
			"task_count": len(tasks),
			"photo_count": len(photos),
			"task_photo_count": len([row for row in tasks if row.get("photo")]),
		}
	)
	return update


def get_client_dpr_tasks(report_doc):
	tasks = []
	for row in report_doc.get("tasks_completed") or []:
		task = frappe._dict(row.as_dict() if hasattr(row, "as_dict") else row)
		task.display_title = task.task_title or task.description or _("Task")
		task.display_description = task.description or task.notes or ""
		task.display_status = task.status or _("Completed")
		task.display_quantity = get_display_task_quantity(task)
		task.display_location = task.location or _("Location not specified")
		tasks.append(task)

	return tasks


def get_client_dpr_photos(report_doc):
	photos = []
	for row in sorted(report_doc.get("photos") or [], key=lambda item: (item.sequence or 0, item.idx or 0)):
		photo = frappe._dict(row.as_dict() if hasattr(row, "as_dict") else row)
		photo.display_caption = photo.caption or _("Site photo")
		photo.display_notes = photo.notes or ""
		photos.append(photo)

	return photos


def get_display_task_quantity(task):
	if not flt(task.quantity):
		return _("Not specified")

	quantity = f"{flt(task.quantity):g}"
	return f"{quantity} {task.uom}" if task.uom else quantity


def get_portal_plain_text(value, fallback=""):
	if not value:
		return fallback

	text = str(value)
	text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
	text = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", text, flags=re.IGNORECASE)
	text = frappe.utils.strip_html(text)
	lines = [unescape(line).strip() for line in text.splitlines()]
	return "\n".join(line for line in lines if line) or fallback


def get_authorized_virtual_client_report(report_type_key, customers, filters=None):
	filters = frappe._dict(filters or {})
	project_name = filters.get("project")
	if not project_name:
		frappe.throw(_("Project is required for this report."), frappe.PermissionError)

	project = get_authorized_customer_project(project_name, customers)
	report_type = get_client_portal_report_type_map().get(report_type_key)
	if not report_type:
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	anchor_date = get_client_report_anchor_date(filters)
	if report_type_key == "weekly-site-summary-report":
		report = build_weekly_site_summary_detail(project, customers, report_type, anchor_date)
	elif report_type_key == "daily-progress-report":
		report = build_daily_progress_report_detail(project, customers, report_type, anchor_date, filters)
	elif report_type_key == "material-status-report":
		report = build_material_status_report_detail(project, report_type, anchor_date)
	elif report_type_key == "monthly-project-performance-report":
		report = build_monthly_project_performance_detail(project, customers, report_type, anchor_date)
	else:
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	return frappe._dict({"report": report, "project": project, "tasks": [], "photos": [], "attachments": []})


def build_virtual_client_report(report_type, project, anchor_date):
	return frappe._dict(
		{
			"name": report_type.key,
			"report_key": report_type.key,
			"report_type": report_type.label,
			"project": project.name,
			"project_display_name": project.display_name,
			"project_route": project.detail_route,
			"detail_route": get_client_report_route(report_type.key, project.name, anchor_date),
			"internal_route": report_type.internal_route,
			"is_virtual": True,
			"prepared_by": _("Construction Management"),
			"display_status": _("Available"),
			"display_date": formatdate(anchor_date),
			"summary": report_type.description,
			"display_summary": report_type.description,
			"sections": [],
			"primary_metric_label": _("Items"),
			"primary_metric_value": 0,
			"secondary_metric_label": _("Updates"),
			"secondary_metric_value": 0,
		}
	)


def build_weekly_site_summary_detail(project, customers, report_type, anchor_date):
	week_start = add_days(anchor_date, -6)
	rows = get_published_client_dpr_rows(customers, [project.name], from_date=week_start, to_date=anchor_date)
	child_counts = get_client_report_child_counts([row.name for row in rows])
	task_count = sum(child_counts.tasks.get(row.name, 0) for row in rows)
	photo_count = sum(child_counts.photos.get(row.name, 0) for row in rows)
	daily_updates = get_client_dpr_update_details(rows, project)
	report = build_virtual_client_report(report_type, project, anchor_date)
	report.display_title = _("Weekly Site Summary - {0}").format(project.display_name)
	report.display_date = _("{0} to {1}").format(formatdate(week_start), formatdate(anchor_date))
	report.period_label = report.display_date
	report.display_status = _("Available") if rows else _("No Published Updates")
	report.summary = (
		_("{0} client-visible DPRs were published in this weekly period.").format(len(rows))
		if rows
		else _("No published DPR entries are available for the selected week.")
	)
	report.display_summary = report.summary
	report.primary_metric_label = _("Updates")
	report.primary_metric_value = len(rows)
	report.secondary_metric_label = _("Tasks")
	report.secondary_metric_value = task_count
	report.daily_updates = daily_updates
	report.sections = [
		get_metric_section(
			_("Weekly Totals"),
			_("Site Summary"),
			[
				(_("Published Updates"), len(rows)),
				(_("Task Entries"), task_count),
				(_("Photos"), photo_count),
			],
		),
		get_dpr_table_section(_("Daily Updates"), rows, child_counts),
	]
	return report


def build_daily_progress_report_detail(project, customers, report_type, anchor_date, filters=None):
	filters = filters or {}
	rows = (
		get_published_client_dpr_rows(customers, [project.name], exact_date=anchor_date)
		if filters.get("date")
		else get_published_client_dpr_rows(customers, [project.name])
	)
	child_counts = get_client_report_child_counts([row.name for row in rows])
	task_count = sum(child_counts.tasks.get(row.name, 0) for row in rows)
	photo_count = sum(child_counts.photos.get(row.name, 0) for row in rows)
	daily_updates = get_client_dpr_update_details(rows, project)
	report = build_virtual_client_report(report_type, project, anchor_date)
	report.display_title = _("Daily Progress Report - {0}").format(project.display_name)
	report.display_date = formatdate(anchor_date) if filters.get("date") else _("All Published Updates")
	report.display_status = _("Published") if rows else _("No Published Updates")
	report.summary = (
		_("{0} published DPR entries are available for this project.").format(len(rows))
		if rows
		else _("No submitted DPR has been published to the client portal for this project yet.")
	)
	report.display_summary = report.summary
	report.primary_metric_label = _("Updates")
	report.primary_metric_value = len(rows)
	report.secondary_metric_label = _("Tasks")
	report.secondary_metric_value = task_count
	report.daily_updates = daily_updates
	report.sections = [
		get_metric_section(
			_("Daily Progress Totals"),
			_("Published DPRs"),
			[
				(_("Published Updates"), len(rows)),
				(_("Task Entries"), task_count),
				(_("Photos"), photo_count),
			],
		),
		get_dpr_table_section(_("DPR Register"), rows, child_counts),
	]
	return report


def build_material_status_report_detail(project, report_type, anchor_date):
	material_data = get_project_material_status_data(project.name, to_date=anchor_date)
	report = build_virtual_client_report(report_type, project, anchor_date)
	report.display_title = _("Material Status Report - {0}").format(project.display_name)
	report.display_date = _("As of {0}").format(formatdate(anchor_date))
	report.display_status = _("Available") if material_data.rows else _("No Material Movement")
	report.summary = (
		_("{0} material item rows are tracked from project-tagged receipts and site consumption.").format(
			material_data.item_count
		)
		if material_data.rows
		else _("No project-tagged material receipts or site consumption entries were found.")
	)
	report.display_summary = report.summary
	report.primary_metric_label = _("Items")
	report.primary_metric_value = material_data.item_count
	report.secondary_metric_label = _("Consumptions")
	report.secondary_metric_value = material_data.consumption_entry_count
	report.sections = [
		get_metric_section(
			_("Material Totals"),
			_("Status"),
			[
				(_("Tracked Items"), material_data.item_count),
				(_("Receipt Rows"), material_data.receipt_row_count),
				(_("Consumption Entries"), material_data.consumption_entry_count),
			],
		),
		frappe._dict(
			{
				"kicker": _("Material Lines"),
				"title": _("Received vs Consumed"),
				"table": frappe._dict(
					{
						"columns": [_("Item"), _("Received"), _("Consumed"), _("Balance")],
						"rows": [
							[
								row.item_name or row.item_code,
								row.display_received_qty,
								row.display_consumed_qty,
								row.display_balance_qty,
							]
							for row in material_data.rows
						],
					}
				),
			}
		),
	]
	return report


def build_monthly_project_performance_detail(project, customers, report_type, anchor_date):
	performance = get_project_monthly_performance_data(project, customers, anchor_date)
	report = build_virtual_client_report(report_type, project, anchor_date)
	report.display_title = _("Monthly Project Performance - {0}").format(project.display_name)
	report.display_date = performance.period_label
	report.summary = _(
		"This report combines the selected month's client financial activity with current project performance."
	)
	report.display_summary = report.summary
	report.primary_metric_label = _("Progress")
	report.primary_metric_value = performance.financials.display_physical_progress
	report.secondary_metric_label = _("Invoices")
	report.secondary_metric_value = performance.monthly_invoice_count
	report.sections = [
		get_metric_section(
			_("Current Performance"),
			_("Progress"),
			[
				(_("Work Completion"), performance.financials.display_physical_progress),
				(_("Billing Progress"), performance.financials.display_billing_progress),
				(_("Collection Progress"), performance.financials.display_collection_progress),
			],
		),
		get_metric_section(
			_("Commercial Position"),
			_("Financials"),
			[
				(_("Contract Value"), performance.financials.display_contract_value),
				(_("Total Invoiced"), performance.financials.display_total_invoiced),
				(_("Total Received"), performance.financials.display_total_received),
				(_("Outstanding"), performance.financials.display_invoice_outstanding),
			],
		),
		frappe._dict(
			{
				"kicker": _("Monthly Activity"),
				"title": performance.period_label,
				"table": frappe._dict(
					{
						"columns": [_("Date"), _("Type"), _("Reference"), _("Amount"), _("Status")],
						"rows": [
							[
								row.display_date,
								row.type,
								row.reference,
								row.display_amount,
								row.status,
							]
							for row in performance.monthly_statement
						],
					}
				),
			}
		),
	]
	return report


def get_metric_section(kicker, title, metrics):
	return frappe._dict(
		{
			"kicker": kicker,
			"title": title,
			"metrics": [frappe._dict({"label": label, "value": value}) for label, value in metrics],
		}
	)


def get_dpr_table_section(title, rows, child_counts):
	return frappe._dict(
		{
			"kicker": _("Daily Reports"),
			"title": title,
			"table": frappe._dict(
				{
					"columns": [_("Date"), _("DPR"), _("Summary"), _("Tasks"), _("Photos")],
					"rows": [
						[
							row.display_date,
							row.display_title,
							row.display_summary,
							child_counts.tasks.get(row.name, 0),
							child_counts.photos.get(row.name, 0),
						]
						for row in rows
					],
				}
			),
		}
	)


def get_project_material_status_data(project_name, to_date=None, limit=None):
	rows = {}
	receipt_row_count = 0
	consumption_entry_count = 0

	if frappe.db.exists("DocType", "Stock Ledger Entry") and frappe.get_meta("Stock Ledger Entry").has_field("project"):
		conditions = ["sle.project = %(project)s", "sle.is_cancelled = 0", "sle.actual_qty > 0"]
		values = {"project": project_name}
		if to_date:
			conditions.append("sle.posting_date <= %(to_date)s")
			values["to_date"] = to_date
		for row in frappe.db.sql(
			f"""
			SELECT
				sle.item_code,
				item.item_name,
				sle.stock_uom AS uom,
				SUM(sle.actual_qty) AS received_qty
			FROM `tabStock Ledger Entry` sle
			INNER JOIN `tabItem` item ON item.name = sle.item_code
			WHERE {" AND ".join(conditions)}
			GROUP BY sle.item_code, item.item_name, sle.stock_uom
			""",
			values,
			as_dict=True,
		):
			receipt_row_count += 1
			material_row = rows.setdefault(row.item_code, get_empty_material_status_row(row))
			material_row.received_qty += flt(row.received_qty)

	if frappe.db.exists("DocType", "Site Material Consumption"):
		conditions = ["smc.docstatus = 1", "(smc.project = %(project)s OR item.project = %(project)s)"]
		values = {"project": project_name}
		if to_date:
			conditions.append("smc.posting_date <= %(to_date)s")
			values["to_date"] = to_date
		consumption_entry_count = frappe.db.sql(
			f"""
			SELECT COUNT(DISTINCT smc.name)
			FROM `tabSite Material Consumption` smc
			INNER JOIN `tabSite Material Consumption Item` item ON item.parent = smc.name
			WHERE {" AND ".join(conditions)}
			""",
			values,
		)[0][0] or 0
		for row in frappe.db.sql(
			f"""
			SELECT
				item.item_code,
				item.item_name,
				item.stock_uom AS uom,
				SUM(item.qty * IFNULL(item.conversion_factor, 1)) AS consumed_qty
			FROM `tabSite Material Consumption` smc
			INNER JOIN `tabSite Material Consumption Item` item ON item.parent = smc.name
			WHERE {" AND ".join(conditions)}
			GROUP BY item.item_code, item.item_name, item.stock_uom
			""",
			values,
			as_dict=True,
		):
			material_row = rows.setdefault(row.item_code, get_empty_material_status_row(row))
			material_row.consumed_qty += flt(row.consumed_qty)

	material_rows = sorted(
		rows.values(),
		key=lambda row: (abs(flt(row.received_qty) - flt(row.consumed_qty)), row.item_name or row.item_code),
		reverse=True,
	)
	if limit:
		material_rows = material_rows[:limit]

	for row in material_rows:
		row.balance_qty = flt(row.received_qty) - flt(row.consumed_qty)
		row.display_received_qty = format_qty(row.received_qty, row.uom)
		row.display_consumed_qty = format_qty(row.consumed_qty, row.uom)
		row.display_balance_qty = format_qty(row.balance_qty, row.uom)

	return frappe._dict(
		{
			"rows": material_rows,
			"item_count": len(rows),
			"receipt_row_count": receipt_row_count,
			"consumption_entry_count": consumption_entry_count,
		}
	)


def get_empty_material_status_row(row):
	return frappe._dict(
		{
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name"),
			"uom": row.get("uom"),
			"received_qty": 0,
			"consumed_qty": 0,
			"balance_qty": 0,
		}
	)


def get_project_monthly_performance_data(project, customers, anchor_date):
	period_start = getdate(anchor_date).replace(day=1)
	financials = get_project_financial_summary(project.name, customers, project=project)
	monthly_statement = [
		row
		for row in financials.statement
		if row.posting_date and period_start <= getdate(row.posting_date) <= getdate(anchor_date)
	]
	monthly_ra_bills = [
		row
		for row in financials.ra_bills
		if row.posting_date and period_start <= getdate(row.posting_date) <= getdate(anchor_date)
	]
	monthly_invoices = [
		row
		for row in financials.invoices
		if row.posting_date and period_start <= getdate(row.posting_date) <= getdate(anchor_date)
	]
	return frappe._dict(
		{
			"period_start": period_start,
			"period_end": anchor_date,
			"period_label": _("{0} to {1}").format(formatdate(period_start), formatdate(anchor_date)),
			"financials": financials,
			"monthly_statement": list(reversed(monthly_statement)),
			"monthly_ra_bill_count": len(monthly_ra_bills),
			"monthly_invoice_count": len(monthly_invoices),
		}
	)


def format_qty(value, uom=None):
	display_value = f"{flt(value, 2):g}"
	return f"{display_value} {uom}".strip() if uom else display_value


def get_client_report_attachments(report_name):
	return frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Daily Progress Report",
			"attached_to_name": report_name,
		},
		fields=["file_name", "file_url", "is_private"],
		order_by="creation asc",
		ignore_permissions=True,
	)


def get_project_timeline(project):
	status = project.get("status")
	end_date = project.get("expected_end_date")
	if status in ("Completed", "Closed"):
		state = _("Completed")
	elif end_date:
		diff = date_diff(getdate(end_date), getdate(today()))
		state = _("Overdue by {0} days").format(abs(diff)) if diff < 0 else _("{0} days remaining").format(diff)
	else:
		state = _("Expected date not specified")

	return frappe._dict(
		{
			"start_date": project.display_start_date,
			"end_date": project.display_end_date,
			"state": state,
		}
	)


def get_project_current_stage(project):
	stage_field = get_project_stage_field()
	if not stage_field:
		return _("Stage not specified")
	return project.get(stage_field) or _("Stage not specified")


def get_project_stage_field(project_meta=None):
	meta = project_meta or frappe.get_meta("Project")
	for fieldname in ("current_stage", "project_stage", "stage", "construction_stage"):
		if meta.has_field(fieldname):
			return fieldname
	return None


def get_project_journey(project):
	stage = get_project_current_stage(project)
	if stage == _("Stage not specified"):
		return []

	stages = [_("Design"), _("Procurement"), _("Construction"), _("Finishing"), _("Handover")]
	if stage not in stages:
		return [frappe._dict({"label": stage, "status": _("Active")})]

	active_index = stages.index(stage)
	journey = []
	for index, label in enumerate(stages):
		if index < active_index:
			status = _("Completed")
		elif index == active_index:
			status = _("Active")
		elif index == active_index + 1:
			status = _("Next")
		else:
			status = _("Upcoming")
		journey.append(frappe._dict({"label": label, "status": status}))
	return journey


def get_next_project_milestone(project_name, customers):
	validate_project_in_customers(project_name, customers)
	if not frappe.db.exists("DocType", "Task"):
		return None

	tasks = frappe.get_all(
		"Task",
		filters={
			"project": project_name,
			"status": ["not in", ["Completed", "Cancelled"]],
		},
		fields=["name", "subject", "status", "exp_end_date", "description", "is_milestone"],
		order_by="is_milestone desc, exp_end_date asc, modified desc",
		limit_page_length=1,
		ignore_permissions=True,
	)
	if not tasks:
		return None

	task = tasks[0]
	return frappe._dict(
		{
			"title": task.subject or task.name,
			"expected_date": formatdate(task.exp_end_date) if task.exp_end_date else _("Date not specified"),
			"description": task.description or _("No description provided"),
			"status": task.status,
		}
	)


def get_dashboard_recent_activity(project_name, customers, financial_summary=None, limit=8):
	activity = []
	ra_bills = (
		financial_summary.ra_bills
		if financial_summary and financial_summary.get("ra_bills") is not None
		else get_project_ra_bills(project_name, customers)
	)
	for row in ra_bills:
		activity.append(
			get_activity_row(
				row.posting_date,
				row.creation,
				_("RA Bill"),
				row.name,
				_("RA Bill {0} {1}").format(row.name, (row.status or "").lower()),
				row.status,
				row.gross_amount,
				row.currency,
			)
		)

	invoices = financial_summary.invoices if financial_summary else get_project_sales_invoices(project_name, customers)
	for row in invoices:
		activity.append(
			get_activity_row(
				row.posting_date,
				row.creation,
				_("Sales Invoice"),
				row.name,
				_("Sales Invoice {0} issued").format(row.name),
				row.status,
				row.invoice_amount,
				row.currency,
			)
		)

	payments = []
	if financial_summary:
		payments = financial_summary.advance_payments + financial_summary.invoice_payments
	else:
		payments = get_project_advance_payments(project_name, customers) + get_project_invoice_payments(
			project_name, customers
		)
	for row in payments:
		activity.append(
			get_activity_row(
				row.posting_date,
				row.creation,
				_("Payment"),
				row.name,
				_("Payment received against {0}").format(row.allocated_reference),
				row.status,
				row.allocated_amount,
				financial_summary.currency if financial_summary else None,
			)
		)

	if frappe.db.exists("DocType", "Daily Progress Report"):
		reports = frappe.get_all(
			"Daily Progress Report",
			filters={
				"project": project_name,
				"customer": ["in", customers],
				"docstatus": 1,
				"publish_to_portal": 1,
				"status": ["!=", "Cancelled"],
			},
			fields=["name", "title", "status", "modified", "creation"],
			order_by="modified desc",
			limit_page_length=limit,
			ignore_permissions=True,
		)
		for row in reports:
			activity.append(
				get_activity_row(
					row.modified,
					row.creation,
					_("Report"),
					row.name,
					_("Published report {0}").format(row.title or row.name),
					row.status,
				)
			)

	return sorted(activity, key=get_activity_sort_key, reverse=True)[:limit]


def get_project_recent_financial_activity(project_name, customers, financial_summary=None, limit=8):
	financial_summary = financial_summary or get_project_financial_summary(project_name, customers)
	rows = []
	ra_bills = (
		financial_summary.ra_bills
		if financial_summary and financial_summary.get("ra_bills") is not None
		else get_project_ra_bills(project_name, customers)
	)
	for row in ra_bills:
		rows.append(
			get_activity_row(
				row.posting_date,
				row.creation,
				_("RA Bill"),
				row.name,
				_("Certified work value"),
				row.status,
				row.gross_amount,
				row.currency,
			)
		)
	for row in financial_summary.statement:
		rows.append(
			get_activity_row(
				row.posting_date,
				row.creation,
				row.type,
				row.reference,
				row.description,
				row.status,
				row.amount,
				financial_summary.currency,
			)
		)

	return sorted(rows, key=get_activity_sort_key, reverse=True)[:limit]


def get_activity_sort_key(row):
	return (
		get_activity_sort_value(row.date),
		get_activity_sort_value(row.creation),
		row.document or "",
	)


def get_activity_sort_value(value):
	if not value:
		return ""

	try:
		return get_datetime(value).isoformat()
	except Exception:
		return str(value)


def get_activity_row(date, creation, activity_type, document, description, status, amount=None, currency=None):
	return frappe._dict(
		{
			"date": date,
			"creation": creation,
			"type": activity_type,
			"document": document,
			"description": description,
			"amount": amount,
			"display_amount": format_currency_value(amount, currency) if amount is not None else "",
			"status": status or _("Submitted"),
			"display_date": formatdate(date) if date else _("Date not specified"),
		}
	)


def get_project_progress_summary(project_name, customers, project=None):
	customers = [customer for customer in (customers or []) if customer]
	if not project_name or not customers:
		return frappe._dict(
			{
				"physical_progress": 0,
				"physical_progress_source": _("Project percent complete"),
				"certified_work_value": 0,
				"contract_value": 0,
			}
		)

	project = project or frappe.db.get_value(
		"Project",
		project_name,
		["name", "percent_complete", "sales_order", get_project_customer_field()],
		as_dict=True,
	)
	if not project or project.get(get_project_customer_field()) not in customers:
		return frappe._dict(
			{
				"physical_progress": 0,
				"physical_progress_source": _("Project percent complete"),
				"certified_work_value": 0,
				"contract_value": 0,
			}
		)

	contract = get_project_contract_summary(project_name, customers, project=project)
	certified_work_value = get_project_certified_work_value(project_name, customers)
	project_percent = clamp_percent(project.get("percent_complete"))

	if certified_work_value and contract.contract_value:
		physical_progress = clamp_percent(certified_work_value / contract.contract_value * 100)
		source = _("RA Bill certified work")
	else:
		physical_progress = project_percent
		source = _("Project percent complete")

	return frappe._dict(
		{
			"physical_progress": physical_progress,
			"physical_progress_source": source,
			"certified_work_value": certified_work_value,
			"contract_value": contract.contract_value,
		}
	)


def get_project_financial_summary(project_name, customers, project=None):
	customers = [customer for customer in (customers or []) if customer]
	if not project:
		project = get_authorized_customer_project(project_name, customers)
	else:
		validate_project_in_customers(project.name, customers)

	contract = get_project_contract_summary(project.name, customers, project=project)
	ra_bills = get_project_ra_bills(project.name, customers)
	invoices = get_project_sales_invoices(project.name, customers)
	invoice_payments = get_project_invoice_payments(project.name, customers, invoices=invoices)
	advance_payments = get_project_advance_payments(project.name, customers, sales_orders=contract.sales_orders)

	currency = get_financial_currency(contract.sales_orders, ra_bills, invoices)
	mixed_currency = has_mixed_currency(contract.sales_orders, ra_bills, invoices)

	certified_work_value = sum(flt(row.gross_amount) for row in ra_bills)
	total_invoiced = sum(get_signed_amount(row, "net_total") for row in invoices)
	total_invoice_receivable = sum(get_invoice_receivable_amount(row) for row in invoices)
	invoice_outstanding = sum(get_signed_amount(row, "outstanding_amount") for row in invoices)
	received_against_invoices = sum(flt(row.allocated_amount) for row in invoice_payments)
	advance_received = sum(flt(row.allocated_amount) for row in advance_payments)
	total_received = received_against_invoices + advance_received
	remaining_contract_value = max(flt(contract.contract_value) - flt(total_invoiced), 0)

	physical_progress = (
		clamp_percent(certified_work_value / contract.contract_value * 100)
		if certified_work_value and contract.contract_value
		else clamp_percent(project.get("percent_complete"))
	)
	billing_progress = (
		clamp_percent(total_invoiced / contract.contract_value * 100)
		if total_invoiced and contract.contract_value
		else 0
	)
	collection_progress = (
		clamp_percent(received_against_invoices / total_invoice_receivable * 100)
		if received_against_invoices and total_invoice_receivable
		else 0
	)

	summary = frappe._dict(
		{
			"project": project.name,
			"currency": currency,
			"mixed_currency": mixed_currency,
			"contract_value": contract.contract_value,
			"certified_work_value": certified_work_value,
			"total_invoiced": total_invoiced,
			"total_invoice_receivable": total_invoice_receivable,
			"received_against_invoices": received_against_invoices,
			"advance_received": advance_received,
			"total_received": total_received,
			"invoice_outstanding": invoice_outstanding,
			"remaining_contract_value": remaining_contract_value,
			"physical_progress": physical_progress,
			"billing_progress": billing_progress,
			"collection_progress": collection_progress,
			"physical_progress_source": _("RA Bill certified work")
			if certified_work_value and contract.contract_value
			else _("Project percent complete"),
			"sales_orders": contract.sales_orders,
			"ra_bills": ra_bills,
			"invoices": invoices,
			"invoice_payments": invoice_payments,
			"advance_payments": advance_payments,
		}
	)
	add_financial_display_values(summary)
	summary.statement = get_project_statement(summary)
	return summary


def get_project_contract_summary(project_name, customers, project=None):
	customers = [customer for customer in (customers or []) if customer]
	sales_orders = get_project_sales_orders(project_name, customers, project=project)
	currencies = {row.currency for row in sales_orders if row.get("currency")}
	mixed_currency = len(currencies) > 1
	contract_value = 0
	for row in sales_orders:
		contract_value += flt(row.base_net_total if mixed_currency else row.net_total)

	return frappe._dict(
		{
			"sales_orders": sales_orders,
			"contract_value": contract_value,
			"currency": get_financial_currency(sales_orders),
			"mixed_currency": mixed_currency,
		}
	)


def get_project_sales_orders(project_name, customers, project=None):
	customers = [customer for customer in (customers or []) if customer]
	if not project_name or not customers:
		return []

	names = set()
	if project and project.get("sales_order"):
		names.add(project.sales_order)

	names.update(
		frappe.get_all(
			"Sales Order",
			filters={
				"project": project_name,
				"customer": ["in", customers],
				"docstatus": 1,
			},
			pluck="name",
			ignore_permissions=True,
		)
	)
	if not names:
		return []

	return frappe.get_all(
		"Sales Order",
		filters={
			"name": ["in", list(names)],
			"project": project_name,
			"customer": ["in", customers],
			"docstatus": 1,
		},
		fields=[
			"name",
			"project",
			"customer",
			"currency",
			"net_total",
			"grand_total",
			"base_net_total",
			"base_grand_total",
			"advance_paid",
			"transaction_date",
			"status",
		],
		order_by="transaction_date asc, name asc",
		ignore_permissions=True,
	)


def get_project_ra_bills(project_name, customers):
	customers = [customer for customer in (customers or []) if customer]
	if not project_name or not customers:
		return []

	return frappe.get_all(
		"RA Bill",
		filters={
			"project": project_name,
			"customer": ["in", customers],
			"docstatus": 1,
			"status": ["!=", "Cancelled"],
		},
		fields=[
			"name",
			"project",
			"boq",
			"sales_order",
			"customer",
			"status",
			"gross_amount",
			"net_payable",
			"net_total",
			"grand_total",
			"retention_amount",
			"total_advance",
			"outstanding_amount",
			"cumulative_billed",
			"sales_invoice",
			"currency",
			"posting_date",
			"creation",
		],
		order_by="posting_date asc, creation asc, name asc",
		ignore_permissions=True,
	)


def get_project_certified_work_value(project_name, customers):
	return sum(flt(row.gross_amount) for row in get_project_ra_bills(project_name, customers))


def get_project_sales_invoices(project_name, customers):
	customers = [customer for customer in (customers or []) if customer]
	if not project_name or not customers:
		return []

	sales_invoice_meta = frappe.get_meta("Sales Invoice")
	names = set(
		frappe.get_all(
			"Sales Invoice",
			filters={
				"project": project_name,
				"customer": ["in", customers],
				"docstatus": 1,
			},
			pluck="name",
			ignore_permissions=True,
		)
	)
	ra_bill_names = [
		row.name for row in get_project_ra_bills(project_name, customers) if row.get("sales_invoice")
	]
	ra_bill_invoice_names = [
		row.sales_invoice for row in get_project_ra_bills(project_name, customers) if row.get("sales_invoice")
	]
	names.update(ra_bill_invoice_names)

	project_sales_orders = get_project_sales_orders(project_name, customers)
	sales_order_names = [row.name for row in project_sales_orders]
	if sales_invoice_meta.has_field("sales_order") and sales_order_names:
		names.update(
			frappe.get_all(
				"Sales Invoice",
				filters={
					"sales_order": ["in", sales_order_names],
					"customer": ["in", customers],
					"docstatus": 1,
				},
				pluck="name",
				ignore_permissions=True,
			)
		)

	if sales_order_names and frappe.get_meta("Sales Invoice Item").has_field("sales_order"):
		names.update(
			frappe.get_all(
				"Sales Invoice Item",
				filters={"sales_order": ["in", sales_order_names], "docstatus": 1},
				pluck="parent",
				ignore_permissions=True,
			)
		)

	if sales_invoice_meta.has_field("ra_bill") and ra_bill_names:
		names.update(
			frappe.get_all(
				"Sales Invoice",
				filters={
					"ra_bill": ["in", ra_bill_names],
					"customer": ["in", customers],
					"docstatus": 1,
				},
				pluck="name",
				ignore_permissions=True,
			)
		)

	if not names:
		return []

	fields = [
		"name",
		"posting_date",
		"due_date",
		"customer",
		"project",
		"currency",
		"docstatus",
		"status",
		"net_total",
		"grand_total",
		"rounded_total",
		"outstanding_amount",
		"is_return",
		"return_against",
		"remarks",
		"creation",
	]
	for fieldname in ("ra_bill", "boq", "sales_order"):
		if sales_invoice_meta.has_field(fieldname):
			fields.append(fieldname)

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"name": ["in", list(names)],
			"customer": ["in", customers],
			"docstatus": 1,
		},
		fields=list(dict.fromkeys(fields)),
		order_by="posting_date asc, creation asc, name asc",
		ignore_permissions=True,
	)
	for invoice in invoices:
		invoice.invoice_amount = get_invoice_receivable_amount(invoice)
		invoice.paid_amount = max(invoice.invoice_amount - get_signed_amount(invoice, "outstanding_amount"), 0)
		invoice.display_date = formatdate(invoice.posting_date) if invoice.posting_date else _("Not specified")
		invoice.display_due_date = formatdate(invoice.due_date) if invoice.due_date else _("Not specified")
		invoice.display_invoice_amount = format_currency_value(invoice.invoice_amount, invoice.currency)
		invoice.display_net_total = format_currency_value(get_signed_amount(invoice, "net_total"), invoice.currency)
		invoice.display_paid_amount = format_currency_value(invoice.paid_amount, invoice.currency)
		invoice.display_outstanding_amount = format_currency_value(
			get_signed_amount(invoice, "outstanding_amount"), invoice.currency
		)
		invoice.ra_bill_label = invoice.get("ra_bill") or None
		invoice.description = get_invoice_description(invoice)

	return invoices


def get_project_invoice_payments(project_name, customers, invoices=None):
	customers = [customer for customer in (customers or []) if customer]
	invoices = invoices if invoices is not None else get_project_sales_invoices(project_name, customers)
	invoice_names = [invoice.name for invoice in invoices]
	if not invoice_names:
		return []

	references = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"reference_doctype": "Sales Invoice",
			"reference_name": ["in", invoice_names],
		},
		fields=[
			"parent",
			"reference_name",
			"total_amount",
			"outstanding_amount",
			"allocated_amount",
		],
		order_by="parent asc, idx asc",
		ignore_permissions=True,
	)
	return get_payment_rows_from_references(references, customers, "Invoice Payment")


def get_project_advance_payments(project_name, customers, sales_orders=None):
	customers = [customer for customer in (customers or []) if customer]
	sales_orders = sales_orders if sales_orders is not None else get_project_sales_orders(project_name, customers)
	sales_order_names = [row.name for row in sales_orders]
	if not sales_order_names:
		return []

	references = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"reference_doctype": "Sales Order",
			"reference_name": ["in", sales_order_names],
		},
		fields=[
			"parent",
			"reference_name",
			"total_amount",
			"outstanding_amount",
			"allocated_amount",
		],
		order_by="parent asc, idx asc",
		ignore_permissions=True,
	)
	return get_payment_rows_from_references(references, customers, "Advance Receipt")


def get_payment_rows_from_references(references, customers, transaction_type):
	payment_names = list(dict.fromkeys(row.parent for row in references if row.parent))
	if not payment_names:
		return []

	payments = frappe.get_all(
		"Payment Entry",
		filters={
			"name": ["in", payment_names],
			"party": ["in", customers],
			"payment_type": "Receive",
			"docstatus": 1,
		},
		fields=[
			"name",
			"posting_date",
			"party",
			"payment_type",
			"paid_amount",
			"received_amount",
			"mode_of_payment",
			"reference_no",
			"reference_date",
			"status",
			"creation",
		],
		ignore_permissions=True,
	)
	payment_map = {payment.name: payment for payment in payments}
	rows = []
	for reference in references:
		payment = payment_map.get(reference.parent)
		if not payment:
			continue

		row = frappe._dict(payment.copy())
		row.transaction_type = transaction_type
		row.allocated_reference = reference.reference_name
		row.allocated_amount = flt(reference.allocated_amount)
		row.display_date = formatdate(row.posting_date) if row.posting_date else _("Not specified")
		row.display_allocated_amount = format_currency_value(row.allocated_amount, None)
		rows.append(row)

	return rows


def get_project_statement(summary):
	rows = []
	for invoice in summary.invoices:
		rows.append(
			frappe._dict(
				{
					"posting_date": invoice.posting_date,
					"creation": invoice.creation,
					"name": invoice.name,
					"type": _("Invoice"),
					"description": invoice.description,
					"reference": invoice.name,
					"amount": invoice.invoice_amount,
					"display_amount": format_currency_value(invoice.invoice_amount, summary.currency),
					"status": invoice.status,
					"display_date": invoice.display_date,
				}
			)
		)

	for payment in summary.advance_payments + summary.invoice_payments:
		rows.append(
			frappe._dict(
				{
					"posting_date": payment.posting_date,
					"creation": payment.creation,
					"name": payment.name,
					"type": payment.transaction_type,
					"description": payment.allocated_reference,
					"reference": payment.name,
					"amount": payment.allocated_amount,
					"display_amount": format_currency_value(payment.allocated_amount, summary.currency),
					"status": payment.status,
					"display_date": payment.display_date,
				}
			)
		)

	return sorted(rows, key=lambda row: (row.posting_date or "", row.creation or "", row.name or ""))


def add_financial_display_values(summary):
	for fieldname in (
		"contract_value",
		"certified_work_value",
		"total_invoiced",
		"total_invoice_receivable",
		"received_against_invoices",
		"advance_received",
		"total_received",
		"invoice_outstanding",
		"remaining_contract_value",
	):
		summary[f"display_{fieldname}"] = format_currency_value(summary.get(fieldname), summary.currency)

	for fieldname in ("physical_progress", "billing_progress", "collection_progress"):
		summary[f"display_{fieldname}"] = f"{flt(summary.get(fieldname), 1)}%"


def get_invoice_description(invoice):
	if invoice.get("ra_bill"):
		return _("Against RA Bill {0}").format(invoice.ra_bill)
	if invoice.get("remarks"):
		return invoice.remarks
	return _("Sales Invoice")


def get_invoice_receivable_amount(invoice):
	total = flt(invoice.rounded_total) if flt(invoice.rounded_total) else flt(invoice.grand_total)
	if invoice.get("is_return") and total > 0:
		return -total
	return total


def get_signed_amount(row, fieldname):
	value = flt(row.get(fieldname))
	if row.get("is_return") and value > 0:
		return -value
	return value


def get_financial_currency(*row_groups):
	currencies = []
	for row_group in row_groups:
		for row in row_group or []:
			if row.get("currency"):
				currencies.append(row.currency)
	if currencies:
		return currencies[0]
	return frappe.defaults.get_global_default("currency")


def has_mixed_currency(*row_groups):
	currencies = set()
	for row_group in row_groups:
		for row in row_group or []:
			if row.get("currency"):
				currencies.add(row.currency)
	return len(currencies) > 1


def format_currency_value(value, currency):
	return fmt_money(flt(value), currency=currency or frappe.defaults.get_global_default("currency"))


def clamp_percent(value):
	return max(0, min(flt(value), 100))


def validate_project_in_customers(project_name, customers):
	customers = [customer for customer in (customers or []) if customer]
	customer_field = get_project_customer_field()
	project_customer = frappe.db.get_value("Project", project_name, customer_field)
	if not project_customer or project_customer not in customers:
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def require_portal_customer():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please login."), frappe.PermissionError)

	return get_customer_for_portal_user()


def get_customer_for_portal_user(user=None):
	user = user or frappe.session.user
	user_ids = get_portal_user_ids(user)

	for user_id in user_ids:
		customer = get_customer_from_contact_email(user_id)
		if customer:
			ensure_customer_portal_user(customer, user)
			return customer

	for user_id in user_ids:
		customer = get_customer_from_contact(user_id)
		if customer:
			ensure_customer_portal_user(customer, user)
			return customer

	for user_id in user_ids:
		customer = get_customer_from_portal_user(user_id)
		if customer:
			ensure_customer_portal_user(customer, user)
			return customer

	customer = get_default_customer_from_erpnext(user)
	if customer:
		ensure_customer_portal_user(customer, user)
		return customer

	frappe.throw(_("No Customer is linked with this portal user."), frappe.PermissionError)


def get_portal_user_ids(user):
	if user == "Guest":
		return [user]

	values = [user]
	user_doc = frappe.db.get_value("User", user, ["name", "email", "username"], as_dict=True)

	if not user_doc:
		user_doc = frappe.db.get_value(
			"User",
			{"username": user},
			["name", "email", "username"],
			as_dict=True,
		)

	if user_doc:
		values.extend([user_doc.name, user_doc.email, user_doc.username])

	return list(dict.fromkeys(value for value in values if value))


def get_customer_from_user():
	return get_customer_for_portal_user()


def get_customer_from_contact_email(email):
	contacts = frappe.get_all(
		"Contact Email",
		filters={"email_id": email},
		pluck="parent",
	)

	return get_customer_from_contacts(contacts)


def get_customers_from_contact_email(email):
	contacts = frappe.get_all(
		"Contact Email",
		filters={"email_id": email},
		pluck="parent",
	)
	return get_customers_from_contacts(contacts)


def get_customers_from_contact_user(user):
	contacts = frappe.get_all(
		"Contact",
		filters={"user": user},
		pluck="name",
	)
	return get_customers_from_contacts(contacts)


def get_customer_from_contact(email):
	contacts = frappe.get_all(
		"Contact",
		filters={"email_id": email},
		pluck="name",
	)

	return get_customer_from_contacts(contacts)


def get_customers_from_contact(email):
	contacts = frappe.get_all(
		"Contact",
		filters={"email_id": email},
		pluck="name",
	)
	return get_customers_from_contacts(contacts)


def get_customer_from_contacts(contacts):
	for contact in contacts or []:
		customer = frappe.db.get_value(
			"Dynamic Link",
			{
				"parenttype": "Contact",
				"parent": contact,
				"link_doctype": "Customer",
			},
			"link_name",
		)
		if customer:
			return customer

		customer = get_matching_customer_for_contact(contact)
		if customer:
			return customer


def get_customers_from_contacts(contacts):
	customers = []
	for contact in contacts or []:
		customers.extend(
			frappe.get_all(
				"Dynamic Link",
				filters={
					"parenttype": "Contact",
					"parent": contact,
					"link_doctype": "Customer",
				},
				pluck="link_name",
			)
		)

		customer = get_matching_customer_for_contact(contact)
		if customer:
			customers.append(customer)

	return list(dict.fromkeys(customer for customer in customers if customer))


def get_matching_customer_for_contact(contact):
	if frappe.db.exists("Customer", contact):
		return contact

	contact_name = frappe.db.get_value("Contact", contact, "full_name")
	if contact_name:
		return frappe.db.get_value("Customer", {"customer_name": contact_name}, "name")


def get_customer_from_portal_user(user):
	return frappe.db.get_value(
		"Portal User",
		{
			"parenttype": "Customer",
			"user": user,
		},
		"parent",
	)


def get_customers_from_portal_user(user):
	return frappe.get_all(
		"Portal User",
		filters={
			"parenttype": "Customer",
			"user": user,
		},
		pluck="parent",
	)


def ensure_customer_portal_user(customer, user=None):
	user = user or frappe.session.user
	if not customer or user == "Guest":
		return

	if frappe.db.exists(
		"Portal User",
		{
			"parenttype": "Customer",
			"parent": customer,
			"parentfield": "portal_users",
			"user": user,
		},
	):
		return

	customer_doc = frappe.get_doc("Customer", customer)
	customer_doc.append("portal_users", {"user": user})
	customer_doc.save(ignore_permissions=True)


def sync_customer_portal_user(login_manager=None):
	if frappe.session.user == "Guest":
		return

	try:
		get_customer_for_portal_user(frappe.session.user)
	except Exception:
		frappe.logger("construction_management.portal").debug(
			{
				"portal_user": frappe.session.user,
				"message": "Unable to sync Customer Portal User for default ERPNext portal access.",
			}
		)


def get_default_customer_from_erpnext(user):
	try:
		from erpnext.utilities import get_default_customer
	except Exception:
		return None

	try:
		return get_default_customer(user)
	except Exception:
		return None


def get_boq_customer_field():
	meta = frappe.get_meta("BOQ")
	if meta.has_field("client"):
		return "client"
	if meta.has_field("customer"):
		return "customer"

	frappe.throw(_("BOQ does not have a Customer field."))


def get_project_customer_field():
	meta = frappe.get_meta("Project")
	if meta.has_field("customer"):
		return "customer"
	if meta.has_field("client"):
		return "client"

	return None


def get_project_customer(project):
	if not project:
		return None

	customer_field = get_project_customer_field()
	if not customer_field:
		return None

	return frappe.db.get_value("Project", project, customer_field)


def validate_project_customer(project_name, customer):
	if not project_name:
		frappe.throw(_("Document not specified."))

	project_customer = get_project_customer(project_name)
	if not project_customer or project_customer != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def validate_boq_customer(boq_name, customer):
	if not boq_name:
		frappe.throw(_("Document not specified."))

	boq_customer = frappe.db.get_value("BOQ", boq_name, get_boq_customer_field())
	if not boq_customer or boq_customer != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def validate_ra_bill_customer(ra_bill_name, customer):
	if not ra_bill_name:
		frappe.throw(_("Document not specified."))

	ra_bill_customer = frappe.db.get_value("RA Bill", ra_bill_name, "customer")
	if not ra_bill_customer or ra_bill_customer != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def validate_dpr_customer(dpr_name, customer):
	if not dpr_name:
		frappe.throw(_("Document not specified."))

	dpr = frappe.db.get_value(
		"Daily Progress Report",
		dpr_name,
		["customer", "docstatus", "publish_to_portal", "status"],
		as_dict=True,
	)
	if (
		not dpr
		or dpr.customer != customer
		or dpr.docstatus != 1
		or not dpr.publish_to_portal
		or dpr.status == "Cancelled"
	):
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def log_portal_access(customer):
	try:
		frappe.logger("construction_management.portal").debug(
			{
				"portal_user": frappe.session.user,
				"detected_customer": customer,
				"route": getattr(frappe.local, "request", None).path
				if getattr(frappe.local, "request", None)
				else "",
			}
		)
	except Exception:
		pass


def setup_portal_context(context, title, route=None, description=None, parents=None):
	context.show_sidebar = True
	context.sidebar_title = _("Construction Portal")
	context.sidebar_items = CONSTRUCTION_PORTAL_ITEMS
	context.title = title
	context.portal_title = title
	context.portal_description = description
	context.parents = parents or [{"name": _("Construction Portal"), "route": "/construction-portal"}]
	context.no_breadcrumbs = False
	if route:
		context.route = route


def get_request_filters(*names):
	return frappe._dict({name: (frappe.form_dict.get(name) or "").strip() for name in names})


def build_like_filter(txt):
	return ["like", f"%{txt}%"] if txt else None
