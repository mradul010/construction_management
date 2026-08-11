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
	if (!frm.doc.source_warehouse) {
		frappe.msgprint(__("Please select a Site Warehouse first."));
		return;
	}

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
			return { filters: { is_stock_item: 1, disabled: 0 } };
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
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Available Materials"), function () {
				smcGetAvailableMaterials(frm);
			});
		}
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), function () {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			});
		}
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
	},
});
