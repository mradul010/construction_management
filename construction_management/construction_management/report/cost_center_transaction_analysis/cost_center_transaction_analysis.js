frappe.query_reports["Cost Center Transaction Analysis"] = {
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
