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

function setChildValues(frm, cdt, cdn, values, tableFieldname = "items") {
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
			frm.refresh_field(tableFieldname);
		})
		.catch((error) => {
			delete frm._ra_bill_setting_child_values[cdn];
			throw error;
		});
}

function setChildValuesIfChanged(frm, cdt, cdn, values) {
	const row = locals[cdt][cdn];
	if (!row) return Promise.resolve();

	const changedValues = {};
	Object.keys(values).forEach((fieldname) => {
		if (!childFieldExists(cdt, fieldname)) return;

		const currentValue = row[fieldname];
		const nextValue = values[fieldname];
		if (typeof nextValue === "number") {
			if (Math.abs(getNumber(currentValue) - nextValue) > 0.0001) {
				changedValues[fieldname] = nextValue;
			}
			return;
		}

		if ((currentValue || "") !== (nextValue || "")) {
			changedValues[fieldname] = nextValue;
		}
	});

	if (!Object.keys(changedValues).length) {
		return Promise.resolve();
	}

	return setChildValues(frm, cdt, cdn, changedValues);
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

function getPreviousQty(row) {
	if (row && row.previous_qty !== undefined && row.previous_qty !== null) {
		return getNumber(row.previous_qty);
	}
	return getNumber(row && row.prev_cumulative_qty);
}

function getRemainingQty(row) {
	if (row && row.remaining_qty !== undefined && row.remaining_qty !== null) {
		return Math.max(0, getNumber(row.remaining_qty));
	}

	return Math.max(0, getNumber(row && row.boq_qty) - getPreviousQty(row || {}));
}

function getRemainingPercent(row) {
	if (row && row.remaining_percent !== undefined && row.remaining_percent !== null) {
		return Math.max(0, getNumber(row.remaining_percent));
	}

	const boqQty = getNumber(row && row.boq_qty);
	return boqQty ? (getRemainingQty(row || {}) / boqQty) * 100 : 0;
}

function getRowTotals(row, workPercent) {
	const pct = clampPercent(workPercent);
	const boqQty = getNumber(row.boq_qty);
	const boqRate = getNumber(row.boq_rate);
	const prevQty = getPreviousQty(row);
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
	const prevQty = getPreviousQty(row);

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
		previous_qty: 0,
		previous_percent: 0,
		remaining_qty: 0,
		remaining_percent: 0,
		prev_cumulative_qty: 0,
		work_percent: 0,
		current_qty: 0,
		cumulative_qty: 0,
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
		previous_qty: 0,
		previous_percent: 0,
		remaining_qty: 0,
		remaining_percent: 0,
		prev_cumulative_qty: 0,
		work_percent: 0,
		current_qty: 0,
		cumulative_qty: 0,
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

function showRaBillItemValidation(message) {
	frappe.msgprint({
		title: __("Invalid RA Bill Item Value"),
		indicator: "red",
		message: message,
	});
}

function getRaBillItemLabel(row) {
	return row.item_name || row.boq_item || __("selected item");
}

function validateRaBillItemValues(row) {
	if (!row || !row.boq_item) return true;

	const item = getRaBillItemLabel(row);

	if (getNumber(row.work_percent) <= 0) {
		showRaBillItemValidation(__("Work % for item {0} must be greater than 0.", [item]));
		return false;
	}

	if (getNumber(row.work_percent) > 100) {
		showRaBillItemValidation(__("Work % for item {0} cannot be greater than 100.", [item]));
		return false;
	}

	if (getNumber(row.current_qty) < 0) {
		showRaBillItemValidation(__("Current Qty for item {0} cannot be negative.", [item]));
		return false;
	}

	if (getNumber(row.boq_qty) <= 0) {
		showRaBillItemValidation(__("BOQ Qty for item {0} must be greater than 0.", [item]));
		return false;
	}

	if (getNumber(row.boq_rate) < 0) {
		showRaBillItemValidation(__("BOQ Rate for item {0} cannot be negative.", [item]));
		return false;
	}

	if (getNumber(row.current_qty) > getRemainingQty(row) + 0.0001) {
		showOverbillingCapMessage(row, getNumber(row.work_percent));
		return false;
	}

	return true;
}

function validateAllRaBillItemValues(frm) {
	return (frm.doc.items || []).every((row) => validateRaBillItemValues(row));
}

function getPreviousWorkValues(summary, fallbackBoqQty = 0) {
	summary = summary || {};
	const previousQty = getNumber(summary.previous_qty);
	const fallbackRemainingQty = Math.max(0, getNumber(fallbackBoqQty) - previousQty);

	return {
		previous_qty: previousQty,
		previous_percent: getNumber(summary.previous_percent),
		remaining_qty:
			summary.remaining_qty === undefined || summary.remaining_qty === null
				? fallbackRemainingQty
				: Math.max(0, getNumber(summary.remaining_qty)),
		remaining_percent:
			summary.remaining_percent === undefined || summary.remaining_percent === null
				? getNumber(fallbackBoqQty)
					? (fallbackRemainingQty / getNumber(fallbackBoqQty)) * 100
					: 0
				: Math.max(0, getNumber(summary.remaining_percent)),
		prev_cumulative_qty: previousQty,
	};
}

function showOverbillingCapMessage(row, enteredPercent) {
	frappe.msgprint({
		title: __("Overbilling Not Allowed"),
		indicator: "orange",
		message: __(
			"Overbilling not allowed. This item already has {0}% completed. Remaining allowed is {1}%. You entered {2}%.",
			[
				formatNumber(getNumber(row.previous_percent)),
				formatNumber(getRemainingPercent(row)),
				formatNumber(enteredPercent),
			],
		),
	});
}

function capWorkToRemaining(frm, cdt, cdn, row, enteredPercent) {
	const remainingPercent = getRemainingPercent(row);
	const remainingQty = getRemainingQty(row);
	const values = {
		work_percent: remainingPercent,
		current_qty: remainingQty,
		cumulative_qty: getPreviousQty(row) + remainingQty,
		current_amount: remainingQty * getNumber(row.boq_rate),
	};

	showOverbillingCapMessage(row, enteredPercent);
	return setChildValues(frm, cdt, cdn, values).then(() => frm.trigger("recalculate_totals"));
}

function fetchPreviousWorkSummary(frm, row) {
	if (!frm.doc.boq || !row || !row.boq_item) {
		return Promise.resolve(null);
	}

	return frappe
		.call({
			method: `${RA_BILL_METHOD}.get_boq_item_previous_work`,
			args: {
				boq: frm.doc.boq,
				boq_item: row.boq_item,
				current_ra_bill: frm.doc.name,
			},
		})
		.then((r) => r.message || null);
}

function updatePreviousWorkSummary(frm, cdt, cdn, options = {}) {
	const row = locals[cdt][cdn];
	if (!row || !row.boq_item) return Promise.resolve();

	return fetchPreviousWorkSummary(frm, row).then((summary) => {
		if (!summary) return;

		const values = getPreviousWorkValues(summary, row.boq_qty);
		const updatedRow = { ...row, ...values };
		const currentQty = getNumber(updatedRow.current_qty);
		const currentPercent = getNumber(updatedRow.work_percent);

		if (options.cap_current !== false && currentQty > values.remaining_qty + 0.0001) {
			return capWorkToRemaining(frm, cdt, cdn, updatedRow, currentPercent);
		}

		return setChildValuesIfChanged(frm, cdt, cdn, values);
	});
}

function refreshPreviousWorkSummaries(frm) {
	if (!frm.doc.boq || frm.doc.docstatus !== 0) return;

	(frm.doc.items || [])
		.filter((row) => row.boq_item)
		.forEach((row) => {
			updatePreviousWorkSummary(frm, row.doctype || "RA Bill Item", row.name, {
				cap_current: false,
			});
		});
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

function formFieldExists(frm, fieldname) {
	return Boolean(frm.fields_dict && frm.fields_dict[fieldname]);
}

function setFormValuesIfChanged(frm, values) {
	const changedValues = {};
	Object.keys(values || {}).forEach((fieldname) => {
		if (!formFieldExists(frm, fieldname)) return;

		const nextValue = values[fieldname] === undefined || values[fieldname] === null ? "" : values[fieldname];
		if ((frm.doc[fieldname] || "") !== (nextValue || "")) {
			changedValues[fieldname] = nextValue;
		}
	});

	if (!Object.keys(changedValues).length) {
		return Promise.resolve();
	}

	return Promise.resolve(frm.set_value(changedValues));
}

function renderAddressDisplay(frm, addressField, displayField) {
	if (!formFieldExists(frm, addressField) || !formFieldExists(frm, displayField)) {
		return Promise.resolve();
	}

	if (!frm.doc[addressField]) {
		return setFormValuesIfChanged(frm, { [displayField]: "" });
	}

	return frappe
		.call({
			method: "frappe.contacts.doctype.address.address.get_address_display",
			args: {
				address_dict: frm.doc[addressField],
			},
		})
		.then((r) => setFormValuesIfChanged(frm, { [displayField]: r.message || "" }));
}

function setCustomerAddressAndContact(frm) {
	if (!frm.doc.customer) {
		return setFormValuesIfChanged(frm, {
			customer_address: "",
			address_display: "",
			shipping_address_name: "",
			shipping_address: "",
			contact_person: "",
			contact_display: "",
			contact_mobile: "",
			contact_email: "",
			territory: "",
		});
	}

	return frappe
		.call({
			method: `${RA_BILL_METHOD}.get_customer_address_and_contact`,
			args: {
				customer: frm.doc.customer,
			},
		})
		.then((r) => setFormValuesIfChanged(frm, r.message || {}));
}

function setContactDetails(frm) {
	if (!frm.doc.contact_person) {
		return setFormValuesIfChanged(frm, {
			contact_display: "",
			contact_mobile: "",
			contact_email: "",
		});
	}

	return frappe
		.call({
			method: "frappe.contacts.doctype.contact.contact.get_contact_details",
			args: {
				contact: frm.doc.contact_person,
			},
		})
		.then((r) => {
			const details = r.message || {};
			return setFormValuesIfChanged(frm, {
				contact_display: details.contact_display || "",
				contact_mobile: details.contact_mobile || "",
				contact_email: details.contact_email || "",
			});
		});
}

function setTermsAndConditions(frm) {
	if (!frm.doc.terms) {
		return setFormValuesIfChanged(frm, { terms_and_conditions: "" });
	}

	return frappe.db
		.get_value("Terms and Conditions", frm.doc.terms, "terms")
		.then((r) =>
			setFormValuesIfChanged(frm, {
				terms_and_conditions: (r.message && r.message.terms) || "",
			}),
		);
}

function setParentValueIfFieldExists(frm, fieldname, value) {
	if (!formFieldExists(frm, fieldname)) return;

	frappe.model.set_value(frm.doctype, frm.docname, fieldname, value);
}

function updateTaxRowTotals(frm, netPayable) {
	let totalTaxes = 0;

	(frm.doc.taxes || []).forEach((row) => {
		totalTaxes += getNumber(row.tax_amount);

		if (row.doctype && row.name && childFieldExists(row.doctype, "total")) {
			const rowTotal = netPayable + totalTaxes;
			if (Math.abs(getNumber(row.total) - rowTotal) > 0.0001) {
				frappe.model.set_value(row.doctype, row.name, "total", rowTotal);
			}
		}
	});

	return totalTaxes;
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

	if (qty <= 0) {
		showRaBillItemValidation(__("BOQ Qty for item {0} must be greater than 0.", [itemName]));
		return clearItemDetailFields(frm, cdt, cdn, {
			keep_sub_category: true,
			keep_boq_item: false,
		});
	}

	if (rate < 0) {
		showRaBillItemValidation(__("BOQ Rate for item {0} cannot be negative.", [itemName]));
		return clearItemDetailFields(frm, cdt, cdn, {
			keep_sub_category: true,
			keep_boq_item: false,
		});
	}

	const parentCategoryFromTree = await getParentCategoryFromSubcategory(subCategory);
	const parentCategory = parentCategoryFromTree || doc.boq_parent_category || row.category_name || "";
	const previousWork = await fetchPreviousWorkSummary(frm, row);
	const previousWorkValues = getPreviousWorkValues(previousWork, qty);
	const rowWithPreviousWork = {
		...row,
		boq_qty: qty,
		boq_rate: rate,
		...previousWorkValues,
	};
	let workPercent = getCurrentWorkPercent(rowWithPreviousWork);
	const enteredQty = qty ? (qty * workPercent) / 100 : 0;
	if (enteredQty > previousWorkValues.remaining_qty + 0.0001) {
		showOverbillingCapMessage(rowWithPreviousWork, workPercent);
		workPercent = previousWorkValues.remaining_percent;
	}
	const values = {
		item_name: itemName,
		boq_qty: qty,
		boq_rate: rate,
		uom: uom,
		sub_category: subCategory || row.sub_category || "",
		category_name: parentCategory || row.category_name || "",
		...previousWorkValues,
		...getRowTotals(
			rowWithPreviousWork,
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
		refreshPreviousWorkSummaries(frm);

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
		if (!validateAllRaBillItemValues(frm)) {
			frappe.validated = false;
			return;
		}

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

	customer: function (frm) {
		setCustomerAddressAndContact(frm);
	},

	customer_address: function (frm) {
		renderAddressDisplay(frm, "customer_address", "address_display");
	},

	shipping_address_name: function (frm) {
		renderAddressDisplay(frm, "shipping_address_name", "shipping_address");
	},

	dispatch_address_name: function (frm) {
		renderAddressDisplay(frm, "dispatch_address_name", "dispatch_address");
	},

	company_address: function (frm) {
		renderAddressDisplay(frm, "company_address", "company_address_display");
	},

	contact_person: function (frm) {
		setContactDetails(frm);
	},

	terms: function (frm) {
		setTermsAndConditions(frm);
	},

	get_advances_received: function () {
		frappe.show_alert(
			{
				message: __("Advance allocation can be filled manually for now."),
				indicator: "blue",
			},
			5,
		);
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
		const netPayable = gross - retention;
		const totalTaxes = updateTaxRowTotals(frm, netPayable);
		const grandTotal = netPayable + totalTaxes;
		const totalAdvance = (frm.doc.advances || []).reduce(
			(total, row) => total + getNumber(row.allocated_amount),
			0,
		);

		frappe.model.set_value(frm.doctype, frm.docname, "gross_amount", gross);
		frappe.model.set_value(frm.doctype, frm.docname, "retention_amount", retention);
		frappe.model.set_value(frm.doctype, frm.docname, "net_payable", netPayable);
		setParentValueIfFieldExists(frm, "net_total", gross);
		setParentValueIfFieldExists(frm, "total_taxes_and_charges", totalTaxes);
		setParentValueIfFieldExists(frm, "grand_total", grandTotal);
		setParentValueIfFieldExists(frm, "total_advance", totalAdvance);
		setParentValueIfFieldExists(frm, "outstanding_amount", grandTotal - totalAdvance);
	},
});

frappe.ui.form.on("RA Bill Item", {
	items_add: function (frm, cdt, cdn) {
		setChildValues(frm, cdt, cdn, {
			uom: "Nos",
			work_percent: 0,
			current_qty: 0,
			current_amount: 0,
			previous_qty: 0,
			previous_percent: 0,
			remaining_qty: 0,
			remaining_percent: 0,
			prev_cumulative_qty: 0,
			cumulative_qty: 0,
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
		const item = getRaBillItemLabel(row);
		const workPercent = getNumber(row.work_percent);

		if (row.boq_item && workPercent <= 0) {
			showRaBillItemValidation(__("Work % for item {0} must be greater than 0.", [item]));
			setChildValues(frm, cdt, cdn, {
				work_percent: 0,
				current_qty: 0,
				cumulative_qty: getNumber(row.prev_cumulative_qty),
				current_amount: 0,
			}).then(() => frm.trigger("recalculate_totals"));
			return;
		}

		if (row.boq_item && workPercent > 100) {
			showRaBillItemValidation(__("Work % for item {0} cannot be greater than 100.", [item]));
			setChildValues(frm, cdt, cdn, getRowTotals(row, 100)).then(() =>
				frm.trigger("recalculate_totals"),
			);
			return;
		}

		const requestedQty = getNumber(row.boq_qty) * (workPercent / 100);
		if (row.boq_item && requestedQty > getRemainingQty(row) + 0.0001) {
			capWorkToRemaining(frm, cdt, cdn, row, workPercent);
			return;
		}

		setChildValues(frm, cdt, cdn, getRowTotals(row, row.work_percent)).then(() =>
			frm.trigger("recalculate_totals"),
		);
	},

	current_qty: function (frm, cdt, cdn) {
		if (isSettingChildValues(frm, cdn)) return;

		const row = locals[cdt][cdn];
		if (row.boq_item && getNumber(row.current_qty) < 0) {
			showRaBillItemValidation(
				__("Current Qty for item {0} cannot be negative.", [getRaBillItemLabel(row)]),
			);
			setChildValues(frm, cdt, cdn, getRowTotalsFromCurrentQty({ ...row, current_qty: 0 })).then(
				() => frm.trigger("recalculate_totals"),
			);
			return;
		}

		if (row.boq_item && getNumber(row.current_qty) > getRemainingQty(row) + 0.0001) {
			const enteredPercent = getNumber(row.boq_qty)
				? (getNumber(row.current_qty) / getNumber(row.boq_qty)) * 100
				: getNumber(row.work_percent);
			capWorkToRemaining(frm, cdt, cdn, row, enteredPercent);
			return;
		}

		setChildValues(frm, cdt, cdn, getRowTotalsFromCurrentQty(row)).then(() =>
			frm.trigger("recalculate_totals"),
		);
	},

	items_remove: function (frm) {
		frm.trigger("recalculate_totals");
	},
});

frappe.ui.form.on("RA Bill Advance", {
	advances_add: function (frm, cdt, cdn) {
		setChildValues(frm, cdt, cdn, {
			advance_amount: 0,
			allocated_amount: 0,
		}, "advances").then(() => frm.trigger("recalculate_totals"));
	},

	advance_amount: function (frm) {
		frm.trigger("recalculate_totals");
	},

	allocated_amount: function (frm) {
		frm.trigger("recalculate_totals");
	},

	advances_remove: function (frm) {
		frm.trigger("recalculate_totals");
	},
});

frappe.ui.form.on("RA Bill Taxes and Charges", {
	taxes_add: function (frm, cdt, cdn) {
		setChildValues(frm, cdt, cdn, {
			rate: 0,
			tax_amount: 0,
			total: getNumber(frm.doc.net_payable),
		}, "taxes").then(() => frm.trigger("recalculate_totals"));
	},

	rate: function (frm) {
		frm.trigger("recalculate_totals");
	},

	tax_amount: function (frm) {
		frm.trigger("recalculate_totals");
	},

	taxes_remove: function (frm) {
		frm.trigger("recalculate_totals");
	},
});
