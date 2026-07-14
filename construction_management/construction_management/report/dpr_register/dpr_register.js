frappe.query_reports["DPR Register"] = {
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
			fieldname: "from_date",
			label: __("DPR Date From"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("DPR Date To"),
			fieldtype: "Date",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nDraft\nSubmitted\nPublished\nCancelled",
		},
		{
			fieldname: "publish_to_portal",
			label: __("Show on Client Portal"),
			fieldtype: "Check",
		},
	],
};
