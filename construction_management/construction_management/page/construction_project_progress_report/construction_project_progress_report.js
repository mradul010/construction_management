frappe.pages["construction-project-progress-report"].on_page_load = function (wrapper) {
	wrapper.project_progress_report = new construction_management.ProjectProgressReport(wrapper);
};

frappe.pages["construction-project-progress-report"].on_page_show = function (wrapper) {
	if (wrapper.project_progress_report && !wrapper.project_progress_report.loaded) {
		wrapper.project_progress_report.refresh();
	}
};

frappe.provide("construction_management");

construction_management.ProjectProgressReport = class ProjectProgressReport {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Project Progress Report"),
			single_column: true,
		});
		this.method =
			"construction_management.construction_management.page.construction_project_progress_report.construction_project_progress_report";
		this.fields = {};
		this.state = {
			view: "list",
			projects: [],
			detail: null,
		};

		frappe.breadcrumbs.add(__("Construction Management"));
		this.add_styles();
		this.make_filters();
		this.make_actions();
		this.make_body();
		this.bind_events();
		this.refresh();
	}

	add_styles() {
		if (document.getElementById("construction-project-progress-report-style")) return;

		$(`<style id="construction-project-progress-report-style">
			.project-progress-report {
				padding: 14px 0 36px;
			}
			.project-progress-report .cm-report-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				gap: 12px;
				margin-bottom: 14px;
			}
			.project-progress-report .cm-report-title {
				font-size: 18px;
				font-weight: 600;
				line-height: 1.35;
				margin: 0;
			}
			.project-progress-report .cm-section {
				margin-top: 22px;
			}
			.project-progress-report .cm-section:first-child {
				margin-top: 0;
			}
			.project-progress-report .cm-section-title {
				font-size: 15px;
				font-weight: 600;
				margin: 0 0 10px;
			}
			.project-progress-report .cm-summary-grid {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
				gap: 10px;
				margin-bottom: 8px;
			}
			.project-progress-report .cm-summary-card {
				border: 1px solid var(--border-color);
				border-radius: 8px;
				background: var(--fg-color);
				padding: 12px;
				min-height: 76px;
			}
			.project-progress-report .cm-summary-label {
				color: var(--text-muted);
				font-size: 12px;
				line-height: 1.25;
				margin-bottom: 8px;
			}
			.project-progress-report .cm-summary-value {
				color: var(--text-color);
				font-size: 16px;
				font-weight: 600;
				line-height: 1.25;
				overflow-wrap: anywhere;
			}
			.project-progress-report .cm-table-frame {
				border: 1px solid var(--border-color);
				border-radius: 8px;
				background: var(--fg-color);
				overflow: hidden;
			}
			.project-progress-report .cm-table-scroll {
				overflow-x: auto;
			}
			.project-progress-report table {
				margin-bottom: 0;
				min-width: 980px;
			}
			.project-progress-report th {
				white-space: nowrap;
				font-size: 12px;
				color: var(--text-muted);
				background: var(--subtle-fg);
			}
			.project-progress-report td {
				vertical-align: middle !important;
			}
			.project-progress-report .cm-link-cell {
				font-weight: 500;
				white-space: nowrap;
			}
			.project-progress-report .cm-actions {
				display: flex;
				gap: 6px;
				flex-wrap: nowrap;
				white-space: nowrap;
			}
			.project-progress-report .cm-number {
				text-align: right;
				white-space: nowrap;
			}
			.project-progress-report .cm-percent {
				min-width: 92px;
			}
			.project-progress-report .cm-progress {
				height: 6px;
				background: var(--control-bg);
				border-radius: 999px;
				margin-top: 5px;
				overflow: hidden;
			}
			.project-progress-report .cm-progress-bar {
				height: 100%;
				background: var(--primary);
				border-radius: 999px;
			}
			.project-progress-report .cm-empty {
				color: var(--text-muted);
				padding: 28px;
				text-align: center;
			}
			.project-progress-report .cm-related-bills {
				display: flex;
				gap: 5px;
				flex-wrap: wrap;
				min-width: 160px;
			}
			@media (max-width: 767px) {
				.project-progress-report .cm-report-header {
					align-items: stretch;
					flex-direction: column;
				}
				.project-progress-report table {
					min-width: 860px;
				}
			}
		</style>`).appendTo(document.head);
	}

	make_filters() {
		this.fields.customer = this.page.add_field({
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		});

		this.fields.project = this.page.add_field({
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			get_query: () => {
				const customer = this.fields.customer.get_value();
				return customer ? { filters: { customer } } : {};
			},
		});

		this.fields.date_range = this.page.add_field({
			fieldname: "date_range",
			label: __("Date Range"),
			fieldtype: "DateRange",
		});

		this.fields.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Completed", "Cancelled"].join("\n"),
		});
	}

	make_actions() {
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.page.add_inner_button(__("Export"), () => this.export_current_view());
	}

	make_body() {
		this.$body = $(`<div class="project-progress-report"></div>`).appendTo(this.page.main);
	}

	bind_events() {
		this.$body.on("click", ".cm-view-project", (event) => {
			const project = $(event.currentTarget).attr("data-project");
			this.show_detail(project);
		});

		this.$body.on("click", ".cm-back-to-projects", () => {
			this.render_project_list();
		});

		this.$body.on("click", ".cm-open-doc", (event) => {
			const $button = $(event.currentTarget);
			const doctype = $button.attr("data-doctype");
			const name = $button.attr("data-name");
			if (doctype && name) {
				frappe.set_route("Form", doctype, name);
			}
		});
	}

	get_filters() {
		const filters = {
			customer: this.fields.customer.get_value(),
			project: this.fields.project.get_value(),
			status: this.fields.status.get_value(),
		};
		const date_range = this.fields.date_range.get_value();
		filters.date_range = date_range;

		if (Array.isArray(date_range)) {
			filters.from_date = date_range[0];
			filters.to_date = date_range[1];
		} else if (typeof date_range === "string" && date_range.includes(",")) {
			const parts = date_range.split(",").map((part) => part.trim());
			filters.from_date = parts[0];
			filters.to_date = parts[1];
		}

		return filters;
	}

	async refresh() {
		this.loaded = false;
		this.state.view = "list";
		this.state.detail = null;
		this.set_loading();

		try {
			const response = await frappe.call({
				method: `${this.method}.get_project_progress_list`,
				args: {
					filters: this.get_filters(),
				},
			});
			this.state.projects = response.message || [];
			this.render_project_list();
			this.loaded = true;
		} catch (error) {
			this.render_error(error);
			throw error;
		}
	}

	async show_detail(project) {
		if (!project) return;

		this.state.view = "detail";
		this.set_loading();

		try {
			const response = await frappe.call({
				method: `${this.method}.get_project_progress_detail`,
				args: {
					project,
					filters: this.get_filters(),
				},
			});
			this.state.detail = response.message || {};
			this.render_detail();
		} catch (error) {
			this.render_error(error);
			throw error;
		}
	}

	set_loading() {
		this.$body.html(`<div class="cm-empty">${__("Loading")}</div>`);
	}

	render_error(error) {
		const message = error && error.message ? error.message : __("Unable to load report");
		this.$body.html(`<div class="cm-empty text-danger">${this.escape(message)}</div>`);
	}

	render_project_list() {
		this.state.view = "list";
		this.page.set_title(__("Project Progress Report"));

		const rows = this.state.projects || [];
		const content = [
			`<div class="cm-report-header">
				<h2 class="cm-report-title">${__("Projects")}</h2>
			</div>`,
			this.render_table({
				columns: this.project_columns(),
				rows,
				empty_message: __("No projects found"),
			}),
		].join("");

		this.$body.html(content);
	}

	render_detail() {
		const detail = this.state.detail || {};
		const summary = detail.summary || {};
		const title = summary.project_name || detail.project?.project_name || summary.project;
		this.page.set_title(__("Project Progress Report"));

		this.$body.html([
			`<div class="cm-report-header">
				<h2 class="cm-report-title">${this.escape(title || __("Project"))}</h2>
				<button class="btn btn-default btn-sm cm-back-to-projects">${__("Back to Projects")}</button>
			</div>`,
			this.render_summary(summary),
			this.render_section(
				__("BOQ Summary"),
				this.render_table({
					columns: this.boq_columns(),
					rows: detail.boqs || [],
					empty_message: __("No BOQs found"),
				})
			),
			this.render_section(
				__("RA Bill Summary"),
				this.render_table({
					columns: this.ra_bill_columns(),
					rows: detail.ra_bills || [],
					empty_message: __("No RA Bills found"),
				})
			),
			this.render_section(
				__("Work Completion Report"),
				this.render_table({
					columns: this.work_completion_columns(summary.currency),
					rows: detail.work_completion || [],
					empty_message: __("No work completion rows found"),
				})
			),
		].join(""));
	}

	render_section(title, content) {
		return `<div class="cm-section">
			<h3 class="cm-section-title">${this.escape(title)}</h3>
			${content}
		</div>`;
	}

	render_summary(summary) {
		const cards = [
			[__("Project Name"), summary.project_name || summary.project],
			[__("Customer"), summary.customer],
			[__("Current BOQ"), summary.current_boq],
			[__("BOQ Value"), this.currency(summary.boq_value, summary.currency)],
			[__("Total RA Billed"), this.currency(summary.total_ra_billed, summary.currency)],
			[__("Total Net Payable"), this.currency(summary.total_net_payable, summary.currency)],
			[__("Total Invoiced"), this.currency(summary.total_invoiced, summary.currency)],
			[__("Completion"), this.percent(summary.completion_percent)],
		];

		return this.render_section(
			__("Project Summary"),
			`<div class="cm-summary-grid">
				${cards
					.map(
						([label, value]) => `<div class="cm-summary-card">
							<div class="cm-summary-label">${this.escape(label)}</div>
							<div class="cm-summary-value">${this.escape(value || "-")}</div>
						</div>`
					)
					.join("")}
			</div>`
		);
	}

	render_table({ columns, rows, empty_message }) {
		if (!rows || !rows.length) {
			return `<div class="cm-table-frame"><div class="cm-empty">${this.escape(empty_message)}</div></div>`;
		}

		return `<div class="cm-table-frame">
			<div class="cm-table-scroll">
				<table class="table table-bordered table-hover">
					<thead>
						<tr>
							${columns.map((column) => `<th>${this.escape(column.label)}</th>`).join("")}
						</tr>
					</thead>
					<tbody>
						${rows
							.map(
								(row) => `<tr>
									${columns
										.map((column) => {
											const value = column.formatter
												? column.formatter(row)
												: this.escape(row[column.fieldname] || "-");
											return `<td class="${column.className || ""}">${value}</td>`;
										})
										.join("")}
								</tr>`
							)
							.join("")}
					</tbody>
				</table>
			</div>
		</div>`;
	}

	project_columns() {
		return [
			{
				label: __("Project"),
				formatter: (row) => this.doc_link("Project", row.project),
			},
			{ label: __("Project Name"), fieldname: "project_name" },
			{ label: __("Customer"), fieldname: "customer" },
			{
				label: __("Current BOQ"),
				formatter: (row) => (row.current_boq ? this.doc_link("BOQ", row.current_boq) : "-"),
			},
			{ label: __("BOQ Count"), className: "cm-number", formatter: (row) => this.integer(row.boq_count) },
			{
				label: __("RA Bill Count"),
				className: "cm-number",
				formatter: (row) => this.integer(row.ra_bill_count),
			},
			{
				label: __("Total BOQ Value"),
				className: "cm-number",
				formatter: (row) => this.currency(row.total_boq_value, row.currency),
			},
			{
				label: __("Total RA Billed"),
				className: "cm-number",
				formatter: (row) => this.currency(row.total_ra_billed, row.currency),
			},
			{
				label: __("Total Net Payable"),
				className: "cm-number",
				formatter: (row) => this.currency(row.total_net_payable, row.currency),
			},
			{
				label: __("Total Invoiced"),
				className: "cm-number",
				formatter: (row) => this.currency(row.total_invoiced, row.currency),
			},
			{
				label: __("Overall Completion %"),
				className: "cm-percent",
				formatter: (row) => this.progress(row.overall_completion_percent),
			},
			{
				label: __("View Report"),
				formatter: (row) =>
					`<button class="btn btn-default btn-xs cm-view-project" data-project="${this.attr(
						row.project
					)}">${__("View Report")}</button>`,
			},
		];
	}

	boq_columns() {
		return [
			{ label: __("BOQ"), formatter: (row) => this.doc_link("BOQ", row.name) },
			{ label: __("Revision No"), className: "cm-number", formatter: (row) => this.integer(row.revision_no) },
			{ label: __("Revision Status"), fieldname: "revision_status" },
			{
				label: __("Active Revision"),
				formatter: (row) => (row.is_active_revision ? __("Yes") : __("No")),
			},
			{ label: __("Currency"), fieldname: "currency" },
			{
				label: __("Total BOQ Value"),
				className: "cm-number",
				formatter: (row) => this.currency(row.total_boq_value, row.currency),
			},
			{ label: __("Status"), fieldname: "status" },
			{
				label: __("View BOQ"),
				formatter: (row) => this.open_button("BOQ", row.name, __("View BOQ")),
			},
		];
	}

	ra_bill_columns() {
		return [
			{ label: __("RA Bill"), formatter: (row) => this.doc_link("RA Bill", row.name) },
			{ label: __("Bill No"), className: "cm-number", formatter: (row) => this.integer(row.bill_no) },
			{ label: __("BOQ"), formatter: (row) => (row.boq ? this.doc_link("BOQ", row.boq) : "-") },
			{ label: __("Billing Period"), formatter: (row) => this.billing_period(row) },
			{ label: __("Status"), fieldname: "status" },
			{
				label: __("Gross Amount"),
				className: "cm-number",
				formatter: (row) => this.currency(row.gross_amount, row.currency),
			},
			{
				label: __("Retention Amount"),
				className: "cm-number",
				formatter: (row) => this.currency(row.retention_amount, row.currency),
			},
			{
				label: __("Net Payable"),
				className: "cm-number",
				formatter: (row) => this.currency(row.net_payable, row.currency),
			},
			{
				label: __("Sales Invoice"),
				formatter: (row) =>
					row.sales_invoice ? this.doc_link("Sales Invoice", row.sales_invoice) : "-",
			},
			{
				label: __("View RA Bill"),
				formatter: (row) => this.open_button("RA Bill", row.name, __("View RA Bill")),
			},
			{
				label: __("View Sales Invoice"),
				formatter: (row) =>
					row.sales_invoice
						? this.open_button("Sales Invoice", row.sales_invoice, __("View Sales Invoice"))
						: "-",
			},
		];
	}

	work_completion_columns(currency) {
		return [
			{ label: __("BOQ"), formatter: (row) => this.doc_link("BOQ", row.boq) },
			{ label: __("Category"), fieldname: "category" },
			{ label: __("Sub Category"), fieldname: "sub_category" },
			{ label: __("Item Name"), fieldname: "item_name" },
			{ label: __("BOQ Qty"), className: "cm-number", formatter: (row) => this.number(row.boq_qty) },
			{
				label: __("Completed Qty"),
				className: "cm-number",
				formatter: (row) => this.number(row.completed_qty),
			},
			{
				label: __("Remaining Qty"),
				className: "cm-number",
				formatter: (row) => this.number(row.remaining_qty),
			},
			{
				label: __("Completion %"),
				className: "cm-percent",
				formatter: (row) => this.progress(row.completion_percent),
			},
			{
				label: __("BOQ Rate"),
				className: "cm-number",
				formatter: (row) => this.currency(row.boq_rate, currency),
			},
			{
				label: __("BOQ Amount"),
				className: "cm-number",
				formatter: (row) => this.currency(row.boq_amount, currency),
			},
			{
				label: __("Completed Amount"),
				className: "cm-number",
				formatter: (row) => this.currency(row.completed_amount, currency),
			},
			{
				label: __("Remaining Amount"),
				className: "cm-number",
				formatter: (row) => this.currency(row.remaining_amount, currency),
			},
			{
				label: __("Related RA Bills"),
				formatter: (row) => this.related_ra_bills(row.related_ra_bills),
			},
		];
	}

	doc_link(doctype, name) {
		if (!name) return "-";
		return `<button class="btn btn-link btn-xs cm-link-cell cm-open-doc" data-doctype="${this.attr(
			doctype
		)}" data-name="${this.attr(name)}">${this.escape(name)}</button>`;
	}

	open_button(doctype, name, label) {
		if (!name) return "-";
		return `<button class="btn btn-default btn-xs cm-open-doc" data-doctype="${this.attr(
			doctype
		)}" data-name="${this.attr(name)}">${this.escape(label)}</button>`;
	}

	related_ra_bills(names) {
		if (!names || !names.length) return "-";
		return `<div class="cm-related-bills">
			${names.map((name) => this.doc_link("RA Bill", name)).join("")}
		</div>`;
	}

	progress(value) {
		const percent = Math.max(0, Math.min(100, flt(value)));
		return `<div>${this.percent(value)}</div>
			<div class="cm-progress"><div class="cm-progress-bar" style="width: ${percent}%"></div></div>`;
	}

	billing_period(row) {
		const from_date = row.billing_period_from ? frappe.datetime.str_to_user(row.billing_period_from) : "";
		const to_date = row.billing_period_to ? frappe.datetime.str_to_user(row.billing_period_to) : "";
		if (from_date && to_date) return `${this.escape(from_date)} - ${this.escape(to_date)}`;
		return this.escape(from_date || to_date || "-");
	}

	export_current_view() {
		if (this.state.view === "detail" && this.state.detail) {
			this.export_work_completion();
			return;
		}
		this.export_project_list();
	}

	export_project_list() {
		const rows = this.state.projects || [];
		const data = [
			[
				__("Project"),
				__("Project Name"),
				__("Customer"),
				__("Current BOQ"),
				__("BOQ Count"),
				__("RA Bill Count"),
				__("Total BOQ Value"),
				__("Total RA Billed"),
				__("Total Net Payable"),
				__("Total Invoiced"),
				__("Overall Completion %"),
			],
			...rows.map((row) => [
				row.project,
				row.project_name,
				row.customer,
				row.current_boq,
				row.boq_count,
				row.ra_bill_count,
				row.total_boq_value,
				row.total_ra_billed,
				row.total_net_payable,
				row.total_invoiced,
				row.overall_completion_percent,
			]),
		];
		frappe.tools.downloadify(data, null, __("Project Progress Report"));
	}

	export_work_completion() {
		const rows = this.state.detail.work_completion || [];
		const data = [
			[
				__("BOQ"),
				__("Category"),
				__("Sub Category"),
				__("Item Name"),
				__("BOQ Qty"),
				__("Completed Qty"),
				__("Remaining Qty"),
				__("Completion %"),
				__("BOQ Rate"),
				__("BOQ Amount"),
				__("Completed Amount"),
				__("Remaining Amount"),
				__("Related RA Bills"),
			],
			...rows.map((row) => [
				row.boq,
				row.category,
				row.sub_category,
				row.item_name,
				row.boq_qty,
				row.completed_qty,
				row.remaining_qty,
				row.completion_percent,
				row.boq_rate,
				row.boq_amount,
				row.completed_amount,
				row.remaining_amount,
				(row.related_ra_bills || []).join(", "),
			]),
		];
		frappe.tools.downloadify(data, null, __("Project Work Completion Report"));
	}

	currency(value, currency) {
		return format_currency(flt(value), currency || frappe.defaults.get_default("currency"));
	}

	number(value) {
		return format_number(flt(value), null, 2);
	}

	integer(value) {
		return format_number(flt(value), null, 0);
	}

	percent(value) {
		return `${format_number(flt(value), null, 2)}%`;
	}

	escape(value) {
		return frappe.utils.escape_html(value === null || value === undefined || value === "" ? "-" : value);
	}

	attr(value) {
		return this.escape(value).replace(/"/g, "&quot;");
	}
};
