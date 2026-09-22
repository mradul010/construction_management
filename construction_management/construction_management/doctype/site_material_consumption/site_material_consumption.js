const SMC_METHOD =
	"construction_management.construction_management.doctype.site_material_consumption.site_material_consumption";

function smcNumber(value) {
	const parsed = parseFloat(value);
	return Number.isFinite(parsed) ? parsed : 0;
}

function smcRecalculateTotals(frm) {
	let totalQty = 0;
	let totalAmount = 0;
	(frm.doc.items || []).forEach((row) => {
		row.amount =
			smcNumber(row.qty) * smcNumber(row.conversion_factor || 1) * smcNumber(row.valuation_rate);
		totalQty += smcNumber(row.qty);
		totalAmount += smcNumber(row.amount);
	});
	frm.set_value("total_qty", totalQty);
	frm.set_value("total_amount", totalAmount);
	frm.refresh_field("items");
}

function smcUpdateIssueType(frm) {
	const itemCodes = (frm.doc.items || []).map((row) => row.item_code).filter(Boolean);
	const unique = [...new Set(itemCodes)];
	frm.set_value("type_of_issued", unique.length === 1 ? unique[0] : null);
}

function smcUpdateItemDetails(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code) return;

	frappe.call({
		method: `${SMC_METHOD}.get_consumption_item_details`,
		args: {
			item_code: row.item_code,
			source_warehouse: frm.doc.source_warehouse,
			company: frm.doc.company,
			project: frm.doc.project,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
			uom: row.uom,
		},
		callback: function (r) {
			const values = r.message || {};
			Object.keys(values).forEach((fieldname) => {
				frappe.model.set_value(cdt, cdn, fieldname, values[fieldname]);
			});
			frappe.model.set_value(
				cdt,
				cdn,
				"amount",
				smcNumber(row.qty) * smcNumber(values.conversion_factor || row.conversion_factor || 1) * smcNumber(values.valuation_rate),
			);
			smcRecalculateTotals(frm);
			smcUpdateIssueType(frm);
		},
	});
}

function smcRefreshItemBalances(frm) {
	(frm.doc.items || []).forEach((row) => {
		if (row.item_code) {
			smcUpdateItemDetails(frm, row.doctype, row.name);
		}
	});
}

function smcGetAvailableMaterials(frm) {
	frappe.call({
		method: `${SMC_METHOD}.get_available_materials`,
		args: {
			source_warehouse: frm.doc.source_warehouse,
			company: frm.doc.company,
			project: frm.doc.project,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
		},
		freeze: true,
		freeze_message: __("Getting available materials..."),
		callback: function (r) {
			const rows = r.message || [];
			const existing = new Set((frm.doc.items || []).map((row) => row.item_code).filter(Boolean));
			let added = 0;
			rows.forEach((material) => {
				if (existing.has(material.item_code)) return;
				const row = frm.add_child("items");
				Object.assign(row, material);
				existing.add(material.item_code);
				added += 1;
			});
			frm.refresh_field("items");
			smcRecalculateTotals(frm);
			frappe.show_alert({
				message: added ? __("Available materials added.") : __("No new available materials found."),
				indicator: added ? "green" : "orange",
			});
		},
	});
}

function smcGetReturnableItems(frm) {
	if (!frm.doc.return_against) {
		frappe.msgprint(__("Please select Return Against first."));
		return;
	}

	frappe.call({
		method: `${SMC_METHOD}.get_returnable_items`,
		args: {
			return_against: frm.doc.return_against,
			exclude_return: frm.is_new() ? null : frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Getting returnable items..."),
		callback: function (r) {
			const data = r.message || {};
			frm.clear_table("items");
			(data.items || []).forEach((item) => {
				const row = frm.add_child("items");
				Object.assign(row, item);
			});
			const updates = {};
			["company", "project", "source_warehouse", "cost_center"].forEach((fieldname) => {
				if (data[fieldname]) updates[fieldname] = data[fieldname];
			});
			if (Object.keys(updates).length) frm.set_value(updates);
			frm.refresh_field("items");
			smcRecalculateTotals(frm);
			smcUpdateIssueType(frm);
		},
	});
}

function smcRefreshActionButtons(frm) {
	if (frm.doc.docstatus !== 1 || frm.doc.transaction_type === "Material Return") return;

	frappe.call({
		method: `${SMC_METHOD}.get_stock_entry_action_status`,
		args: {
			name: frm.doc.name,
		},
		callback: function (r) {
			const status = r.message || {};

			if (status.can_create_stock_entry) {
				frm.add_custom_button(__("Stock Entry"), function () {
					frappe.call({
						method: `${SMC_METHOD}.create_stock_entry_from_consumption`,
						args: {
							name: frm.doc.name,
						},
						freeze: true,
						freeze_message: __("Creating Stock Entry..."),
						callback: function () {
							frappe.show_alert({
								message: __("Stock Entry created."),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				});
				return;
			}

			if (status.can_open_stock_entry && status.stock_entry) {
				frm.add_custom_button(__("Open Stock Entry"), function () {
					frappe.set_route("Form", "Stock Entry", status.stock_entry);
				});
				return;
			}

			if (status.can_return_material) {
				frm.add_custom_button(__("Return Material"), function () {
					frappe.call({
						method: `${SMC_METHOD}.make_return_stock_entry`,
						args: {
							name: frm.doc.name,
						},
						freeze: true,
						freeze_message: __("Preparing Return Stock Entry..."),
						callback: function (r) {
							frappe.model.sync(r.message);
							frappe.set_route("Form", r.message.doctype, r.message.name);
						},
					});
				});
			}

			if (status.can_view_stock_entry && status.stock_entry) {
				frm.add_custom_button(__("View Stock Entry"), function () {
					frappe.set_route("Form", "Stock Entry", status.stock_entry);
				});
			}
		},
	});
}

frappe.ui.form.on("Site Material Consumption", {
	setup: function (frm) {
		frm.set_query("project", function () {
			return {
				filters: frm.doc.company ? { company: frm.doc.company } : {},
			};
		});
		frm.set_query("source_warehouse", function () {
			const filters = { is_group: 0 };
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
		});
		frm.set_query("cost_center", function () {
			const filters = { is_group: 0 };
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
		});
		frm.set_query("item_code", "items", function () {
			return { filters: { disabled: 0 } };
		});
		frm.set_query("type_of_issued", function () {
			return { filters: { disabled: 0 } };
		});
		frm.set_query("return_against", function () {
			const filters = {
				docstatus: 1,
				transaction_type: "Material Issue",
			};
			if (frm.doc.company) filters.company = frm.doc.company;
			if (frm.doc.project) filters.project = frm.doc.project;
			return { filters };
		});
		frm.set_query("expense_account", "items", function () {
			const filters = { is_group: 0 };
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
		});
	},

	onload: function (frm) {
		if (frm.is_new() && !frm.doc.company) {
			frappe.db.get_single_value("Construction Settings", "default_company").then((company) => {
				if (company && !frm.doc.company) frm.set_value("company", company);
			});
		}
	},

	refresh: function (frm) {
		if (frm.doc.docstatus === 0 && frm.doc.transaction_type !== "Material Return") {
			frm.add_custom_button(__("Get Available Materials"), function () {
				smcGetAvailableMaterials(frm);
			});
		}
		if (frm.doc.docstatus === 0 && frm.doc.transaction_type === "Material Return") {
			frm.add_custom_button(__("Get Items from Original Consumption"), function () {
				smcGetReturnableItems(frm);
			});
		}
		smcRefreshActionButtons(frm);
	},

	transaction_type: function (frm) {
		if (frm.doc.transaction_type !== "Material Return") {
			frm.set_value("return_against", null);
		}
		frm.refresh();
	},

	return_against: function (frm) {
		if (!frm.doc.return_against) return;
		if (frm.doc.transaction_type !== "Material Return") {
			frm.set_value("transaction_type", "Material Return").then(() => smcGetReturnableItems(frm));
			return;
		}
		smcGetReturnableItems(frm);
	},

	project: function (frm) {
		if (!frm.doc.project) return;
		frappe.db.get_value("Project", frm.doc.project, ["company", "cost_center"]).then((r) => {
			const project = r.message || {};
			const updates = {};
			if (project.company && !frm.doc.company) updates.company = project.company;
			if (project.cost_center && !frm.doc.cost_center) updates.cost_center = project.cost_center;
			if (Object.keys(updates).length) frm.set_value(updates);
		});
	},

	employee: function (frm) {
		if (!frm.doc.employee) {
			frm.set_value("employee_name", null);
			frm.set_value("subcontractor_supplier", null);
			frm.set_value("subcontractor_supplier_name", null);
			return;
		}

		frappe.db
			.get_value("Employee", frm.doc.employee, ["employee_name", "subcontractor_supplier"])
			.then((r) => {
				const employee = r.message || {};
				frm.set_value("employee_name", employee.employee_name);
				if (employee.subcontractor_supplier) {
					frm.set_value("subcontractor_supplier", employee.subcontractor_supplier);
				}
			});
	},

	subcontractor_supplier: function (frm) {
		if (!frm.doc.subcontractor_supplier) {
			frm.set_value("subcontractor_supplier_name", null);
			return;
		}
		frappe.db.get_value("Supplier", frm.doc.subcontractor_supplier, "supplier_name").then((r) => {
			frm.set_value("subcontractor_supplier_name", r.message?.supplier_name);
		});
	},

	source_warehouse: function (frm) {
		smcRefreshItemBalances(frm);
	},

	posting_date: function (frm) {
		smcRefreshItemBalances(frm);
	},

	posting_time: function (frm) {
		smcRefreshItemBalances(frm);
	},

	validate: function (frm) {
		smcRecalculateTotals(frm);
		smcUpdateIssueType(frm);
	},
});

frappe.ui.form.on("Site Material Consumption Item", {
	item_code: smcUpdateItemDetails,
	uom: smcUpdateItemDetails,
	qty: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(
			cdt,
			cdn,
			"amount",
			smcNumber(row.qty) * smcNumber(row.conversion_factor || 1) * smcNumber(row.valuation_rate),
		);
		smcRecalculateTotals(frm);
		smcUpdateIssueType(frm);
	},
});
