import frappe
import os


def after_install():
	create_boq_client_script()
	ensure_project_current_boq_field()
	ensure_sales_invoice_ra_bill_field()
	ensure_sales_invoice_retention_records_field()
	backfill_sales_invoice_ra_bill_links()
	ensure_ra_bill_items()
	backfill_boq_revision_fields()


def after_migrate():
	create_boq_client_script()
	ensure_project_current_boq_field()
	ensure_sales_invoice_ra_bill_field()
	ensure_sales_invoice_retention_records_field()
	backfill_sales_invoice_ra_bill_links()
	ensure_ra_bill_items()
	backfill_boq_revision_fields()


def create_boq_client_script():
	script_path = os.path.join(
		os.path.dirname(__file__),
		"client_script",
		"boq_client_script.js"
	)
	with open(script_path, "r") as f:
		script_content = f.read()

	if frappe.db.exists("Client Script", "BOQ-client-script"):
		doc = frappe.get_doc("Client Script", "BOQ-client-script")
		doc.script = script_content
		doc.enabled = 1
		doc.save()
	else:
		doc = frappe.get_doc({
			"doctype": "Client Script",
			"name": "BOQ-client-script",
			"dt": "BOQ",
			"script": script_content,
			"enabled": 1,
			"view": "Form"
		})
		doc.insert()
	frappe.db.commit()
	print("BOQ client script created/updated successfully")


def ensure_sales_invoice_ra_bill_field():
	"""
	Ensure Sales Invoice carries the retention and RA Bill linkage fields used by the workflow.
	"""
	for fieldname, label, options, insert_after in [
		("ra_bill", "RA Bill", "RA Bill", "project"),
		("boq", "BOQ", "BOQ", "ra_bill"),
		("retention_record", "Retention Record", "Retention Record", "boq"),
	]:
		if frappe.get_meta("Sales Invoice").has_field(fieldname):
			continue
		if frappe.db.exists("Custom Field", f"Sales Invoice-{fieldname}"):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Sales Invoice",
				"fieldname": fieldname,
				"label": label,
				"fieldtype": "Link",
				"options": options,
				"insert_after": insert_after,
				"read_only": 1,
				"no_copy": 1,
				"module": "Construction Management",
			}
		).insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Sales Invoice")
	frappe.db.commit()
	print("Sales Invoice retention custom fields created successfully")


def ensure_sales_invoice_retention_records_field():
	"""
	Ensure Sales Invoice can carry multiple Retention Record references for bulk releases.
	"""
	fieldname = "retention_records"
	if frappe.get_meta("Sales Invoice").has_field(fieldname):
		frappe.clear_cache(doctype="Sales Invoice")
		return

	if frappe.db.exists("Custom Field", f"Sales Invoice-{fieldname}"):
		frappe.clear_cache(doctype="Sales Invoice")
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Sales Invoice",
			"fieldname": fieldname,
			"label": "Retention Records",
			"fieldtype": "Table",
			"options": "Sales Invoice Retention Reference",
			"insert_after": "retention_record",
			"read_only": 1,
			"no_copy": 1,
			"module": "Construction Management",
		}
	).insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Sales Invoice")
	frappe.db.commit()
	print("Sales Invoice Retention Records custom field created successfully")


def ensure_project_current_boq_field():
	"""
	Ensure Project points at the currently active BOQ revision.
	The field is maintained when a BOQ revision is activated.
	"""
	if frappe.get_meta("Project").has_field("current_boq"):
		frappe.clear_cache(doctype="Project")
		return

	if frappe.db.exists("Custom Field", "Project-current_boq"):
		frappe.clear_cache(doctype="Project")
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Project",
			"fieldname": "current_boq",
			"label": "Current BOQ",
			"fieldtype": "Link",
			"options": "BOQ",
			"insert_after": "project_name",
			"read_only": 1,
			"no_copy": 1,
			"module": "Construction Management",
		}
	).insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Project")
	frappe.db.commit()
	print("Project Current BOQ custom field created successfully")


def backfill_sales_invoice_ra_bill_links():
	"""
	Backfill Sales Invoice.ra_bill from existing RA Bill.sales_invoice links.
	Only updates the reference field and does not touch financial fields.
	"""
	frappe.clear_cache(doctype="Sales Invoice")
	if not frappe.get_meta("Sales Invoice").has_field("ra_bill"):
		return

	ra_bills = frappe.get_all(
		"RA Bill",
		filters={"sales_invoice": ["is", "set"]},
		fields=["name", "sales_invoice"],
	)

	for rb in ra_bills:
		if not rb.sales_invoice or not frappe.db.exists("Sales Invoice", rb.sales_invoice):
			continue

		current_ra_bill = frappe.db.get_value("Sales Invoice", rb.sales_invoice, "ra_bill")
		if current_ra_bill == rb.name:
			continue

		frappe.db.set_value(
			"Sales Invoice",
			rb.sales_invoice,
			"ra_bill",
			rb.name,
			update_modified=False,
		)

	frappe.db.commit()


def _doctype_has_field(doctype, fieldname):
	try:
		return frappe.get_meta(doctype).has_field(fieldname)
	except Exception:
		return False


def _table_exists(doctype):
	try:
		return frappe.db.table_exists(doctype)
	except Exception:
		return False


def _set_value_if_changed(doctype, name, values):
	values = {
		fieldname: value
		for fieldname, value in (values or {}).items()
		if _doctype_has_field(doctype, fieldname)
	}
	if not values:
		return

	current = frappe.db.get_value(doctype, name, list(values), as_dict=True) or {}
	changed = {
		fieldname: value
		for fieldname, value in values.items()
		if current.get(fieldname) != value
	}
	if changed:
		frappe.db.set_value(doctype, name, changed, update_modified=False)


def _get_original_boq(boq):
	if not boq:
		return None
	original_boq = frappe.db.get_value("BOQ", boq, "original_boq")
	return original_boq or boq


def _get_boq_item_key(boq_item):
	if not boq_item:
		return None

	fields = ["name"]
	for fieldname in ("boq_item_key", "component_key", "item"):
		if _doctype_has_field("BOQ Item", fieldname):
			fields.append(fieldname)

	row = frappe.db.get_value("BOQ Item", boq_item, fields, as_dict=True)
	if not row:
		return None

	return (
		row.get("boq_item_key")
		or row.get("component_key")
		or row.get("item")
		or row.get("name")
	)


def backfill_boq_revision_fields():
	"""
	Idempotently backfill revision metadata and stable item lineage.

	Run manually if needed:
	bench --site Qatra.local execute construction_management.construction_management.setup.backfill_boq_revision_fields
	"""
	frappe.clear_cache()
	if not _table_exists("BOQ"):
		return

	ensure_project_current_boq_field()
	_backfill_boq_roots()
	_backfill_boq_item_keys()
	_backfill_ra_bill_item_revision_fields()
	_backfill_ra_bill_transaction_revision_fields()
	_backfill_project_current_boq()
	frappe.db.commit()


def _backfill_boq_roots():
	active_statuses = {"Submitted", "Approved", "Active", "Current"}
	fields = [
		"name",
		"project",
		"status",
		"docstatus",
		"revision_no",
		"is_revision",
		"parent_boq",
		"original_boq",
		"is_active_revision",
		"revision_status",
		"active_from_date",
	]

	boqs = frappe.get_all("BOQ", fields=fields)
	for boq in boqs:
		values = {}
		is_revision = bool(boq.get("is_revision") or boq.get("parent_boq"))

		if is_revision and not boq.get("original_boq") and boq.get("parent_boq"):
			values["original_boq"] = _get_original_boq(boq.parent_boq)
		elif not is_revision:
			values["is_revision"] = 0
			values["original_boq"] = boq.name
			if boq.get("revision_no") in (None, "", 1):
				values["revision_no"] = 0

		if boq.docstatus == 2:
			values["is_active_revision"] = 0
			values["revision_status"] = "Cancelled"
		elif (
			not is_revision
			and boq.status in active_statuses
			and boq.revision_status not in {"Superseded", "Cancelled"}
		):
			values["is_active_revision"] = 1
			values["revision_status"] = "Active"
			if not boq.active_from_date:
				values["active_from_date"] = frappe.utils.today()
		elif not boq.revision_status:
			values["revision_status"] = "Draft"

		_set_value_if_changed("BOQ", boq.name, values)


def _backfill_boq_item_keys():
	fields = ["name", "component_key", "boq_item_key", "item"]
	for row in frappe.get_all("BOQ Item", fields=fields):
		component_key = row.component_key or frappe.generate_hash(length=12)
		boq_item_key = row.boq_item_key or component_key or row.item or frappe.generate_hash(length=12)
		_set_value_if_changed(
			"BOQ Item",
			row.name,
			{
				"component_key": component_key,
				"boq_item_key": boq_item_key,
			},
		)


def _backfill_ra_bill_item_revision_fields():
	if not _table_exists("RA Bill Item") or not _table_exists("RA Bill"):
		return

	rows = frappe.db.sql(
		"""
		SELECT rbi.name, rbi.parent, rbi.boq_item, rb.boq
		FROM `tabRA Bill Item` rbi
		JOIN `tabRA Bill` rb ON rb.name = rbi.parent
		WHERE COALESCE(rbi.boq_item, '') != ''
		""",
		as_dict=True,
	)
	for row in rows:
		boq_revision = row.boq
		_set_value_if_changed(
			"RA Bill Item",
			row.name,
			{
				"boq_item_key": _get_boq_item_key(row.boq_item),
				"boq_revision": boq_revision,
				"original_boq": _get_original_boq(boq_revision),
			},
		)


def _backfill_ra_bill_transaction_revision_fields():
	if not _table_exists("RA Bill Transaction"):
		return

	rows = frappe.db.sql(
		"""
		SELECT t.name, t.ra_bill, t.boq, t.boq_item, rb.boq AS ra_bill_boq
		FROM `tabRA Bill Transaction` t
		LEFT JOIN `tabRA Bill` rb ON rb.name = t.ra_bill
		WHERE COALESCE(t.boq_item, '') != ''
		""",
		as_dict=True,
	)
	for row in rows:
		boq_revision = row.boq or row.ra_bill_boq
		_set_value_if_changed(
			"RA Bill Transaction",
			row.name,
			{
				"boq": boq_revision,
				"boq_revision": boq_revision,
				"original_boq": _get_original_boq(boq_revision),
				"boq_item_key": _get_boq_item_key(row.boq_item),
			},
		)


def _backfill_project_current_boq():
	if not _doctype_has_field("Project", "current_boq"):
		return

	active_boqs = frappe.get_all(
		"BOQ",
		filters={
			"project": ["is", "set"],
			"is_active_revision": 1,
			"docstatus": ["!=", 2],
		},
		fields=["name", "project", "revision_no", "modified"],
		order_by="modified desc, revision_no desc",
	)

	seen_projects = set()
	for boq in active_boqs:
		if boq.project in seen_projects:
			continue
		seen_projects.add(boq.project)
		current_boq = frappe.db.get_value("Project", boq.project, "current_boq")
		if current_boq != boq.name:
			frappe.db.set_value(
				"Project",
				boq.project,
				"current_boq",
				boq.name,
				update_modified=False,
			)


def get_or_create_ra_bill_receivable_account(company, currency):
	"""
	Return a receivable account whose currency matches the RA Bill invoice currency.
	ERPNext requires Sales Invoice debit_to currency to match document currency.
	"""
	import frappe

	if not company:
		return None

	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if not currency or currency == company_currency:
		return frappe.get_cached_value("Company", company, "default_receivable_account")

	account = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_type": "Receivable",
			"account_currency": currency,
			"is_group": 0,
			"disabled": 0,
		},
		"name",
	)
	if account:
		return account

	account_name = f"RA Bill Receivable {currency}"
	account = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_name": account_name,
			"is_group": 0,
		},
		"name",
	)
	if account:
		return account

	parent_account = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_name": "Accounts Receivable",
			"root_type": "Asset",
			"is_group": 1,
		},
		"name",
	)
	if not parent_account:
		frappe.throw("Please create an Accounts Receivable group before creating RA Bill invoices.")

	account_doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"parent_account": parent_account,
			"company": company,
			"root_type": "Asset",
			"report_type": "Balance Sheet",
			"account_type": "Receivable",
			"account_currency": currency,
			"is_group": 0,
		}
	)
	account_doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Created receivable account: {account_doc.name}")
	return account_doc.name


def ensure_ra_bill_items():
	"""
	Ensure the two service items used in RA Bill Sales Invoices exist.
	Safe to run multiple times - skips if already exists.
	"""
	import frappe

	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	income_account = frappe.db.get_value("Company", company, "default_income_account") if company else None

	items = [
		{
			"item_code": "RA Bill Services",
			"item_name": "RA Bill Services",
			"description": "Construction progress billing services",
			"item_group": "Services",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_purchase_item": 0,
			"is_sales_item": 1,
		},
		{
			"item_code": "Retention Deduction",
			"item_name": "Retention Deduction",
			"description": "Retention amount held per contract terms",
			"item_group": "Services",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_purchase_item": 0,
			"is_sales_item": 1,
		},
	]

	for item_data in items:
		if not frappe.db.exists("Item", item_data["item_code"]):
			doc = frappe.get_doc({"doctype": "Item", **item_data})
			if company:
				doc.append(
					"item_defaults",
					{
						"company": company,
						"income_account": income_account,
					},
				)
			doc.insert(ignore_permissions=True)
			print(f"Created item: {item_data['item_code']}")
		else:
			doc = frappe.get_doc("Item", item_data["item_code"])
			changed = False
			for field, value in item_data.items():
				if doc.get(field) != value:
					doc.set(field, value)
					changed = True

			if company:
				default_row = None
				for row in doc.item_defaults:
					if row.company == company:
						default_row = row
						break

				if not default_row:
					doc.append(
						"item_defaults",
						{
							"company": company,
							"income_account": income_account,
						},
					)
					changed = True
				elif income_account and default_row.income_account != income_account:
					default_row.income_account = income_account
					changed = True

			if changed:
				doc.save(ignore_permissions=True)
				print(f"Updated item: {item_data['item_code']}")
			else:
				print(f"Item already exists: {item_data['item_code']}")

	frappe.db.commit()
