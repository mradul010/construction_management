const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
	path.join(__dirname, "../public/js/design_reference_filters.js"),
	"utf8"
);

function load(precedingScript = "") {
	const handlers = {};
	const locals = {};
	const frappe = {
		ui: { form: { on(doctype, events) {
			handlers[doctype] = { ...handlers[doctype], ...events };
		} } },
	};
	vm.runInNewContext(precedingScript + "\n" + script, { frappe, locals });
	return { handlers, locals };
}

test("loads after a form hook without a terminating semicolon", () => {
	// Frappe concatenates doctype_js hooks; CRM's Sales Order hook ends this way.
	const { handlers } = load('frappe.ui.form.on("Sales Order", { refresh() {} })');
	assert.equal(typeof handlers["Sales Order"].refresh, "function");
	assert.equal(typeof handlers["Sales Order"].setup, "function");
	assert.equal(typeof handlers["Sales Order Item"].drawing_revision, "function");
});

test("retains the IFC drawing revision query on Sales Order items", () => {
	const { handlers, locals } = load();
	locals["Sales Order Item"] = { row: { drawing: "DRAWING-1" } };
	let query;
	handlers["Sales Order"].setup({
		fields_dict: { items: {} },
		set_query(fieldname, tablefield, callback) {
			assert.equal(fieldname, "drawing_revision");
			assert.equal(tablefield, "items");
			query = callback;
		},
	});
	assert.deepEqual(JSON.parse(JSON.stringify(query({}, "Sales Order Item", "row"))), {
		filters: { ifc: 1, status: "Issued For Construction", drawing: "DRAWING-1" },
	});
});

test("retains IFC revision synchronization on Sales Order items", () => {
	const { handlers, locals } = load();
	const row = { drawing_revision: "REV-1", parentfield: "items" };
	locals["Sales Order Item"] = { row };
	const refreshed = [];
	handlers["Sales Order Item"].drawing_revision(
		{ refresh_field: (fieldname) => refreshed.push(fieldname) }, "Sales Order Item", "row"
	);
	assert.equal(row.ifc_revision, "REV-1");
	assert.deepEqual(refreshed, ["items"]);
});
