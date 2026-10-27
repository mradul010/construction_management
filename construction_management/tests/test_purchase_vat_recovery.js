const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function setup(roles = ["Accounts Manager"]) {
	let handler, dialog;
	const calls = [];
	const frappe = {
		ui: {form: {on: (doctype, handlers) => handler = handlers}, Dialog: class {constructor(options) {dialog = options;} show() {} hide() {}}},
		user_roles: roles, msgprint: message => calls.push(message), call: async args => calls.push(args),
	};
	vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../public/js/purchase_vat_recovery.js"), "utf8"), {frappe, __: value => value});
	const frm = {doc: {name: "PI", docstatus: 1, recoverable_standard_rated_expenses: 0, modified: "2026-10-27 12:00:00"},
		perm: [{write: 1}], set_df_property() {}, is_dirty: () => false, reload_doc: async () => calls.push("reload"),
		add_custom_button(label, action) {this.action = action;}};
	return {handler, frm, calls, dialog: () => dialog};
}

test("submitted manager action uses saved amount including zero and a required reason", async () => {
	const env = setup();
	env.handler.refresh(env.frm);
	env.frm.action();
	const dialog = env.dialog();
	assert.equal(dialog.fields[0].fieldtype, "Currency");
	assert.equal(dialog.fields[0].default, 0);
	assert.equal(dialog.fields[1].reqd, 1);
	await dialog.primary_action({amount: 77.88, reason: "Confirmed full recovery"});
	assert.equal(env.calls[0].args.amount, 77.88);
	assert.equal(env.calls[0].args.modified, env.frm.doc.modified);
	assert.equal(env.calls[0].args.reason, "Confirmed full recovery");
	assert.equal(env.calls[1], "reload");
});

test("no action for drafts, nonmanagers or read-only users", () => {
	for (const kind of ["draft", "nonmanager", "readonly"]) {
		const env = setup(kind === "nonmanager" ? ["Accounts User"] : ["Accounts Manager"]);
		if (kind === "draft") env.frm.doc.docstatus = 0;
		if (kind === "readonly") env.frm.perm = [{write: 0}];
		env.handler.refresh(env.frm);
		assert.equal(env.frm.action, undefined);
	}
});

test("dirty documents must be saved or reloaded first", () => {
	const env = setup();
	env.frm.is_dirty = () => true;
	env.handler.refresh(env.frm);
	env.frm.action();
	assert.equal(env.dialog(), undefined);
	assert.equal(env.calls.length, 1);
});
