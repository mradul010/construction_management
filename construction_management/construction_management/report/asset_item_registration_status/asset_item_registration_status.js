frappe.query_reports["Asset Item Registration Status"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
		{
			fieldname: "registration_status",
			label: __("Registration Status"),
			fieldtype: "Select",
			options: "All\nRegistered\nNot Registered",
			default: "All",
		},
	],
};
