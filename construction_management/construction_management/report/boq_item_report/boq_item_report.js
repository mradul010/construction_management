frappe.query_reports["BOQ Item Report"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "boq",
			label: __("BOQ"),
			fieldtype: "Link",
			options: "BOQ",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Link",
			options: "BOQ Category",
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "active_revision",
			label: __("Active Revision"),
			fieldtype: "Check",
		},
	],
};
