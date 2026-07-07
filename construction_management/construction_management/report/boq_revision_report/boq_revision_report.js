frappe.query_reports["BOQ Revision Report"] = {
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
			fieldname: "original_boq",
			label: __("Original BOQ"),
			fieldtype: "Link",
			options: "BOQ",
		},
		{
			fieldname: "boq",
			label: __("Revision BOQ"),
			fieldtype: "Link",
			options: "BOQ",
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
