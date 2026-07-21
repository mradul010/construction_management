frappe.query_reports["DPR Register"] = {
	onload: function () {
		apply_dpr_register_summary_cards();
	},
	refresh: function () {
		apply_dpr_register_summary_cards();
	},
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

function apply_dpr_register_summary_cards() {
	ensure_dpr_register_summary_card_styles();

	[100, 500, 1000].forEach(function (delay) {
		setTimeout(tag_dpr_register_summary, delay);
	});
}

function tag_dpr_register_summary() {
	const $summary = $(".report-summary");
	if (!$summary.length) {
		return;
	}

	$summary.addClass("cm-dpr-register-summary");
}

function ensure_dpr_register_summary_card_styles() {
	if (document.getElementById("cm-dpr-register-summary-style")) {
		return;
	}

	const style = document.createElement("style");
	style.id = "cm-dpr-register-summary-style";
	style.textContent = `
		.report-summary.cm-dpr-register-summary {
			display: grid !important;
			grid-template-columns: repeat(3, minmax(0, 240px));
			gap: 32px;
			margin: 16px 0 24px;
			padding: 0;
			border: none;
			align-items: stretch;
			justify-content:space-around;
		}
		.report-summary.cm-dpr-register-summary .summary-item {
			display: flex;
			flex-direction: column;
			justify-content: space-between;
			width: 100%;
			max-width: none;
			min-height: 120px;
			height: auto;
			margin: 0;
			padding: 20px;
			border-radius: 8px;
			background: #ffffff;
			border: 1px solid #e5e7eb;
			border-left: 4px solid #d1d5db;
			box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
			overflow: visible;
		}
		.report-summary.cm-dpr-register-summary .summary-label,
		.report-summary.cm-dpr-register-summary .summary-value {
			overflow: visible !important;
			text-overflow: clip !important;
			white-space: normal !important;
			overflow-wrap: anywhere;
		}
		@media (max-width: 991px) {
			.report-summary.cm-dpr-register-summary {
				grid-template-columns: repeat(2, minmax(0, 1fr));
			}
		}
		@media (max-width: 575px) {
			.report-summary.cm-dpr-register-summary {
				grid-template-columns: 1fr;
			}
		}
	`;
	document.head.appendChild(style);
}
