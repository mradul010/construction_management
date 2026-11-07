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

test("GL view defaults without removing internal review actions", () => {
	const { report } = setup();
	assert.deepEqual(
		Array.from(report.filters, (f) => f.fieldname),
		["report_view", "company", "filing_period", "from_date", "to_date"]
	);
	assert.equal(report.filters[0].default, "General Ledger");
	const source = fs.readFileSync(`${__dirname}/uae_vat_201_return.js`, "utf8");
	for (const text of [
		"open_review",
		"Approve Classification",
		"Generate Review Suggestions",
		"classification_status",
		"review_endpoint",
		"data-review-source",
		"Resolve VAT Exception",
		"Approve Override",
		"Needs Attention",
	])
		assert.ok(!source.includes(text));
	assert.ok(source.includes('report.raw_data?.vat201_context'));
	for (const tab of ["Sales", "Purchases", "Journal Entries"])
		assert.ok(source.includes(`"${tab}"`));
});

test("recovery workflow and filing register are limited to accounting managers", () => {
 const source = fs.readFileSync(`${__dirname}/uae_vat_201_return.js`, "utf8");
 for (const field of ["recovery_percent", "supporting_reference", "expected_fingerprint", "Review VAT Treatment", "VAT 201 Filing", "VAT 201 Payment"])
  assert.ok(source.includes(field));
 assert.ok(source.includes('["Accounts Manager", "System Manager"].includes(role)'));
});

test("formatter preserves numeric values and distinguishes pending from nil", () => {
	const { report } = setup();
	const data = { _box: true, box: "9", vat_amount: 0 };
	const col = { fieldname: "vat_amount", fieldtype: "Currency" };
	assert.ok(
		report.formatter(0, {}, col, data, () => "AED 0.00").includes('data-field="vat_amount"')
	);
	assert.equal(data.vat_amount, 0);
	data.completeness = {vat_amount: {provisional: true, reasons: ["Purchase journal recovery unresolved"]}};
	assert.ok(
		report.formatter(0, {}, col, data, () => "AED 0.00").includes("Provisional known subtotal")
	);
	assert.ok(report.formatter(0, {}, col, data, () => "AED 0.00").includes("AED 0.00"));
	assert.ok(!report.formatter(0, {}, {fieldname: "adjustment", fieldtype: "Currency"}, data, () => "AED 0.00").includes("Provisional"));
	assert.ok(report.formatter(-50, {}, col, data, () => "AED -50.00").includes("text-danger"));
});

test("native row numbers and fixed layout preserve other datatable options", () => {
	const {report} = setup();
	const options = report.get_datatable_options({cellHeight: 33, inlineFilters: true});
	assert.equal(options.serialNoColumn, true);
	assert.equal(options.layout, "fixed");
	assert.equal(options.cellHeight, 33);
	assert.equal(options.inlineFilters, true);
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
	assert.deepEqual(buttons, ["View Details", "Excel", "PDF", "Detailed Audit (Excel)", "Detailed Audit (CSV)"]);
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

test("transaction columns show source taxable and recorded VAT independently of zero claims", async () => {
	const { report, frappe } = setup();
	let html;
	frappe.call = async () => ({
		message: [
			{
				voucher_type: "Purchase Invoice",
				voucher_no: "ACC-PINV-2026-00293-1",
				base: 1557.5,
				raw_vat: 77.88,
				invoice_taxable_amount: 1557.5,
				recorded_vat_amount: 77.88,
				recoverable_vat_amount: 0,
				amount: 0,
				vat_amount: 0,
				adjustment: 0,
				box: null,
				treatment: "No input VAT claimed",
			},
			{
				voucher_type: "Purchase Invoice",
				voucher_no: "ACC-PINV-2026-00210-1",
				base: 323,
				raw_vat: 16.15,
				invoice_taxable_amount: 323,
				recorded_vat_amount: 16.15,
				recoverable_vat_amount: 0,
				amount: 0,
				vat_amount: 0,
				adjustment: 0,
				box: null,
				treatment: "No input VAT claimed",
			},
		],
	});
	frappe.ui.Dialog = class {
		constructor() {
			this.fields_dict = { transactions: { $wrapper: { html: (value) => (html = value) } } };
		}
		show() {}
	};
	let handler;
	report.after_datatable_render({
		wrapper: {
			contains: () => true,
			addEventListener: (type, fn) => {
				handler = fn;
			},
		},
	});
	await handler({
		type: "click",
		target: { closest: () => ({ dataset: { box: "9", field: "vat_amount" } }) },
		preventDefault() {},
		stopImmediatePropagation() {},
	});
	for (const label of [
		"Date",
		"Voucher Number",
		"Party",
		"Taxable Amount",
		"VAT Amount",
		"VAT Treatment",
		"VAT Box",
		"Remarks",
	])
		assert.ok(html.includes(`<th>${label}</th>`));
	const rows = [...html.matchAll(/<tr>([\s\S]*?)<\/tr>/g)]
		.slice(1)
		.map((match) =>
			[...match[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((cell) => cell[1])
		);
	assert.deepEqual(
		rows.map((row) => row.slice(3, 5)),
		[
			["AED 1557.5", "AED 77.88"],
			["AED 323", "AED 16.15"],
		]
	);
	assert.equal(rows[0][6], "");
	assert.equal(rows[0].length, 8);
	assert.ok(html.includes("No input VAT claimed"));
});

test("unknown source base is not replaced with a reviewed claim allocation", async () => {
	const { report, frappe } = setup();
	let html;
	frappe.call = async () => ({
		message: [
			{
				voucher_type: "Purchase Invoice",
				voucher_no: "PI",
				invoice_taxable_amount: null,
				recorded_vat_amount: 50,
				recoverable_vat_amount: 20,
				amount: 1000,
				vat_amount: 20,
				box: "9",
			},
		],
	});
	frappe.ui.Dialog = class {
		constructor() {
			this.fields_dict = { transactions: { $wrapper: { html: (value) => (html = value) } } };
		}
		show() {}
	};
	let handler;
	report.after_datatable_render({
		wrapper: {
			contains: () => true,
			addEventListener: (type, fn) => {
				handler = fn;
			},
		},
	});
	await handler({
		type: "click",
		target: { closest: () => ({ dataset: { box: "9", field: "amount" } }) },
		preventDefault() {},
		stopImmediatePropagation() {},
	});
	const cells = [...html.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((cell) => cell[1]);
	assert.equal(cells[3], "Not specified");
	assert.equal(cells[6], "9");
	assert.equal(cells.length, 8);
	assert.ok(!html.includes("AED 1000"));
});

test("manager review calls the correct backend and preserves explicit zero recovery", async () => {
	const { report, frappe } = setup();
	const buttons = new Map();
	const dialogs = [];
	const calls = [];
	frappe.user_roles = ["Accounts Manager"];
	frappe.ui.Dialog = class {
		constructor(options) { this.options = options; dialogs.push(this); }
		show() {}
		hide() {}
		set_values() {}
		set_secondary_action() {}
		set_secondary_action_label() {}
		get_values() { return {box: "9", tax_date: "2026-06-01", recovery_confirmed: 1, recovery_percent: 0, reason: "Reviewed exclusion", supporting_reference: "TEST"}; }
	};
	frappe.call = async (args) => {
		calls.push(args);
		if (args.method.endsWith("report_context")) return {message: {details: [{voucher_type: "Purchase Invoice", voucher_no: "TEST-PI", source_row: "TEST-TAX", raw_vat: 50}]}};
		if (args.method.endsWith("review_source")) return {message: {records: [], decision_fingerprint: "CURRENT-EVIDENCE"}};
		return {message: {status: "Approved"}};
	};
	const view = {page: {add_inner_button: (label, action) => buttons.set(label, action)}, get_filter_value: () => null, get_filter_values: () => ({company: "TEST"}), refresh() {}};
	await report.onload(view);
	await buttons.get("Review VAT Treatment")();
	await dialogs[0].options.primary_action({source: "0"});
	await dialogs[1].options.primary_action();
	const decision = calls.at(-1);
	assert.equal(decision.method, "construction_management.construction_management.report.uae_vat_201_return.review.decide");
	assert.equal(decision.args.values.recovery_percent, 0);
	assert.equal(decision.args.expected_fingerprint, "CURRENT-EVIDENCE");
	assert.equal(decision.args.action, "Approve");
});
