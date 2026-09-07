import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, today


COST_BREAKDOWN_TOLERANCE = 0.01
REVISION_MANAGER_ROLES = {
	"System Manager",
	"Construction Manager",
	"Project Manager",
	"Estimator",
}


class BOQ(Document):

	def _validate_links(self):
		self._sanitize_standard_duplicate_references()
		super()._validate_links()

	def validate(self):
		self._sanitize_standard_duplicate_references()
		self._set_revision_defaults()
		self._sync_and_validate_sales_order()
		self._validate_design_references()
		self._validate_revision_edit_allowed()
		self._ensure_component_keys()
		self._fill_parent_categories()
		self.validate_item_values()
		self._calculate_totals()
		self._calculate_revision_comparison()
		self.validate_cost_breakdown_matches_amount()

	def _sanitize_standard_duplicate_references(self):
		if not self.is_new() or self.flags.get("from_boq_revision"):
			return

		self.original_boq = None
		self.parent_boq = None
		self.superseded_by = None
		self.is_revision = 0
		self.is_active_revision = 0
		self.revision_no = 0
		self.revision_status = "Draft"
		self.status = "Draft"
		self.active_from_date = None
		self.active_to_date = None

	def _sync_and_validate_sales_order(self):
		"""Populate empty contract fields and keep the BOQ revision chain consistent."""
		chain_source = self.parent_boq or self.original_boq
		if chain_source and chain_source != self.name:
			chain_sales_order = frappe.db.get_value("BOQ", chain_source, "sales_order")
			if chain_sales_order and self.sales_order and self.sales_order != chain_sales_order:
				frappe.throw(
					_("BOQ revision Sales Order must match the Sales Order linked to BOQ {0}.").format(
						chain_source
					)
				)
			if chain_sales_order and not self.sales_order:
				self.sales_order = chain_sales_order

		if not self.sales_order:
			return

		sales_order = frappe.db.get_value(
			"Sales Order",
			self.sales_order,
			["name", "customer", "project", "company", "currency", "docstatus", "status"],
			as_dict=True,
		)
		if not sales_order:
			frappe.throw(_("Sales Order {0} does not exist.").format(self.sales_order))
		if sales_order.docstatus == 2 or sales_order.status == "Cancelled":
			frappe.throw(
				_("Sales Order {0} is cancelled and cannot be linked.").format(self.sales_order)
			)
		if sales_order.docstatus != 1:
			frappe.throw(_("Sales Order {0} must be submitted before it can be linked.").format(self.sales_order))
		if sales_order.status in ("Closed", "On Hold"):
			frappe.throw(
				_("Sales Order {0} has status {1} and cannot be linked.").format(
					self.sales_order, sales_order.status
				)
			)

		self._set_or_validate_contract_field("client", sales_order.customer, _("Customer"))
		self._set_or_validate_contract_field("project", sales_order.project, _("Project"))
		self._set_or_validate_contract_field("company", sales_order.company, _("Company"))
		self._set_or_validate_contract_field("currency", sales_order.currency, _("Currency"))

	def _set_or_validate_contract_field(self, fieldname, sales_order_value, label):
		if not sales_order_value:
			return
		boq_value = self.get(fieldname)
		if boq_value and boq_value != sales_order_value:
			frappe.throw(_("BOQ {0} must match Sales Order {0}.").format(label))
		if not boq_value:
			self.set(fieldname, sales_order_value)

	def _validate_design_references(self):
		from construction_management.design_management.design_management import (
			validate_design_references,
		)

		validate_design_references(self)

	def _set_revision_defaults(self):
		if self.revision_no is None:
			self.revision_no = 0

		if not self.status:
			self.status = "Draft"

		if not self.revision_status:
			self.revision_status = "Draft"

		if self.parent_boq:
			self.is_revision = 1

		if not self.original_boq:
			if self.parent_boq:
				parent_original = frappe.db.get_value("BOQ", self.parent_boq, "original_boq")
				self.original_boq = parent_original or self.parent_boq
			elif not self.is_new() and self.name:
				self.original_boq = self.name

	def _validate_revision_edit_allowed(self):
		if self.flags.ignore_revision_lock or self.is_new() or self.docstatus == 0:
			return

		original_boq = get_revision_chain_root(self)
		active_boq = get_active_revision_for_chain(original_boq)
		if not active_boq or active_boq == self.name:
			return

		active_revision_no = flt(
			frappe.db.get_value("BOQ", active_boq, "revision_no")
		)
		is_old_revision = (
			self.revision_status == "Superseded"
			or flt(self.revision_no) < active_revision_no
		)

		if is_old_revision:
			frappe.throw(
				_(
					"BOQ {0} has been superseded by active revision {1}. "
					"Please create a new revision instead of editing an old BOQ."
				).format(self.name, active_boq),
				title=_("Superseded BOQ"),
			)

	def _ensure_component_keys(self):
		ref_map = {}
		for row in self.items:
			old_ref = row.name
			if not row.get("component_key"):
				row.component_key = frappe.generate_hash(length=12)
			if not row.get("boq_item_key"):
				row.boq_item_key = row.component_key or frappe.generate_hash(length=12)
			ref_map[old_ref] = row.component_key

		for component in self.cost_components or []:
			if component.boq_item in ref_map:
				component.boq_item = ref_map[component.boq_item]

	def _fill_parent_categories(self):
		for row in self.items:
			if not row.boq_category:
				row.boq_parent_category = ""
				continue

			parent = frappe.db.get_value(
				"BOQ Category", row.boq_category, "parent_node"
			)
			if parent:
				row.boq_parent_category = frappe.db.get_value(
					"BOQ Category", parent, "category_name"
				) or parent
			else:
				row.boq_parent_category = frappe.db.get_value(
					"BOQ Category", row.boq_category, "category_name"
				) or row.boq_category

	def validate_item_values(self):
		if flt(self.global_margin_percent) < 0:
			frappe.throw(_("Global Margin % cannot be negative."))

		for row in self.items:
			item = row.item_name or row.item or row.name

			if not row.get("is_deleted_in_revision") and flt(row.qty) <= 0:
				frappe.throw(_("Qty for item {0} must be greater than 0.").format(item))

			if flt(row.margin_percent) < 0:
				frappe.throw(_("Margin % for item {0} cannot be negative.").format(item))

			if flt(row.unit_cost) < 0 or flt(row.unit_rate) < 0:
				frappe.throw(_("Unit Cost/Rate for item {0} cannot be negative.").format(item))

	def validate_cost_breakdown_matches_amount(self):
		all_components = self.cost_components or []

		for row in self.items:
			component_key = row.get("component_key") or row.name
			components = [
				component
				for component in all_components
				if component.boq_item in (component_key, row.name)
			]
			if not components:
				continue

			amount = self._get_item_amount(row)
			breakdown_total = sum(flt(component.amount) for component in components)
			difference = amount - breakdown_total

			if abs(difference) > COST_BREAKDOWN_TOLERANCE:
				item = row.item_name or row.item or row.name
				frappe.throw(
					_(
						"Cost Breakdown Mismatch for item {0}.<br>"
						"Amount: {1}<br>"
						"Cost Breakdown Total: {2}<br>"
						"Difference: {3}<br>"
						"Cost Breakdown must match Amount."
					).format(
						item,
						self._format_currency(amount),
						self._format_currency(breakdown_total),
						self._format_currency(abs(difference)),
					),
					title=_("Cost Breakdown Mismatch"),
				)

	def _get_item_amount(self, row):
		if row.get("amount") not in (None, ""):
			return flt(row.amount)

		qty = 0 if row.get("is_deleted_in_revision") else flt(row.qty)
		return qty * flt(row.unit_cost)

	def _format_currency(self, value):
		return fmt_money(
			flt(value),
			currency=self.currency or frappe.defaults.get_global_default("currency"),
		)

	def _calculate_totals(self):
		grand_total = 0
		total_cost = 0

		for row in self.items:
			unit_cost = flt(row.unit_cost)
			margin_percent = flt(row.margin_percent)
			qty = 0 if row.get("is_deleted_in_revision") else flt(row.qty)

			row.unit_rate = unit_cost * (1 + margin_percent / 100)
			row.amount = qty * unit_cost
			row.amount_after_margin = qty * flt(row.unit_rate)

			total_cost += row.amount
			grand_total += row.amount_after_margin

		self.total_cost = total_cost
		self.grand_total = grand_total
		self.total_margin = grand_total - total_cost
		self.margin_percent = (
			(grand_total - total_cost) / grand_total * 100
		) if grand_total else 0
		self.rate_per_bua = (
			grand_total / float(self.built_up_area)
		) if self.built_up_area else 0

	def _calculate_revision_comparison(self):
		previous_items = {}
		previous_boq = self.parent_boq

		if previous_boq:
			for row in frappe.get_all(
				"BOQ Item",
				filters={
					"parent": previous_boq,
					"parenttype": "BOQ",
					"parentfield": "items",
				},
				fields=[
					"name",
					"item",
					"boq_category",
					"qty",
					"unit_cost",
					"unit_rate",
					"amount_after_margin",
					"boq_item_key",
					"component_key",
				],
			):
				previous_items[row.name] = row

		for row in self.items:
			if not row.get("boq_item_key"):
				row.boq_item_key = row.get("component_key") or frappe.generate_hash(length=12)

			previous = previous_items.get(row.previous_boq_item)
			if not previous:
				row.previous_qty = 0
				row.previous_unit_cost = 0
				row.previous_unit_rate = 0
				row.qty_difference = 0 if row.get("is_deleted_in_revision") else flt(row.qty)
				row.rate_difference = flt(row.unit_rate)
				row.amount_difference = flt(row.amount_after_margin)
				row.revision_item_status = (
					"Deleted" if row.get("is_deleted_in_revision") else "Added"
				) if self.parent_boq else "Unchanged"
				continue

			if not row.get("boq_item_key"):
				row.boq_item_key = (
					previous.boq_item_key
					or previous.component_key
					or frappe.generate_hash(length=12)
				)

			current_qty = 0 if row.get("is_deleted_in_revision") else flt(row.qty)
			current_amount = 0 if row.get("is_deleted_in_revision") else flt(row.amount_after_margin)

			row.previous_qty = flt(previous.qty)
			row.previous_unit_cost = flt(previous.unit_cost)
			row.previous_unit_rate = flt(previous.unit_rate)
			row.qty_difference = current_qty - flt(previous.qty)
			row.rate_difference = flt(row.unit_rate) - flt(previous.unit_rate)
			row.amount_difference = current_amount - flt(previous.amount_after_margin)

			if row.get("is_deleted_in_revision"):
				row.revision_item_status = "Deleted"
				continue

			changed = (
				row.item != previous.item
				or row.boq_category != previous.boq_category
				or abs(row.qty_difference) > 0.0001
				or abs(row.rate_difference) > COST_BREAKDOWN_TOLERANCE
				or abs(flt(row.unit_cost) - flt(previous.unit_cost)) > COST_BREAKDOWN_TOLERANCE
				or abs(row.amount_difference) > COST_BREAKDOWN_TOLERANCE
			)
			row.revision_item_status = "Modified" if changed else "Unchanged"

	def on_submit(self):
		self.db_set("status", "Submitted")
		if self.revision_status == "Draft":
			self.db_set("revision_status", "Submitted")

	def on_cancel(self):
		unlink_non_revision_duplicate_boqs(self.name)
		was_active_revision = self.is_active_revision
		self.db_set("status", "Cancelled")
		self.db_set("revision_status", "Cancelled")
		self.db_set("is_active_revision", 0)
		if was_active_revision:
			self.db_set("active_to_date", today())

	def on_trash(self):
		if frappe.db.exists("RA Bill", {"boq": self.name}):
			frappe.throw(
				_("Cannot delete BOQ {0} because RA Bills exist against it.").format(
					self.name
				),
				title=_("Linked RA Bills Found"),
			)
		unlink_non_revision_duplicate_boqs(self.name)

	def on_amend(self):
		self.revision_no = (self.revision_no or 1) + 1
		self.status = "Draft"
		self.append("revisions", {
			"revision_no": self.revision_no,
			"revision_date": frappe.utils.today(),
			"revised_by": frappe.session.user,
			"remarks": "Amended from " + (self.amended_from or "")
		})


def user_can_manage_revisions():
	return bool(set(frappe.get_roles()) & REVISION_MANAGER_ROLES)


def require_revision_manager():
	if not user_can_manage_revisions():
		frappe.throw(
			_("Only System Manager, Construction Manager, Project Manager, or Estimator can manage BOQ revisions."),
			frappe.PermissionError,
		)


def get_revision_chain_root(boq):
	if isinstance(boq, str):
		values = frappe.db.get_value("BOQ", boq, ["name", "original_boq"], as_dict=True)
		if not values:
			return boq
		return values.original_boq or values.name

	return boq.get("original_boq") or boq.get("name")


def get_revision_chain_names(original_boq):
	if not original_boq:
		return []

	names = {original_boq}
	names.update(
		frappe.get_all(
			"BOQ",
			filters={"original_boq": original_boq},
			pluck="name",
		)
	)
	return list(names)


def get_active_revision_for_chain(original_boq):
	names = get_revision_chain_names(original_boq)
	if not names:
		return None

	active = frappe.get_all(
		"BOQ",
		filters={
			"name": ["in", names],
			"is_active_revision": 1,
			"docstatus": ["!=", 2],
		},
		fields=["name"],
		order_by="revision_no desc, modified desc",
		limit=1,
	)
	return active[0].name if active else None


def get_next_revision_no(original_boq):
	revisions = frappe.get_all(
		"BOQ",
		filters={"name": ["in", get_revision_chain_names(original_boq)]},
		fields=["revision_no"],
	)
	current_max = max([flt(row.revision_no) for row in revisions] or [0])
	return int(current_max) + 1


def get_active_boq_for_project(project):
	if not project:
		return None

	if frappe.get_meta("Project").has_field("current_boq"):
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


def set_project_current_boq(project, boq):
	if not project or not boq:
		return

	from construction_management.construction_management.setup import (
		ensure_project_current_boq_field,
	)

	ensure_project_current_boq_field()
	if frappe.get_meta("Project").has_field("current_boq"):
		frappe.db.set_value(
			"Project",
			project,
			"current_boq",
			boq,
		update_modified=False,
	)


def unlink_non_revision_duplicate_boqs(source_boq):
	if not source_boq:
		return

	duplicates = frappe.db.sql(
		"""
		SELECT name
		FROM `tabBOQ`
		WHERE original_boq = %(source_boq)s
		  AND name != %(source_boq)s
		  AND COALESCE(is_revision, 0) = 0
		  AND (parent_boq IS NULL OR parent_boq = '')
		""",
		{"source_boq": source_boq},
		pluck=True,
	)
	for duplicate in duplicates:
		frappe.db.set_value(
			"BOQ",
			duplicate,
			{
				"original_boq": duplicate,
				"parent_boq": None,
				"superseded_by": None,
				"is_revision": 0,
				"is_active_revision": 0,
			},
			update_modified=False,
		)

	if duplicates:
		frappe.clear_cache(doctype="BOQ")


def _get_source_reference_map(source_doc, revision_doc):
	ref_map = {}
	for source_row, revision_row in zip(source_doc.items or [], revision_doc.items or []):
		if not source_row.component_key:
			source_row.component_key = frappe.generate_hash(length=12)
		if not source_row.boq_item_key:
			source_row.boq_item_key = source_row.component_key

		revision_row.component_key = source_row.component_key
		revision_row.boq_item_key = source_row.boq_item_key
		revision_row.previous_boq_item = source_row.name
		revision_row.previous_qty = flt(source_row.qty)
		revision_row.previous_unit_cost = flt(source_row.unit_cost)
		revision_row.previous_unit_rate = flt(source_row.unit_rate)
		revision_row.qty_difference = 0
		revision_row.rate_difference = 0
		revision_row.amount_difference = 0
		revision_row.revision_item_status = "Unchanged"
		revision_row.is_deleted_in_revision = 0

		ref_map[source_row.name] = revision_row.component_key
		ref_map[source_row.component_key] = revision_row.component_key
		ref_map[source_row.boq_item_key] = revision_row.component_key

	return ref_map


@frappe.whitelist()
def create_revision(boq, revision_reason):
	require_revision_manager()
	if not revision_reason:
		frappe.throw(_("Revision Reason is required."))

	source_doc = frappe.get_doc("BOQ", boq)
	if source_doc.docstatus == 2:
		frappe.throw(_("Cannot create a revision from a cancelled BOQ."))
	if source_doc.docstatus == 0:
		frappe.throw(_("Submit or approve the BOQ before creating a revision."))

	allowed_source_statuses = {"Submitted", "Approved", "Active"}
	if (
		not source_doc.is_active_revision
		and source_doc.status not in allowed_source_statuses
		and source_doc.revision_status not in allowed_source_statuses
	):
		frappe.throw(_("Create Revision is allowed only from submitted, approved, or active BOQs."))

	revision_doc = frappe.copy_doc(source_doc)
	original_boq = source_doc.original_boq or source_doc.name

	revision_doc.docstatus = 0
	revision_doc.amended_from = None
	revision_doc.status = "Draft"
	revision_doc.is_revision = 1
	revision_doc.original_boq = original_boq
	revision_doc.parent_boq = source_doc.name
	revision_doc.revision_no = get_next_revision_no(original_boq)
	revision_doc.revision_reason = revision_reason
	revision_doc.revision_date = today()
	revision_doc.is_active_revision = 0
	revision_doc.revision_status = "Draft"
	revision_doc.superseded_by = None
	revision_doc.active_from_date = None
	revision_doc.active_to_date = None

	ref_map = _get_source_reference_map(source_doc, revision_doc)
	for component in revision_doc.cost_components or []:
		if component.boq_item in ref_map:
			component.boq_item = ref_map[component.boq_item]

	revision_doc.append(
		"revisions",
		{
			"revision_no": revision_doc.revision_no,
			"revision_date": revision_doc.revision_date,
			"revised_by": frappe.session.user,
			"remarks": revision_reason,
		},
	)
	revision_doc.flags.from_boq_revision = True
	revision_doc.insert(ignore_permissions=True)
	return revision_doc.name


@frappe.whitelist()
def activate_revision(boq):
	require_revision_manager()
	doc = frappe.get_doc("BOQ", boq)
	if doc.docstatus == 2:
		frappe.throw(_("Cannot activate a cancelled BOQ."))
	if doc.docstatus == 0:
		frappe.throw(_("Submit the BOQ revision before activation."))
	if doc.revision_status != "Approved" and doc.status != "Approved":
		frappe.throw(_("Only an approved BOQ revision can be activated."))

	original_boq = doc.original_boq or doc.name
	chain_names = get_revision_chain_names(original_boq)
	if not chain_names:
		chain_names = [doc.name]

	current_date = today()
	for other in chain_names:
		if other == doc.name:
			continue

		frappe.db.set_value(
			"BOQ",
			other,
			{
				"is_active_revision": 0,
				"revision_status": "Superseded",
				"status": "Superseded",
				"active_to_date": current_date,
				"superseded_by": doc.name,
			},
			update_modified=False,
		)

	frappe.db.set_value(
		"BOQ",
		doc.name,
		{
			"original_boq": original_boq,
			"is_active_revision": 1,
			"revision_status": "Active",
			"status": "Active",
			"active_from_date": current_date,
			"active_to_date": None,
			"superseded_by": None,
		},
		update_modified=False,
	)
	set_project_current_boq(doc.project, doc.name)
	frappe.clear_cache(doctype="BOQ")
	return doc.name


@frappe.whitelist()
def get_revision_history(boq):
	doc = frappe.get_doc("BOQ", boq)
	original_boq = doc.original_boq or doc.name
	return frappe.get_all(
		"BOQ",
		filters={"name": ["in", get_revision_chain_names(original_boq)]},
		fields=[
			"name",
			"revision_no",
			"parent_boq",
			"revision_date",
			"revision_reason",
			"revision_status",
			"is_active_revision",
			"active_from_date",
			"active_to_date",
			"superseded_by",
			"status",
			"docstatus",
		],
		order_by="revision_no asc, creation asc",
	)


@frappe.whitelist()
def get_revision_comparison(boq):
	doc = frappe.get_doc("BOQ", boq)
	if not doc.parent_boq:
		return []

	previous_doc = frappe.get_doc("BOQ", doc.parent_boq)
	rows = []
	seen_previous_items = set()
	seen_keys = set()

	for row in doc.items or []:
		status = row.revision_item_status or ("Deleted" if row.is_deleted_in_revision else "Added")
		previous_amount = 0
		if row.previous_boq_item:
			seen_previous_items.add(row.previous_boq_item)
			previous_amount = frappe.db.get_value(
				"BOQ Item",
				row.previous_boq_item,
				"amount_after_margin",
			) or 0
		if row.boq_item_key:
			seen_keys.add(row.boq_item_key)

		rows.append(
			{
				"item": row.item,
				"item_name": row.item_name,
				"boq_item": row.name,
				"previous_boq_item": row.previous_boq_item,
				"boq_item_key": row.boq_item_key,
				"previous_qty": flt(row.previous_qty),
				"current_qty": 0 if row.is_deleted_in_revision else flt(row.qty),
				"qty_difference": flt(row.qty_difference),
				"previous_rate": flt(row.previous_unit_rate),
				"current_rate": flt(row.unit_rate),
				"rate_difference": flt(row.rate_difference),
				"previous_amount": flt(previous_amount),
				"current_amount": 0 if row.is_deleted_in_revision else flt(row.amount_after_margin),
				"amount_difference": flt(row.amount_difference),
				"status": status,
			}
		)

	for previous in previous_doc.items or []:
		previous_key = previous.boq_item_key or previous.component_key or previous.name
		if previous.name in seen_previous_items or previous_key in seen_keys:
			continue

		rows.append(
			{
				"item": previous.item,
				"item_name": previous.item_name,
				"boq_item": None,
				"previous_boq_item": previous.name,
				"boq_item_key": previous_key,
				"previous_qty": flt(previous.qty),
				"current_qty": 0,
				"qty_difference": -flt(previous.qty),
				"previous_rate": flt(previous.unit_rate),
				"current_rate": 0,
				"rate_difference": -flt(previous.unit_rate),
				"previous_amount": flt(previous.amount_after_margin),
				"current_amount": 0,
				"amount_difference": -flt(previous.amount_after_margin),
				"status": "Deleted",
			}
		)

	return rows
