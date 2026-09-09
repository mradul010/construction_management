frappe.query_reports["Material Status Report"] = {
	filters: frappe.query_reports["Project Material Balance"]
		? frappe.query_reports["Project Material Balance"].filters
		: [
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
					fieldname: "warehouse",
					label: __("Warehouse"),
					fieldtype: "Link",
					options: "Warehouse",
				},
				{
					fieldname: "item",
					label: __("Item"),
					fieldtype: "Link",
					options: "Item",
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
