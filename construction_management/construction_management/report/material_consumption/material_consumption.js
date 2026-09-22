frappe.query_reports["Material Consumption"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				"January",
				"February",
				"March",
				"April",
				"May",
				"June",
				"July",
				"August",
				"September",
				"October",
				"November",
				"December",
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).toLocaleString("en", {
				month: "long",
			}),
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
			reqd: 1,
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, {
			inlineFilters: false,
			cellHeight: 30,
		});
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (data.row_type === "company" || data.row_type === "project" || data.row_type === "title") {
			return `<strong>${value || ""}</strong>`;
		}
		if (data.row_type === "group_header" || data.row_type === "column_header") {
			return `<strong>${value || ""}</strong>`;
		}
		return value;
	},
};
