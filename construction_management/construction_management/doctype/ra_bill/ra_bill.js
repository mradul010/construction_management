const boqItemLabels = {};
const boqCategoryLabels = {};

const RA_BILL_METHOD =
	"construction_management.construction_management.doctype.ra_bill.ra_bill";

frappe.form.link_formatters["BOQ Item"] = function (value, doc) {
	if (!value) return "";
	if (doc && doc.item_name && (doc.boq_item === value || doc.name === value)) {
		return doc.item_name;
	}
	return boqItemLabels[value] || value;
};

frappe.form.link_formatters["BOQ Category"] = function (value, doc) {
	if (!value) return "";
	if (doc && doc.name === value && doc.category_name) {
		return doc.category_name;
	}
	return boqCategoryLabels[value] || value;
};

function getNumber(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

function clampPercent(value) {
	return Math.max(0, Math.min(100, getNumber(value)));
}

function formatNumber(value, digits = 2) {
	return getNumber(value).toLocaleString("en-AE", {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits,
	});
}

function showStandardItemsGrid(frm) {
	$(frm.wrapper).find("#ra-bill-custom-items-grid").remove();
	if (frm.fields_dict.items && frm.fields_dict.items.$wrapper) {
		frm.fields_dict.items.$wrapper.show();
	}
}

function isSettingChildValues(frm, cdn) {
	return Boolean(frm._ra_bill_setting_child_values && frm._ra_bill_setting_child_values[cdn]);
}

function childFieldExists(cdt, fieldname) {
	return Boolean(frappe.meta.get_docfield(cdt, fieldname));
}

function setChildValues(frm, cdt, cdn, values) {
	frm._ra_bill_setting_child_values = frm._ra_bill_setting_child_values || {};
	frm._ra_bill_setting_child_values[cdn] = true;

	const setters = Object.keys(values)
		.filter((fieldname) => childFieldExists(cdt, fieldname))
		.map((fieldname) =>
			Promise.resolve(frappe.model.set_value(cdt, cdn, fieldname, values[fieldname])),
		);

	return Promise.all(setters)
		.then(() => {
			delete frm._ra_bill_setting_child_values[cdn];
			frm.refresh_field("items");
		})
		.catch((error) => {
			delete frm._ra_bill_setting_child_values[cdn];
			throw error;
		});
}

function getCurrentWorkPercent(row) {
	if (getNumber(row.work_percent)) {
		return getNumber(row.work_percent);
	}

	const boqQty = getNumber(row.boq_qty);
	if (boqQty) {
		return (getNumber(row.current_qty) / boqQty) * 100;
	}
	return 0;
}

function getRowTotals(row, workPercent) {
	const pct = clampPercent(workPercent);
	const boqQty = getNumber(row.boq_qty);
	const boqRate = getNumber(row.boq_rate);
	const prevQty = getNumber(row.prev_cumulative_qty);
	const currentQty = boqQty ? (boqQty * pct) / 100 : 0;

	return {
		work_percent: pct,
		current_qty: currentQty,
		cumulative_qty: prevQty + currentQty,
		current_amount: currentQty * boqRate,
	};
}

function getRowTotalsFromCurrentQty(row) {
	const currentQty = getNumber(row.current_qty);
	const boqQty = getNumber(row.boq_qty);
	const boqRate = getNumber(row.boq_rate);
	const prevQty = getNumber(row.prev_cumulative_qty);

	return {
		work_percent: boqQty ? (currentQty / boqQty) * 100 : 0,
		current_qty: currentQty,
		cumulative_qty: prevQty + currentQty,
		current_amount: currentQty * boqRate,
	};
}

function clearItemDetailFields(frm, cdt, cdn, options = {}) {
	const values = {
		item_name: "",
		boq_qty: 0,
		boq_rate: 0,
		uom: "Nos",
		work_percent: 0,
		current_qty: 0,
		cumulative_qty: getNumber(locals[cdt][cdn].prev_cumulative_qty),
		current_amount: 0,
	};

	if (!options.keep_sub_category) {
		values.sub_category = "";
	}
	if (!options.keep_boq_item) {
		values.boq_item = "";
	}

	return setChildValues(frm, cdt, cdn, values).then(() => frm.trigger("recalculate_totals"));
}

function clearDuplicateBoqItemFields(frm, cdt, cdn) {
	return setChildValues(frm, cdt, cdn, {
		boq_item: "",
		item_name: "",
		boq_qty: 0,
		boq_rate: 0,
		uom: "",
		work_percent: 0,
		current_qty: 0,
		cumulative_qty: getNumber(locals[cdt][cdn].prev_cumulative_qty),
		current_amount: 0,
	}).then(() => frm.trigger("recalculate_totals"));
}

function hasDuplicateBoqItem(frm, row) {
	if (!row || !row.boq_item) return false;

	return (frm.doc.items || []).some(
		(item) => item.name !== row.name && item.boq_item === row.boq_item,
	);
}

function rejectDuplicateBoqItem(frm, cdt, cdn) {
	frappe.msgprint({
		title: __("Duplicate Item Not Allowed"),
		indicator: "red",
		message: __(
			"This BOQ Item is already selected in this RA Bill. Please update the existing row instead of adding it again.",
		),
	});

	return clearDuplicateBoqItemFields(frm, cdt, cdn);
}

function cacheCategoryLabel(category) {
	if (!category || boqCategoryLabels[category]) return Promise.resolve();

	return frappe.db
		.get_value("BOQ Category", category, "category_name")
		.then((r) => {
			if (r.message) {
				boqCategoryLabels[category] = r.message.category_name || category;
			}
		});
}

function hydrateBoqLabels(frm) {
	(frm.doc.items || []).forEach((row) => {
		if (row.boq_item && row.item_name) {
			boqItemLabels[row.boq_item] = row.item_name;
		}
		if (row.category_name) {
			cacheCategoryLabel(row.category_name);
		}
		if (row.sub_category) {
			cacheCategoryLabel(row.sub_category);
		}
	});

	if (frm.ra_bill_load_boq_context) {
		frm.ra_bill_load_boq_context().then(() => frm.refresh_field("items"));
	}
}

function getParentCategoryFromSubcategory(category) {
	if (!category) return Promise.resolve("");

	return frappe.db
		.get_value("BOQ Category", category, ["category_name", "parent_node"])
		.then((r) => {
			const categoryInfo = r.message || {};
			if (categoryInfo.category_name) {
				boqCategoryLabels[category] = categoryInfo.category_name;
			}
			return categoryInfo.parent_node || "";
		});
}

async function setBoqItemDetails(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.boq_item) return Promise.resolve();

	if (hasDuplicateBoqItem(frm, row)) {
		return rejectDuplicateBoqItem(frm, cdt, cdn);
	}

	const doc = await frappe.db.get_doc("BOQ Item", row.boq_item);
	console.log("Fetched BOQ Item full doc:", doc);
	console.log("Applying BOQ Item to RA Bill row:", doc);

	if (!doc) {
		frappe.msgprint("Unable to fetch BOQ Item details.");
		return Promise.resolve();
	}

	const qty = getNumber(doc.qty || doc.quantity || 0);
	const rate = getNumber(doc.unit_rate || doc.rate || doc.unit_cost || 0);
	const uom = doc.uom || doc.stock_uom || "Nos";
	const itemName = doc.item_name || doc.item || row.boq_item;
	const subCategory = doc.boq_category || "";
	const parentCategoryFromTree = await getParentCategoryFromSubcategory(subCategory);
	const parentCategory = parentCategoryFromTree || doc.boq_parent_category || row.category_name || "";
	const workPercent = getCurrentWorkPercent(row);
	const values = {
		item_name: itemName,
		boq_qty: qty,
		boq_rate: rate,
		uom: uom,
		sub_category: subCategory || row.sub_category || "",
		category_name: parentCategory || row.category_name || "",
		...getRowTotals(
			{
				...row,
				boq_qty: qty,
				boq_rate: rate,
			},
			workPercent,
		),
	};

	boqItemLabels[row.boq_item] = itemName;
	if (subCategory) {
		cacheCategoryLabel(subCategory);
	}
	if (parentCategory) {
		cacheCategoryLabel(parentCategory);
	}

	await setChildValues(frm, cdt, cdn, values);
	frm.trigger("recalculate_totals");
	console.log("RA Bill row after BOQ item apply:", locals[cdt][cdn]);
}

frappe.ui.form.on("RA Bill", {
	setup: function (frm) {
		frm.set_query("boq", function () {
			return {
				filters: {
					project: frm.doc.project,
					docstatus: 1,
				},
			};
		});

		frm.set_query("category_name", "items", function () {
			return {
				query: `${RA_BILL_METHOD}.search_ra_bill_categories`,
				filters: {
					boq: frm.doc.boq,
				},
			};
		});

		frm.set_query("sub_category", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return {
				query: `${RA_BILL_METHOD}.search_ra_bill_subcategories`,
				filters: {
					boq: frm.doc.boq,
					category: row.category_name,
				},
			};
		});

		frm.set_query("boq_item", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn] || {};
			const selected_items = (frm.doc.items || [])
				.filter((item) => item.name !== row.name && item.boq_item)
				.map((item) => item.boq_item);

			return {
				query: `${RA_BILL_METHOD}.search_boq_items_for_ra_bill`,
				filters: {
					boq: frm.doc.boq,
					category: row.category_name,
					subcategory: row.sub_category,
					exclude_items: selected_items,
					current_ra_bill: frm.doc.name,
				},
			};
		});

		frm.ra_bill_format_number = formatNumber;
		frm.ra_bill_apply_selected_boq_item = async function (cdt, cdn) {
			return setBoqItemDetails(frm, cdt, cdn);
		};

		frm.ra_bill_load_boq_context = function () {
			if (!frm.doc.boq) {
				frm._ra_bill_context_boq = null;
				return Promise.resolve();
			}

			if (frm._ra_bill_context_boq === frm.doc.boq) {
				return Promise.resolve();
			}

			return frappe.db
				.get_list("BOQ Item", {
					filters: {
						parent: frm.doc.boq,
						parenttype: "BOQ",
						parentfield: "items",
					},
					fields: ["name", "boq_category", "item", "item_name"],
					limit: 1000,
					order_by: "idx asc",
				})
				.then((items) => {
					const categoryNames = [
						...new Set((items || []).map((item) => item.boq_category).filter(Boolean)),
					];

					(items || []).forEach((item) => {
						boqItemLabels[item.name] = item.item_name || item.item || item.name;
					});

					if (!categoryNames.length) {
						frm._ra_bill_context_boq = frm.doc.boq;
						return [];
					}

					return frappe.db
						.get_list("BOQ Category", {
							filters: [["name", "in", categoryNames]],
							fields: ["name", "category_name", "parent_node"],
							limit: 1000,
						})
						.then((subcategories) => {
							const parentNames = [
								...new Set(
									(subcategories || [])
										.map((category) => category.parent_node)
										.filter(Boolean),
								),
							];
							const parentPromise = parentNames.length
								? frappe.db.get_list("BOQ Category", {
										filters: [["name", "in", parentNames]],
										fields: ["name", "category_name"],
										limit: 1000,
								  })
								: Promise.resolve([]);

							return parentPromise.then((parents) => {
								[...(subcategories || []), ...(parents || [])].forEach((category) => {
									boqCategoryLabels[category.name] =
										category.category_name || category.name;
								});
								frm._ra_bill_context_boq = frm.doc.boq;
							});
						});
				});
		};
	},

	refresh: function (frm) {
		showStandardItemsGrid(frm);
		hydrateBoqLabels(frm);

		if (frm.doc.status === "Submitted" && frm.doc.docstatus === 1) {
			frm.add_custom_button(
				"Approve",
				function () {
					frappe.confirm("Are you sure you want to approve this RA Bill?", function () {
						frappe.call({
							method: "approve",
							doc: frm.doc,
							freeze: true,
							freeze_message: "Approving RA Bill...",
							callback: function () {
								frm.reload_doc();
								frappe.show_alert(
									{
										message: "RA Bill Approved",
										indicator: "green",
									},
									3,
								);
							},
							error: function (err) {
								frappe.dom.unfreeze();
								console.error(err);
							},
						});
					});
				},
				"Actions",
			);
		}

		if (frm.doc.status === "Approved" && !frm.doc.sales_invoice) {
			frm.add_custom_button(
				"Create Sales Invoice",
				function () {
					const currency = frm.doc.currency || "AED";
					const gross = formatNumber(frm.doc.gross_amount);
					const retention = formatNumber(frm.doc.retention_amount);
					const net = formatNumber(frm.doc.net_payable);
					const retPct = frm.doc.retention_percent || 0;

					const msg = `
						<table style="width:100%;font-size:13px;border-collapse:collapse">
							<tr>
								<td style="padding:6px 0;color:#6b7280">Gross Amount</td>
								<td style="padding:6px 0;text-align:right;font-weight:500">${currency} ${gross}</td>
							</tr>
							<tr>
								<td style="padding:6px 0;color:#6b7280">Retention (${retPct}%)</td>
								<td style="padding:6px 0;text-align:right;color:#dc2626">- ${currency} ${retention}</td>
							</tr>
							<tr style="border-top:1px solid #e5e7eb">
								<td style="padding:8px 0;font-weight:600">Net Payable</td>
								<td style="padding:8px 0;text-align:right;font-weight:600;color:#185FA5">${currency} ${net}</td>
							</tr>
						</table>
						<p style="margin-top:10px;font-size:12px;color:#6b7280">
							A draft Sales Invoice will be created.
							The accounts team will review and submit it.
						</p>
					`;

					frappe.confirm(msg, function () {
						frappe.call({
							method: "create_sales_invoice",
							doc: frm.doc,
							freeze: true,
							freeze_message: "Creating Sales Invoice...",
							callback: function (r) {
								if (r.message) {
									frm.reload_doc();
									frappe.set_route("Form", "Sales Invoice", r.message);
								}
							},
							error: function (err) {
								frappe.dom.unfreeze();
								console.error(err);
							},
						});
					});
				},
				"Actions",
			);
		}

		if (frm.doc.sales_invoice) {
			frm.add_custom_button(
				frm.doc.sales_invoice,
				function () {
					frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
				},
				"View",
			);
		}
	},

	validate: function (frm) {
		frm.trigger("recalculate_totals");
	},

	project: function (frm) {
		if (frm.doc.boq) {
			frm.set_value("boq", null);
			frm.clear_table("items");
			frm.refresh_field("items");
			frm.trigger("recalculate_totals");
		}
	},

	boq: function (frm) {
		frm._ra_bill_context_boq = null;

		if (frm.doc.boq) {
			const selectedBoq = frm.doc.boq;

			frappe.db.get_value("BOQ", selectedBoq, "client").then((r) => {
				if (frm.doc.boq === selectedBoq && r.message && r.message.client) {
					frm.set_value("customer", r.message.client);
				}
			});
		}

		if (frm.doc.items && frm.doc.items.length > 0) {
			frappe.confirm("Changing the BOQ will clear all current items. Continue?", function () {
				frm.clear_table("items");
				frm.refresh_field("items");
				frm.trigger("recalculate_totals");
			});
		}

		hydrateBoqLabels(frm);
	},

	retention_percent: function (frm) {
		frm.trigger("recalculate_totals");
	},

	recalculate_totals: function (frm) {
		let gross = 0;

		(frm.doc.items || []).forEach((row) => {
			gross += getNumber(row.current_amount);
		});

		const retention = gross * (getNumber(frm.doc.retention_percent) / 100);

		frappe.model.set_value(frm.doctype, frm.docname, "gross_amount", gross);
		frappe.model.set_value(frm.doctype, frm.docname, "retention_amount", retention);
		frappe.model.set_value(frm.doctype, frm.docname, "net_payable", gross - retention);
	},
});

frappe.ui.form.on("RA Bill Item", {
	items_add: function (frm, cdt, cdn) {
		setChildValues(frm, cdt, cdn, {
			uom: "Nos",
			work_percent: 0,
			current_qty: 0,
			current_amount: 0,
			cumulative_qty: getNumber(locals[cdt][cdn].prev_cumulative_qty),
		});
	},

	category_name: function (frm, cdt, cdn) {
		if (isSettingChildValues(frm, cdn)) return;

		clearItemDetailFields(frm, cdt, cdn, {
			keep_sub_category: false,
			keep_boq_item: false,
		});
	},

	sub_category: function (frm, cdt, cdn) {
		if (isSettingChildValues(frm, cdn)) return;

		clearItemDetailFields(frm, cdt, cdn, {
			keep_sub_category: true,
			keep_boq_item: false,
		});
	},

	boq_item: function (frm, cdt, cdn) {
		if (isSettingChildValues(frm, cdn)) return;

		const row = locals[cdt][cdn];
		console.log("RA Bill Item boq_item triggered");
		console.log("Selected boq_item:", row && row.boq_item);
		console.log("Current row before fetch:", row);

		if (!row.boq_item) {
			clearItemDetailFields(frm, cdt, cdn, {
				keep_sub_category: true,
				keep_boq_item: true,
			});
			return;
		}

		if (hasDuplicateBoqItem(frm, row)) {
			rejectDuplicateBoqItem(frm, cdt, cdn);
			return;
		}

		frm.ra_bill_apply_selected_boq_item(cdt, cdn);
	},

	work_percent: function (frm, cdt, cdn) {
		if (isSettingChildValues(frm, cdn)) return;

		const row = locals[cdt][cdn];
		setChildValues(frm, cdt, cdn, getRowTotals(row, row.work_percent)).then(() =>
			frm.trigger("recalculate_totals"),
		);
	},

	current_qty: function (frm, cdt, cdn) {
		if (isSettingChildValues(frm, cdn)) return;

		const row = locals[cdt][cdn];
		setChildValues(frm, cdt, cdn, getRowTotalsFromCurrentQty(row)).then(() =>
			frm.trigger("recalculate_totals"),
		);
	},

	items_remove: function (frm) {
		frm.trigger("recalculate_totals");
	},
});
