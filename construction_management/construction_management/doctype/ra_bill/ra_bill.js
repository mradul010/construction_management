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
		boq_item_key: "",
		boq_revision: "",
		original_boq: "",
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
		boq_item_key: "",
		boq_revision: "",
		original_boq: "",
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

function getRaBillTaxReferenceRow(row, previousRows) {
	const rowId = parseInt(row.row_id, 10);
	if (!rowId || rowId < 1 || rowId > previousRows.length) {
		return null;
	}
	return previousRows[rowId - 1];
}

function getRaBillTaxAmount(row, taxBase, previousRows) {
	const chargeType = row.charge_type || "Actual";
	const rate = getNumber(row.rate);

	if (chargeType === "Actual") {
		return getNumber(row.tax_amount);
	}

	if (chargeType === "On Net Total") {
		return taxBase * rate / 100;
	}

	if (chargeType === "On Previous Row Amount" || chargeType === "On Previous Row Total") {
		const referenceRow = getRaBillTaxReferenceRow(row, previousRows);
		if (!referenceRow) return 0;

		const referenceAmount =
			chargeType === "On Previous Row Total"
				? getNumber(referenceRow.total)
				: getNumber(referenceRow.tax_amount);
		return referenceAmount * rate / 100;
	}

	return getNumber(row.tax_amount);
}

function updateTaxRowTotals(frm, taxBase) {
	let totalTaxes = 0;
	let runningTotal = taxBase;
	const previousRows = [];

	(frm.doc.taxes || []).forEach((row) => {
		const chargeType = row.charge_type || "Actual";
		const taxAmount = getRaBillTaxAmount(row, taxBase, previousRows);

		if (
			chargeType !== "Actual" &&
			chargeType !== "On Item Quantity" &&
			childFieldExists(row.doctype, "tax_amount")
		) {
			row.tax_amount = taxAmount;
		}

		totalTaxes += taxAmount;
		runningTotal += taxAmount;

		if (childFieldExists(row.doctype, "total")) {
			row.total = runningTotal;
		}

		previousRows.push({
			tax_amount: taxAmount,
			total: runningTotal,
		});
	});

	return totalTaxes;
}

function isTemplateTaxRow(row) {
	return Boolean(row && (getNumber(row.from_template) || row.source_tax_template));
}

function copyTaxRowValues(row) {
	const values = {};
	Object.keys(row || {}).forEach((fieldname) => {
		if (["doctype", "name", "owner", "creation", "modified", "modified_by", "parent", "parentfield", "parenttype", "idx", "__islocal"].includes(fieldname)) {
			return;
		}
		values[fieldname] = row[fieldname];
	});
	return values;
}

function clearTemplateTaxRows(frm) {
	const manualRows = (frm.doc.taxes || [])
		.filter((row) => !isTemplateTaxRow(row))
		.map(copyTaxRowValues);

	frm.clear_table("taxes");
	manualRows.forEach((source) => {
		const row = frm.add_child("taxes");
		Object.keys(source).forEach((fieldname) => {
			if (childFieldExists(row.doctype, fieldname)) {
				row[fieldname] = source[fieldname];
			}
		});
	});
}

function getRaBillTaxCompany(frm) {
	if (frm._ra_bill_tax_company || !frm.doc.boq) {
		return Promise.resolve(frm._ra_bill_tax_company || "");
	}

	return frappe.db.get_value("BOQ", frm.doc.boq, "company").then((r) => {
		const company = (r.message && r.message.company) || "";
		frm._ra_bill_tax_company = company;
		return company;
	});
}

function getSalesTaxTemplateFilters(frm) {
	const filters = { disabled: 0 };
	if (frm._ra_bill_tax_company) {
		filters.company = frm._ra_bill_tax_company;
	}
	if (frm.doc.tax_category) {
		filters.tax_category = frm.doc.tax_category;
	}
	return filters;
}

function addTemplateTaxRows(frm, rows) {
	(rows || []).forEach((source) => {
		const row = frm.add_child("taxes");
		Object.keys(source || {}).forEach((fieldname) => {
			if (childFieldExists(row.doctype, fieldname)) {
				row[fieldname] = source[fieldname];
			}
		});
	});
}

function applySalesTaxesAndChargesTemplate(frm) {
	const selectedTemplate = frm.doc.sales_taxes_and_charges_template;
	const requestId = `${selectedTemplate || ""}:${Date.now()}:${Math.random()}`;
	frm._ra_bill_tax_template_request = requestId;

	clearTemplateTaxRows(frm);
	frm.refresh_field("taxes");

	if (!selectedTemplate) {
		frm.trigger("recalculate_totals");
		return Promise.resolve();
	}

	return getRaBillTaxCompany(frm).then((company) =>
		frappe.call({
			method: `${RA_BILL_METHOD}.get_ra_bill_template_tax_rows`,
			args: {
				template: selectedTemplate,
				company: company,
				boq: frm.doc.boq,
			},
			callback: function (r) {
				if (
					frm._ra_bill_tax_template_request !== requestId ||
					frm.doc.sales_taxes_and_charges_template !== selectedTemplate
				) {
					return;
				}

				addTemplateTaxRows(frm, r.message || []);
				frm.refresh_field("taxes");
				frm.trigger("recalculate_totals");
			},
		}),
	);
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
	const boqItemKey = doc.boq_item_key || doc.component_key || row.boq_item;
	const rowWithPreviousWork = {
		...row,
		boq_qty: qty,
		boq_rate: rate,
		boq_item_key: boqItemKey,
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
		boq_item_key: boqItemKey,
		boq_revision: frm.doc.boq,
		original_boq: (previousWork && previousWork.original_boq) || "",
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

function applyBoqContractToRaBill(frm, selectedBoq) {
	return frappe.db
		.get_value("BOQ", selectedBoq, ["project", "client", "company", "currency", "sales_order"])
		.then((r) => {
			if (frm.doc.boq !== selectedBoq) return;

			const boq = r.message || {};
			frm._ra_bill_tax_company = boq.company || "";
			const mappings = {
				project: boq.project,
				customer: boq.client,
				currency: boq.currency,
			};
			const conflicts = [];
			const updates = [frm.set_value("sales_order", boq.sales_order || "")];

			Object.entries(mappings).forEach(([fieldname, value]) => {
				if (!value) return;
				if (!frm.doc[fieldname]) {
					updates.push(frm.set_value(fieldname, value));
				} else if (frm.doc[fieldname] !== value) {
					conflicts.push(frm.fields_dict[fieldname]?.df.label || fieldname);
				}
			});

			if (conflicts.length) {
				frappe.msgprint({
					title: __("BOQ Mismatch"),
					indicator: "orange",
					message: __(
						"The following RA Bill values differ from BOQ {0}: {1}. Correct them before saving.",
						[selectedBoq, conflicts.join(", ")],
					),
				});
			}

			return Promise.all(updates);
		});
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

		frm.set_query("sales_taxes_and_charges_template", function () {
			return { filters: getSalesTaxTemplateFilters(frm) };
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
						is_deleted_in_revision: 0,
					},
					fields: ["name", "boq_category", "item", "item_name", "boq_item_key"],
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
		getRaBillTaxCompany(frm);
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
					const currency = frm.doc.currency || frappe.defaults.get_default("currency") || "";
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
		const selectedProject = frm.doc.project;

		if (frm.doc.boq) {
			frm.set_value("boq", null);
		}
		frm.clear_table("items");
		frm.refresh_field("items");
		frm.trigger("recalculate_totals");

		if (!selectedProject) return;

		frappe.call({
			method: `${RA_BILL_METHOD}.get_active_boq_for_project`,
			args: {
				project: selectedProject,
			},
			callback: function (r) {
				if (frm.doc.project !== selectedProject || !r.message) return;
				frm.set_value("boq", r.message);
			},
		});
	},

	boq: function (frm) {
		frm._ra_bill_context_boq = null;
		frm._ra_bill_tax_company = "";

		if (frm.doc.boq) {
			const selectedBoq = frm.doc.boq;
			applyBoqContractToRaBill(frm, selectedBoq);
		} else {
			frm.set_value("sales_order", "");
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

	tax_category: function (frm) {
		frm.set_query("sales_taxes_and_charges_template", function () {
			return { filters: getSalesTaxTemplateFilters(frm) };
		});
	},

	sales_taxes_and_charges_template: function (frm) {
		return applySalesTaxesAndChargesTemplate(frm);
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

	get_advances_received: function (frm) {
		frappe.call({
			doc: frm.doc,
			method: "get_advances_received",
			freeze: true,
			freeze_message: __("Fetching advances..."),
			callback: function (response) {
				const data = response.message || {};
				frm.clear_table("advances");
				(data.advances || []).forEach((source) => {
					const row = frm.add_child("advances");
					[
						"reference_type",
						"reference_name",
						"remarks",
						"advance_amount",
						"allocated_amount",
						"difference_posting_date",
					].forEach((fieldname) => {
						if (childFieldExists(row.doctype, fieldname)) {
							row[fieldname] = source[fieldname];
						}
					});
				});
				[
					"total_advance",
					"outstanding_amount",
					"total_advance_received",
					"previously_recovered_advance",
					"remaining_advance_before_current_bill",
					"proposed_advance_recovery",
					"actual_advance_recovered",
					"remaining_advance_after_current_bill",
				].forEach((fieldname) => {
					if (formFieldExists(frm, fieldname) && data[fieldname] !== undefined) {
						frm.set_value(fieldname, data[fieldname]);
					}
				});
				frm.refresh_field("advances");
				frm.trigger("recalculate_totals");
			},
		});
	},

	retention_percent: function (frm) {
		frm.trigger("recalculate_totals");
	},

	advance_recovery_percent: function (frm) {
		frm.trigger("recalculate_totals");
	},

	recalculate_totals: function (frm) {
		let gross = 0;

		(frm.doc.items || []).forEach((row) => {
			gross += getNumber(row.current_amount);
		});

		const retention = gross * (getNumber(frm.doc.retention_percent) / 100);
		const netPayable = gross - retention;
		const totalTaxes = updateTaxRowTotals(frm, gross);
		const grandTotal = gross + totalTaxes;
		const allocatedAdvance = (frm.doc.advances || []).reduce(
			(total, row) => total + getNumber(row.allocated_amount),
			0,
		);
		const totalAdvanceReceived = getNumber(frm.doc.total_advance_received);
		const previouslyRecovered = getNumber(frm.doc.previously_recovered_advance);
		const remainingBefore = Math.max(totalAdvanceReceived - previouslyRecovered, 0);
		const recoveryPercent = getNumber(frm.doc.advance_recovery_percent);
		const proposedRecovery = recoveryPercent
			? (totalAdvanceReceived * recoveryPercent) / 100
			: getNumber(frm.doc.proposed_advance_recovery);
		const totalAdvance = recoveryPercent
			? Math.min(proposedRecovery, remainingBefore)
			: allocatedAdvance;

		if (recoveryPercent) {
			let remainingAllocation = totalAdvance;
			(frm.doc.advances || []).forEach((row) => {
				const available = getNumber(row.advance_amount) || getNumber(row.allocated_amount);
				row.allocated_amount = remainingAllocation > 0
					? Math.min(available, remainingAllocation)
					: 0;
				remainingAllocation -= row.allocated_amount;
			});
			frm.refresh_field("advances");
		}

		frappe.model.set_value(frm.doctype, frm.docname, "gross_amount", gross);
		frappe.model.set_value(frm.doctype, frm.docname, "retention_amount", retention);
		frappe.model.set_value(frm.doctype, frm.docname, "net_payable", netPayable);
		setParentValueIfFieldExists(frm, "net_total", gross);
		setParentValueIfFieldExists(frm, "total_taxes_and_charges", totalTaxes);
		setParentValueIfFieldExists(frm, "grand_total", grandTotal);
		setParentValueIfFieldExists(frm, "total_advance", totalAdvance);
		setParentValueIfFieldExists(frm, "outstanding_amount", grandTotal - totalAdvance);
		setParentValueIfFieldExists(frm, "remaining_advance_before_current_bill", remainingBefore);
		setParentValueIfFieldExists(frm, "proposed_advance_recovery", proposedRecovery);
		setParentValueIfFieldExists(frm, "actual_advance_recovered", totalAdvance);
		setParentValueIfFieldExists(frm, "remaining_advance_after_current_bill", Math.max(remainingBefore - totalAdvance, 0));
		frm.refresh_field("taxes");
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
			boq_item_key: "",
			boq_revision: "",
			original_boq: "",
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
			total: getNumber(frm.doc.net_total),
		}, "taxes").then(() => frm.trigger("recalculate_totals"));
	},

	charge_type: function (frm) {
		frm.trigger("recalculate_totals");
	},

	row_id: function (frm) {
		frm.trigger("recalculate_totals");
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
