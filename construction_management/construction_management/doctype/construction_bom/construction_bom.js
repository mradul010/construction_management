frappe.ui.form.on("Construction BOM", {
	setup(frm) {
		frm.set_query("boq", () => {
			const filters = {};
			if (frm.doc.project) {
				filters.project = frm.doc.project;
			}
			return { filters };
		});
	},

	project(frm) {
		if (frm.doc.boq) {
			frappe.db.get_value("BOQ", frm.doc.boq, "project").then((response) => {
				const boqProject = response && response.message && response.message.project;
				if (boqProject && boqProject !== frm.doc.project) {
					frm.set_value("boq", "");
				}
			});
		}
	},

	boq(frm) {
		if (!frm.doc.boq || frm.doc.project) {
			return;
		}

		frappe.db.get_value("BOQ", frm.doc.boq, "project").then((response) => {
			const boqProject = response && response.message && response.message.project;
			if (boqProject) {
				frm.set_value("project", boqProject);
			}
		});
	},

	validate(frm) {
		sync_construction_bom_items(frm);
	},

	items_add(frm) {
		sync_construction_bom_items(frm);
	},

	items_remove(frm) {
		sync_construction_bom_items(frm);
	},

	items_move(frm) {
		sync_construction_bom_items(frm);
	},
});

frappe.ui.form.on("Construction BOM Item", {
	mark_no(frm, cdt, cdn) {
		ensure_construction_bom_item(cdt, cdn, "mark_no", "item_code");
	},

	mark_item(frm, cdt, cdn) {
		ensure_construction_bom_item(cdt, cdn, "mark_item", "mark_item_item_code");
	},

	qty(frm, cdt, cdn) {
		update_construction_bom_item(frm, cdt, cdn);
	},

	unit_weight(frm, cdt, cdn) {
		update_construction_bom_item(frm, cdt, cdn);
		ensure_construction_bom_item(cdt, cdn, "mark_no", "item_code");
		ensure_construction_bom_item(cdt, cdn, "mark_item", "mark_item_item_code");
	},
});

function sync_construction_bom_items(frm) {
	(frm.doc.items || []).forEach((row) => {
		const values = get_construction_bom_weight_values(row);
		row.serial_no = row.idx;
		row.total_weight = values.total_weight;
		row.total_wt_mt = values.total_wt_mt;
	});
	frm.refresh_field("items");
}

function update_construction_bom_item(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const values = get_construction_bom_weight_values(row);
	frappe.model.set_value(cdt, cdn, "serial_no", row.idx);
	frappe.model.set_value(cdt, cdn, "total_weight", values.total_weight);
	frappe.model.set_value(cdt, cdn, "total_wt_mt", values.total_wt_mt);
}

function get_construction_bom_weight_values(row) {
	const totalWeight = flt(row.qty) * flt(row.unit_weight);
	return {
		total_weight: flt(totalWeight, 2),
		total_wt_mt: flt(totalWeight / 1000, 4),
	};
}

function ensure_construction_bom_item(cdt, cdn, sourceField, targetField) {
	const row = locals[cdt][cdn];
	const itemValue = (row[sourceField] || "").trim();
	if (!itemValue) {
		frappe.model.set_value(cdt, cdn, targetField, "");
		return;
	}

	const signatureField = `__last_${targetField}_sync_signature`;
	const signature = `${itemValue}::${row.unit_weight || ""}`;
	if (row[signatureField] === signature && row[targetField]) {
		return;
	}
	row[signatureField] = signature;

	frappe.call({
		method: "construction_management.construction_activity.item_sync.ensure_item_for_mark",
		args: {
			mark_no: itemValue,
			unit_weight: row.unit_weight,
		},
		callback(r) {
			if (r.message && r.message.item) {
				frappe.model.set_value(cdt, cdn, targetField, r.message.item);
			}
		},
	});
}
