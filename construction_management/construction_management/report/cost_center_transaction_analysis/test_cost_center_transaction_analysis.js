// Run with node --test path/to/this/file.js.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
	const calls = [];
	const frappe = {
		query_reports: {},
		defaults: { get_user_default: () => "QATRA BUILDING CONTG LLC" },
		datetime: { get_today: () => "2026-10-20", add_months: () => "2026-09-20" },
		utils: { escape_html: (s) => s.replaceAll("&", "&amp;").replaceAll('"', "&quot;") },
		query_report: { get_filter_values: () => ({ project: "PROJ-0016" }) },
		call: async (args) => {
			calls.push(args);
			return { message: { filters: { cost_center: args.args.cost_center, project: "PROJ-0016", account: "", gl_entry: args.args.gl_entry } } };
		},
		set_route: (...route) => calls.push(route),
	};
	vm.runInNewContext(fs.readFileSync(`${__dirname}/cost_center_transaction_analysis.js`, "utf8"), {
		frappe, __: (s) => s, erpnext: { utils: { add_dimensions() {} } },
	});
	return { report: frappe.query_reports["Cost Center Transaction Analysis"], frappe, calls };
}

test("formatter preserves currency markup, numeric data and zero; skips total rows", () => {
	const { report } = setup();
	for (const amount of [21120, 0, -100]) {
		const data = { cost_center: "Scaffolding & Forms - QBC", cost_spent: amount };
		const markup = report.formatter(amount, {}, { fieldname: "cost_spent" }, data, () => "AED 21,120.00");
		assert.ok(markup.includes("AED 21,120.00</a>"));
		assert.ok(markup.includes("Scaffolding &amp; Forms - QBC"));
		assert.equal(data.cost_spent, amount);
	}
	assert.equal(report.formatter(0, {}, { fieldname: "cost_spent" }, {}, () => "0.00"), "0.00");
	assert.equal(report.formatter(1, {}, { fieldname: "total_debit" }, { cost_center: "X" }, () => "1.00"), "1.00");
});

test("click routes all requested centers with filters and stops cell handling", async () => {
	for (const center of ["Concrete - QBC", "Steel - QBC", "Scaffolding & Forms - QBC", "Tools & Consumables - QBC"]) {
		const { report, frappe, calls } = setup();
		let handler;
		let removed = 0;
		const wrapper = {
			contains: () => true,
			addEventListener: (name, callback, capture) => { assert.equal(capture, true); handler = callback; },
			removeEventListener: () => removed++,
		};
		report.after_datatable_render({ wrapper });
		report.after_datatable_render({ wrapper });
		assert.equal(removed, 3);
		let prevented = false, stopped = false;
		const event = {
			type: "mousedown",
			target: { closest: () => ({ dataset: { costCenter: center } }) },
			preventDefault: () => prevented = true,
			stopImmediatePropagation: () => stopped = true,
		};
		await handler(event);
		assert.ok(prevented && stopped);
		assert.equal(calls.length, 0);
		event.type = "click";
		await handler(event);
		assert.ok(prevented && stopped);
		assert.equal(calls[0].args.cost_center, center);
		assert.equal(calls[0].args.filters.project, "PROJ-0016");
		assert.ok(calls[0].method.endsWith(".get_expense_detail_filters"));
		assert.equal(calls[0].args.gl_entry, "");
		assert.deepEqual(calls[1], ["query-report", "Cost Center Expense Details"]);
		assert.equal(frappe.route_options.cost_center, center);
		assert.equal(frappe.route_options.account, "");
		event.target.closest = () => ({ dataset: { costCenter: center, glEntry: "GLE-1" } });
		await handler(event);
		assert.equal(frappe.route_options.gl_entry, "GLE-1");
	}
});

test("expense details restores the original parent filters and uses standard numeric export", () => {
	const { frappe } = setup();
	vm.runInNewContext(fs.readFileSync(`${__dirname}/../cost_center_expense_details/cost_center_expense_details.js`, "utf8"), {
		frappe, __: s => s, erpnext: { utils: { add_dimensions() {} } },
	});
	const report = frappe.query_reports["Cost Center Expense Details"];
	let back;
	report.onload({
		page: { add_inner_button: (label, callback) => back = callback },
		get_filter_value: () => JSON.stringify({ company: "QBC", cost_center: "Group - QBC", include_child_cost_centers: 1, view_mode: "Transaction Details" }),
	});
	back();
	assert.equal(frappe.route_options.cost_center, "Group - QBC");
	assert.equal(frappe.route_options.include_child_cost_centers, 1);
	assert.equal(frappe.route_options.view_mode, "Transaction Details");
	assert.equal(report.filters.find(f => f.fieldname === "account").fieldtype, "Link");
	assert.equal(report.formatter(10, {}, { fieldname: "net_cost" }, {}, () => "AED 10.00"), "AED 10.00");
});

test("installed Frappe router clears stale GL accounts before consecutive refreshes", async () => {
	const path = require("node:path");
	const bench = path.resolve(__dirname, "../../../../../..");
	const frappe = {
		ui: { form: { ControlData: class {} } },
		views: { BaseList: class {} },
		query_reports: {}, standard_pages: {}, provide() {},
		run_serially: async (steps) => { for (const step of steps) await step(); },
	};
	const context = vm.createContext({ frappe, window: {}, DataTable: class {}, CSS: { escape: s => s } });
	vm.runInContext(fs.readFileSync(`${bench}/apps/frappe/frappe/public/js/frappe/form/controls/multiselect_list.js`, "utf8"), context);
	vm.runInContext(fs.readFileSync(`${bench}/apps/frappe/frappe/public/js/frappe/views/reports/query_report.js`, "utf8").replace('import DataTable from "frappe-datatable";', ""), context);
	const account = Object.create(frappe.ui.form.ControlMultiSelectList.prototype);
	Object.assign(account, {
		df: { fieldname: "account" }, values: ["Previously Selected - QBC"],
		$list_wrapper: { find: () => ({ toggleClass() {} }) },
		parse_validate_and_set_in_model() {}, update_status() {}, update_selected_values() {},
	});
	const ledger = Object.create(frappe.views.QueryReport.prototype);
	ledger.filters = [account];
	// Passing an empty string does not clear this v16 control.
	await ledger.set_route_filters({ account: "" });
	assert.equal(account.values.length, 1);
	for (const center of ["Concrete - QBC", "Steel - QBC", "Tools & Consumables - QBC", "Scaffolding & Forms - QBC"]) {
		await ledger.set_route_filters({ account: "[]", cost_center: [center] });
		assert.equal(account.values.length, 0);
	}
	await ledger.set_route_filters({ account: ["Explicit Account - QBC"] });
	assert.equal(account.values[0], "Explicit Account - QBC");
	await ledger.set_route_filters({ account: "[]" });
	assert.equal(account.values.length, 0);
});
