frappe.query_reports["Site Material Consumption Register"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "transaction_type",
			label: __("Transaction Type"),
			fieldtype: "Select",
			options: "\nMaterial Issue\nMaterial Return",
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: function () {
				return { filters: { is_stock_item: 1, disabled: 0 } };
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};
