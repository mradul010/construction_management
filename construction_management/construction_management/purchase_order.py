import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt, today

from construction_management.construction_management.accounting_dimensions import (
	get_ra_bill_project_cost_center,
)


TOLERANCE = 0.0001


@frappe.whitelist()
def make_purchase_order(source_name, target_doc=None):
	work_order = frappe.get_doc("SC Work Order", source_name)
	validate_sc_work_order_for_purchase_order(work_order)

	def set_missing_values(source, target):
		target.supplier = source.supplier
		target.company = source.company
		target.transaction_date = today()
		target.schedule_date = source.end_date or source.start_date or today()
		target.project = source.project
		target.currency = source.currency
		target.conversion_rate = source.conversion_rate or 1
		target.boq = source.boq
		target.sc_work_order = source.name
		target.status = "Draft"
		target.terms = source.terms
		target.remarks = source.remarks or _("Created from SC Work Order {0}").format(source.name)
		_set_if_exists(
			target,
			"cost_center",
			get_ra_bill_project_cost_center(project=source.project, company=source.company),
		)

	def update_item(source, target, source_parent):
		ordered_qty = get_ordered_qty(source_parent.name, source.name)
		remaining_qty = max(flt(source.assigned_qty) - ordered_qty, 0)
		if remaining_qty <= TOLERANCE:
			target.qty = 0
			return

		cost_center = get_ra_bill_project_cost_center(
			project=source_parent.project,
			company=source_parent.company,
		)
		target.item_code = source.item
		target.item_name = source.description
		target.description = source.description
		target.qty = remaining_qty
		target.uom = source.uom
		target.stock_uom = source.uom
		target.conversion_factor = 1
		target.rate = flt(source.sc_rate)
		target.amount = remaining_qty * flt(source.sc_rate)
		target.schedule_date = source_parent.end_date or source_parent.start_date or today()
		target.project = source.get("project") or source_parent.project
		_set_if_exists(target, "cost_center", source.get("cost_center") or cost_center)
		_set_if_exists(target, "boq_item", source.boq_item)
		_set_if_exists(target, "sc_work_order_item", source.name)

	doc = get_mapped_doc(
		"SC Work Order",
		source_name,
		{
			"SC Work Order": {
				"doctype": "Purchase Order",
				"validation": {"docstatus": ["=", 1]},
			},
			"SC Work Order Item": {
				"doctype": "Purchase Order Item",
				"postprocess": update_item,
			},
		},
		target_doc,
		set_missing_values,
	)
	doc.items = [row for row in doc.items if flt(row.qty) > TOLERANCE]
	if not doc.items:
		frappe.throw(_("All scope items in SC Work Order {0} are already fully ordered.").format(source_name))
	return doc


@frappe.whitelist()
def make_sc_bill(source_name, target_doc=None):
	purchase_order = frappe.get_doc("Purchase Order", source_name)
	validate_purchase_order_for_sc_bill(purchase_order)

	def set_missing_values(source, target):
		target.sc_work_order = source.sc_work_order
		target.purchase_order = source.name
		target.project = source.project
		target.supplier = source.supplier
		target.company = source.company
		target.currency = source.currency
		target.boq = source.boq
		target.billing_type = frappe.db.get_value("SC Work Order", source.sc_work_order, "billing_type") or "Measured"
		target.contract_value = get_purchase_order_contract_value(source.name)
		target.previous_billed = get_submitted_sc_bill_total(source.name)
		target.status = "Draft"

	def update_item(source, target, source_parent):
		previous = get_po_item_billing_summary(source_parent.name, source.name)
		contract_qty = flt(source.qty)
		previous_qty = flt(previous.get("previous_qty"))
		previous_amount = flt(previous.get("previous_amount"))
		target.purchase_order = source_parent.name
		target.purchase_order_item = source.name
		target.sc_work_order_item = source.get("sc_work_order_item")
		target.boq_item = source.get("boq_item")
		target.item_code = source.item_code
		target.description = source.description or source.item_name or source.item_code
		target.assigned_qty = contract_qty
		target.uom = source.uom
		target.sc_rate = flt(source.rate)
		target.previous_qty = previous_qty
		target.previous_amount = previous_amount
		_set_if_exists(target, "previous_percent", _qty_percent(previous_qty, contract_qty))
		target.cumulative_qty = previous_qty
		_set_if_exists(target, "cumulative_percent", _qty_percent(previous_qty, contract_qty))
		target.balance_qty = max(contract_qty - previous_qty, 0)
		_set_if_exists(target, "balance_percent", max(100 - _qty_percent(previous_qty, contract_qty), 0))
		target.cumulative_amount = previous_amount
		target.balance_amount = max((contract_qty * flt(source.rate)) - previous_amount, 0)
		_set_if_exists(target, "cost_center", source.get("cost_center"))

	doc = get_mapped_doc(
		"Purchase Order",
		source_name,
		{
			"Purchase Order": {
				"doctype": "SC Bill",
				"validation": {"docstatus": ["=", 1]},
			},
			"Purchase Order Item": {
				"doctype": "SC Bill Item",
				"postprocess": update_item,
			},
		},
		target_doc,
		set_missing_values,
	)
	doc.items = [row for row in doc.items if flt(row.balance_qty) > TOLERANCE]
	if not doc.items:
		frappe.throw(_("Purchase Order {0} is already fully billed.").format(source_name))
	return doc


def validate_sc_work_order_for_purchase_order(work_order):
	if work_order.docstatus != 1:
		frappe.throw(_("SC Work Order must be submitted before creating a Purchase Order."))
	if work_order.status in ("Cancelled", "Closed", "Completed"):
		frappe.throw(_("Cannot create a Purchase Order from SC Work Order with status {0}.").format(work_order.status))
	if not work_order.supplier:
		frappe.throw(_("Supplier is required to create a Purchase Order."))
	if not work_order.items:
		frappe.throw(_("Please add scope items before creating a Purchase Order."))
	if get_sc_work_order_ordering_summary(work_order.name).get("remaining_qty") <= TOLERANCE:
		frappe.throw(_("SC Work Order {0} is already fully ordered.").format(work_order.name))


def validate_purchase_order_for_sc_bill(purchase_order):
	if purchase_order.docstatus != 1:
		frappe.throw(_("Purchase Order must be submitted before creating an SC Bill."))
	if purchase_order.status == "Cancelled":
		frappe.throw(_("Cancelled Purchase Orders cannot be billed."))
	if not purchase_order.meta.has_field("sc_work_order") or not purchase_order.get("sc_work_order"):
		frappe.throw(_("Purchase Order {0} is not linked to an SC Work Order.").format(purchase_order.name))
	if get_purchase_order_billing_summary(purchase_order.name).get("remaining_qty") <= TOLERANCE:
		frappe.throw(_("Purchase Order {0} is already fully billed.").format(purchase_order.name))


def validate_purchase_order(doc, method=None):
	if not doc or not doc.meta.has_field("sc_work_order") or not doc.get("sc_work_order"):
		return

	work_order = frappe.db.get_value(
		"SC Work Order",
		doc.sc_work_order,
		["name", "docstatus", "supplier", "company", "project", "boq"],
		as_dict=True,
	)
	if not work_order:
		frappe.throw(_("SC Work Order {0} does not exist.").format(doc.sc_work_order))
	if work_order.docstatus != 1:
		frappe.throw(_("SC Work Order must be submitted before linking a Purchase Order."))

	for fieldname, label in (
		("supplier", _("Supplier")),
		("company", _("Company")),
		("project", _("Project")),
		("boq", _("BOQ")),
	):
		expected = work_order.get(fieldname)
		if expected and doc.get(fieldname) and doc.get(fieldname) != expected:
			frappe.throw(_("Purchase Order {0} must match SC Work Order {0}.").format(label))
		if expected and not doc.get(fieldname):
			doc.set(fieldname, expected)

	seen = set()
	for row in doc.items:
		scope_item = row.get("sc_work_order_item")
		if not scope_item:
			continue
		if scope_item in seen:
			frappe.throw(_("SC Work Order Scope Item {0} is duplicated in this Purchase Order.").format(scope_item))
		seen.add(scope_item)
		validate_purchase_order_item_qty(doc, row)


def validate_purchase_order_item_qty(doc, row):
	scope_item = frappe.db.get_value(
		"SC Work Order Item",
		row.get("sc_work_order_item"),
		["parent", "assigned_qty", "description"],
		as_dict=True,
	)
	if not scope_item:
		frappe.throw(_("SC Work Order Scope Item {0} does not exist.").format(row.get("sc_work_order_item")))
	if scope_item.parent != doc.sc_work_order:
		frappe.throw(_("Scope Item {0} does not belong to SC Work Order {1}.").format(row.get("sc_work_order_item"), doc.sc_work_order))

	ordered_qty = get_ordered_qty(doc.sc_work_order, row.get("sc_work_order_item"), doc.name)
	if ordered_qty + flt(row.qty) > flt(scope_item.assigned_qty) + TOLERANCE:
		frappe.throw(
			_("Purchase Order Qty for {0} cannot exceed remaining quantity {1}.").format(
				scope_item.description or row.get("item_code"),
				max(flt(scope_item.assigned_qty) - ordered_qty, 0),
			)
		)


def update_sc_work_order_from_purchase_order(doc, method=None):
	if not doc or not doc.meta.has_field("sc_work_order") or not doc.get("sc_work_order"):
		return
	from construction_management.construction_management.doctype.sc_work_order.sc_work_order import (
		update_sc_work_order_summary,
	)

	update_sc_work_order_summary(doc.sc_work_order)


def get_ordered_qty(sc_work_order, sc_work_order_item=None, exclude_purchase_order=None):
	conditions = [
		"po.sc_work_order = %(sc_work_order)s",
		"po.docstatus = 1",
		"poi.docstatus = 1",
	]
	values = {"sc_work_order": sc_work_order}
	if sc_work_order_item:
		conditions.append("poi.sc_work_order_item = %(sc_work_order_item)s")
		values["sc_work_order_item"] = sc_work_order_item
	if exclude_purchase_order:
		conditions.append("po.name != %(exclude_purchase_order)s")
		values["exclude_purchase_order"] = exclude_purchase_order

	return flt(
		(frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(poi.qty), 0)
			FROM `tabPurchase Order Item` poi
			INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
			WHERE {" AND ".join(conditions)}
			""",
			values,
		) or [[0]])[0][0]
	)


def get_sc_work_order_ordering_summary(sc_work_order):
	total_qty = flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(assigned_qty), 0)
			FROM `tabSC Work Order Item`
			WHERE parent = %s
			""",
			sc_work_order,
		)[0][0]
	)
	ordered_qty = get_ordered_qty(sc_work_order)
	return {
		"total_qty": total_qty,
		"ordered_qty": ordered_qty,
		"remaining_qty": max(total_qty - ordered_qty, 0),
	}


def get_purchase_order_contract_value(purchase_order):
	return flt(
		frappe.db.get_value("Purchase Order", purchase_order, "total")
		or frappe.db.get_value("Purchase Order", purchase_order, "net_total")
	)


def get_submitted_sc_bill_total(purchase_order, exclude_sc_bill=None):
	conditions = [
		"purchase_order = %(purchase_order)s",
		"docstatus = 1",
		"status != 'Cancelled'",
	]
	values = {"purchase_order": purchase_order}
	if exclude_sc_bill:
		conditions.append("name != %(exclude_sc_bill)s")
		values["exclude_sc_bill"] = exclude_sc_bill

	return flt(
		(frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(gross_amount), 0)
			FROM `tabSC Bill`
			WHERE {" AND ".join(conditions)}
			""",
			values,
		) or [[0]])[0][0]
	)


def get_po_item_billing_summary(purchase_order, purchase_order_item, exclude_sc_bill=None):
	conditions = [
		"bill.purchase_order = %(purchase_order)s",
		"bill.docstatus = 1",
		"bill.status != 'Cancelled'",
		"item.purchase_order_item = %(purchase_order_item)s",
	]
	values = {
		"purchase_order": purchase_order,
		"purchase_order_item": purchase_order_item,
	}
	if exclude_sc_bill:
		conditions.append("bill.name != %(exclude_sc_bill)s")
		values["exclude_sc_bill"] = exclude_sc_bill

	result = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(item.current_qty), 0) AS previous_qty,
			COALESCE(SUM(item.current_amount), 0) AS previous_amount
		FROM `tabSC Bill Item` item
		INNER JOIN `tabSC Bill` bill ON bill.name = item.parent
		WHERE {" AND ".join(conditions)}
		""",
		values,
		as_dict=True,
	)
	return result[0] if result else {"previous_qty": 0, "previous_amount": 0}


def get_purchase_order_billing_summary(purchase_order):
	total_qty = flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(qty), 0)
			FROM `tabPurchase Order Item`
			WHERE parent = %s
			""",
			purchase_order,
		)[0][0]
	)
	billed_qty = flt(
		(frappe.db.sql(
			"""
			SELECT COALESCE(SUM(item.current_qty), 0)
			FROM `tabSC Bill Item` item
			INNER JOIN `tabSC Bill` bill ON bill.name = item.parent
			WHERE bill.purchase_order = %s
			  AND bill.docstatus = 1
			  AND bill.status != 'Cancelled'
			""",
			purchase_order,
		) or [[0]])[0][0]
	)
	return {
		"total_qty": total_qty,
		"billed_qty": billed_qty,
		"remaining_qty": max(total_qty - billed_qty, 0),
	}


def _qty_percent(qty, total_qty):
	total_qty = flt(total_qty)
	return flt((flt(qty) / total_qty) * 100) if total_qty else 0


def _set_if_exists(doc, fieldname, value):
	if doc.meta.has_field(fieldname) and value not in (None, ""):
		doc.set(fieldname, value)
