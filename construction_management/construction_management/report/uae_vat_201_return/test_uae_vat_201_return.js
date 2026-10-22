const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
	const calls = [];
	const frappe = {
		query_reports: {},
		defaults: { get_user_default: () => "TEST" },
		utils: {
			escape_html: (s) => String(s).replaceAll('"', "&quot;").replaceAll("<", "&lt;"),
			get_form_link: () => "link",
		},
		format: (value) => `AED ${value}`,
		query_report: { get_filter_values: () => ({ company: "TEST" }) },
		call: async (args) => {
			calls.push(args);
			return { message: [] };
		},
		ui: {
			Dialog: class {
				constructor() {
					this.fields_dict = { transactions: { $wrapper: { html() {} } } };
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

test("only Company, filing period and dates are exposed; no approval workflow", () => {
	const { report } = setup();
	assert.deepEqual(
		Array.from(report.filters, (f) => f.fieldname),
		["company", "filing_period", "from_date", "to_date"]
	);
	const source = fs.readFileSync(`${__dirname}/uae_vat_201_return.js`, "utf8");
	for (const text of [
		"open_review",
		"Approve Classification",
		"Generate Review Suggestions",
		"review_endpoint",
		"classification_status",
	])
		assert.ok(!source.includes(text));
	for (const tab of ["Sales", "Purchases", "Journal Entries", "Needs Attention"])
		assert.ok(source.includes(`"${tab}"`));
});

test("formatter preserves numeric values and distinguishes pending from nil", () => {
	const { report } = setup();
	const data = { _box: true, box: "9", vat_amount: 0 };
	const col = { fieldname: "vat_amount", fieldtype: "Currency" };
	assert.ok(
		report.formatter(0, {}, col, data, () => "AED 0.00").includes('data-field="vat_amount"')
	);
	assert.equal(data.vat_amount, 0);
	data._incomplete = true;
	assert.ok(
		report.formatter(0, {}, col, data, () => "AED 0.00").includes("Pending Verification")
	);
	assert.ok(report.formatter(-50, {}, col, data, () => "AED -50.00").includes("text-danger"));
});

test("first configured period is selected without recursive refresh or rewriting explicit dates", async () => {
	const { report, frappe } = setup();
	const values = { company: "TEST" };
	const buttons = [];
	frappe.call = async () => ({
		message: {
			from_date: values.from_date || "2026-05-01",
			to_date: values.to_date || "2026-07-31",
			available_periods: ["2026-05-01 to 2026-07-31"],
		},
	});
	const instance = {
		_no_refresh: true,
		page: { add_inner_button: (label) => buttons.push(label) },
		get_filter_values: () => ({ ...values }),
		get_filter_value: (key) => values[key],
		get_filter: (key) => ({
			df: {},
			refresh() {},
			set_value: async (value) => {
				assert.equal(instance._no_refresh, true);
				values[key] = value;
			},
		}),
	};
	await report.onload(instance);
	assert.equal(values.from_date, "2026-05-01");
	assert.equal(values.to_date, "2026-07-31");
	assert.equal(values.filing_period, "2026-05-01 to 2026-07-31");
	assert.deepEqual(buttons, ["Excel", "CSV", "PDF"]);
	assert.equal(instance._no_refresh, true);
	values.filing_period = "";
	values.from_date = "2026-08-05";
	values.to_date = "2026-08-10";
	await report.onload(instance);
	assert.equal(values.from_date, "2026-08-05");
	assert.equal(values.filing_period, "");
});

test("manual date edit clears the period so backend cannot override the new dates", async () => {
	const { report } = setup();
	let cleared, refreshed;
	const instance = {
		get_filter: () => ({
			set_value: async (value) => {
				cleared = value;
			},
		}),
		refresh: () => {
			refreshed = true;
		},
	};
	await report.filters.find((f) => f.fieldname === "from_date").on_change(instance);
	assert.equal(cleared, "");
	assert.equal(refreshed, true);
	assert.equal(instance._no_refresh, false);
});

test("currency clicks capture cell events and send exact box and value column", async () => {
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
		target: { closest: () => ({ dataset: { box: "14", field: "amount" } }) },
		preventDefault: () => stopped++,
		stopImmediatePropagation: () => stopped++,
	};
	await handlers.mousedown(event);
	assert.equal(stopped, 2);
	assert.equal(calls.length, 0);
	event.type = "click";
	await handlers.click(event);
	assert.equal(calls[0].args.box, "14");
	assert.equal(calls[0].args.fieldname, "amount");
	assert.ok(calls[0].method.endsWith(".transactions"));
});
