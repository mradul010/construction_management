frappe.query_reports["Cost Center Transaction Analysis"] = {
	formatter(value, row, column, data, default_formatter) {
		const formatted = default_formatter(value, row, column, data);
		if (column.fieldname !== "cost_spent" || !data?.cost_center || value == null) {
			return formatted;
		}
		return `<a href="/app/query-report/Cost%20Center%20Expense%20Details" class="cost-spent-ledger"
			data-cost-center="${frappe.utils.escape_html(data.cost_center)}"
			data-gl-entry="${frappe.utils.escape_html(data.gl_entry || "")}"
			title="${frappe.utils.escape_html(__("Open Cost Center Expense Details"))}">${formatted}</a>`;
	},

	after_datatable_render(datatable) {
		const wrapper = datatable.wrapper;
		if (wrapper.cost_spent_click_handler) {
			for (const type of ["click", "mousedown", "dblclick"]) {
				wrapper.removeEventListener(type, wrapper.cost_spent_click_handler, true);
			}
		}
		wrapper.cost_spent_click_handler = async (event) => {
			const link = event.target.closest(".cost-spent-ledger");
			if (!link || !wrapper.contains(link)) return;
			event.preventDefault();
			event.stopImmediatePropagation();
			if (event.type !== "click") return;
			const { message } = await frappe.call({
				method: "construction_management.construction_management.report.cost_center_transaction_analysis.cost_center_transaction_analysis.get_expense_detail_filters",
				args: {
					filters: frappe.query_report.get_filter_values(),
					cost_center: link.dataset.costCenter,
					gl_entry: link.dataset.glEntry || "",
				},
			});
			frappe.route_options = message.filters;
			frappe.set_route("query-report", "Cost Center Expense Details");
		};
		// Capture before DataTable handles mousedown as a cell selection.
		for (const type of ["click", "mousedown", "dblclick"]) {
			wrapper.addEventListener(type, wrapper.cost_spent_click_handler, true);
		}
	},

	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "view_mode",
			label: __("View"),
			fieldtype: "Select",
			options: "Cost Summary\nTransaction Details\nAccounting Summary",
			default: "Cost Summary",
			reqd: 1,
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: function () {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
					},
				};
			},
		},
		{
			fieldname: "include_child_cost_centers",
			label: __("Include Child Cost Centers"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: function () {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
					},
				};
			},
		},
		{
			fieldname: "account_type",
			label: __("Account Type"),
			fieldtype: "Select",
			options: [
				"",
				"Expense",
				"Income",
				"Asset",
				"Liability",
				"Equity",
				"Expense Account",
				"Income Account",
				"Fixed Asset",
				"Payable",
				"Receivable",
				"Bank",
				"Cash",
				"Stock",
				"Tax",
				"Cost of Goods Sold",
			],
			default: "Expense",
		},
		{
			fieldname: "voucher_type",
			label: __("Voucher Type"),
			fieldtype: "Link",
			options: "DocType",
		},
		{
			fieldname: "voucher_no",
			label: __("Voucher No"),
			fieldtype: "Data",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			get_query: function () {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
					},
				};
			},
		},
		{
			fieldname: "finance_book",
			label: __("Finance Book"),
			fieldtype: "Link",
			options: "Finance Book",
		},
		{
			fieldname: "include_default_book_entries",
			label: __("Include Default FB Entries"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_cancelled_entries",
			label: __("Show Cancelled Entries"),
			fieldtype: "Check",
			default: 0,
		},
	],
};

erpnext.utils.add_dimensions("Cost Center Transaction Analysis", 11);
