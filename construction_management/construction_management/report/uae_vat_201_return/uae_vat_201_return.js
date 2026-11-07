(() => {
	const endpoint =
		"construction_management.construction_management.report.uae_vat_201_return.uae_vat_201_return.";
	const esc = (value) => frappe.utils.escape_html(String(value ?? ""));
	const money = (value, currency = "AED") =>
		value == null
			? __("Not specified")
			: frappe.format(value, { fieldtype: "Currency", options: currency, precision: 2 });
	const voucher = (row) =>
		frappe.utils.get_form_link(row.voucher_type, row.voucher_no, true, esc(row.voucher_no));

	function paginate_tables(root) {
		for (const container of root?.querySelectorAll?.(".vat201-paged-table") || []) {
			if (container.dataset.paginationReady) continue;
			container.dataset.paginationReady = "1";
			const rows = Array.from(container.querySelectorAll("tbody > tr"));
			const normalize = value => value.toLocaleLowerCase().replaceAll(",", "").replace(/\s+/g, " ").trim();
			const texts = rows.map(row => normalize(row.textContent));
			let page = 0, size = 25, matching = rows;
			const controls = document.createElement("div");
			controls.className = "vat201-pagination d-flex flex-wrap align-items-center mb-2";
			controls.style.gap = "8px";
			controls.innerHTML = `<input type="search" class="form-control input-sm" style="max-width:320px" aria-label="${esc(__("Search transactions"))}" placeholder="${esc(__("Search voucher, date, account or amount"))}">
				<label class="mb-0">${esc(__("Rows per page"))} <select class="form-control input-sm" style="display:inline-block;width:auto"><option>25</option><option>50</option><option>100</option></select></label>
				<button type="button" class="btn btn-default btn-sm" data-page="previous">${esc(__("Previous"))}</button>
				<button type="button" class="btn btn-default btn-sm" data-page="next">${esc(__("Next"))}</button>
				<span class="text-muted" aria-live="polite"></span>`;
			container.before(controls);
			const search = controls.querySelector("input");
			const select = controls.querySelector("select");
			const previous = controls.querySelector('[data-page="previous"]');
			const next = controls.querySelector('[data-page="next"]');
			const status = controls.querySelector("span");
			const render = () => {
				page = Math.max(0, Math.min(page, Math.ceil(matching.length / size) - 1));
				const visible = new Set(matching.slice(page * size, (page + 1) * size));
				rows.forEach(row => row.style.display = visible.has(row) ? "" : "none");
				previous.disabled = page === 0;
				next.disabled = (page + 1) * size >= matching.length;
				status.textContent = matching.length ? `${page * size + 1}–${Math.min((page + 1) * size, matching.length)} / ${matching.length} (${rows.length} ${__("total")})` : __("No matching transactions");
			};
			search.addEventListener("input", () => {
				const terms = normalize(search.value).split(" ").filter(Boolean);
				matching = rows.filter((row, index) => terms.every(term => texts[index].includes(term)));
				page = 0;
				render();
			});
			select.addEventListener("change", () => { size = Number(select.value); page = 0; render(); });
			previous.addEventListener("click", () => { page--; render(); });
			next.addEventListener("click", () => { page++; render(); });
			render();
		}
	}

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
	function table(rows) {
		const headings = [
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
			.map((row, index) => {
				const currency = row.currency || "AED";
				const taxable =
					"invoice_taxable_amount" in row ? row.invoice_taxable_amount : row.base;
				const vat = "recorded_vat_amount" in row ? row.recorded_vat_amount : row.raw_vat;
				const values = [
							`<span class="text-muted mr-2">${index + 1}.</span>${esc(frappe.datetime?.str_to_user ? frappe.datetime.str_to_user(row.posting_date) : row.posting_date)}`,
							voucher(row),
							esc(row.party),
							money(taxable, currency),
							money(vat, currency),
							esc(row.treatment),
							esc(row.vat_box ?? row.box),
							esc(
								row.display_remarks || row.issue || row.remarks || row.reason || row.supporting_reference
							),
					  ];
				return `<tr>${values
					.map(
						(value, index) =>
							`<td style="${
								(index === 3 || index === 4)
									? "text-align:right;white-space:nowrap"
									: "min-width:140px;white-space:normal"
							}">${value}</td>`
					)
					.join("")}</tr>`;
			})
			.join("");
		return `<div class="table-responsive vat201-paged-table"><table class="table table-bordered"><thead><tr>${headings
			.map((h) => `<th>${esc(__(h))}</th>`)
			.join("")}</tr></thead><tbody>${
			body || `<tr><td colspan="${headings.length}">${__("No transactions")}</td></tr>`
		}</tbody></table></div>`;
	}
	async function details(report) {
		const filters = report.get_filter_values();
		const snapshot = JSON.stringify(filters);
		const { message } = report.raw_data?.vat201_context ? { message: report.raw_data.vat201_context } : await frappe.call({
			method: endpoint + "report_context",
			args: { filters },
		});
		if (snapshot !== JSON.stringify(report.get_filter_values()))
			return;
		report._vat_details_dialog?.hide();
		const panel = document.createElement("section");
		panel.className = "vat201-transaction-details mt-4";
		const tabs = ["Sales", "Purchases", "Journal Entries"];
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
		if (message.warnings?.length) panel.insertAdjacentHTML("afterbegin", `<details><summary>${__("Source and completeness notes")}</summary><ul>${message.warnings.map(note=>`<li>${esc(note)}</li>`).join("")}</ul></details>`);
		const reconciliation = message.reconciliation || [];
		if (message.filed_comparison) panel.insertAdjacentHTML("beforeend", `<details class="mt-3"><summary>${__("Submitted FTA Return Comparison")}</summary><table class="table table-bordered"><tbody>${Object.entries(message.filed_comparison).filter(([,value]) => !Array.isArray(value)).map(([key,value]) => `<tr><th>${esc(key.replaceAll("_", " "))}</th><td>${typeof value === "number" ? money(value) : esc(value ?? __("Unknown"))}</td></tr>`).join("")}</tbody></table></details>`);
		for (const [title, values, currency] of [["Ledger Balances",message.ledger_summary,message.ledger_summary?.currency], ["Recorded Tax and Return Bridge",message.tax_measures,"AED"]]) {
			if (values) panel.insertAdjacentHTML("beforeend", `<details class="mt-3"><summary>${__(title)}</summary><div class="table-responsive"><table class="table table-bordered"><tbody>${Object.entries(values).filter(([key]) => key !== "currency").map(([key,value])=>`<tr><td>${esc(__(message.measure_labels?.[key] || key.replaceAll("_"," ")))}</td><td class="text-right">${money(value,currency)}</td></tr>`).join("")}</tbody></table></div></details>`);
		}
		if (message.recorded_breakdown?.length) panel.insertAdjacentHTML("beforeend", `<details class="mt-3"><summary>${__("Recorded VAT by Voucher Type")}</summary><div class="table-responsive"><table class="table table-bordered"><thead><tr>${["Voucher Type","Tax Category","Period Debit","Period Credit","Recorded Output","Recorded Net Input"].map(h=>`<th>${esc(__(h))}</th>`).join("")}</tr></thead><tbody>${message.recorded_breakdown.map(row=>`<tr><td>${esc(row.voucher_type)}</td><td>${esc(row.category)}</td>${["raw_debit","raw_credit","recorded_output","recorded_input"].map(k=>`<td class="text-right">${money(row[k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`);
		if (reconciliation.length) panel.insertAdjacentHTML("afterbegin", `<h4 class="mt-4">${__("Recorded Versus Return")}</h4><div class="table-responsive"><table class="table table-bordered"><thead><tr>${["Description","Known Return VAT","Recorded Ledger VAT","Difference","Explanation"].map(label=>`<th>${esc(__(label))}</th>`).join("")}</tr></thead><tbody>${reconciliation.map(row=>`<tr><td>${esc(row.description)}</td>${["report_amount","ledger_amount","difference"].map(field=>`<td class="text-right" style="white-space:nowrap">${row[field] == null ? "" : money(row[field])}</td>`).join("")}<td>${esc(row.explanation)}</td></tr>`).join("")}</tbody></table></div>`);
		const rows = message.details || [];
		const groups = [
			rows.filter((r) => ["Sales Invoice", "POS Invoice"].includes(r.voucher_type)),
			rows.filter((r) => r.voucher_type === "Purchase Invoice"),
			rows.filter(
				(r) =>
					!["Sales Invoice", "POS Invoice", "Purchase Invoice"].includes(r.voucher_type)
			),
		];
		const select = (index) => {
			panel.querySelectorAll("[data-tab]").forEach((button) => {
				const active = Number(button.dataset.tab) === index;
				button.classList.toggle("active", active);
				button.setAttribute("aria-selected", String(active));
			});
			panel.querySelector(".vat201-tab-content").innerHTML = table(
				groups[index]
			);
			paginate_tables(panel.querySelector(".vat201-tab-content"));
		};
		panel.addEventListener("click", (event) => {
			const button = event.target.closest("[data-tab]");
			if (button) select(Number(button.dataset.tab));
		});
		const dialog = new frappe.ui.Dialog({ title: __("VAT 201 Supporting Details"), size: "extra-large",
			fields: [{ fieldname: "supporting", fieldtype: "HTML" }] });
		dialog.fields_dict.supporting.$wrapper[0].appendChild(panel);
		report._vat_details_dialog = dialog;
		select(0);
		dialog.show();
	}

	async function review_transaction(report) {
		const { message: context } = await frappe.call({method: endpoint + "report_context", args: {filters: report.get_filter_values()}});
		const rows = (context.details || []).filter(row => row.voucher_type !== "VAT 201 Tax Evidence");
		const pick = new frappe.ui.Dialog({title: __("Review VAT Treatment"), fields: [{fieldname: "source", fieldtype: "Select", label: __("Source transaction"), reqd: 1, options: rows.map((r, i) => ({value: String(i), label: `${r.voucher_no} / ${r.source_row} — ${r.recovery_status || r.issue || r.treatment}`}))}], primary_action_label: __("Review"), primary_action: async (v) => {
			pick.hide();
			const row = rows[Number(v.source)];
			if (!row) return;
			const method = endpoint.slice(0, -"uae_vat_201_return.".length) + "review.";
			const args = {filters: report.get_filter_values(), voucher_type: row.voucher_type, voucher_no: row.voucher_no, source_row: row.source_row};
			const {message: evidence} = await frappe.call({method: method + "review_source", args});
			if (evidence.records.length > 1) {
				frappe.msgprint(__("This source has multiple tax-side decisions. Review the classifications in UAE VAT Settings."));
				return;
			}
			const saved = evidence.records[0] || {};
			const fields = [
				{fieldname: "source_notes", fieldtype: "HTML", options: `<p>${esc(row.issue || row.system_reason || "")}</p><p>${esc((row.source_quality_warnings || []).join("; "))}</p><p>${__("Source recorded VAT")}: ${money(row.recorded_vat_amount ?? row.raw_vat)}</p>`},
				{fieldname: "box", fieldtype: "Select", label: __("VAT Box / Emirate Allocation"), options: ["", "1a", "1b", "1c", "1d", "1e", "1f", "1g", "2", "3", "4", "5", "6", "7", "9", "10", "Outside VAT"], reqd: 1},
				{fieldname: "tax_date", fieldtype: "Date", label: __("Reviewed Tax Date"), reqd: 1},
				{fieldname: "recovery_confirmed", fieldtype: "Check", label: __("Recovery Eligibility Reviewed")},
				{fieldname: "recovery_percent", fieldtype: "Percent", label: __("Recoverable VAT Percent (explicit zero permitted)")},
				{fieldname: "override_base", fieldtype: "Check", label: __("Use Reviewed Taxable Base")},
				{fieldname: "taxable_base_aed", fieldtype: "Currency", options: "AED", label: __("Reviewed Taxable Base")},
				{fieldname: "aed_exchange_rate", fieldtype: "Float", label: __("AED per Company Currency")},
				{fieldname: "journal_treatment", fieldtype: "Select", label: __("Journal Treatment"), options: "\nUnresolved\nVAT settlement\nVAT payment\nVAT reclassification\nVAT correction\nTaxable adjustment\nReverse-charge adjustment"},
				{fieldname: "is_adjustment", fieldtype: "Check", label: __("FTA Adjustment Column")},
				{fieldname: "adjustment_type", fieldtype: "Select", label: __("Adjustment Type"), options: "\nBad Debt Relief\nCommercial Property Tax Paid by Buyer\nAnnual Input Tax Apportionment\nCapital Assets Scheme"},
				{fieldname: "overlap_reviewed", fieldtype: "Check", label: __("Advance / Invoice VAT Overlap Reconciled")},
				{fieldname: "overlap_reference", fieldtype: "Data", label: __("Overlap Reconciliation Evidence Reference")},
				{fieldname: "reason", fieldtype: "Small Text", label: __("Recovery / Tax Date / Place of Supply Basis"), reqd: 1},
				{fieldname: "supporting_reference", fieldtype: "Data", label: __("Supporting Tax Invoice / Evidence Reference"), reqd: 1},
				{fieldname: "review_remarks", fieldtype: "Small Text", label: __("Review Remarks")},
			];
			const d = new frappe.ui.Dialog({title: row.voucher_no + " / " + row.source_row, size: "large", fields, primary_action_label: saved.approved ? __("Revoke Approval for Revision") : __("Approve"), primary_action: async () => save(saved.approved ? "Save" : "Approve")});
			async function save(action) {
				const values = d.get_values();
				if (!values) return;
				await frappe.call({method: method + "decide", args: {...args, values, action, classification_id: saved.name, expected_fingerprint: evidence.decision_fingerprint}});
				d.hide(); report.refresh();
			}
			d.set_values(saved);
			if (!saved.approved) d.set_secondary_action(() => save("Save"));
			if (!saved.approved) d.set_secondary_action_label(__("Save Pending Review"));
			d.show();
		}});
		pick.show();
	}

	frappe.query_reports["UAE VAT 201 Return"] = {
		paginate_tables,
		html_format: "<div>{%= report.raw_data.vat201_context.form_print_html %}</div>",
		async onload(report) {
			report.ignore_prepared_report = true;
			report.page.add_inner_button(__("View Details"), () => details(report));
			if ((frappe.user_roles || []).some(role => ["Accounts Manager", "System Manager"].includes(role))) {
				report.page.add_inner_button(__("Review VAT Treatment"), () => review_transaction(report));
				for (const doctype of ["VAT 201 Filing", "VAT 201 Payment", "VAT 201 Filed Difference", "VAT 201 Tax Evidence"])
					report.page.add_inner_button(__(doctype), () => { frappe.route_options = {company: report.get_filter_value("company")}; frappe.set_route("List", doctype); }, __("Filing Evidence"));
			}
			for (const [type, label, detailed = 0] of [
				["xlsx", "Excel"],
				["pdf", "PDF"],
				["xlsx", "Detailed Audit (Excel)", 1],
				["csv", "Detailed Audit (CSV)", 1],
			]) {
				report.page.add_inner_button(
					__(label),
					() => {
						const params = new URLSearchParams({
							filters: JSON.stringify(report.get_filter_values()),
							file_type: type,
							detailed,
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
			{fieldname: "report_view", label: __("View"), fieldtype: "Select",
				options: "General Ledger\nInternal VAT Review", default: "General Ledger"},
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
		get_datatable_options(options) {
			return {...options, serialNoColumn: true, layout: "fixed"};
		},
		formatter(value, row, column, data, default_formatter) {
			let formatted = default_formatter(value, row, column, data);
			const state = data?.completeness?.[column.fieldname];
			if (data?._box && state?.provisional && column.fieldtype === "Currency")
				formatted = `<span class="text-warning" title="${esc(
					__("Provisional known subtotal") + ": " + (state.reasons || []).join("; ")
				)}">${formatted}</span>`;
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
			const report = frappe.query_report;
			const native_wrapper = datatable.wrapper;
			const form_wrapper = report.$report_message?.[0];
			const wrapper = form_wrapper?.querySelector(".qatra-vat201-form") || native_wrapper;
			if (wrapper !== native_wrapper) {
				native_wrapper.querySelectorAll(":scope > .qatra-vat201-form").forEach(node => node.remove());
				native_wrapper.querySelector(".datatable")?.style.setProperty("display", "none");
				native_wrapper.appendChild(wrapper);
				report.$report_message.hide();
				report.$summary?.children().addClass("qatra-vat201-return-card").css({ "flex": "1 1 220px", "min-width": "0", "border-radius": "4px" });
			}
			paginate_tables(wrapper);
			if (wrapper.vat201_handler)
				for (const type of ["click", "mousedown", "dblclick"])
					wrapper.removeEventListener(type, wrapper.vat201_handler, true);
			wrapper.vat201_handler = async (event) => {
				const ledgerLink = event.target.closest(".vat201-ledger-total");
				if (ledgerLink && wrapper.contains(ledgerLink)) {
					event.preventDefault();
					event.stopImmediatePropagation();
					if (event.type !== "click") return;
					const {message} = await frappe.call({method: endpoint + "ledger_details", args: {
						filters: report.get_filter_values(), group: ledgerLink.dataset.group, component: ledgerLink.dataset.component,
					}});
					const currency = report.raw_data?.vat201_context?.ledger_summary?.currency || "AED";
					const headings = message.kind === "sources" ? ["Date", "Voucher", "Amount Excluding VAT", "Recorded VAT", "GL Entries", "Category"] : ["Date", "Voucher", "VAT Account", "GL Entry", "Debit", "Credit"];
					const rows = message.rows.map(row => {
						const cells = message.kind === "sources" ? [esc(row.posting_date), voucher(row), money(row.base, currency), money(row.vat, currency), (row.gl_entries || "").split(", ").filter(Boolean).map(name => frappe.utils.get_form_link("GL Entry", name, true, esc(name))).join(", "), esc(row.category)] :
							[esc(row.posting_date), voucher(row), esc(row.account), frappe.utils.get_form_link("GL Entry", row.name, true, esc(row.name)), money(row.debit, currency), money(row.credit, currency)];
						return `<tr>${cells.map(cell => `<td>${cell}</td>`).join("")}</tr>`;
					}).join("");
					const dialog = new frappe.ui.Dialog({title: __(message.label), size: "extra-large", fields: [{fieldname: "transactions", fieldtype: "HTML"}]});
					dialog.fields_dict.transactions.$wrapper.html(`<div class="table-responsive vat201-paged-table"><table class="table table-bordered"><thead><tr>${headings.map(h => `<th>${__(h)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`);
					dialog.show();
					paginate_tables(dialog.fields_dict.transactions.$wrapper[0]);
					return;
				}
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
				paginate_tables(dialog.fields_dict.transactions.$wrapper[0]);
			};
			for (const type of ["click", "mousedown", "dblclick"])
				wrapper.addEventListener(type, wrapper.vat201_handler, true);
			report._vat_details_dialog?.hide();
		},
	};
})();
