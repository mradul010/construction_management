(() => {
	const method =
		"construction_management.construction_management.report.project_profitability.project_profitability.";
	const company_query = () => ({
		filters: { company: frappe.query_report.get_filter_value("company") },
	});
	async function fiscal_dates(fill_missing = false) {
		const report = frappe.query_report;
		const company = report.get_filter_value("company");
		const fiscal_year = report.get_filter_value("fiscal_year");
		if (!company) return;
		const { message } = await frappe.call({
			method: method + "fiscal_dates",
			args: { company, fiscal_year },
		});
		if (
			company !== report.get_filter_value("company") ||
			fiscal_year !== report.get_filter_value("fiscal_year")
		)
			return;
		if (fill_missing) {
			for (const key of Object.keys(message)) {
				if (report.get_filter_value(key)) delete message[key];
			}
		}
		await report.set_filter_value(message);
	}
	function fiscal_change(report) {
		if (!report._no_refresh) return fiscal_dates();
	}
	frappe.query_reports["Project Profitability"] = {
		onload(report) {
			if (!report.get_filter_value("from_date") || !report.get_filter_value("to_date"))
				return fiscal_dates(true);
		},
		filters: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				default: frappe.defaults.get_user_default("Company"),
				reqd: 1,
				on_change: fiscal_change,
			},
			{
				fieldname: "fiscal_year",
				label: __("Fiscal Year"),
				fieldtype: "Link",
				options: "Fiscal Year",
				on_change: fiscal_change,
			},
			{
				fieldname: "period_type",
				label: __("Period Type"),
				fieldtype: "Select",
				options: "Monthly\nQuarterly\nYearly",
				default: "Monthly",
				reqd: 1,
			},
			{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1 },
			{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1 },
			{
				fieldname: "project",
				label: __("Project"),
				fieldtype: "Link",
				options: "Project",
				get_query: company_query,
			},
			{
				fieldname: "cost_center",
				label: __("Cost Center"),
				fieldtype: "Link",
				options: "Cost Center",
				get_query: company_query,
			},
			{
				fieldname: "account",
				label: __("Account"),
				fieldtype: "Link",
				options: "Account",
				get_query: company_query,
			},
			{
				fieldname: "view_type",
				label: __("View Type"),
				fieldtype: "Select",
				options:
					"Summary\nDetailed Accounts\nCost Center Breakdown\nTimesheet Profitability",
				default: "Summary",
				reqd: 1,
			},
			{
				fieldname: "show_percentage_analysis",
				label: __("Show Percentage Analysis"),
				fieldtype: "Check",
				default: 1,
				depends_on: "eval:doc.view_type != 'Timesheet Profitability'",
			},
			{
				fieldname: "metric",
				label: __("Metric"),
				fieldtype: "Select",
				options: "Income\nExpenses\nGross Profit\nNet Profit",
				default: "Net Profit",
				reqd: 1,
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
				fieldname: "customer",
				label: __("Customer"),
				fieldtype: "Link",
				options: "Customer",
			},
			{
				fieldname: "employee",
				label: __("Employee"),
				fieldtype: "Link",
				options: "Employee",
				depends_on: "eval:doc.view_type == 'Timesheet Profitability'",
			},
		],
		formatter(value, row, column, data, default_formatter) {
			let formatted = default_formatter(value, row, column, data);
			if (frappe.query_report.get_filter_value("view_type") === "Timesheet Profitability")
				return formatted;
			if (column.fieldtype === "Percent" && value == null) return "";
			if (data?._project_summary || data?._grand_total) formatted = `<strong>${formatted}</strong>`;
			if (column.description)
				formatted = `<span title="${frappe.utils.escape_html(column.description)}">${formatted}</span>`;
			if (
				!data ||
				column.fieldtype !== "Currency" ||
				value == null ||
				!(data.project || data._grand_total)
			)
				return formatted;
			const loss =
				["net_profit", "gross_profit", "total"].includes(column.fieldname) ||
				column.fieldname.startsWith("period_");
			if (loss && value < 0) formatted = `<span class="text-danger">${formatted}</span>`;
			const context = {
				project: data.project,
				account: data.account,
				cost_center: data.cost_center,
				exact_center: data._exact_center,
				category: data._category,
				fieldname: column.fieldname,
			};
			if (data._periods?.[column.fieldname])
				Object.assign(context, data._periods[column.fieldname]);
			if (column.fieldname === "total" || column.fieldname.startsWith("period_"))
				context.metric = frappe.query_report.get_filter_value("metric");
			return `<a href="/app/query-report/General%20Ledger" class="project-profitability-ledger"
				data-context="${frappe.utils.escape_html(JSON.stringify(context))}">${formatted}</a>`;
		},
		get_datatable_options(options) {
			return { ...options, layout: "fixed" };
		},
		after_datatable_render(datatable) {
			const wrapper = datatable.wrapper;
			const types = ["mousedown", "click", "dblclick"];
			if (wrapper.profitability_handler)
				types.forEach((type) =>
					wrapper.removeEventListener(type, wrapper.profitability_handler, true)
				);
			wrapper.profitability_handler = async (event) => {
				const link = event.target.closest(".project-profitability-ledger");
				if (!link || !wrapper.contains(link)) return;
				event.preventDefault();
				event.stopImmediatePropagation();
				if (event.type !== "click") return;
				const { message } = await frappe.call({
					method: method + "drilldown",
					args: {
						filters: frappe.query_report.get_filter_values(),
						context: JSON.parse(link.dataset.context),
					},
				});
				if (!message.breakdown) {
					frappe.route_options = message.filters;
					frappe.set_route("query-report", "General Ledger");
					return;
				}
				const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
				const body = message.entries
					.map(
						(e) => `<tr><td>${escape(e.posting_date)}</td><td>${escape(e.project)}</td>
					<td>${escape(e.cost_center)}</td><td>${escape(e.account)}</td>
					<td>${frappe.utils.get_form_link(e.voucher_type, e.voucher_no, true)}</td>
					<td class="text-right">${frappe.format(
						e.debit,
						{ fieldtype: "Currency", options: "currency" },
						{},
						{ currency: message.currency }
					)}</td>
					<td class="text-right">${frappe.format(
						e.credit,
						{ fieldtype: "Currency", options: "currency" },
						{},
						{ currency: message.currency }
					)}</td></tr>`
					)
					.join("");
				const dialog = new frappe.ui.Dialog({
					title: __("Accounting Transactions"),
					size: "extra-large",
					fields: [{ fieldname: "transactions", fieldtype: "HTML" }],
				});
				dialog.fields_dict.transactions.$wrapper
					.html(`<div class="table-responsive"><table class="table table-bordered">
					<thead><tr>${["Posting Date", "Project", "Cost Center", "Account", "Voucher", "Debit", "Credit"]
						.map((label) => `<th>${escape(__(label))}</th>`)
						.join("")}</tr></thead>
					<tbody>${body}</tbody></table></div>`);
				dialog.show();
			};
			types.forEach((type) =>
				wrapper.addEventListener(type, wrapper.profitability_handler, true)
			);
		},
	};
})();
