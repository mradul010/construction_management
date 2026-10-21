const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("Project Name links retain Project IDs, escape names and preserve other formatting", () => {
	const frappe = {
		query_reports: {},
		defaults: { get_user_default() {} },
		datetime: { get_today() {}, add_months() {} },
		utils: {
			escape_html: s => s.replaceAll("&", "&amp;").replaceAll("<", "&lt;"),
			get_form_link: (doctype, name, html, label) => `<a href="/desk/project/${name}">${label}</a>`,
		},
	};
	vm.runInNewContext(fs.readFileSync(`${__dirname}/cost_center_expense_details.js`, "utf8"), {
		frappe, __: s => s, erpnext: { utils: { add_dimensions() {} } },
	});
	const report = frappe.query_reports["Cost Center Expense Details"];
	const format = (value, fieldname, data) => report.formatter(value, {}, { fieldname }, data, () => "default");
	assert.equal(format("Emerald Hills Villa 95", "project_name", { project: "PROJ-0015" }),
		'<a href="/desk/project/PROJ-0015">Emerald Hills Villa 95</a>');
	assert.ok(format("Villa <95> & Annex", "project_name", { project: "PROJ-0015" }).includes("Villa &lt;95> &amp; Annex"));
	assert.ok(format(null, "project_name", { project: "PROJ-0016" }).endsWith(">PROJ-0016</a>"));
	assert.equal(format(null, "project_name", {}), "default");
	assert.equal(format(6000, "net_cost", {}), "default");
	assert.equal(report.filters.find(f => f.fieldname === "project").options, "Project");
	const options = report.get_datatable_options({ showTotalRow: true, cellHeight: 33, layout: "fluid" });
	assert.equal(options.layout, "fixed");
	assert.equal(options.cellHeight, 64);
	assert.equal(options.showTotalRow, true);
	const styles = [];
	report.after_datatable_render({
		datamanager: { getColumns: () => [
			{ id: "project_name", colIndex: 1 }, { id: "cost_center", colIndex: 2 },
			{ id: "voucher_no", colIndex: 8 }, { id: "remarks", colIndex: 9 },
			{ id: "debit", colIndex: 4 },
		] },
		style: { setStyle: (selector, rules) => styles.push({ selector, rules }) },
	});
	assert.equal(styles.length, 5);
	assert.equal(styles[0].rules.whiteSpace, "normal");
	assert.equal(styles[0].rules.lineHeight, "20px");
	assert.equal(styles[0].rules.boxSizing, "border-box");
	assert.equal(styles[3].rules.overflow, "auto");
	assert.ok(styles[0].selector.includes(":not(.dt-row-header):not(.dt-row-filter)"));
	assert.equal(styles[4].rules.fontWeight, "bold");
});
