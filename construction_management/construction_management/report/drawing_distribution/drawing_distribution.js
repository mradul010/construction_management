        frappe.query_reports[frappe.query_report.report_name] = {
        	filters: [
        		{fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project"},
        		{fieldname: "design_package", label: __("Design Package"), fieldtype: "Link", options: "Design Package"},
        		{fieldname: "discipline", label: __("Discipline"), fieldtype: "Link", options: "Design Discipline"},
        		{fieldname: "current_status", label: __("Current Status"), fieldtype: "Select", options: "
Draft
Internal Review
Consultant Review
Client Review
Approved
Issued For Construction
Superseded
Cancelled"},
        	],
        };
