frappe.query_reports["Retention Payable Outstanding"] = {
	filters: [
		{fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company"},
		{fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project"},
		{fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier"},
		{fieldname: "sc_bill", label: __("SC Bill"), fieldtype: "Link", options: "SC Bill"},
		{fieldname: "purchase_invoice", label: __("Purchase Invoice"), fieldtype: "Link", options: "Purchase Invoice"},
		{fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nHeld\nPartially Released\nReleased\nCancelled"},
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date"},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date"},
	],
};
