frappe.query_reports["Construction Activity Tracking"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "building_number", label: __("Building Number"), fieldtype: "Link", options: "Building Number" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "mark_no", label: __("Mark No."), fieldtype: "Data" },
	],
};
