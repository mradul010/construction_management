const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("Project Name links retain Project IDs, escape names and preserve other formatting", () => {
	const observers = [];
	class ResizeObserverMock {
		constructor(callback) {
			this.callback = callback;
			this.disconnected = false;
			observers.push(this);
		}
		observe(target) {
			this.target = target;
		}
		disconnect() {
			this.disconnected = true;
		}
	}
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
		frappe, __: s => s, ResizeObserver: ResizeObserverMock,
		erpnext: { utils: { add_dimensions() {} } },
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
	assert.equal(report.get_datatable_options, undefined);

	const sequenceColumn = { id: "_rowIndex", colIndex: 0, width: 30 };
	const parentElement = {};
	const wrapper = { parentElement };
	const calls = [];
	report.after_datatable_render({
		wrapper,
		setDimensions() {
			calls.push("setDimensions");
			sequenceColumn.width = 30;
		},
		getColumns: () => [sequenceColumn],
		datamanager: {
			updateColumn: (index, changes) => {
				calls.push(["updateColumn", index, changes.width]);
				Object.assign(sequenceColumn, changes);
			},
		},
		columnmanager: {
			setColumnHeaderWidth: index => calls.push(["setColumnHeaderWidth", index]),
			setColumnWidth: index => calls.push(["setColumnWidth", index]),
		},
		style: {
			setStickyColumnStyle: () => calls.push("setStickyColumnStyle"),
			setBodyStyle: () => calls.push("setBodyStyle"),
		},
	});
	assert.equal(sequenceColumn.width, 40);
	assert.deepEqual(calls, [
		"setDimensions",
		["updateColumn", 0, 40],
		["setColumnHeaderWidth", 0],
		["setColumnWidth", 0],
		"setStickyColumnStyle",
		"setBodyStyle",
	]);
	assert.equal(observers[0].target, parentElement);

	observers[0].callback();
	assert.equal(sequenceColumn.width, 40);
	assert.equal(calls.filter(call => call === "setDimensions").length, 2);

	report.after_datatable_render({
		wrapper,
		setDimensions() {},
		getColumns: () => [sequenceColumn],
		datamanager: { updateColumn() {} },
		columnmanager: { setColumnHeaderWidth() {}, setColumnWidth() {} },
		style: { setStickyColumnStyle() {}, setBodyStyle() {} },
	});
	assert.equal(observers[0].disconnected, true);
});
