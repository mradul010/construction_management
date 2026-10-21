const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
	const calls = [];
	const frappe = {
		query_reports: {},
		defaults: { get_user_default: () => "TEST" },
		datetime: { get_today: () => "2026-10-20", month_start: () => "2026-10-01" },
		utils: { escape_html: (s) => s },
		model: { unscrub: (s) => s },
		query_report: { get_filter_values: () => ({ company: "TEST" }) },
		call: async (args) => {
			calls.push(args);
			return { message: [] };
		},
		ui: {
			Dialog: class {
				constructor() {
					this.fields_dict = { transactions: { $wrapper: { html() {}, on() {} } } };
				}
				show() {}
			},
		},
	};
	vm.runInNewContext(fs.readFileSync(`${__dirname}/uae_vat_201_return.js`, "utf8"), {
		frappe,
		__: (s) => s,
		URLSearchParams,
		window: { open() {} },
	});
	return { report: frappe.query_reports["UAE VAT 201 Return"], frappe, calls };
}

test("all boxes keep numeric currency data; zero remains clickable", () => {
	const { report } = setup();
	const row = { _box: true, box: "9", vat_amount: 0 };
	assert.ok(
		report
			.formatter(
				0,
				{},
				{ fieldname: "vat_amount", fieldtype: "Currency" },
				row,
				() => "AED 0.00"
			)
			.includes('data-box="9"')
	);
	assert.equal(row.vat_amount, 0);
	assert.ok(
		report
			.formatter(
				-50,
				{},
				{ fieldname: "amount", fieldtype: "Currency" },
				row,
				() => "AED -50.00"
			)
			.includes("text-danger")
	);
});

test("VAT period options do not silently select Profit Margin Scheme", () => {
	const { report } = setup();
	assert.equal(
		report.filters.find((f) => f.fieldname === "profit_margin_scheme").default,
		undefined
	);
	assert.ok(
		report.filters.find((f) => f.fieldname === "period_type").options.includes("Quarterly")
	);
	assert.equal(report.filters.find((f) => f.fieldname === "show_zero").default, 1);
});

test("initial load selects the configured first return without refresh loops", async () => {
	const { report, frappe } = setup();
	const values = { company: "TEST", period_type: "Custom Date Range" };
	frappe.call = async () => ({ message: {
		from_date: "2026-05-01", to_date: "2026-07-31", quarter_number: 2,
		filing_frequency: "Quarterly", trn: "105452509000003", stagger: "February-January",
		profit_margin_scheme: "No",
	} });
	const instance = {
		_no_refresh: true,
		page: { add_inner_button() {} },
		get_filter_values: () => ({ ...values }),
		get_filter_value: key => values[key],
		get_filter: key => ({ set_value: async value => {
			assert.equal(instance._no_refresh, true);
			values[key] = value;
		} }),
	};
	await report.onload(instance);
	assert.equal(values.from_date, "2026-05-01");
	assert.equal(values.to_date, "2026-07-31");
	assert.equal(values.period_type, "Quarterly");
	assert.equal(values.year, 2026);
	assert.equal(values.quarter, "2");
	assert.equal(values.profit_margin_scheme, "No");
	assert.equal(instance._no_refresh, true);
	values.from_date = "2026-08-01";
	values.to_date = "2026-10-31";
	values.quarter = "3";
	await report.onload(instance);
	assert.equal(values.from_date, "2026-08-01");
	assert.equal(values.quarter, "3");
});

test("capture handler blocks cell selection and calls permission-checked drilldown", async () => {
	const { report, calls } = setup();
	const handlers = {};
	let removed = 0,
		stopped = 0;
	const wrapper = {
		contains: () => true,
		addEventListener: (type, fn, capture) => {
			assert.equal(capture, true);
			handlers[type] = fn;
		},
		removeEventListener: () => removed++,
	};
	report.after_datatable_render({ wrapper });
	report.after_datatable_render({ wrapper });
	assert.equal(removed, 3);
	const event = {
		type: "mousedown",
		target: { closest: () => ({ dataset: { box: "9" } }) },
		preventDefault: () => stopped++,
		stopImmediatePropagation: () => stopped++,
	};
	await handlers.mousedown(event);
	assert.equal(stopped, 2);
	assert.equal(calls.length, 0);
	event.type = "click";
	await handlers.click(event);
	assert.equal(calls[0].args.box, "9");
	assert.ok(calls[0].method.endsWith(".transactions"));
});
