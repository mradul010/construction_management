frappe.query_reports["RA Bill Item Report"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "boq",
			label: __("BOQ"),
			fieldtype: "Link",
			options: "BOQ",
		},
		{
			fieldname: "ra_bill",
			label: __("RA Bill"),
			fieldtype: "Link",
			options: "RA Bill",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Link",
			options: "BOQ Category",
		},
		{
			fieldname: "boq_item",
			label: __("BOQ Item"),
			fieldtype: "Link",
			options: "BOQ Item",
		},
		{
			fieldname: "status",
			label: __("RA Bill Status"),
			fieldtype: "Select",
			options: "\nDraft\nSubmitted\nApproved\nInvoiced\nCancelled",
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
