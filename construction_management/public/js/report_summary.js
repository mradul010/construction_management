frappe.provide("construction_management.report");

construction_management.report.CONSTRUCTION_REPORTS = [
	"BOQ Report",
	"BOQ Item Report",
	"RA Bill Report",
	"RA Bill Item Report",
	"RA Bill Sales Invoice Report",
	"Work Progress Report",
	"Project Construction Report",
	"Project Advance Summary",
	"Retention Report",
	"BOQ Revision Report",
	"DPR Register",
];

construction_management.report.CURRENCY_SYMBOLS = {
	INR: [/₹\s*/g, /\bRs\.?\s+/gi],
	AED: [/د\.?إ\.?\s*/g, /\bDh\.?\s+/gi, /\bAED\s+AED\s+/g],
};

construction_management.report.get_row_currency = function (column, data) {
	const currency_field = column && column.options;
	return (
		(data && currency_field && data[currency_field]) ||
		(data && data.currency) ||
		(column && column.currency) ||
		""
	);
};

construction_management.report.normalize_currency_text = function (text, currency) {
	let normalized = String(text || "");
	const currency_code = String(currency || "").toUpperCase();
	const currency_symbols = construction_management.report.CURRENCY_SYMBOLS;

	Object.keys(currency_symbols).forEach(function (code) {
		if (currency_code && code !== currency_code) {
			return;
		}

		currency_symbols[code].forEach(function (pattern) {
			normalized = normalized.replace(pattern, code + " ");
		});
	});

	return normalized.replace(/\s{2,}/g, " ").trim();
};

construction_management.report.format_currency_with_code = function (value, column, data) {
	const currency = construction_management.report.get_row_currency(column, data);
	const formatted = frappe.format(value, column, { inline: true }, data);
	return construction_management.report.normalize_currency_text(formatted, currency);
};

construction_management.report.install_currency_formatter = function (report_name) {
	const report = frappe.query_reports && frappe.query_reports[report_name];
	if (!report || report.__construction_currency_formatter) {
		return;
	}

	const original_formatter = report.formatter;
	report.formatter = function (value, row, column, data, default_formatter) {
		const formatted = original_formatter
			? original_formatter(value, row, column, data, default_formatter)
			: default_formatter(value, row, column, data);

		if (column && column.fieldtype === "Currency") {
			return construction_management.report.normalize_currency_text(
				formatted,
				construction_management.report.get_row_currency(column, data),
			);
		}

		return formatted;
	};
	report.__construction_currency_formatter = true;
};

construction_management.report.get_current_report_name = function () {
	const route = frappe.get_route ? frappe.get_route() || [] : [];
	if (Array.isArray(route) && route[0] === "query-report" && route[1]) {
		return decodeURIComponent(route[1]);
	}

	return (frappe.query_report && frappe.query_report.report_name) || "";
};

construction_management.report.normalize_currency_labels = function () {
	const selectors = [
		".report-summary .summary-value",
		".dt-cell__content",
		".dt-cell__edit",
		".datatable .dt-row .dt-cell",
	];

	$(selectors.join(", ")).each(function () {
		const element = this;
		const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);

		while (walker.nextNode()) {
			const node = walker.currentNode;
			const normalized = construction_management.report.normalize_currency_text(node.nodeValue);
			if (node.nodeValue !== normalized) {
				node.nodeValue = normalized;
			}
		}

		const $element = $(element);
		const title = $element.attr("title");
		if (title) {
			const normalizedTitle = construction_management.report.normalize_currency_text(title);
			if (title !== normalizedTitle) {
				$element.attr("title", normalizedTitle);
			}
		}
	});
};

construction_management.report.apply_summary_styles = function () {
	const report_name = construction_management.report.get_current_report_name();
	if (!construction_management.report.CONSTRUCTION_REPORTS.includes(report_name)) {
		document.body.classList.remove("construction-management-report");
		$(".report-summary").removeClass("construction-management-report-summary");
		return;
	}

	document.body.classList.add("construction-management-report");
	construction_management.report.install_currency_formatter(report_name);
	construction_management.report.normalize_currency_labels();

	const $summary = $(".report-summary");
	if (!$summary.length) {
		return;
	}
	$summary.addClass("construction-management-report-summary");

	$summary.find(".summary-item").each(function () {
		const $item = $(this);
		const label = ($item.find(".summary-label").text() || "").trim().toLowerCase();
		let colorClass = "";

		if (label.includes("advance")) {
			colorClass = "cm-summary-teal";
		} else if (label.includes("boq")) {
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

	construction_management.report.normalize_currency_labels();
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
		characterData: true,
		subtree: true,
	});
}
