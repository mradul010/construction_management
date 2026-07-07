frappe.provide("construction_management.report");

construction_management.report.CONSTRUCTION_REPORTS = [
	"BOQ Report",
	"BOQ Item Report",
	"RA Bill Report",
	"RA Bill Item Report",
	"Work Progress Report",
	"Project Construction Report",
	"Retention Report",
	"BOQ Revision Report",
];

construction_management.report.apply_summary_styles = function () {
	if (!frappe.get_route) {
		return;
	}

	const route = frappe.get_route() || [];
	const report_name = Array.isArray(route) && route[0] === "query-report" ? route[1] : "";
	if (!construction_management.report.CONSTRUCTION_REPORTS.includes(report_name)) {
		document.body.classList.remove("construction-management-report");
		return;
	}

	document.body.classList.add("construction-management-report");
	const $summary = $(".report-summary");
	if (!$summary.length) {
		return;
	}

	$summary.find(".summary-item").each(function () {
		const $item = $(this);
		const label = ($item.find(".summary-label").text() || "").trim().toLowerCase();
		let colorClass = "";

		if (label.includes("boq")) {
			colorClass = "cm-summary-blue";
		} else if (
			label.includes("ra billed") ||
			label.includes("ra bill") ||
			label.includes("billed")
		) {
			colorClass = "cm-summary-green";
		} else if (label.includes("invoice") || label.includes("invoiced")) {
			colorClass = "cm-summary-orange";
		} else if (label.includes("retention held") || label.includes("held")) {
			colorClass = "cm-summary-red";
		} else if (label.includes("released")) {
			colorClass = "cm-summary-purple";
		} else if (label.includes("balance")) {
			colorClass = "cm-summary-indigo";
		} else if (label.includes("completion") || label.includes("complete")) {
			colorClass = "cm-summary-teal";
		}

		$item.removeClass(
			"cm-summary-blue cm-summary-green cm-summary-orange cm-summary-red cm-summary-purple cm-summary-indigo cm-summary-teal",
		);
		if (colorClass) {
			$item.addClass(colorClass);
		}
	});
};

$(document).ready(function () {
	construction_management.report.apply_summary_styles();
});

$(document).on("page-change frappe:page-update", function () {
	setTimeout(construction_management.report.apply_summary_styles, 150);
});

if (window.MutationObserver) {
	const reportSummaryObserver = new MutationObserver(function () {
		construction_management.report.apply_summary_styles();
	});

	reportSummaryObserver.observe(document.body || document.documentElement, {
		childList: true,
		subtree: true,
	});
}
