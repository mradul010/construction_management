frappe.query_reports["RA Bill Sales Invoice Report"] = {
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
			fieldname: "sales_invoice",
			label: __("Sales Invoice"),
			fieldtype: "Link",
			options: "Sales Invoice",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "ra_bill_status",
			label: __("RA Bill Status"),
			fieldtype: "Select",
			options: "\nDraft\nSubmitted\nApproved\nInvoiced\nCancelled",
		},
		{
			fieldname: "invoice_status",
			label: __("Invoice Status"),
			fieldtype: "Select",
			options: "\nDraft\nReturn\nCredit Note Issued\nSubmitted\nPaid\nPartly Paid\nUnpaid\nOverdue\nCancelled",
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
