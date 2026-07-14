import frappe
from frappe.utils import flt

from construction_management.portal_utils import (
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
	validate_boq_customer,
)
from construction_management.www.work_progress import get_work_progress


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	boq = frappe.form_dict.get("boq")
	validate_boq_customer(boq, customer)
	rows = [row for row in get_work_progress(customer) if row.boq == boq]
	completed_qty = sum(flt(row.completed_qty) for row in rows)
	boq_qty = sum(flt(row.boq_qty) for row in rows)
	remaining_qty = sum(flt(row.remaining_qty) for row in rows)
	progress_percent = (completed_qty / boq_qty * 100) if boq_qty else 0

	setup_portal_context(
		context,
		boq,
		description="Work progress by BOQ item.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "Work Progress", "route": "/work-progress"},
			{"name": boq, "route": f"/work-progress-detail?boq={boq}"},
		],
	)
	context.customer = customer
	context.boq = boq
	context.project = rows[0].project if rows else frappe.db.get_value("BOQ", boq, "project")
	context.rows = rows
	context.completed_qty = completed_qty
	context.boq_qty = boq_qty
	context.remaining_qty = remaining_qty
	context.progress_percent = progress_percent
