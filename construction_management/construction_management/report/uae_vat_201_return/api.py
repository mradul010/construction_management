"""Supported Frappe API adapters, scoped strictly to the existing VAT201 report."""
import frappe

REPORT = "UAE VAT 201 Return"


@frappe.whitelist()
@frappe.read_only()
def run(report_name, filters=None, user=None, ignore_prepared_report=False, custom_columns=None,
		is_tree=False, parent_field=None, are_default_filters=True, js_filters=None):
	from frappe.desk import query_report
	arguments = dict(report_name=report_name, filters=filters, user=user, ignore_prepared_report=ignore_prepared_report,
		custom_columns=custom_columns, is_tree=is_tree, parent_field=parent_field, are_default_filters=are_default_filters, js_filters=js_filters)
	if report_name != REPORT:
		return query_report.run(**arguments)
	values = dict(frappe.parse_json(filters) or {})
	values.pop("prepared_report_name", None)
	arguments.update(filters=values, ignore_prepared_report=True)
	frappe.local.vat201_current_result = None
	data = query_report.run(**arguments)
	result = frappe.local.vat201_current_result
	if result is None:
		frappe.throw("The VAT201 report did not produce a live result. Check its Construction Management report binding.")
	from construction_management.construction_management.report.uae_vat_201_return.uae_vat_201_return import context_for
	data["vat201_context"] = context_for(result)
	return data


@frappe.whitelist()
def export_query():
	from frappe.desk import query_report
	parameters = frappe.local.form_dict
	if parameters.get("report_name") != REPORT:
		return query_report.export_query()
	from construction_management.construction_management.report.uae_vat_201_return.uae_vat_201_return import download
	format_name = parameters.get("file_format_type") or "Excel"
	if format_name not in ("Excel", "CSV"):
		frappe.throw("Unsupported VAT201 export format")
	# Standard Export now supplies the complete live preparation workbook, not
	# just the visible box grid. Other reports retain the native export behavior.
	return download(parameters.get("filters"), "csv" if format_name == "CSV" else "xlsx")
