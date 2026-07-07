frappe.query_reports["BOQ Report"] = {
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
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nDraft\nSubmitted\nApproved\nActive\nSuperseded\nRevised\nCancelled",
		},
		{
			fieldname: "revision_status",
			label: __("Revision Status"),
			fieldtype: "Select",
			options: "\nDraft\nSubmitted\nApproved\nActive\nSuperseded\nCancelled",
		},
		{
			fieldname: "active_revision",
			label: __("Active Revision"),
			fieldtype: "Check",
		},
	],
};
