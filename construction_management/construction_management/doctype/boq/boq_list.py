import frappe


def get_list_context(context=None):
	if context is None:
		context = frappe._dict()

	context.title = "BOQ"
	context.route = "boqs"
	context.template = "construction_management/templates/pages/boq_list.html"
	context.get_list = get_boq_list

	return context


def get_boq_list(doctype=None, txt=None, filters=None, limit_start=0, limit_page_length=20, order_by=None):
	return frappe.get_all(
		"BOQ",
		fields=["name", "project", "client", "grand_total", "status", "modified"],
		limit_start=limit_start,
		limit_page_length=limit_page_length,
		order_by="modified desc"
	)