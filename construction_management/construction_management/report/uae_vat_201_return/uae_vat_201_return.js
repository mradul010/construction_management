(() => {
	const endpoint =
		"construction_management.construction_management.report.uae_vat_201_return.uae_vat_201_return.";
	const esc = (value) => frappe.utils.escape_html(String(value ?? ""));
	const money = (value, currency = "AED") =>
		value == null
			? __("Pending Verification")
			: frappe.format(value, { fieldtype: "Currency", options: currency });
	const voucher = (row) =>
		frappe.utils.get_form_link(row.voucher_type, row.voucher_no, true, esc(row.voucher_no));

	async function period(report, reset = false, requested_period = null) {
		if (report._no_refresh || !report.get_filter_value("company")) return;
		const filters = report.get_filter_values();
		if (requested_period) filters.filing_period = requested_period;
		const request = (report._vat_period_request = (report._vat_period_request || 0) + 1);
		if (reset) {
			delete filters.filing_period;
			delete filters.from_date;
			delete filters.to_date;
		}
		const { message } = await frappe.call({
			method: endpoint + "period_context",
			args: { filters },
		});
		if (
			request !== report._vat_period_request ||
			filters.company !== report.get_filter_value("company")
		)
			return;
		const previous = report._no_refresh;
		report._no_refresh = true;
		try {
			const field = report.get_filter("filing_period");
			field.df.options = ["", ...(message.available_periods || [])].join("\n");
			field.refresh();
			await field.set_value(
				`${message.from_date} to ${message.to_date}` === filters.filing_period ||
					reset ||
					(!filters.from_date && !filters.to_date)
					? `${message.from_date} to ${message.to_date}`
					: ""
			);
			await report.get_filter("from_date").set_value(message.from_date);
			await report.get_filter("to_date").set_value(message.to_date);
		} finally {
			report._no_refresh = previous;
		}
	}
	async function date_changed(report) {
		if (report._no_refresh) return;
		report._no_refresh = true;
		try {
			await report.get_filter("filing_period").set_value("");
		} finally {
			report._no_refresh = false;
		}
		report.refresh();
	}
	function table(rows, attention = false) {
		const headings = attention
			? ["Voucher Number", "Issue", "Recorded VAT", "Recommended Action"]
			: [
					"Date",
					"Voucher Number",
					"Party",
					"Taxable Amount",
					"VAT Amount",
					"VAT Treatment",
					"VAT Box",
					"Remarks",
			  ];
		const body = rows
			.map((row) => {
				const currency = row.currency || "AED";
				const vat = row.vat_amount ?? row.raw_vat;
				const values = attention
					? [
							voucher(row),
							esc(row.issue),
							money(vat, currency),
							esc(row.recommended_action),
					  ]
					: [
							esc(row.posting_date),
							voucher(row),
							esc(row.party),
							money(row.amount ?? row.base, currency),
							money(vat, currency),
							esc(row.treatment),
							esc(row.vat_box),
							esc(
								row.issue || row.remarks || row.reason || row.supporting_reference
							),
					  ];
				return `<tr>${values
					.map(
						(value, index) =>
							`<td style="${
								(attention ? index === 2 : index === 3 || index === 4)
									? "text-align:right;white-space:nowrap"
									: "min-width:140px;white-space:normal"
							}">${value}</td>`
					)
					.join("")}</tr>`;
			})
			.join("");
		return `<div class="table-responsive"><table class="table table-bordered"><thead><tr>${headings
			.map((h) => `<th>${esc(__(h))}</th>`)
			.join("")}</tr></thead><tbody>${
			body || `<tr><td colspan="${headings.length}">${__("No transactions")}</td></tr>`
		}</tbody></table></div>`;
	}
	async function details(report, wrapper) {
		const filters = report.get_filter_values();
		const snapshot = JSON.stringify(filters);
		const { message } = await frappe.call({
			method: endpoint + "report_context",
			args: { filters },
		});
		if (snapshot !== JSON.stringify(report.get_filter_values()) || !wrapper.isConnected)
			return;
		report._vat_details?.remove();
		const panel = document.createElement("section");
		panel.className = "vat201-transaction-details mt-4";
		const tabs = ["Sales", "Purchases", "Journal Entries", "Needs Attention"];
		panel.innerHTML = `<h4>${__(
			"Transaction Details"
		)}</h4><ul class="nav nav-tabs" role="tablist">${tabs
			.map(
				(tab, index) =>
					`<li class="nav-item"><button type="button" class="nav-link${
						index === 0 ? " active" : ""
					}" role="tab" aria-selected="${index === 0}" data-tab="${index}">${esc(
						__(tab)
					)}</button></li>`
			)
			.join("")}</ul><div class="vat201-tab-content mt-3"></div>`;
		const rows = message.details || [];
		const groups = [
			rows.filter((r) => ["Sales Invoice", "POS Invoice"].includes(r.voucher_type)),
			rows.filter((r) => r.voucher_type === "Purchase Invoice"),
			rows.filter(
				(r) =>
					!["Sales Invoice", "POS Invoice", "Purchase Invoice"].includes(r.voucher_type)
			),
			rows.filter((r) => r.issue),
		];
		const select = (index) => {
			panel.querySelectorAll("[data-tab]").forEach((button) => {
				const active = Number(button.dataset.tab) === index;
				button.classList.toggle("active", active);
				button.setAttribute("aria-selected", String(active));
			});
			panel.querySelector(".vat201-tab-content").innerHTML = table(
				groups[index],
				index === 3
			);
		};
		panel.addEventListener("click", (event) => {
			const button = event.target.closest("[data-tab]");
			if (button) select(Number(button.dataset.tab));
		});
		wrapper.insertAdjacentElement("afterend", panel);
		report._vat_details = panel;
		select(0);
	}

	frappe.query_reports["UAE VAT 201 Return"] = {
		async onload(report) {
			for (const [type, label] of [
				["xlsx", "Excel"],
				["csv", "CSV"],
				["pdf", "PDF"],
			]) {
				report.page.add_inner_button(
					__(label),
					() => {
						const params = new URLSearchParams({
							filters: JSON.stringify(report.get_filter_values()),
							file_type: type,
						});
						window.open(
							`/api/method/${endpoint}download?${params}`,
							"_blank",
							"noopener"
						);
					},
					__("Export")
				);
			}
			// Frappe suppresses automatic refresh while initially loading filters.
			const previous = report._no_refresh;
			report._no_refresh = false;
			try {
				await period(
					report,
					false,
					new URLSearchParams(window.location?.search || "").get("filing_period")
				);
			} finally {
				report._no_refresh = previous;
			}
		},
		filters: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				default: frappe.defaults.get_user_default("Company"),
				reqd: 1,
				on_change: async (report) => {
					if (report._no_refresh) return;
					await period(report, true);
					report.refresh();
				},
			},
			{
				fieldname: "filing_period",
				label: __("VAT Filing Period"),
				fieldtype: "Select",
				options: "",
				on_change: async (report) => {
					if (report._no_refresh) return;
					await period(report);
					report.refresh();
				},
			},
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				reqd: 1,
				on_change: date_changed,
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				reqd: 1,
				on_change: date_changed,
			},
		],
		formatter(value, row, column, data, default_formatter) {
			let formatted = default_formatter(value, row, column, data);
			if (
				data?._box &&
				data._incomplete &&
				column.fieldtype === "Currency" &&
				(value === 0 || ["12", "13", "14"].includes(data.box))
			)
				return `<span class="text-warning">${__("Pending Verification")}</span>`;
			if (value < 0 && column.fieldtype === "Currency")
				formatted = `<span class="text-danger">${formatted}</span>`;
			if (
				data?._box &&
				["amount", "vat_amount", "adjustment"].includes(column.fieldname) &&
				value != null
			)
				return `<a href="#" class="vat201-amount" data-box="${esc(
					data.box
				)}" data-field="${esc(column.fieldname)}">${formatted}</a>`;
			return formatted;
		},
		after_datatable_render(datatable) {
			const wrapper = datatable.wrapper;
			const report = frappe.query_report;
			if (wrapper.vat201_handler)
				for (const type of ["click", "mousedown", "dblclick"])
					wrapper.removeEventListener(type, wrapper.vat201_handler, true);
			wrapper.vat201_handler = async (event) => {
				const link = event.target.closest(".vat201-amount");
				if (!link || !wrapper.contains(link)) return;
				event.preventDefault();
				event.stopImmediatePropagation();
				if (event.type !== "click") return;
				const { message } = await frappe.call({
					method: endpoint + "transactions",
					args: {
						filters: report.get_filter_values(),
						box: link.dataset.box,
						fieldname: link.dataset.field,
					},
				});
				const dialog = new frappe.ui.Dialog({
					title: __("VAT Transactions") + " - " + link.dataset.box,
					size: "extra-large",
					fields: [{ fieldname: "transactions", fieldtype: "HTML" }],
				});
				dialog.fields_dict.transactions.$wrapper.html(table(message));
				dialog.show();
			};
			for (const type of ["click", "mousedown", "dblclick"])
				wrapper.addEventListener(type, wrapper.vat201_handler, true);
			report._vat_details?.remove();
			if (wrapper.isConnected)
				details(report, wrapper).catch(() => report._vat_details?.remove());
		},
	};
})();
