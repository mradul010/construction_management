frappe.query_reports["Daily Progress Report Register"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
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
		{
			fieldname: "contractor",
			label: __("Contractor"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "work_location",
			label: __("Work Location / Building"),
			fieldtype: "Link",
			options: "Building",
			get_query() {
				const project = frappe.query_report.get_filter_value("project");
				const filters = {
					disabled: 0,
				};
				if (project) {
					filters.project = ["in", [project, ""]];
				}
				return { filters };
			},
		},
		{
			fieldname: "gang_name",
			label: __("Gang Name"),
			fieldtype: "Data",
		},
		{
			fieldname: "mark_no",
			label: __("Mark No"),
			fieldtype: "Data",
		},
	],
	onload() {
		const style_id = "daily-progress-report-register-print-style";
		if (document.getElementById(style_id)) {
			return;
		}

		const style = document.createElement("style");
		style.id = style_id;
		style.textContent = `
			@media print {
				@page { size: landscape; }
				[data-report-name="Daily Progress Report Register"] .dt-scrollable {
					font-size: 8px;
				}
			}
		`;
		document.head.appendChild(style);
	},
};
