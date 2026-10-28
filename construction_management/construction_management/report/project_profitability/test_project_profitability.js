const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
	const calls = [];
	const filters = {
		metric: "Net Profit",
		view_type: "Summary",
		company: "QBC",
		project: "PROJ-0016",
	};
	const frappe = {
		query_reports: {},
		defaults: { get_user_default: () => "QBC" },
		utils: { escape_html: (s) => s.replaceAll('"', "&quot;") },
		query_report: {
			get_filter_value: (key) => filters[key],
			get_filter_values: () => filters,
		},
		call: async (args) => {
			calls.push(args);
			return {
				message: { breakdown: false, filters: { project: [args.args.context.project] } },
			};
		},
		set_route: (...args) => calls.push(args),
	};
	vm.runInNewContext(fs.readFileSync(`${__dirname}/project_profitability.js`, "utf8"), {
		frappe,
		__: (s) => s,
	});
	return { frappe, report: frappe.query_reports["Project Profitability"], calls, filters };
}

test("saved date ranges survive onload and fiscal route-filter application", async () => {
	const { report, frappe, calls, filters } = setup();
	filters.from_date = "2026-09-20";
	filters.to_date = "2026-10-20";
	await report.onload(frappe.query_report);
	assert.equal(calls.length, 0);
	frappe.query_report._no_refresh = true;
	await report.filters.find((f) => f.fieldname === "fiscal_year").on_change(frappe.query_report);
	assert.equal(calls.length, 0);
	assert.equal(filters.from_date, "2026-09-20");
});

test("currency links preserve numeric values, zero and exact period boundaries", () => {
	const { report } = setup();
	const row = {
		project: "PROJ-0016",
		period_0: -20,
		_periods: { period_0: { from_date: "2026-07-01", to_date: "2026-09-30" } },
	};
	const result = report.formatter(
		-20,
		{},
		{ fieldtype: "Currency", fieldname: "period_0" },
		row,
		() => "AED -20.00"
	);
	assert.ok(result.includes("text-danger"));
	const context = JSON.parse(
		result.match(/data-context="([^"]+)"/)[1].replaceAll("&quot;", '"')
	);
	assert.equal(context.from_date, "2026-07-01");
	assert.equal(context.to_date, "2026-09-30");
	assert.equal(context.metric, "Net Profit");
	assert.equal(row.period_0, -20);
	assert.ok(
		report
			.formatter(0, {}, { fieldtype: "Currency", fieldname: "income" }, row, () => "0.00")
			.includes("<a ")
	);
	assert.equal(
		report.formatter(
			null,
			{},
			{ fieldtype: "Currency", fieldname: "gross_profit" },
			row,
			() => ""
		),
		""
	);
});

test("mouse selection is blocked and clicking routes to standard GL", async () => {
	const { report, frappe, calls } = setup();
	const handlers = {};
	let removed = 0;
	const wrapper = {
		contains: () => true,
		addEventListener: (type, cb, capture) => {
			assert.equal(capture, true);
			handlers[type] = cb;
		},
		removeEventListener: () => removed++,
	};
	report.after_datatable_render({ wrapper });
	report.after_datatable_render({ wrapper });
	assert.equal(removed, 3);
	let blocked = 0;
	const event = {
		type: "mousedown",
		target: {
			closest: () => ({
				dataset: {
					context: JSON.stringify({ project: "PROJ-0016", fieldname: "income" }),
				},
			}),
		},
		preventDefault: () => blocked++,
		stopImmediatePropagation: () => blocked++,
	};
	await handlers.mousedown(event);
	assert.equal(blocked, 2);
	assert.equal(calls.length, 0);
	event.type = "click";
	await handlers.click(event);
	assert.equal(calls[0].args.context.project, "PROJ-0016");
	assert.equal(frappe.route_options.project[0], "PROJ-0016");
	assert.deepEqual(calls[1], ["query-report", "General Ledger"]);
});

test("percentage analysis defaults on, blanks undefined margins and keeps native scrolling", () => {
	const { report, filters } = setup();
	filters.view_type = "Cost Center Breakdown";
	assert.equal(report.filters.find((f) => f.fieldname === "show_percentage_analysis").default, 1);
	assert.equal(report.formatter(null, {}, { fieldtype: "Percent" }, { project: "P" }, () => "0%"), "");
	const column = { fieldtype: "Percent", fieldname: "expense_contribution", description: "Center expenses / Project expenses" };
	const data = { project: "P", expense_contribution: -2.08 };
	const value = report.formatter(-2.08, {}, column, data, () => "-2.08%");
	assert.ok(value.includes("title="));
	assert.ok(value.includes("-2.08%"));
	assert.ok(!value.includes("<a "));
	assert.equal(data.expense_contribution, -2.08);
	assert.ok(report.formatter("Project", {}, { fieldtype: "Data" }, { _project_summary: true }, () => "Project").includes("<strong>"));
	const options = report.get_datatable_options({ checkboxColumn: true, layout: "fluid" });
	assert.equal(options.layout, "fixed");
	assert.equal(options.checkboxColumn, true);
});
