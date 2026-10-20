(() => {
	const endpoint =
		"construction_management.construction_management.report.uae_vat_201_return.uae_vat_201_return.";
	async function update_period(report) {
		if (report._no_refresh || !report.get_filter_value("company")) return;
		const { message } = await frappe.call({
			method: endpoint + "period_context",
			args: { filters: report.get_filter_values() },
		});
		report.set_filter_value({
			from_date: message.from_date,
			to_date: message.to_date,
			trn: message.trn || __("Not Configured"),
			vat_stagger: message.stagger || __("Not Configured"),
		});
		report.refresh();
	}
	function export_file(type) {
		const params = new URLSearchParams({
			filters: JSON.stringify(frappe.query_report.get_filter_values()),
			file_type: type,
		});
		window.open(`/api/method/${endpoint}download?${params}`, "_blank", "noopener");
	}
	frappe.query_reports["UAE VAT 201 Return"] = {
		tree: true,
		name_field: "row_id",
		parent_field: "parent_id",
		initial_depth: 1,
		async onload(report) {
			for (const [type, label] of [
				["xlsx", "Excel: VAT Preparation"],
				["csv", "CSV: VAT Preparation"],
				["pdf", "PDF: VAT 201 Preparation"],
			]) {
				report.page.add_inner_button(__(label), () => export_file(type), __("Export"));
			}
			if (report.get_filter_value("company")) {
				const { message } = await frappe.call({
					method: endpoint + "period_context",
					args: { filters: report.get_filter_values() },
				});
				const previous = report._no_refresh;
				report._no_refresh = true;
				try {
					await report.get_filter("trn").set_value(message.trn || __("Not Configured"));
					await report
						.get_filter("vat_stagger")
						.set_value(message.stagger || __("Not Configured"));
				} finally {
					report._no_refresh = previous;
				}
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
				on_change: update_period,
			},
			{
				fieldname: "period_type",
				label: __("VAT Return Period"),
				fieldtype: "Select",
				options: "Custom Date Range\nMonthly\nQuarterly",
				default: "Custom Date Range",
				reqd: 1,
				on_change: update_period,
			},
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				default: frappe.datetime.month_start(),
				reqd: 1,
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{
				fieldname: "year",
				label: __("Year"),
				fieldtype: "Int",
				default: Number(frappe.datetime.get_today().slice(0, 4)),
				on_change: update_period,
			},
			{
				fieldname: "month",
				label: __("Month"),
				fieldtype: "Select",
				options: "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12",
				default: String(Number(frappe.datetime.get_today().slice(5, 7))),
				depends_on: "eval:doc.period_type == 'Monthly'",
				on_change: update_period,
			},
			{
				fieldname: "quarter",
				label: __("Quarter"),
				fieldtype: "Select",
				options: "1\n2\n3\n4",
				default: "1",
				depends_on: "eval:doc.period_type == 'Quarterly'",
				on_change: update_period,
			},
			{
				fieldname: "vat_stagger",
				label: __("VAT Stagger"),
				fieldtype: "Data",
				read_only: 1,
			},
			{
				fieldname: "trn",
				label: __("Tax Registration Number"),
				fieldtype: "Data",
				read_only: 1,
			},
			{
				fieldname: "view_type",
				label: __("View Type"),
				fieldtype: "Select",
				options: "Summary\nDetailed",
				default: "Summary",
			},
			{
				fieldname: "include_adjustments",
				label: __("Include Adjustments"),
				fieldtype: "Check",
				default: 1,
			},
			{
				fieldname: "show_zero",
				label: __("Show Zero-Value Boxes"),
				fieldtype: "Check",
				default: 1,
			},
			{
				fieldname: "profit_margin_scheme",
				label: __("Profit Margin Scheme"),
				fieldtype: "Select",
				options: "\nYes\nNo",
			},
		],
		formatter(value, row, column, data, default_formatter) {
			let formatted = default_formatter(value, row, column, data);
			if (data?._section) return `<strong>${formatted}</strong>`;
			if (data?._review && column.fieldname === "description")
				return `<span class="text-warning">${formatted}</span>`;
			if (value < 0 && column.fieldtype === "Currency")
				formatted = `<span class="text-danger">${formatted}</span>`;
			if (
				data?._box &&
				["amount", "vat_amount", "adjustment"].includes(column.fieldname) &&
				value != null
			) {
				return `<a href="#" class="vat201-amount" data-box="${data.box}">${formatted}</a>`;
			}
			return formatted;
		},
		after_datatable_render(datatable) {
			const wrapper = datatable.wrapper;
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
						filters: frappe.query_report.get_filter_values(),
						box: link.dataset.box,
					},
				});
				const esc = (value) => frappe.utils.escape_html(String(value ?? ""));
				const fields = [
					"tax_date",
					"posting_date",
					"voucher_type",
					"voucher_no",
					"party",
					"amount",
					"vat_amount",
					"adjustment",
					"tax_rate",
					"classification",
					"emirate",
					"account",
					"tax_account",
					"company",
					"currency",
				];
				const dialog = new frappe.ui.Dialog({
					title: __("VAT 201 Transactions") + " - " + link.dataset.box,
					size: "extra-large",
					fields: [{ fieldname: "transactions", fieldtype: "HTML" }],
				});
				const body = message
					.map(
						(row, index) =>
							`<tr>${fields
								.map(
									(field) =>
										`<td>${
											field === "voucher_no"
												? frappe.utils.get_form_link(
														row.voucher_type,
														row.voucher_no,
														true
												  )
												: ["amount", "vat_amount", "adjustment"].includes(
														field
												  )
												? frappe.format(row[field], {
														fieldtype: "Currency",
														options: "AED",
												  })
												: esc(row[field])
										}</td>`
								)
								.join(
									""
								)}<td><a href="#" data-index="${index}" class="vat201-gl">${__(
								"General Ledger"
							)}</a></td></tr>`
					)
					.join("");
				dialog.fields_dict.transactions.$wrapper.html(
					`<div class="table-responsive"><table class="table table-bordered"><thead><tr>${fields
						.map((f) => `<th>${esc(__(frappe.model.unscrub(f)))}</th>`)
						.join("")}<th>${__("General Ledger")}</th></tr></thead><tbody>${
						body ||
						`<tr><td colspan="16">${__(
							"No classified transactions for this box."
						)}</td></tr>`
					}</tbody></table></div>`
				);
				dialog.fields_dict.transactions.$wrapper.on(
					"click",
					".vat201-gl",
					function (event) {
						event.preventDefault();
						const row = message[Number(this.dataset.index)];
						frappe.route_options = {
							company: row.company,
							from_date: row.posting_date,
							to_date: row.posting_date,
							voucher_no: row.voucher_no,
							account: row.tax_account ? [row.tax_account] : [],
							cost_center: [],
							project: [],
							party: [],
							party_type: "",
							categorize_by: "",
							show_cancelled_entries: 0,
							disable_opening_balance_calculation: 1,
							presentation_currency: "AED",
						};
						frappe.set_route("query-report", "General Ledger");
						dialog.hide();
					}
				);
				dialog.show();
			};
			for (const type of ["click", "mousedown", "dblclick"])
				wrapper.addEventListener(type, wrapper.vat201_handler, true);
		},
	};
})();
