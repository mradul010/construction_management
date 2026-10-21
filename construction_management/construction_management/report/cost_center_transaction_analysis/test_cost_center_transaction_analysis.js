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
			return { message: { filters: { cost_center: [args.args.cost_center], project: ["PROJ-0016"] }, warnings: [] } };
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
	for (const center of ["Concrete - QBC", "Scaffolding & Forms - QBC", "Tools & Consumables - QBC"]) {
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
		assert.deepEqual(calls[1], ["query-report", "General Ledger"]);
		assert.equal(frappe.route_options.cost_center[0], center);
	}
});
