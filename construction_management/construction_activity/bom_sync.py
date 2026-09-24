import frappe
from frappe import _
from frappe.utils import flt, nowdate

from construction_management.construction_activity.item_sync import ensure_item_for_mark
from construction_management.construction_management.doctype.construction_bom.construction_bom import get_weight_values


def sync_unloading_to_construction_bom(unloading_doc, create_if_missing=True):
	if not unloading_doc.project or not unloading_doc.building_number:
		return None

	aggregates = get_unloading_aggregates(unloading_doc.project, unloading_doc.building_number)
	bom = get_construction_bom(unloading_doc.project, unloading_doc.building_number)

	if not bom and not create_if_missing:
		return None

	if not bom:
		bom = frappe.new_doc("Construction BOM")
		bom.project = unloading_doc.project
		bom.building_number = unloading_doc.building_number
		bom.posting_date = nowdate()

	if bom.docstatus == 1:
		frappe.throw(
			_(
				"Construction BOM {0} is already submitted and cannot be updated from Unloading. "
				"Please cancel/amend the Construction BOM or keep it in Draft while activity sync is active."
			).format(frappe.bold(bom.name))
		)

	apply_unloading_aggregates(bom, aggregates)

	if not bom.get("items"):
		return bom

	bom.flags.ignore_permissions = True
	bom.save()
	return bom


def get_construction_bom(project, building_number):
	boms = frappe.get_all(
		"Construction BOM",
		filters={
			"project": project,
			"building_number": building_number,
			"docstatus": ["!=", 2],
		},
		fields=["name", "docstatus"],
		order_by="docstatus asc, modified desc",
		limit=1,
	)
	if not boms:
		return None
	return frappe.get_doc("Construction BOM", boms[0].name)


def get_unloading_aggregates(project, building_number):
	rows = frappe.db.sql(
		"""
		select
			item.mark_no,
			item.mark_item,
			item.item_code,
			item.mark_item_item_code,
			item.qty,
			item.unit_weight,
			parent.activity_date,
			parent.creation,
			item.idx
		from `tabUnloading` parent
		inner join `tabConstruction Activity Item` item on item.parent = parent.name
		where
			parent.docstatus in (0, 1)
			and parent.project = %(project)s
			and parent.building_number = %(building_number)s
		order by parent.activity_date, parent.creation, item.idx
		""",
		{"project": project, "building_number": building_number},
		as_dict=True,
	)

	aggregates = {}
	for row in rows:
		mark_no = (row.mark_no or "").strip()
		mark_item = (row.mark_item or "").strip()
		if not mark_no:
			continue

		item_code = get_stock_item(row)
		mark_item_item_code = get_mark_item_stock_item(row)
		key = (mark_no, mark_item)
		aggregate = aggregates.setdefault(
			key,
			{
				"mark_no": mark_no,
				"mark_item": mark_item,
				"item_code": item_code,
				"mark_item_item_code": mark_item_item_code,
				"qty": 0,
				"unit_weight": 0,
			},
		)
		aggregate["qty"] += flt(row.qty)
		if item_code:
			aggregate["item_code"] = item_code
		if mark_item_item_code:
			aggregate["mark_item_item_code"] = mark_item_item_code
		if flt(row.unit_weight):
			aggregate["unit_weight"] = flt(row.unit_weight)

	return aggregates


def get_stock_item(row):
	if row.item_code and frappe.db.exists("Item", row.item_code):
		return row.item_code

	item = ensure_item_for_mark(row.mark_no, unit_weight=row.unit_weight)
	return item.get("item") if item else None


def get_mark_item_stock_item(row):
	if row.mark_item_item_code and frappe.db.exists("Item", row.mark_item_item_code):
		return row.mark_item_item_code
	if not row.mark_item:
		return None

	item = ensure_item_for_mark(row.mark_item, unit_weight=row.unit_weight)
	return item.get("item") if item else None


def apply_unloading_aggregates(bom, aggregates):
	rows_by_key = {
		get_bom_row_key(row): row
		for row in bom.get("items") or []
		if row.mark_no
	}

	for key, aggregate in aggregates.items():
		row = rows_by_key.get(key)
		if not row:
			row = bom.append(
				"items",
				{
					"mark_no": aggregate["mark_no"],
					"mark_item": aggregate["mark_item"],
				},
			)
			rows_by_key[key] = row

		row.activity_sync = 1
		row.mark_no = aggregate["mark_no"]
		row.mark_item = aggregate["mark_item"]
		row.item_code = aggregate["item_code"]
		row.mark_item_item_code = aggregate["mark_item_item_code"]
		row.qty = flt(aggregate["qty"])
		row.unit_weight = flt(aggregate["unit_weight"])
		row.total_weight, row.total_wt_mt = get_weight_values(row.qty, row.unit_weight)

	for row in bom.get("items") or []:
		if row.get("activity_sync") and get_bom_row_key(row) not in aggregates:
			row.qty = 0
			row.total_weight = 0
			row.total_wt_mt = 0

	bom.run_method("update_item_values")


def get_bom_row_key(row):
	return ((row.mark_no or "").strip(), (row.mark_item or "").strip())
