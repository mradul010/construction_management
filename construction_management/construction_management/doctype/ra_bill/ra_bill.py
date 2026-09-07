import hashlib
import re

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.model.document import Document
from frappe.utils import cint, flt, fmt_money, getdate, today
from erpnext.controllers.accounts_controller import get_taxes_and_charges

from construction_management.construction_management.advance_management import (
	get_ra_bill_advance_recovery_target,
	get_ra_bill_sales_invoice_receivable_account,
	set_item_sales_order,
	sync_ra_bill_advance_rows,
	update_ra_bill_advance_fields,
	validate_ra_bill_advance_recovery,
)
from construction_management.construction_management.accounting_dimensions import (
	apply_ra_bill_cost_center_to_sales_invoice,
	get_ra_bill_project_cost_center,
)
from construction_management.construction_management.utils.accounting import get_construction_account
from construction_management.construction_management.doctype.retention_record.retention_record import (
	get_ra_bill_sales_order,
	mark_cancelled_from_ra_bill,
	set_sales_invoice_for_ra_bill,
	sync_from_ra_bill,
	validate_sales_invoice_references,
)
from construction_management.construction_management.overrides.sales_invoice import (
	apply_ra_bill_deduction_taxes_to_sales_invoice,
	clear_ra_bill_item_tax_overrides,
)
from construction_management.construction_management.ra_bill_dates import (
	apply_ra_bill_dates_to_sales_invoice,
	get_ra_bill_due_date,
	get_ra_bill_posting_date,
	set_default_ra_bill_invoice_dates,
	validate_ra_bill_invoice_dates,
)


OVERBILLING_TOLERANCE = 0.0001

RA_BILL_TAX_CHARGE_TYPES = {
	"Actual",
	"On Net Total",
	"On Previous Row Amount",
	"On Previous Row Total",
	"On Item Quantity",
}

RA_BILL_TEMPLATE_TAX_FIELDS = (
	"charge_type",
	"row_id",
	"account_head",
	"description",
	"included_in_print_rate",
	"cost_center",
	"rate",
)

RA_BILL_VISIBLE_PREFIX = "RAB-"
RA_BILL_VISIBLE_DIGITS = 3


def format_ra_bill_no(sequence):
	return f"{RA_BILL_VISIBLE_PREFIX}{cint(sequence):0{RA_BILL_VISIBLE_DIGITS}d}"


def get_ra_bill_project_key(project):
	project_key = re.sub(r"[^A-Za-z0-9_-]+", "-", str(project or "")).strip("-")
	return project_key or hashlib.sha1(str(project or "").encode()).hexdigest()[:10]


def get_ra_bill_project_series_key(project):
	project_hash = hashlib.sha1(str(project or "").encode()).hexdigest()[:12]
	return f"RA-BILL-{project_hash}-"


def get_max_project_ra_bill_sequence(project, exclude_name=None):
	conditions = ["project = %s", "COALESCE(bill_no, 0) > 0"]
	values = [project]
	if exclude_name:
		conditions.append("name != %s")
		values.append(exclude_name)

	return cint(
		frappe.db.sql(
			f"""
			SELECT MAX(COALESCE(bill_no, 0))
			FROM `tabRA Bill`
			WHERE {" AND ".join(conditions)}
			""",
			values,
		)[0][0]
	)


def get_next_project_ra_bill_sequence(project, exclude_name=None):
	series_key = get_ra_bill_project_series_key(project)
	max_existing = get_max_project_ra_bill_sequence(project, exclude_name=exclude_name)
	frappe.db.sql(
		"""
		INSERT INTO `tabSeries` (`name`, `current`)
		VALUES (%s, %s)
		ON DUPLICATE KEY UPDATE `current` = GREATEST(`current`, VALUES(`current`))
		""",
		(series_key, max_existing),
	)
	return cint(getseries(series_key, RA_BILL_VISIBLE_DIGITS))


def resolve_ra_bill_company(ra_bill):
	project = ra_bill.get("project")
	if not project:
		frappe.throw(_("Please set the Project on this RA Bill."))

	project_company = frappe.db.get_value("Project", project, "company")
	if not project_company and not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} does not exist.").format(frappe.bold(project)))

	company = (
		project_company
		or ra_bill.get("company")
		or frappe.defaults.get_user_default("Company")
		or frappe.defaults.get_global_default("company")
	)
	if not company:
		frappe.throw(
			_(
				"Unable to determine Company for RA Bill {0}. Please configure Company in the Project or system defaults."
			).format(ra_bill.name)
		)

	if project_company and company != project_company:
		frappe.throw(
			_("RA Bill Project {0} belongs to Company {1}, but resolved Company is {2}.").format(
				frappe.bold(project),
				frappe.bold(project_company),
				frappe.bold(company),
			)
		)

	return company


class RABill(Document):
	def before_insert(self):
		if self.amended_from:
			self.bill_no = None
			self.ra_bill_no = None
		self._set_project_wise_bill_identity()

	def autoname(self):
		if not self.bill_no or not self.ra_bill_no:
			self._set_project_wise_bill_identity()
		self.name = self._get_project_wise_internal_name()

	def _validate_links(self):
		self._reset_generated_fields_for_amendment()
		super()._validate_links()

	def validate(self):
		self._reset_generated_fields_for_amendment()
		self._set_active_boq_for_project()
		self._sync_and_validate_boq_contract()
		self._validate_boq_matches_project()
		self._validate_boq_is_active_for_new_bill()
		self._set_default_invoice_dates()
		validate_ra_bill_invoice_dates(self)
		self._set_bill_no()
		self._validate_project_ra_bill_no_unique()
		self._fetch_boq_item_details()
		self._validate_item_hierarchy()
		self._fill_previous_work_summary()
		self.validate_item_values()
		self._calculate_row_totals()
		self._validate_no_duplicate_items()
		self._validate_not_overbilling()
		self._calculate_header_totals()
		self._set_template_tax_rows_if_missing()
		self._validate_payment_and_tax_fields()
		self.calculate_taxes_and_grand_total()
		validate_ra_bill_advance_recovery(self)

	def _reset_generated_fields_for_amendment(self):
		if not self.amended_from or self.docstatus != 0:
			return

		self.sales_invoice = None
		self.status = "Draft"

	def _is_adjustment_row(self, row):
		return (row.get("progress_type") or "Progress") == "Adjustment"

	def _sync_and_validate_boq_contract(self):
		if not self.boq:
			return

		boq = frappe.db.get_value(
			"BOQ",
			self.boq,
			["name", "project", "client", "company", "currency", "sales_order"],
			as_dict=True,
		)
		if not boq:
			frappe.throw(_("BOQ {0} does not exist.").format(self.boq))

		if self.sales_order and self.sales_order != boq.sales_order:
			frappe.throw(
				_("RA Bill Sales Order must match the Sales Order linked to BOQ {0}.").format(
					self.boq
				)
			)
		self.sales_order = boq.sales_order

		self._set_or_validate_boq_field("project", boq.project, _("Project"))
		self._set_or_validate_boq_field("customer", boq.client, _("Customer"))
		self._set_or_validate_boq_field("currency", boq.currency, _("Currency"))

		if boq.sales_order:
			sales_order = frappe.db.get_value(
				"Sales Order",
				boq.sales_order,
				["customer", "project", "company", "currency"],
				as_dict=True,
			)
			if not sales_order:
				frappe.throw(_("Sales Order {0} does not exist.").format(boq.sales_order))
			for label, boq_value, sales_order_value in (
				(_("Customer"), boq.client, sales_order.customer),
				(_("Project"), boq.project, sales_order.project),
				(_("Company"), boq.company, sales_order.company),
				(_("Currency"), boq.currency, sales_order.currency),
			):
				if boq_value and sales_order_value and boq_value != sales_order_value:
					frappe.throw(
						_("BOQ {0} must match Sales Order {0}.").format(label)
					)

	def _set_or_validate_boq_field(self, fieldname, boq_value, label):
		if not boq_value:
			return
		current_value = self.get(fieldname)
		if current_value and current_value != boq_value:
			frappe.throw(_("RA Bill {0} must match BOQ {0}.").format(label))
		if not current_value:
			self.set(fieldname, boq_value)

	def _set_default_invoice_dates(self):
		if self.docstatus == 2:
			return

		set_default_ra_bill_invoice_dates(
			self,
			company=get_ra_bill_tax_company(boq=self.boq),
		)

	@frappe.whitelist()
	def get_invoice_date_defaults(self):
		company = get_ra_bill_tax_company(boq=self.boq)
		posting_date = get_ra_bill_posting_date(self)
		due_date = get_ra_bill_due_date(self, posting_date=posting_date, company=company)
		return {
			"posting_date": posting_date,
			"due_date": due_date,
		}

	def _set_bill_no(self):
		"""
		Auto-increment bill_no per project.
		User-facing RA Bill No. is RAB-001, RAB-002 ... independently per Project.
		"""
		if not self.bill_no:
			self._set_project_wise_bill_identity()
		if not self.ra_bill_no and self.bill_no:
			self.ra_bill_no = format_ra_bill_no(self.bill_no)

	def _set_project_wise_bill_identity(self):
		self._ensure_project_for_numbering()
		if self.bill_no:
			self.ra_bill_no = self.ra_bill_no or format_ra_bill_no(self.bill_no)
			return

		self.bill_no = get_next_project_ra_bill_sequence(self.project, exclude_name=self.name)
		self.ra_bill_no = format_ra_bill_no(self.bill_no)

	def _ensure_project_for_numbering(self):
		if not self.project and self.boq:
			self.project = frappe.db.get_value("BOQ", self.boq, "project")
		if not self.project:
			frappe.throw(_("Project is required before RA Bill number can be generated."))

	def _get_project_wise_internal_name(self):
		project_key = get_ra_bill_project_key(self.project)
		base = f"{project_key}-{self.ra_bill_no}"
		if len(base) > 140:
			project_key = project_key[: max(1, 139 - len(self.ra_bill_no))]
			base = f"{project_key}-{self.ra_bill_no}"

		if not frappe.db.exists("RA Bill", base):
			return base

		project_hash = hashlib.sha1((self.project or "").encode()).hexdigest()[:8]
		base = f"{project_key[: max(1, 130 - len(self.ra_bill_no))]}-{project_hash}-{self.ra_bill_no}"
		if not frappe.db.exists("RA Bill", base):
			return base

		return f"{base[:133]}-{frappe.generate_hash(length=6)}"

	def _validate_project_ra_bill_no_unique(self):
		if not self.project or not self.ra_bill_no:
			return

		duplicate = frappe.db.get_value(
			"RA Bill",
			{
				"project": self.project,
				"ra_bill_no": self.ra_bill_no,
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("RA Bill No. {0} already exists for Project {1} in {2}.").format(
					frappe.bold(self.ra_bill_no),
					frappe.bold(self.project),
					frappe.bold(duplicate),
				)
			)

	def _set_active_boq_for_project(self):
		if self.boq or not self.project:
			return

		active_boq = _get_active_boq_for_project(self.project)
		if active_boq:
			self.boq = active_boq

	def _validate_boq_matches_project(self):
		if not self.project or not self.boq:
			return

		boq_project = frappe.db.get_value("BOQ", self.boq, "project")
		if boq_project and boq_project != self.project:
			frappe.throw(
				_("BOQ {0} belongs to Project {1}, not {2}.").format(
					self.boq, boq_project, self.project
				)
			)

	def _validate_boq_is_active_for_new_bill(self):
		if self.docstatus != 0 or not self.project or not self.boq:
			return

		active_boq = _get_active_boq_for_project(self.project)
		if not active_boq or active_boq == self.boq:
			return

		if "System Manager" in frappe.get_roles():
			frappe.msgprint(
				_(
					"BOQ {0} is not the current active BOQ for Project {1}. "
					"The active BOQ is {2}."
				).format(self.boq, self.project, active_boq),
				indicator="orange",
				alert=True,
			)
			return

		frappe.throw(
			_(
				"New RA Bills must use the active BOQ revision for the Project.<br>"
				"Selected BOQ: {0}<br>Active BOQ: {1}"
			).format(self.boq, active_boq),
			title=_("Inactive BOQ Revision"),
		)

	def validate_item_values(self):
		for row in self.items:
			if not row.boq_item:
				continue

			item = row.item_name or row.boq_item
			progress_type = row.get("progress_type") or "Progress"
			if progress_type not in ("Progress", "Adjustment"):
				frappe.throw(
					_("Progress Type for item {0} must be Progress or Adjustment.").format(item)
				)
			row.progress_type = progress_type

			if progress_type == "Progress" and flt(row.work_percent) <= 0:
				frappe.throw(
					_("Work % for item {0} must be greater than 0.").format(item)
				)

			if progress_type == "Adjustment" and flt(row.work_percent) == 0:
				frappe.throw(
					_("Adjustment % for item {0} cannot be zero.").format(item)
				)

			if progress_type == "Progress" and flt(row.work_percent) > 100:
				frappe.throw(
					_("Work % for item {0} cannot be greater than 100.").format(item)
				)

			if progress_type == "Progress" and flt(row.current_qty) < 0:
				frappe.throw(
					_("Current Qty for item {0} cannot be negative.").format(item)
				)

			if flt(row.boq_qty) <= 0:
				frappe.throw(
					_("BOQ Qty for item {0} must be greater than 0.").format(item)
				)

			if flt(row.boq_rate) < 0:
				frappe.throw(
					_("BOQ Rate for item {0} cannot be negative.").format(item)
				)

	def _fetch_boq_item_details(self):
		"""
		For each RA Bill Item row, fetch item_name, boq_qty,
		boq_rate, uom, and hierarchy from the linked BOQ Item.
		"""
		for row in self.items:
			if not row.boq_item:
				continue

			boq_item = frappe.db.get_value(
				"BOQ Item",
				row.boq_item,
				[
					"item_name",
					"qty",
					"unit_rate",
					"uom",
					"boq_category",
					"boq_item_key",
					"component_key",
				],
				as_dict=True,
			)
			if boq_item:
				hierarchy = _get_boq_item_hierarchy(boq_item.boq_category)
				item = boq_item.item_name or row.boq_item
				if row.category_name and row.category_name != hierarchy.category_name:
					frappe.throw(
						_(
							"Category for RA Bill Item {0} must match the linked BOQ Item."
						).format(item)
					)
				if row.sub_category and row.sub_category != hierarchy.sub_category:
					frappe.throw(
						_(
							"Sub Category for RA Bill Item {0} must match the linked BOQ Item."
						).format(item)
					)

				row.item_name = boq_item.item_name
				row.boq_qty = boq_item.qty
				row.boq_rate = boq_item.unit_rate
				row.uom = boq_item.uom
				row.boq_item_key = (
					boq_item.boq_item_key or boq_item.component_key or row.boq_item
				)
				row.boq_revision = self.boq
				row.original_boq = _get_original_boq(self.boq)
				row.category_name = hierarchy.category_name
				row.sub_category = hierarchy.sub_category

	def _validate_item_hierarchy(self):
		for row in self.items:
			if not row.boq_item:
				continue

			boq_item = frappe.db.get_value(
				"BOQ Item",
				row.boq_item,
				["parent", "boq_category"],
				as_dict=True,
			)
			if not boq_item:
				frappe.throw(_("BOQ Item {0} does not exist.").format(row.boq_item))
			if boq_item.parent != self.boq:
				frappe.throw(
					_("BOQ Item {0} does not belong to BOQ {1}.").format(
						row.boq_item, self.boq
					)
				)

			expected = _get_boq_item_hierarchy(boq_item.boq_category)
			if (row.category_name or "") != (expected.category_name or ""):
				frappe.throw(
					_(
						"Category for RA Bill Item {0} must match the linked BOQ Item."
					).format(row.item_name or row.boq_item)
				)
			if (row.sub_category or "") != (expected.sub_category or ""):
				frappe.throw(
					_(
						"Sub Category for RA Bill Item {0} must match the linked BOQ Item."
					).format(row.item_name or row.boq_item)
				)

	def _fill_previous_work_summary(self):
		"""
		For each row, read previous submitted billing from RA Bill Transaction.
		If transaction history has not been backfilled yet, the helper falls
		back to submitted RA Bill Items. Values are saved on the row so users
		can see previous and remaining work after reload.
		"""
		for row in self.items:
			if not row.boq_item:
				continue

			summary = _get_boq_item_billing_summary(
				self.boq,
				row.boq_item,
				self.name,
			)
			row.previous_qty = summary["previous_qty"]
			row.previous_percent = summary["previous_percent"]
			row.remaining_qty = summary["remaining_qty"]
			row.remaining_percent = summary["remaining_percent"]
			row.prev_cumulative_qty = summary["previous_qty"]

	def _fill_prev_cumulative_qty(self):
		self._fill_previous_work_summary()

	def _calculate_row_totals(self):
		"""
		Calculate current_qty and current_amount for each row from Work %.
		Adjustment rows intentionally keep the sign of Work %.
		"""
		for row in self.items:
			row.work_percent = flt(row.work_percent)
			row.current_qty = flt(row.boq_qty) * (row.work_percent / 100)
			row.current_amount = flt(row.current_qty) * flt(row.boq_rate)
			row.cumulative_qty = flt(row.prev_cumulative_qty) + flt(row.current_qty)
			row.remaining_qty = flt(row.boq_qty) - flt(row.cumulative_qty)
			row.remaining_percent = (
				_qty_to_percent(row.remaining_qty, row.boq_qty) if flt(row.boq_qty) > 0 else 0
			)

	def _validate_no_duplicate_items(self):
		seen_items = set()

		for row in self.items:
			if not row.boq_item:
				continue

			item_key = row.boq_item_key or row.boq_item
			if item_key in seen_items:
				frappe.throw(
					_(
						"Duplicate BOQ Item found: {0}. "
						"The same BOQ Item cannot be selected more than once in the same RA Bill."
					).format(row.item_name or row.boq_item)
				)

			seen_items.add(item_key)

	def _validate_not_overbilling(self):
		for row in self.items:
			if not row.boq_item:
				continue

			boq_qty = flt(row.boq_qty)
			current_qty = flt(row.current_qty)
			summary = _get_boq_item_billing_summary(self.boq, row.boq_item, self.name)
			previous_qty = summary["previous_qty"]
			available_qty = summary["remaining_qty"]
			previous_pct = summary["previous_percent"]
			available_pct = summary["remaining_percent"]

			row.previous_qty = previous_qty
			row.previous_percent = previous_pct
			row.prev_cumulative_qty = previous_qty
			row.cumulative_qty = previous_qty + current_qty
			row.remaining_qty = boq_qty - row.cumulative_qty
			row.remaining_percent = (
				_qty_to_percent(row.remaining_qty, boq_qty) if boq_qty > 0 else 0
			)

			if self._is_adjustment_row(row):
				if previous_qty <= OVERBILLING_TOLERANCE:
					frappe.throw(
						_("Adjustment item {0} must have previous submitted RA progress.").format(
							row.item_name or row.boq_item
						)
					)

				if row.cumulative_qty < -OVERBILLING_TOLERANCE:
					frappe.throw(
						_(
							"Adjustment for item {item} would reduce cumulative progress below zero.<br>"
							"Previous Qty: {previous_qty}<br>"
							"Adjustment Qty: {current_qty}"
						).format(
							item=row.item_name or row.boq_item,
							previous_qty=flt(previous_qty, 4),
							current_qty=flt(current_qty, 4),
						),
						title=_("Invalid Adjustment"),
					)

				if row.cumulative_qty > boq_qty + OVERBILLING_TOLERANCE:
					frappe.throw(
						_(
							"Adjustment for item {item} would increase cumulative progress above 100%.<br>"
							"BOQ Qty: {boq_qty}<br>"
							"Previous Qty: {previous_qty}<br>"
							"Adjustment Qty: {current_qty}"
						).format(
							item=row.item_name or row.boq_item,
							boq_qty=flt(boq_qty, 4),
							previous_qty=flt(previous_qty, 4),
							current_qty=flt(current_qty, 4),
						),
						title=_("Invalid Adjustment"),
					)
				continue

			if current_qty > available_qty + OVERBILLING_TOLERANCE:
				frappe.throw(
					_(
						"Item: {item}<br>"
						"BOQ Qty: {boq_qty}<br>"
						"Previously Billed Qty: {previous_qty}<br>"
						"Previously Billed %: {previous_pct}<br>"
						"Available Qty Before Current Bill: {remaining_qty}<br>"
						"Available % Before Current Bill: {remaining_pct}<br>"
						"You Entered Qty: {current_qty}<br>"
						"You Entered %: {work_percent}<br><br>"
						"Please reduce Work % / Current Qty."
					).format(
						item=row.item_name or row.boq_item,
						boq_qty=flt(boq_qty, 4),
						previous_qty=flt(previous_qty, 4),
						previous_pct=flt(previous_pct, 4),
						remaining_qty=flt(available_qty, 4),
						remaining_pct=flt(available_pct, 4),
						current_qty=flt(current_qty, 4),
						work_percent=flt(row.work_percent, 4),
					),
					title=_("Overbilling Not Allowed"),
				)

	def _calculate_header_totals(self):
		"""
		Sum up gross_amount, retention_amount, net_payable,
		and cumulative_billed across all submitted bills
		for this project + BOQ including this one.
		"""
		self.gross_amount = sum(row.current_amount or 0 for row in self.items)

		retention_pct = float(self.retention_percent or 0)
		self.retention_amount = self.gross_amount * (retention_pct / 100)
		self.net_payable = self.gross_amount - self.retention_amount

		chain_names = _get_boq_chain_names(self.boq)
		prev_billed = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(gross_amount), 0)
			FROM `tabRA Bill`
			WHERE project = %s
			  AND boq IN %s
			  AND docstatus = 1
			  AND name != %s
			""",
			(self.project, tuple(chain_names or [self.boq]), self.name or "__new__"),
		)
		self.cumulative_billed = (prev_billed[0][0] if prev_billed else 0) + self.gross_amount

	def _validate_payment_and_tax_fields(self):
		for row in self.get("advances") or []:
			advance_amount = flt(row.advance_amount)
			allocated_amount = flt(row.allocated_amount)

			if advance_amount < 0:
				frappe.throw(_("Advance Amount cannot be negative."))

			if allocated_amount < 0:
				frappe.throw(_("Allocated Amount cannot be negative."))

			if advance_amount and allocated_amount > advance_amount + OVERBILLING_TOLERANCE:
				frappe.throw(
					_(
						"Allocated Amount cannot be greater than Advance Amount "
						"for reference {0}."
					).format(row.reference_name or row.idx)
				)

		for row in self.get("taxes") or []:
			if row.charge_type and row.charge_type not in RA_BILL_TAX_CHARGE_TYPES:
				frappe.throw(_("Invalid tax charge type: {0}").format(row.charge_type))

		if self.sales_taxes_and_charges_template:
			validate_ra_bill_tax_template_company(
				self.sales_taxes_and_charges_template,
				get_ra_bill_tax_company(boq=self.boq),
			)

	def _set_template_tax_rows_if_missing(self):
		if not self.sales_taxes_and_charges_template or self.get("taxes"):
			return

		for row in get_ra_bill_template_tax_rows(
			self.sales_taxes_and_charges_template,
			boq=self.boq,
		):
			self.append("taxes", row)

	def calculate_taxes_and_grand_total(self):
		"""
		Calculate Sales Invoice-like tax totals on the RA Bill certified amount.
		Retention remains a separate RA Bill field and does not reduce this tax base.
		"""
		calculate_ra_bill_taxes(self)

		advance_values = update_ra_bill_advance_fields(self)
		self.total_advance = (
			flt(advance_values.get("actual_advance_recovered"))
			if advance_values
			else sum(flt(row.allocated_amount) for row in self.get("advances") or [])
		)
		self.outstanding_amount = flt(self.grand_total) - flt(self.total_advance)

	def on_submit(self):
		self._validate_no_duplicate_items()
		self._validate_not_overbilling()
		self._create_ra_bill_transactions()
		sync_from_ra_bill(self)
		self.db_set("status", "Submitted")

	def on_cancel(self):
		self._cancel_linked_sales_invoice()
		self._delete_ra_bill_transactions()
		mark_cancelled_from_ra_bill(self)
		self.db_set("status", "Cancelled")

	def _cancel_linked_sales_invoice(self):
		if not self.sales_invoice:
			return

		invoice = frappe.db.get_value(
			"Sales Invoice",
			self.sales_invoice,
			["name", "docstatus"],
			as_dict=True,
		)
		if not invoice or invoice.docstatus == 2:
			return

		if invoice.docstatus != 1:
			frappe.throw(
				_(
					"Sales Invoice {0} must be submitted before it can be cancelled with RA Bill {1}."
				).format(self.sales_invoice, self.name)
			)

		frappe.get_doc("Sales Invoice", self.sales_invoice).cancel()

	def on_trash(self):
		if self.docstatus != 2 or not self.sales_invoice:
			return

		invoice = frappe.db.get_value(
			"Sales Invoice",
			self.sales_invoice,
			["name", "docstatus", "ra_bill"],
			as_dict=True,
		)
		if not invoice or invoice.ra_bill != self.name:
			return

		if invoice.docstatus != 2:
			frappe.throw(
				_(
					"Cannot delete cancelled RA Bill {0} while linked Sales Invoice {1} is not cancelled."
				).format(self.name, self.sales_invoice)
			)

		frappe.db.set_value(
			"Sales Invoice",
			self.sales_invoice,
			"ra_bill",
			None,
			update_modified=False,
		)

	def _delete_ra_bill_transactions(self):
		_delete_ra_bill_transactions(self.name)

	def _create_ra_bill_transactions(self):
		self._delete_ra_bill_transactions()

		for row in self.items:
			current_qty = _get_row_current_qty(row)
			current_amount = _get_row_current_amount(row)
			is_adjustment = self._is_adjustment_row(row)
			if not is_adjustment and (current_qty <= 0 or current_amount <= 0):
				continue

			previous_qty = _get_previous_billed_qty(self.boq, row.boq_item, self.name)
			_create_ra_bill_transaction(self, row, previous_qty)

	@frappe.whitelist()
	def approve(self):
		"""
		Approve a submitted RA Bill without saving the submitted document.
		The Create Sales Invoice flow depends on this status.
		"""
		if self.docstatus != 1:
			frappe.throw("Only submitted RA Bills can be approved.")

		if self.status == "Approved":
			return self.name

		if self.status != "Submitted":
			frappe.throw(
				"RA Bill must have status 'Submitted' before approval. "
				f"Current status: {self.status}"
			)

		self.db_set("status", "Approved")
		return self.name

	@frappe.whitelist()
	def get_advances_received(self):
		source_sales_order = get_ra_bill_sales_order(self)
		if not source_sales_order:
			frappe.throw(_("No Sales Order is linked to this RA Bill or its BOQ."))

		if not self.customer:
			frappe.throw(_("Please set the Customer before fetching advances."))

		company = resolve_ra_bill_company(self)

		self.calculate_taxes_and_grand_total()
		advance_values = update_ra_bill_advance_fields(self)
		sync_ra_bill_advance_rows(
			self,
			source_sales_order,
			flt(advance_values.get("actual_advance_recovered")),
			flt(advance_values.get("previously_recovered_advance")),
		)
		return {
			"advances": [row.as_dict() for row in self.get("advances")],
			"total_advance": self.total_advance,
			"outstanding_amount": self.outstanding_amount,
			"total_advance_received": self.get("total_advance_received"),
			"previously_recovered_advance": self.get("previously_recovered_advance"),
			"remaining_advance_before_current_bill": self.get("remaining_advance_before_current_bill"),
			"proposed_advance_recovery": self.get("proposed_advance_recovery"),
			"actual_advance_recovered": self.get("actual_advance_recovered"),
			"remaining_advance_after_current_bill": self.get("remaining_advance_after_current_bill"),
		}

	@frappe.whitelist()
	def create_sales_invoice(self):
		"""
		Creates a draft Sales Invoice from this approved RA Bill.
		Detailed lines:
		  1. One line per RA Bill Item current_amount (positive)
		The Sales Invoice remains at the full certified value. Retention is tracked
		on the RA Bill/Retention Record and deducted later through Payment Entry.
		Status set to Invoiced after creation.
		"""
		if self.status != "Approved":
			frappe.throw(
				"RA Bill must have status 'Approved' before creating a Sales Invoice. "
				f"Current status: {self.status}"
			)

		if self.sales_invoice:
			frappe.throw(
				f"Sales Invoice {self.sales_invoice} already exists for this RA Bill. "
				"Cannot create another one."
			)

		if not self.customer:
			frappe.throw("Please set the Customer on this RA Bill before creating a Sales Invoice.")

		if not self.project:
			frappe.throw("Please set the Project on this RA Bill before creating a Sales Invoice.")

		if not frappe.db.exists("Customer", self.customer):
			frappe.throw(f"Customer {self.customer} does not exist.")

		if not self.gross_amount or self.gross_amount <= 0:
			frappe.throw("Gross amount must be greater than 0 to create a Sales Invoice.")

		from construction_management.construction_management.setup import ensure_ra_bill_items
		from construction_management.construction_management.regional import (
			get_default_construction_service_item,
			get_default_construction_uom,
			validate_construction_service_item_can_be_created,
		)

		company = resolve_ra_bill_company(self)

		ensure_ra_bill_items(company=company)
		service_item = get_default_construction_service_item(company)
		service_uom = get_default_construction_uom(company)
		if not frappe.db.exists("Item", service_item):
			validate_construction_service_item_can_be_created(company)
			frappe.throw(
				_("Please create construction service Item {0} before creating the Sales Invoice.").format(
					frappe.bold(service_item)
				)
			)
		company_currency = frappe.get_cached_value("Company", company, "default_currency")
		income_account = get_construction_account(
			company,
			"ra_bill_income",
			project=self.project,
			transaction=self,
		)
		invoice_currency = self.currency or company_currency or frappe.defaults.get_global_default("currency")

		def format_invoice_currency(value):
			return fmt_money(flt(value), currency=invoice_currency)

		conversion_rate = 1.0
		receivable_account = get_ra_bill_sales_invoice_receivable_account(
			self.customer,
			company,
			invoice_currency,
			project=self.project,
		)
		source_sales_order = get_ra_bill_sales_order(self)
		project_cost_center = get_ra_bill_project_cost_center(
			self.name,
			project=self.project,
			company=company,
		)

		def set_if_exists(doc, fieldname, value):
			if doc.meta.has_field(fieldname) and value not in (None, ""):
				doc.set(fieldname, value)

		def append_child_if_table_exists(doc, table_field, row_data):
			table_df = doc.meta.get_field(table_field)
			if not table_df or table_df.fieldtype != "Table" or not table_df.options:
				return

			child_meta = frappe.get_meta(table_df.options)
			filtered_row = {
				fieldname: value
				for fieldname, value in row_data.items()
				if child_meta.has_field(fieldname) and value not in (None, "")
			}
			if filtered_row:
				doc.append(table_field, filtered_row)

		def set_link_if_valid(doc, fieldname, value, parenttype, link_doctype, link_name):
			if not doc.meta.has_field(fieldname) or value in (None, ""):
				return

			if frappe.db.exists(
				"Dynamic Link",
				{
					"parent": value,
					"parenttype": parenttype,
					"link_doctype": link_doctype,
					"link_name": link_name,
				},
			):
				doc.set(fieldname, value)

		def get_posting_date():
			return get_ra_bill_posting_date(self)

		def get_due_date():
			return get_ra_bill_due_date(
				self,
				posting_date=get_posting_date(),
				company=company,
			)

		def add_advanced_fields(si):
			set_if_exists(si, "customer", self.customer)
			set_if_exists(si, "company", company)
			set_if_exists(si, "debit_to", receivable_account)
			set_if_exists(si, "project", self.project)
			set_if_exists(si, "cost_center", project_cost_center)
			set_if_exists(si, "currency", invoice_currency)
			set_if_exists(si, "conversion_rate", conversion_rate)
			set_if_exists(si, "posting_date", get_posting_date())
			set_if_exists(si, "due_date", get_due_date())
			set_if_exists(si, "remarks", self.remarks or f"Created from RA Bill {self.name}")
			set_if_exists(si, "letter_head", self.letter_head)
			set_if_exists(si, "select_print_heading", self.select_print_heading)
			set_if_exists(si, "language", self.language)
			set_if_exists(si, "ra_bill", self.name)
			set_if_exists(si, "boq", self.boq)
			set_if_exists(si, "sales_order", source_sales_order)
			set_if_exists(si, "allocate_advances_automatically", 0)

			set_link_if_valid(
				si,
				"customer_address",
				self.customer_address,
				"Address",
				"Customer",
				self.customer,
			)
			set_link_if_valid(
				si,
				"shipping_address_name",
				self.shipping_address_name,
				"Address",
				"Customer",
				self.customer,
			)
			set_link_if_valid(
				si,
				"contact_person",
				self.contact_person,
				"Contact",
				"Customer",
				self.customer,
			)
			set_link_if_valid(
				si,
				"dispatch_address_name",
				self.dispatch_address_name,
				"Address",
				"Company",
				company,
			)
			set_link_if_valid(
				si,
				"company_address",
				self.company_address,
				"Address",
				"Company",
				company,
			)
			set_link_if_valid(
				si,
				"company_contact_person",
				self.company_contact_person,
				"Contact",
				"Company",
				company,
			)

			for source_field, target_field in (
				("address_display", "address_display"),
				("contact_display", "contact_display"),
				("contact_mobile", "contact_mobile"),
				("contact_email", "contact_email"),
				("shipping_address", "shipping_address"),
				("dispatch_address", "dispatch_address"),
				("company_address_display", "company_address_display"),
				("territory", "territory"),
				("payment_terms_template", "payment_terms_template"),
				("terms", "tc_name"),
				("terms_and_conditions", "terms"),
				("tax_category", "tax_category"),
				("shipping_rule", "shipping_rule"),
				("incoterm", "incoterm"),
				("sales_taxes_and_charges_template", "taxes_and_charges"),
			):
				set_if_exists(si, target_field, self.get(source_field))

			for row in self.get("payment_schedule") or []:
				append_child_if_table_exists(
					si,
					"payment_schedule",
					{
						"payment_term": row.payment_term,
						"description": row.description,
						"due_date": row.due_date,
						"invoice_portion": row.invoice_portion,
						"payment_amount": row.payment_amount,
					},
				)

			for row in self.get("timesheets") or []:
				append_child_if_table_exists(
					si,
					"timesheets",
					{
						"activity_type": row.activity_type,
						"description": row.description,
						"billing_hours": row.billing_hours,
						"billing_amount": row.billing_amount,
						"time_sheet": row.timesheet,
					},
				)

		def make_sales_invoice(items):
			si_data = {
				"doctype": "Sales Invoice",
				"items": items,
			}
			si = frappe.get_doc(si_data)
			add_advanced_fields(si)
			apply_ra_bill_dates_to_sales_invoice(si, self, company=company)
			apply_ra_bill_cost_center_to_sales_invoice(si)
			validate_sales_invoice_references(si)
			if hasattr(si, "set_missing_values"):
				si.set_missing_values()
			apply_ra_bill_dates_to_sales_invoice(si, self, company=company)
			apply_ra_bill_cost_center_to_sales_invoice(si)
			recovery_target = get_ra_bill_advance_recovery_target(self)
			apply_ra_bill_deduction_taxes_to_sales_invoice(
				si,
				self,
				advance_native=recovery_target,
			)
			if hasattr(si, "calculate_taxes_and_totals"):
				si.calculate_taxes_and_totals()
			apply_ra_bill_dates_to_sales_invoice(si, self, company=company)
			clear_ra_bill_item_tax_overrides(si)
			si.insert(ignore_permissions=True)
			return si

		period_str = ""
		if self.billing_period_from and self.billing_period_to:
			period_str = (
				f"{frappe.format(self.billing_period_from, {'fieldtype': 'Date'})} to "
				f"{frappe.format(self.billing_period_to, {'fieldtype': 'Date'})}"
			)

		category_labels = {}

		def get_category_label(category):
			if not category:
				return ""
			if category not in category_labels:
				category_labels[category] = (
					frappe.db.get_value("BOQ Category", category, "category_name") or category
				)
			return category_labels[category]

		invoice_items = []
		has_adjustment_rows = any(
			(row.get("progress_type") or "Progress") == "Adjustment"
			or flt(row.get("current_amount")) < 0
			for row in self.items
		)

		if has_adjustment_rows:
			ra_bill_no = self.ra_bill_no or format_ra_bill_no(self.bill_no)
			description_lines = [
				f"RA Bill: {ra_bill_no}",
				f"Project: {self.project}",
				f"BOQ: {self.boq}",
				"Includes progress adjustments/corrections recorded in the RA Bill detail.",
			]
			if period_str:
				description_lines.insert(1, f"Billing Period: {period_str}")

			invoice_items.append(
				{
					"item_code": service_item,
					"item_name": f"{ra_bill_no} Progress Payment",
					"description": "\n".join(description_lines),
					"qty": 1,
					"rate": flt(self.gross_amount),
					"uom": service_uom,
					"income_account": income_account,
					"cost_center": project_cost_center,
				}
			)
		else:
			ra_bill_no = self.ra_bill_no or format_ra_bill_no(self.bill_no)
			for row in self.items:
				qty = flt(row.current_qty or 0)
				rate = flt(row.boq_rate or 0)
				amount = flt(row.current_amount or 0)

				if qty <= 0 or amount <= 0:
					continue

				calculated_amount = flt(qty * rate)

				description_lines = [
					f"Category: {get_category_label(row.category_name)}",
					f"Sub Category: {get_category_label(row.sub_category)}",
					f"Item: {row.item_name or ''}",
					f"BOQ Qty: {flt(row.boq_qty)} {row.uom or ''}".strip(),
					f"BOQ Rate: {rate}",
					f"Work Completed: {flt(row.work_percent)}%",
					f"Current Qty: {qty}",
					f"Amount: {amount}",
				]
				if abs(calculated_amount - amount) > 0.01:
					description_lines.append(
						f"Amount Check: Qty x Rate = {calculated_amount}; RA Bill Current Amount = {amount}"
					)
				if period_str:
					description_lines.append(f"Billing Period: {period_str}")
				description_lines.extend(
					[
						f"RA Bill: {ra_bill_no}",
						f"Project: {self.project}",
						f"BOQ: {self.boq}",
					]
				)

				invoice_items.append(
					{
						"item_code": service_item,
						"item_name": row.item_name or service_item,
						"description": "\n".join(description_lines),
						"qty": qty,
						"rate": rate,
						"uom": row.uom or service_uom,
						"income_account": income_account,
						"cost_center": project_cost_center,
					}
				)

		if not invoice_items:
			frappe.throw("No RA Bill Items with a positive current amount were found to invoice.")

		validate_ra_bill_advance_recovery(self)
		set_item_sales_order(invoice_items, source_sales_order)

		invoice_gross = sum(
			flt(item.get("qty")) * flt(item.get("rate")) for item in invoice_items
		)
		if flt(invoice_gross, 2) != flt(self.gross_amount, 2):
			frappe.throw(
				"Detailed RA Bill Item total does not match the RA Bill gross amount. "
				f"Item total: {format_invoice_currency(invoice_gross)}, "
				f"Gross amount: {format_invoice_currency(self.gross_amount)}."
			)

		invoice_certified_total = sum(
			flt(item.get("qty")) * flt(item.get("rate")) for item in invoice_items
		)
		if flt(invoice_certified_total, 2) != flt(self.gross_amount, 2):
			frappe.throw(
				"Sales Invoice item total does not match the RA Bill certified amount. "
				f"Invoice total: {format_invoice_currency(invoice_certified_total)}, "
				f"Certified amount: {format_invoice_currency(self.gross_amount)}."
			)

		si = make_sales_invoice(invoice_items)

		self.db_set("sales_invoice", si.name)
		allocated_advance = get_ra_bill_advance_recovery_target(self)
		outstanding_amount = flt(si.outstanding_amount)
		field_updates = {
			"actual_advance_recovered": allocated_advance,
			"total_advance": allocated_advance,
			"outstanding_amount": outstanding_amount,
			"remaining_advance_after_current_bill": max(
				flt(self.remaining_advance_before_current_bill) - allocated_advance,
				0,
			),
		}
		for fieldname, value in field_updates.items():
			if self.meta.has_field(fieldname):
				self.db_set(fieldname, value, update_modified=False)
		set_sales_invoice_for_ra_bill(self, si.name)
		self.db_set("status", "Invoiced")

		frappe.msgprint(
			f"Draft Sales Invoice <b>{si.name}</b> created successfully. "
			f"Certified amount: {format_invoice_currency(self.gross_amount)}. "
			f"Please review and submit from the Accounts module.",
			title="Sales Invoice Created",
			indicator="green",
		)

		return si.name


def get_ra_bill_tax_company(company=None, boq=None):
	if company:
		return company

	if boq:
		boq_company = frappe.db.get_value("BOQ", boq, "company")
		if boq_company:
			return boq_company

	return frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")


def validate_ra_bill_tax_template_company(template, company=None):
	if not template:
		return

	template_doc = frappe.db.get_value(
		"Sales Taxes and Charges Template",
		template,
		["name", "company", "disabled"],
		as_dict=True,
	)
	if not template_doc:
		frappe.throw(_("Sales Taxes and Charges Template {0} does not exist.").format(template))

	if template_doc.disabled:
		frappe.throw(_("Sales Taxes and Charges Template {0} is disabled.").format(template))

	if company and template_doc.company and template_doc.company != company:
		frappe.throw(
			_("Sales Taxes and Charges Template {0} belongs to Company {1}, not {2}.").format(
				template,
				template_doc.company,
				company,
			)
		)


@frappe.whitelist()
def get_ra_bill_template_tax_rows(template, company=None, boq=None):
	company = get_ra_bill_tax_company(company=company, boq=boq)
	validate_ra_bill_tax_template_company(template, company)

	child_meta = frappe.get_meta("RA Bill Taxes and Charges")
	rows = []
	for source in get_taxes_and_charges("Sales Taxes and Charges Template", template) or []:
		row = {}
		for fieldname in RA_BILL_TEMPLATE_TAX_FIELDS:
			if child_meta.has_field(fieldname):
				row[fieldname] = source.get(fieldname)
		if source.get("charge_type") == "Actual" and child_meta.has_field("tax_amount"):
			row["tax_amount"] = flt(source.get("tax_amount"))
		if child_meta.has_field("from_template"):
			row["from_template"] = 1
		if child_meta.has_field("source_tax_template"):
			row["source_tax_template"] = template
		rows.append(row)

	return rows


def _get_permission_checked_boq(boq, permission_type="read"):
	if not boq:
		frappe.throw(_("Please select a BOQ."))

	doc = frappe.get_doc("BOQ", boq)
	doc.check_permission(permission_type)
	return doc


def _get_boq_child_item_row(boq_doc, boq_item):
	for row in boq_doc.get("items") or []:
		if row.name == boq_item:
			return row

	frappe.throw(_("BOQ Item {0} does not belong to BOQ {1}.").format(boq_item, boq_doc.name))


def _get_boq_category_label_map(category_names):
	category_names = [name for name in set(category_names or []) if name]
	if not category_names:
		return {}, []

	categories = frappe.get_all(
		"BOQ Category",
		filters={"name": ["in", category_names]},
		fields=["name", "category_name", "parent_node"],
		limit_page_length=1000,
	)
	parent_names = [row.parent_node for row in categories if row.parent_node]
	parents = []
	if parent_names:
		parents = frappe.get_all(
			"BOQ Category",
			filters={"name": ["in", list(set(parent_names))]},
			fields=["name", "category_name", "parent_node"],
			limit_page_length=1000,
		)

	label_map = {}
	for row in [*categories, *parents]:
		label_map[row.name] = row.category_name or row.name

	return label_map, categories


def _get_boq_item_hierarchy(boq_category):
	if not boq_category:
		return frappe._dict(
			{
				"category_name": "",
				"sub_category": "",
				"category_label": "",
				"sub_category_label": "",
			}
		)

	category = frappe.db.get_value(
		"BOQ Category",
		boq_category,
		["name", "category_name", "parent_node"],
		as_dict=True,
	)
	if not category:
		return frappe._dict(
			{
				"category_name": boq_category,
				"sub_category": "",
				"category_label": boq_category,
				"sub_category_label": "",
			}
		)

	if category.parent_node:
		parent_label = (
			frappe.db.get_value("BOQ Category", category.parent_node, "category_name")
			or category.parent_node
		)
		return frappe._dict(
			{
				"category_name": category.parent_node,
				"sub_category": category.name,
				"category_label": parent_label,
				"sub_category_label": category.category_name or category.name,
			}
		)

	return frappe._dict(
		{
			"category_name": category.name,
			"sub_category": "",
			"category_label": category.category_name or category.name,
			"sub_category_label": "",
		}
	)


@frappe.whitelist()
def get_boq_item_details_for_ra_bill(boq, boq_item):
	boq_doc = _get_permission_checked_boq(boq)
	row = _get_boq_child_item_row(boq_doc, boq_item)
	hierarchy = _get_boq_item_hierarchy(row.get("boq_category"))

	return {
		"name": row.name,
		"parent": boq_doc.name,
		"item": row.get("item"),
		"item_name": row.get("item_name"),
		"qty": flt(row.get("qty")),
		"unit_rate": flt(row.get("unit_rate")),
		"unit_cost": flt(row.get("unit_cost")),
		"uom": row.get("uom"),
		"boq_category": row.get("boq_category"),
		"boq_parent_category": row.get("boq_parent_category"),
		"category_name": hierarchy.category_name,
		"sub_category": hierarchy.sub_category,
		"parent_category": hierarchy.category_name,
		"category_label": hierarchy.sub_category_label or hierarchy.category_label,
		"parent_category_label": hierarchy.category_label,
		"boq_item_key": row.get("boq_item_key"),
		"component_key": row.get("component_key"),
		"is_deleted_in_revision": row.get("is_deleted_in_revision"),
	}


@frappe.whitelist()
def get_boq_context_for_ra_bill(boq):
	boq_doc = _get_permission_checked_boq(boq)
	items = []
	category_names = []

	for row in boq_doc.get("items") or []:
		if row.get("is_deleted_in_revision"):
			continue

		if row.get("boq_category"):
			category_names.append(row.boq_category)
		items.append(
			{
				"name": row.name,
				"boq_category": row.get("boq_category"),
				"item": row.get("item"),
				"item_name": row.get("item_name"),
				"boq_item_key": row.get("boq_item_key"),
			}
		)

	label_map, categories = _get_boq_category_label_map(category_names)
	parent_names = [category.parent_node for category in categories if category.parent_node]
	all_category_names = list(set([*category_names, *parent_names]))

	return {
		"items": items,
		"categories": [
			{"name": name, "category_name": label_map.get(name) or name}
			for name in all_category_names
			if name
		],
	}


def calculate_ra_bill_taxes(doc):
	doc.net_total = flt(doc.gross_amount)
	running_total = flt(doc.net_total)
	total_taxes = 0
	calculated_rows = []

	for row in doc.get("taxes") or []:
		tax_amount = get_ra_bill_tax_amount(row, doc.net_total, calculated_rows)
		if row.charge_type != "On Item Quantity":
			row.tax_amount = tax_amount
		else:
			tax_amount = flt(row.tax_amount)

		total_taxes += tax_amount
		running_total += tax_amount
		row.total = running_total
		calculated_rows.append(
			frappe._dict(
				{
					"tax_amount": tax_amount,
					"total": running_total,
				}
			)
		)

	doc.total_taxes_and_charges = total_taxes
	doc.grand_total = running_total


def get_ra_bill_tax_amount(row, net_total, previous_rows):
	charge_type = row.charge_type or "Actual"

	if charge_type == "Actual":
		return flt(row.tax_amount)

	if charge_type == "On Net Total":
		return flt(net_total) * flt(row.rate) / 100

	if charge_type in ("On Previous Row Amount", "On Previous Row Total"):
		reference_row = get_previous_ra_bill_tax_row(row, previous_rows)
		reference_amount = (
			flt(reference_row.total)
			if charge_type == "On Previous Row Total"
			else flt(reference_row.tax_amount)
		)
		return reference_amount * flt(row.rate) / 100

	return flt(row.tax_amount)


def get_previous_ra_bill_tax_row(row, previous_rows):
	try:
		row_id = int(row.row_id)
	except (TypeError, ValueError):
		row_id = 0

	if row_id < 1 or row_id > len(previous_rows):
		frappe.throw(
			_("Tax row {0} must reference a previous row for charge type {1}.").format(
				row.idx or "",
				row.charge_type,
			)
		)

	return previous_rows[row_id - 1]


@frappe.whitelist()
def get_customer_address_and_contact(customer):
	if not customer:
		return {}

	from frappe.contacts.doctype.address.address import get_address_display, get_default_address
	from frappe.contacts.doctype.contact.contact import get_default_contact

	billing_address = get_default_address("Customer", customer, "is_primary_address")
	shipping_address = get_default_address("Customer", customer, "is_shipping_address")
	contact = get_default_contact("Customer", customer)
	contact_details = {}

	if contact:
		contact_details = frappe.db.get_value(
			"Contact",
			contact,
			["full_name", "email_id", "mobile_no"],
			as_dict=True,
		) or {}

	return {
		"customer_address": billing_address,
		"address_display": get_address_display(billing_address) if billing_address else "",
		"shipping_address_name": shipping_address,
		"shipping_address": get_address_display(shipping_address) if shipping_address else "",
		"contact_person": contact,
		"contact_display": contact_details.get("full_name") or "",
		"contact_email": contact_details.get("email_id") or "",
		"contact_mobile": contact_details.get("mobile_no") or "",
		"territory": frappe.db.get_value("Customer", customer, "territory") or "",
	}


def _has_ra_bill_transaction_table():
	try:
		return frappe.db.table_exists("RA Bill Transaction")
	except Exception:
		return False


def _delete_ra_bill_transactions(ra_bill):
	if not ra_bill or not _has_ra_bill_transaction_table():
		return

	for transaction in frappe.get_all(
		"RA Bill Transaction",
		filters={"ra_bill": ra_bill},
		pluck="name",
	):
		frappe.delete_doc(
			"RA Bill Transaction",
			transaction,
			force=True,
			ignore_permissions=True,
		)


def _doctype_has_field(doctype, fieldname):
	try:
		return frappe.get_meta(doctype).has_field(fieldname)
	except Exception:
		return False


def _get_original_boq(boq):
	if not boq:
		return None

	if not _doctype_has_field("BOQ", "original_boq"):
		return boq

	values = frappe.db.get_value(
		"BOQ",
		boq,
		["original_boq", "parent_boq"],
		as_dict=True,
	)
	if not values:
		return boq
	if values.original_boq:
		return values.original_boq
	if values.parent_boq:
		return _get_original_boq(values.parent_boq)
	return boq


def _get_boq_chain_names(boq):
	original_boq = _get_original_boq(boq)
	if not original_boq:
		return []

	names = {original_boq}
	if _doctype_has_field("BOQ", "original_boq"):
		names.update(
			frappe.get_all(
				"BOQ",
				filters={"original_boq": original_boq},
				pluck="name",
			)
		)
	return list(names)


def _get_boq_item_context(boq, boq_item):
	if not boq_item:
		return frappe._dict(
			{
				"boq": boq,
				"boq_item": boq_item,
				"boq_item_key": None,
				"qty": 0,
				"unit_rate": 0,
			}
		)

	fields = ["name", "parent", "qty", "unit_rate", "item"]
	for fieldname in ("boq_item_key", "component_key"):
		if _doctype_has_field("BOQ Item", fieldname):
			fields.append(fieldname)

	row = frappe.db.get_value("BOQ Item", boq_item, fields, as_dict=True) or {}
	boq_item_key = (
		row.get("boq_item_key")
		or row.get("component_key")
		or row.get("item")
		or boq_item
	)

	return frappe._dict(
		{
			"boq": boq or row.get("parent"),
			"boq_item": boq_item,
			"boq_item_key": boq_item_key,
			"qty": flt(row.get("qty")),
			"unit_rate": flt(row.get("unit_rate")),
		}
	)


def _get_active_boq_for_project(project):
	if not project:
		return None

	if _doctype_has_field("Project", "current_boq"):
		current_boq = frappe.db.get_value("Project", project, "current_boq")
		if current_boq:
			current = frappe.db.get_value(
				"BOQ",
				current_boq,
				["project", "is_active_revision", "docstatus"],
				as_dict=True,
			)
			if (
				current
				and current.project == project
				and current.is_active_revision
				and current.docstatus != 2
			):
				return current_boq

	active = frappe.get_all(
		"BOQ",
		filters={
			"project": project,
			"is_active_revision": 1,
			"docstatus": ["!=", 2],
		},
		fields=["name"],
		order_by="revision_no desc, modified desc",
		limit=1,
	)
	return active[0].name if active else None


@frappe.whitelist()
def get_active_boq_for_project(project):
	return _get_active_boq_for_project(project)


def _get_previous_billed_qty(boq, boq_item, current_ra_bill=None):
	if not boq or not boq_item:
		return 0

	context = _get_boq_item_context(boq, boq_item)
	original_boq = _get_original_boq(context.boq or boq)
	boq_item_key = context.boq_item_key

	transaction_qty = 0
	transaction_count = 0
	if _has_ra_bill_transaction_table():
		transaction_qty, transaction_count = _get_previous_billed_qty_from_transactions(
			original_boq,
			boq_item_key,
			boq_item,
			current_ra_bill,
		)

	fallback_qty = _get_previous_billed_qty_from_submitted_ra_bills(
		original_boq,
		boq,
		boq_item_key,
		boq_item,
		current_ra_bill,
	)

	if transaction_count:
		return max(transaction_qty, fallback_qty)

	return fallback_qty


def _get_previous_billed_qty_from_transactions(
	original_boq,
	boq_item_key,
	boq_item,
	current_ra_bill=None,
):
	if (
		not original_boq
		or not boq_item_key
		or not _doctype_has_field("RA Bill Transaction", "original_boq")
		or not _doctype_has_field("RA Bill Transaction", "boq_item_key")
	):
		return _get_previous_billed_qty_from_exact_transactions(
			original_boq,
			boq_item,
			current_ra_bill,
		)

	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(t.current_qty), 0) AS qty, COUNT(*) AS transaction_count
		FROM `tabRA Bill Transaction` t
		JOIN `tabRA Bill` rb ON rb.name = t.ra_bill
		LEFT JOIN `tabBOQ` b
		  ON b.name = COALESCE(NULLIF(t.boq_revision, ''), NULLIF(t.boq, ''))
		LEFT JOIN `tabBOQ Item` bi ON bi.name = t.boq_item
		WHERE rb.docstatus = 1
		  AND COALESCE(NULLIF(t.original_boq, ''), NULLIF(b.original_boq, ''), t.boq)
		      = %(original_boq)s
		  AND COALESCE(
				NULLIF(t.boq_item_key, ''),
				NULLIF(bi.boq_item_key, ''),
				NULLIF(bi.component_key, ''),
				t.boq_item
			  ) = %(boq_item_key)s
		  AND (%(current_ra_bill)s = '' OR t.ra_bill != %(current_ra_bill)s)
		""",
		{
			"original_boq": original_boq,
			"boq_item_key": boq_item_key,
			"current_ra_bill": current_ra_bill or "",
		},
		as_dict=True,
	)
	if not result:
		return 0, 0

	return flt(result[0].qty), result[0].transaction_count or 0


def _get_previous_billed_qty_from_exact_transactions(
	original_boq,
	boq_item,
	current_ra_bill=None,
):
	if not original_boq or not boq_item:
		return 0, 0

	chain_names = _get_boq_chain_names(original_boq)
	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(t.current_qty), 0) AS qty, COUNT(*) AS transaction_count
		FROM `tabRA Bill Transaction` t
		JOIN `tabRA Bill` rb ON rb.name = t.ra_bill
		WHERE rb.docstatus = 1
		  AND t.boq IN %(chain_names)s
		  AND t.boq_item = %(boq_item)s
		  AND (%(current_ra_bill)s = '' OR t.ra_bill != %(current_ra_bill)s)
		""",
		{
			"chain_names": tuple(chain_names or [original_boq]),
			"boq_item": boq_item,
			"current_ra_bill": current_ra_bill or "",
		},
		as_dict=True,
	)
	if not result:
		return 0, 0

	return flt(result[0].qty), result[0].transaction_count or 0


def _get_previous_billed_qty_from_submitted_ra_bills(
	original_boq,
	boq,
	boq_item_key,
	boq_item,
	current_ra_bill=None,
):
	if (
		original_boq
		and boq_item_key
		and _doctype_has_field("RA Bill Item", "original_boq")
		and _doctype_has_field("RA Bill Item", "boq_item_key")
	):
		return _get_previous_billed_qty_from_lineage_ra_bill_items(
			original_boq,
			boq_item_key,
			current_ra_bill,
		)

	result = frappe.db.sql(
		"""
		SELECT COALESCE(
			SUM(
				CASE
					WHEN COALESCE(rbi.current_qty, 0) > 0 THEN rbi.current_qty
					ELSE COALESCE(NULLIF(rbi.boq_qty, 0), bi.qty, 0)
						* COALESCE(rbi.work_percent, 0) / 100
				END
			),
			0
		) AS qty
		FROM `tabRA Bill Item` rbi
		JOIN `tabRA Bill` rb ON rb.name = rbi.parent
		LEFT JOIN `tabBOQ Item` bi ON bi.name = rbi.boq_item
		WHERE rb.boq = %(boq)s
		  AND rbi.boq_item = %(boq_item)s
		  AND rb.docstatus = 1
		  AND (%(current_ra_bill)s = '' OR rb.name != %(current_ra_bill)s)
		""",
		{
			"boq": boq,
			"boq_item": boq_item,
			"current_ra_bill": current_ra_bill or "",
		},
	)
	return flt(result[0][0]) if result else 0


def _get_previous_billed_qty_from_lineage_ra_bill_items(
	original_boq,
	boq_item_key,
	current_ra_bill=None,
):
	result = frappe.db.sql(
		"""
		SELECT COALESCE(
			SUM(
				CASE
					WHEN COALESCE(rbi.current_qty, 0) > 0 THEN rbi.current_qty
					ELSE COALESCE(NULLIF(rbi.boq_qty, 0), bi.qty, 0)
						* COALESCE(rbi.work_percent, 0) / 100
				END
			),
			0
		) AS qty
		FROM `tabRA Bill Item` rbi
		JOIN `tabRA Bill` rb ON rb.name = rbi.parent
		LEFT JOIN `tabBOQ` b
		  ON b.name = COALESCE(NULLIF(rbi.boq_revision, ''), rb.boq)
		LEFT JOIN `tabBOQ Item` bi ON bi.name = rbi.boq_item
		WHERE rb.docstatus = 1
		  AND COALESCE(NULLIF(rbi.original_boq, ''), NULLIF(b.original_boq, ''), rb.boq)
		      = %(original_boq)s
		  AND COALESCE(
				NULLIF(rbi.boq_item_key, ''),
				NULLIF(bi.boq_item_key, ''),
				NULLIF(bi.component_key, ''),
				rbi.boq_item
			  ) = %(boq_item_key)s
		  AND (%(current_ra_bill)s = '' OR rb.name != %(current_ra_bill)s)
		""",
		{
			"original_boq": original_boq,
			"boq_item_key": boq_item_key,
			"current_ra_bill": current_ra_bill or "",
		},
	)
	return flt(result[0][0]) if result else 0


def _get_boq_item_qty(boq, boq_item):
	if not boq_item:
		return 0

	context = _get_boq_item_context(boq, boq_item)
	return flt(context.qty)


def _qty_to_percent(qty, boq_qty):
	boq_qty = flt(boq_qty)
	return (flt(qty) / boq_qty * 100) if boq_qty else 0


def _get_row_boq_qty(row, boq=None):
	return flt(row.get("boq_qty")) or _get_boq_item_qty(boq, row.get("boq_item"))


def _get_row_current_qty(row):
	current_qty = flt(row.get("current_qty"))
	if current_qty:
		return current_qty

	return _get_row_boq_qty(row) * flt(row.get("work_percent")) / 100


def _get_row_current_amount(row):
	current_amount = flt(row.get("current_amount"))
	if current_amount:
		return current_amount

	return _get_row_current_qty(row) * flt(row.get("boq_rate"))


def _get_transaction_date(ra_bill):
	date_value = (
		ra_bill.get("billing_period_to")
		or ra_bill.get("billing_period_from")
		or ra_bill.get("creation")
	)
	return getdate(date_value) if date_value else today()


def _create_ra_bill_transaction(ra_bill, row, previous_qty=0):
	context = _get_boq_item_context(ra_bill.boq, row.boq_item)
	original_boq = _get_original_boq(ra_bill.boq)
	boq_item_key = row.get("boq_item_key") or context.boq_item_key
	boq_qty = _get_row_boq_qty(row, ra_bill.boq)
	current_qty = _get_row_current_qty(row)
	current_amount = _get_row_current_amount(row)
	cumulative_qty = flt(previous_qty) + current_qty
	cumulative_percent = _qty_to_percent(cumulative_qty, boq_qty)
	remaining_qty = boq_qty - cumulative_qty
	remaining_percent = 100 - cumulative_percent if boq_qty else 0

	transaction = frappe.get_doc(
		{
			"doctype": "RA Bill Transaction",
			"ra_bill": ra_bill.name,
			"project": ra_bill.project,
			"boq": ra_bill.boq,
			"original_boq": original_boq,
			"boq_revision": ra_bill.boq,
			"boq_item_key": boq_item_key,
			"boq_item": row.boq_item,
			"item_name": row.item_name,
			"category_name": row.category_name,
			"sub_category": row.sub_category,
			"boq_qty": boq_qty,
			"boq_rate": flt(row.boq_rate),
			"uom": row.uom,
			"progress_type": row.get("progress_type") or "Progress",
			"work_percent": flt(row.work_percent),
			"current_qty": current_qty,
			"current_amount": current_amount,
			"cumulative_qty_after_bill": cumulative_qty,
			"cumulative_percent_after_bill": cumulative_percent,
			"remaining_qty_after_bill": remaining_qty,
			"remaining_percent_after_bill": remaining_percent,
			"transaction_date": _get_transaction_date(ra_bill),
			"docstatus_source": ra_bill.docstatus or 1,
		}
	)
	transaction.insert(ignore_permissions=True)
	return transaction


def _get_boq_item_billing_summary(boq, boq_item, current_ra_bill=None):
	context = _get_boq_item_context(boq, boq_item)
	boq_qty = _get_boq_item_qty(boq, boq_item)
	previous_qty = _get_previous_billed_qty(boq, boq_item, current_ra_bill)
	previous_percent = _qty_to_percent(previous_qty, boq_qty) if boq_qty > 0 else 0
	remaining_qty = max(0, boq_qty - previous_qty)
	remaining_percent = max(0, 100 - previous_percent) if boq_qty > 0 else 0

	return {
		"boq_qty": boq_qty,
		"previous_qty": previous_qty,
		"previous_percent": previous_percent,
		"remaining_qty": remaining_qty,
		"remaining_percent": remaining_percent,
		"original_boq": _get_original_boq(context.boq or boq),
		"boq_revision": context.boq or boq,
		"boq_item_key": context.boq_item_key,
	}


def _coerce_list(value):
	if not value:
		return []

	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except Exception:
			value = [item.strip() for item in value.split(",")]

	if isinstance(value, (list, tuple, set)):
		return [item for item in value if item]

	return [value]


@frappe.whitelist()
def get_boq_item_billing_summary(boq, boq_item, current_ra_bill=None):
	_get_permission_checked_boq(boq)
	return _get_boq_item_billing_summary(boq, boq_item, current_ra_bill)


@frappe.whitelist()
def get_boq_item_previous_work(boq, boq_item, current_ra_bill=None):
	"""
	Return previous completed qty/percent and remaining qty/percent
	for selected BOQ Item in selected BOQ.
	"""
	_get_permission_checked_boq(boq)
	return _get_boq_item_billing_summary(boq, boq_item, current_ra_bill)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_ra_bill_categories(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	boq = filters.get("boq")

	if not boq:
		return []
	_get_permission_checked_boq(boq)

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"

	return frappe.db.sql(
		"""
		SELECT DISTINCT parent_cat.name, parent_cat.category_name
		FROM `tabBOQ Item` item
		JOIN `tabBOQ Category` sub_cat ON sub_cat.name = item.boq_category
		JOIN `tabBOQ Category` parent_cat
		  ON parent_cat.name = COALESCE(NULLIF(sub_cat.parent_node, ''), sub_cat.name)
		WHERE item.parent = %(boq)s
		  AND item.parenttype = 'BOQ'
		  AND item.parentfield = 'items'
		  AND COALESCE(item.is_deleted_in_revision, 0) = 0
		  AND (%(txt)s = ''
		    OR parent_cat.category_name LIKE %(like_txt)s
		    OR parent_cat.name LIKE %(like_txt)s)
		ORDER BY
		  CASE
		    WHEN parent_cat.category_name LIKE %(prefix_txt)s THEN 0
		    WHEN parent_cat.category_name LIKE %(like_txt)s THEN 1
		    WHEN parent_cat.name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		  END,
		  parent_cat.category_name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"boq": boq,
			"txt": txt,
			"like_txt": like_txt,
			"prefix_txt": prefix_txt,
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_ra_bill_subcategories(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	boq = filters.get("boq")
	category = filters.get("category")

	if not boq or not category:
		return []
	_get_permission_checked_boq(boq)

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"

	return frappe.db.sql(
		"""
		SELECT DISTINCT sub_cat.name, sub_cat.category_name
		FROM `tabBOQ Item` item
		JOIN `tabBOQ Category` sub_cat ON sub_cat.name = item.boq_category
		WHERE item.parent = %(boq)s
		  AND item.parenttype = 'BOQ'
		  AND item.parentfield = 'items'
		  AND COALESCE(item.is_deleted_in_revision, 0) = 0
		  AND sub_cat.parent_node = %(category)s
		  AND (%(txt)s = ''
		    OR sub_cat.category_name LIKE %(like_txt)s
		    OR sub_cat.name LIKE %(like_txt)s)
		ORDER BY
		  CASE
		    WHEN sub_cat.category_name LIKE %(prefix_txt)s THEN 0
		    WHEN sub_cat.category_name LIKE %(like_txt)s THEN 1
		    WHEN sub_cat.name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		  END,
		  sub_cat.category_name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"boq": boq,
			"category": category,
			"txt": txt,
			"like_txt": like_txt,
			"prefix_txt": prefix_txt,
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_boq_items_for_ra_bill(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	return _search_boq_items_for_ra_bill(
		txt,
		start,
		page_len,
		filters,
		include_adjustment_history=bool(cint(filters.get("include_completed_for_adjustment"))),
		include_adjustment_items=bool(cint(filters.get("include_adjustment_items"))),
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_boq_adjustment_items_for_ra_bill(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	return _search_boq_items_for_ra_bill(
		txt,
		start,
		page_len,
		filters,
		include_adjustment_history=True,
	)


def _search_boq_items_for_ra_bill(
	txt,
	start,
	page_len,
	filters,
	include_adjustment_history=False,
	include_adjustment_items=False,
):
	boq = filters.get("boq")
	category = filters.get("category")
	subcategory = filters.get("subcategory")
	exclude_items = set(_coerce_list(filters.get("exclude_items")))
	current_ra_bill = filters.get("current_ra_bill")

	if not boq:
		return []
	_get_permission_checked_boq(boq)

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"
	start = int(start or 0)
	page_len = int(page_len or 20)
	candidate_limit = (
		max(start + page_len + 50, page_len)
		if not include_adjustment_history and not include_adjustment_items
		else 0
	)
	limit_clause = "LIMIT %(candidate_limit)s" if candidate_limit else ""

	conditions = [
		"parent = %(boq)s",
		"parenttype = 'BOQ'",
		"parentfield = 'items'",
		"COALESCE(is_deleted_in_revision, 0) = 0",
		"(%(txt)s = '' OR item_name LIKE %(like_txt)s OR item LIKE %(like_txt)s OR name LIKE %(like_txt)s)",
	]
	params = {
		"boq": boq,
		"txt": txt,
		"like_txt": like_txt,
		"prefix_txt": prefix_txt,
	}
	if candidate_limit:
		params["candidate_limit"] = candidate_limit
	if subcategory:
		conditions.append("boq_category = %(subcategory)s")
		params["subcategory"] = subcategory
	elif category:
		conditions.append("boq_category = %(category)s")
		params["category"] = category
	else:
		conditions.append("(boq_category IS NULL OR boq_category = '')")

	if exclude_items:
		conditions.append("name NOT IN %(exclude_items)s")
		params["exclude_items"] = tuple(exclude_items)

	candidates = frappe.db.sql(
		f"""
		SELECT name, item_name, qty, unit_rate, uom
		FROM `tabBOQ Item`
		WHERE {" AND ".join(conditions)}
		ORDER BY
		  CASE
		    WHEN item_name LIKE %(prefix_txt)s THEN 0
		    WHEN item_name LIKE %(like_txt)s THEN 1
		    WHEN name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		END,
		  item_name ASC
		{limit_clause}
		""",
		params,
	)

	available_items = []
	for name, item_name, qty, unit_rate, uom in candidates:
		summary = _get_boq_item_billing_summary(boq, name, current_ra_bill)
		previous_qty = flt(summary.get("previous_qty"))
		if include_adjustment_history:
			if previous_qty <= OVERBILLING_TOLERANCE:
				continue
			previous_percent = flt(summary.get("previous_percent"))
			remaining_percent = flt(summary.get("remaining_percent"))
			available_items.append(
				(
					name,
					item_name,
					qty,
					unit_rate,
					uom,
					previous_percent,
					previous_qty,
					remaining_percent,
				)
			)
		elif include_adjustment_items:
			is_pending = previous_qty < flt(qty) - OVERBILLING_TOLERANCE
			is_previously_certified = previous_qty > OVERBILLING_TOLERANCE
			if not is_pending and not is_previously_certified:
				continue
			available_items.append((name, item_name, qty, unit_rate, uom))
		elif previous_qty >= flt(qty) - OVERBILLING_TOLERANCE:
			continue
		else:
			available_items.append((name, item_name, qty, unit_rate, uom))

	return available_items[start : start + page_len]
