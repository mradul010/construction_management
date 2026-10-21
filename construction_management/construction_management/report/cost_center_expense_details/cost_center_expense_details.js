(() => {
	const parent = "Cost Center Transaction Analysis";
	const field = (fieldname, label, fieldtype, options, extra = {}) => ({ fieldname, label: __(label), fieldtype, options, ...extra });
	frappe.query_reports["Cost Center Expense Details"] = {
		get_datatable_options(options) {
			return { ...options, layout: "fixed", cellHeight: 64 };
		},
		after_datatable_render(datatable) {
			// Instance-scoped rules preserve DataTable's virtual row and scroll geometry.
			for (const column of datatable.datamanager.getColumns()) {
				if (!["project_name", "cost_center", "voucher_no", "remarks"].includes(column.id)) continue;
				datatable.style.setStyle(
					`.dt-row:not(.dt-row-header):not(.dt-row-filter) .dt-cell--col-${column.colIndex} .dt-cell__content`,
					{
						whiteSpace: "normal", overflowWrap: "anywhere", overflow: "auto",
						textOverflow: "clip", lineHeight: "20px", boxSizing: "border-box"
					}
				);
			}
			datatable.style.setStyle(".dt-row-totalRow .dt-cell__content", { fontWeight: "bold" });
		},
		formatter(value, row, column, data, default_formatter) {
			if (column.fieldname === "project_name" && data?.project) {
				return frappe.utils.get_form_link(
					"Project", data.project, true,
					frappe.utils.escape_html(value || data.project)
				);
			}
			return default_formatter(value, row, column, data);
		},
		onload(report) {
			report.page.add_inner_button(__("Back to Cost Center Report"), () => {
				const original = report.get_filter_value("parent_filters");
				if (original) {
					frappe.route_options = JSON.parse(original);
				} else {
					const { gl_entry, parent_filters, ...filters } = report.get_filter_values();
					frappe.route_options = { ...filters, view_mode: "Cost Summary" };
				}
				frappe.set_route("query-report", parent);
			});
		},
		filters: [
			field("company", "Company", "Link", "Company", { reqd: 1, default: frappe.defaults.get_user_default("Company") }),
			field("from_date", "From Date", "Date", null, { reqd: 1, default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) }),
			field("to_date", "To Date", "Date", null, { reqd: 1, default: frappe.datetime.get_today() }),
			field("cost_center", "Cost Center", "Link", "Cost Center", { get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }) }),
			field("project", "Project", "Link", "Project"),
			field("account", "Account", "Link", "Account", { get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }) }),
			field("account_type", "Account Type", "Select", "All\nExpense\nIncome\nAsset\nLiability\nEquity\nExpense Account\nIncome Account\nFixed Asset\nPayable\nReceivable\nBank\nCash\nStock\nTax\nCost of Goods Sold", { default: "Expense" }),
			field("include_child_cost_centers", "Include Child Cost Centers", "Check", null, { default: 1 }),
			field("finance_book", "Finance Book", "Link", "Finance Book"),
			field("include_default_book_entries", "Include Default FB Entries", "Check", null, { default: 1 }),
			field("voucher_type", "Voucher Type", "Link", "DocType"),
			field("voucher_no", "Voucher Number", "Data"),
			field("gl_entry", "GL Entry", "Link", "GL Entry", { hidden: 1 }),
			field("parent_filters", "Source Filters", "Data", null, { hidden: 1 }),
			field("show_cancelled_entries", "Source Cancelled Entries", "Check", null, { hidden: 1, default: 0 }),
		],
	};
	erpnext.utils.add_dimensions("Cost Center Expense Details", 8);
})();
