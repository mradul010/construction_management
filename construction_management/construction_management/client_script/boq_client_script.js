function boqNumber(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

function getBoqCurrency(frm) {
	return frm && frm.doc
		? frm.doc.currency || frappe.defaults.get_default("currency") || ""
		: frappe.defaults.get_default("currency") || "";
}

function formatBoqCurrency(value, currency) {
	return format_currency(boqNumber(value), currency || frappe.defaults.get_default("currency") || "");
}

const BOQ_COST_BREAKDOWN_TOLERANCE = 0.01;
const BOQ_METHOD =
	"construction_management.construction_management.doctype.boq.boq";
const BOQ_REVISION_ROLES = [
	"System Manager",
	"Construction Manager",
	"Project Manager",
	"Estimator",
];

function calculateBoqRowAmounts(row) {
	if (!row) return row;

	const qty = row.is_deleted_in_revision ? 0 : boqNumber(row.qty);
	const unitCost = boqNumber(row.unit_cost);
	const margin = boqNumber(row.margin_percent);

	row.unit_rate = unitCost * (1 + margin / 100);
	row.amount = qty * unitCost;
	row.amount_after_margin = qty * boqNumber(row.unit_rate);

	return row;
}

function recalculateBoqTotals(frm) {
	let totalCost = 0;
	let grandTotal = 0;

	(frm.doc.items || []).forEach((row) => {
		calculateBoqRowAmounts(row);
		totalCost += boqNumber(row.amount);
		grandTotal += boqNumber(row.amount_after_margin);
	});

	frm.doc.total_cost = totalCost;
	frm.doc.grand_total = grandTotal;
	frm.doc.total_margin = grandTotal - totalCost;
	frm.doc.margin_percent = grandTotal ? ((grandTotal - totalCost) / grandTotal) * 100 : 0;
	frm.doc.rate_per_bua = frm.doc.built_up_area ? grandTotal / boqNumber(frm.doc.built_up_area) : 0;

	[
		"total_cost",
		"grand_total",
		"total_margin",
		"margin_percent",
		"rate_per_bua",
	].forEach((fieldname) => frm.refresh_field(fieldname));
}

function getBoqBaseAmount(row) {
	return getBoqItemAmount(row);
}

function getBoqAmountAfterMargin(row) {
	if (!row) return 0;

	if (
		row.amount_after_margin !== undefined &&
		row.amount_after_margin !== null &&
		row.amount_after_margin !== ""
	) {
		return boqNumber(row.amount_after_margin);
	}

	return boqNumber(row.qty) * boqNumber(row.unit_rate);
}

function getBoqItemAmount(row) {
	if (!row) return 0;

	if (row.amount !== undefined && row.amount !== null && row.amount !== "") {
		return boqNumber(row.amount);
	}

	const qty = row.is_deleted_in_revision ? 0 : boqNumber(row.qty);
	return qty * boqNumber(row.unit_cost);
}


function getCostBreakdownValidationHTML(amount, breakdownTotal, currency) {
	const difference = boqNumber(amount) - boqNumber(breakdownTotal);

	if (Math.abs(difference) <= BOQ_COST_BREAKDOWN_TOLERANCE) {
		return `
			<div class="cost-breakdown-status success">
				✓ Cost Breakdown matches Amount.
			</div>
		`;
	}

	return `
		<div class="cost-breakdown-status error">
			<b>Amount Mismatch</b><br>
			Amount:
			<b>${formatBoqCurrency(amount, currency)}</b>
			&nbsp;&nbsp;|&nbsp;&nbsp;
			Your Total:
			<b>${formatBoqCurrency(breakdownTotal, currency)}</b>
			&nbsp;&nbsp;|&nbsp;&nbsp;
			Difference:
			<b>${formatBoqCurrency(Math.abs(difference), currency)}</b>
		</div>
	`;
}

function getCostBreakdownMismatchLine(amount, breakdownTotal, currency) {
	const difference = boqNumber(amount) - boqNumber(breakdownTotal);

	if (Math.abs(difference) <= BOQ_COST_BREAKDOWN_TOLERANCE) {
		return "";
	}

	return `
		<div class="boq-cost-breakdown-mismatch-line">
			<style>
				.boq-cost-breakdown-mismatch-line {
					margin-top: 4px;
					padding-top: 4px;
					border-top: 1px solid #d1d5db;
					font-size: 11px;
					color: #6b7280;
					line-height: 1.4;
				}
				.boq-cost-breakdown-mismatch-line b:last-child {
					color: #dc2626;
				}
			</style>
			Cost Breakdown not matched with Amount. Amount: <b>${formatBoqCurrency(amount, currency)}</b>, Your Total: <b>${formatBoqCurrency(breakdownTotal, currency)}</b>, Difference: <b>${formatBoqCurrency(Math.abs(difference), currency)}</b>
		</div>
	`;
}

function getBoqCostBreakdownComponents(frm, row) {
	return (frm.doc.cost_components || []).filter((component) =>
		frm.boq_matches_item_component(component, row),
	);
}

function validateBoqCostBreakdownTotal(frm, row, breakdownAmount) {
	const amount = getBoqItemAmount(row);
	const total = boqNumber(breakdownAmount);

	if (Math.abs(amount - total) > BOQ_COST_BREAKDOWN_TOLERANCE) {
		return false;
	}

	return true;
}

function validateAllBoqCostBreakdowns(frm) {
	return (frm.doc.items || []).every((row) => {
		const components = getBoqCostBreakdownComponents(frm, row);
		if (!components.length) return true;

		const total = components.reduce(
			(sum, component) => sum + boqNumber(component.amount),
			0,
		);
		return validateBoqCostBreakdownTotal(frm, row, total);
	});
}

function getBoqItemLabel(row) {
	return row.item_name || row.item || __("selected item");
}

function showBoqItemValidation(message) {
	frappe.msgprint({
		title: __("Invalid BOQ Item Value"),
		indicator: "red",
		message: message,
	});
}

function validateBoqItemValues(row) {
	if (!row) return true;

	const item = getBoqItemLabel(row);

	if (!row.is_deleted_in_revision && boqNumber(row.qty) <= 0) {
		showBoqItemValidation(__("Qty for item {0} must be greater than 0.", [item]));
		return false;
	}

	if (boqNumber(row.margin_percent) < 0) {
		showBoqItemValidation(__("Margin % for item {0} cannot be negative.", [item]));
		return false;
	}

	if (boqNumber(row.unit_cost) < 0 || boqNumber(row.unit_rate) < 0) {
		showBoqItemValidation(__("Unit Cost/Rate for item {0} cannot be negative.", [item]));
		return false;
	}

	return true;
}

function validateGlobalMargin(frm, requireValue = false) {
	if (frm.doc.global_margin_percent === undefined || frm.doc.global_margin_percent === null || frm.doc.global_margin_percent === "") {
		if (!requireValue) {
			return true;
		}
		frappe.msgprint({
			title: __("Global Margin Required"),
			indicator: "orange",
			message: __("Please enter Global Margin % before applying."),
		});
		return false;
	}

	if (boqNumber(frm.doc.global_margin_percent) < 0) {
		frappe.msgprint({
			title: __("Invalid Global Margin"),
			indicator: "red",
			message: __("Global Margin % cannot be negative."),
		});
		return false;
	}

	return true;
}

function validateAllBoqItemValues(frm) {
	return (frm.doc.items || []).every((row) => validateBoqItemValues(row));
}

function canManageBoqRevisions() {
	return BOQ_REVISION_ROLES.some((role) => frappe.user.has_role(role));
}

function canWriteBoq(frm) {
	if (frm.has_perm) {
		return frm.has_perm("write");
	}
	return Boolean(frm.perm && frm.perm[0] && frm.perm[0].write);
}

function isActiveBoqItem(row) {
	return Boolean(row && !row.is_deleted_in_revision && row.item);
}

function applyGlobalMarginToItems(frm) {
	if (!validateGlobalMargin(frm, true)) return;

	const items = frm.doc.items || [];
	if (!items.length) {
		frappe.msgprint({
			title: __("No BOQ Items"),
			indicator: "orange",
			message: __("No BOQ items available."),
		});
		return;
	}

	const globalMargin = boqNumber(frm.doc.global_margin_percent);
	const activeItems = items.filter((row) => isActiveBoqItem(row));
	if (!activeItems.length) {
		frappe.msgprint({
			title: __("No BOQ Items"),
			indicator: "orange",
			message: __("No BOQ items available."),
		});
		return;
	}

	frappe.warn(
		__("Apply Global Margin"),
		__(
			"This will set Margin % to {0}% for all active BOQ items. Existing item-level margins will be overwritten. Continue?",
			[globalMargin],
		),
		function () {
			activeItems.forEach((row) => {
				row.margin_percent = globalMargin;
				calculateBoqRowAmounts(row);
			});

			recalculateBoqTotals(frm);
			frm.refresh_field("items");
			if (frm.boq_render_grid) {
				frm.boq_render_grid();
			}
			if (frm.dirty) {
				frm.dirty();
			}

			frappe.show_alert(
				{
					message: __("Global Margin % applied to active BOQ items. Click Save to keep changes."),
					indicator: "blue",
				},
				5,
			);
		},
		__("Apply"),
	);
}

function carryGlobalMarginToItems(frm) {
	if (!validateGlobalMargin(frm)) return;
	if (frm.doc.global_margin_percent === undefined || frm.doc.global_margin_percent === null || frm.doc.global_margin_percent === "") {
		return;
	}

	const items = frm.doc.items || [];
	if (!items.length) return;

	const globalMargin = boqNumber(frm.doc.global_margin_percent);
	const activeItems = items.filter((row) => isActiveBoqItem(row));
	if (!activeItems.length) return;

	activeItems.forEach((row) => {
		row.margin_percent = globalMargin;
		calculateBoqRowAmounts(row);
	});

	recalculateBoqTotals(frm);
	frm.refresh_field("items");
	if (frm.boq_render_grid) {
		frm.boq_render_grid();
	}
	if (frm.dirty) {
		frm.dirty();
	}
}

function addGlobalMarginButton(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0 || frm.doc.docstatus === 2) return;
	if (!canWriteBoq(frm)) return;

	frm.add_custom_button(
		__("Apply Global Margin to All Items"),
		function () {
			applyGlobalMarginToItems(frm);
		},
		__("Actions"),
	);
}

const BOQ_INVALID_SALES_ORDER_STATUSES = ["Closed", "Cancelled", "On Hold"];

function getBoqSalesOrderFilters(frm, options = {}) {
	const filters = [
		["Sales Order", "docstatus", "=", 1],
		["Sales Order", "status", "not in", BOQ_INVALID_SALES_ORDER_STATUSES],
	];
	const project =
		Object.prototype.hasOwnProperty.call(options, "project") ? options.project : frm.doc.project;
	const includeContractFilters = options.includeContractFilters !== false;

	if (includeContractFilters && frm.doc.client) {
		filters.push(["Sales Order", "customer", "=", frm.doc.client]);
	}
	if (project) {
		filters.push(["Sales Order", "project", "=", project]);
	}
	if (includeContractFilters && frm.doc.company) {
		filters.push(["Sales Order", "company", "=", frm.doc.company]);
	}

	return filters;
}

function applySalesOrderToBoq(frm) {
	if (!frm.doc.sales_order) return Promise.resolve();

	const selectedSalesOrder = frm.doc.sales_order;
	const previousApplyState = frm._boq_applying_sales_order;
	frm._boq_applying_sales_order = true;

	return frappe.db
		.get_value("Sales Order", selectedSalesOrder, [
			"customer",
			"project",
			"company",
			"currency",
		])
		.then((r) => {
			if (frm.doc.sales_order !== selectedSalesOrder) return;

			const salesOrder = r.message || {};
			const mappings = {
				client: salesOrder.customer,
				project: salesOrder.project,
				company: salesOrder.company,
				currency: salesOrder.currency,
			};
			const conflicts = [];
			const updates = [];

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
					title: __("Sales Order Mismatch"),
					indicator: "orange",
					message: __(
						"The following BOQ values differ from Sales Order {0}: {1}. Correct them before saving.",
						[selectedSalesOrder, conflicts.join(", ")],
					),
				});
			}

			return Promise.all(updates);
		})
		.finally(() => {
			frm._boq_applying_sales_order = previousApplyState;
		});
}

function getSalesOrdersForProject(frm, project) {
	return frappe.db.get_list("Sales Order", {
		filters: getBoqSalesOrderFilters(frm, {
			project: project,
			includeContractFilters: false,
		}),
		fields: ["name", "customer", "company", "currency", "transaction_date", "modified"],
		order_by: "transaction_date desc, modified desc",
		limit: 20,
	});
}

function showMultipleSalesOrdersForProject(project, salesOrders) {
	const orderList = (salesOrders || [])
		.slice(0, 10)
		.map((row) => `<li>${escapeBoqHtml(row.name)}</li>`)
		.join("");

	frappe.msgprint({
		title: __("Multiple Sales Orders"),
		indicator: "orange",
		message: __(
			"Project {0} has multiple submitted Sales Orders. Select the correct Sales Order in the Sales Order field.",
			[project],
		) + (orderList ? `<ul>${orderList}</ul>` : ""),
	});
}

function autoSelectSalesOrderForProject(frm) {
	if (frm._boq_applying_sales_order) return Promise.resolve();

	const selectedProject = frm.doc.project;
	const requestId = `${selectedProject || ""}:${Date.now()}:${Math.random()}`;
	frm._boq_project_sales_order_request = requestId;

	const clearSalesOrder = frm.doc.sales_order
		? frm.set_value("sales_order", "")
		: Promise.resolve();

	if (!selectedProject) {
		return clearSalesOrder;
	}

	return clearSalesOrder.then(() => {
		return getSalesOrdersForProject(frm, selectedProject).then((salesOrders) => {
			if (
				frm._boq_project_sales_order_request !== requestId ||
				frm.doc.project !== selectedProject
			) {
				return;
			}

			if (!salesOrders.length) {
				frappe.show_alert(
					{
						message: __("No submitted Sales Order found for Project {0}.", [
							selectedProject,
						]),
						indicator: "orange",
					},
					5,
				);
				return;
			}

			if (salesOrders.length > 1) {
				showMultipleSalesOrdersForProject(selectedProject, salesOrders);
				return;
			}

			frm._boq_skip_sales_order_apply = true;
			return frm
				.set_value("sales_order", salesOrders[0].name)
				.then(() => applySalesOrderToBoq(frm))
				.finally(() => {
					frm._boq_skip_sales_order_apply = false;
				});
		});
	});
}

function isSubmittedApprovedOrActiveBoq(frm) {
	const status = frm.doc.status || "";
	const revisionStatus = frm.doc.revision_status || "";
	return (
		frm.doc.docstatus === 1 ||
		frm.doc.is_active_revision ||
		["Submitted", "Approved", "Active"].includes(status) ||
		["Submitted", "Approved", "Active"].includes(revisionStatus)
	);
}

function escapeBoqHtml(value) {
	return frappe.utils.escape_html(String(value || ""));
}

function formatBoqDate(value) {
	return value ? frappe.datetime.str_to_user(value) : "";
}

function renderBoqRevisionHistory(rows) {
	const body = (rows || [])
		.map(
			(row) => `
				<tr>
					<td>${escapeBoqHtml(row.name)}</td>
					<td style="text-align:center">${escapeBoqHtml(row.revision_no)}</td>
					<td>${escapeBoqHtml(row.parent_boq)}</td>
					<td>${escapeBoqHtml(row.revision_status || row.status)}</td>
					<td style="text-align:center">${row.is_active_revision ? __("Yes") : ""}</td>
					<td>${formatBoqDate(row.active_from_date)}</td>
					<td>${formatBoqDate(row.active_to_date)}</td>
					<td>${escapeBoqHtml(row.superseded_by)}</td>
				</tr>`,
		)
		.join("");

	return `
		<div style="max-height:420px;overflow:auto">
			<table class="table table-bordered table-condensed">
				<thead>
					<tr>
						<th>${__("BOQ")}</th>
						<th style="text-align:center">${__("Rev")}</th>
						<th>${__("Previous")}</th>
						<th>${__("Status")}</th>
						<th style="text-align:center">${__("Active")}</th>
						<th>${__("Active From")}</th>
						<th>${__("Active To")}</th>
						<th>${__("Superseded By")}</th>
					</tr>
				</thead>
				<tbody>${body || `<tr><td colspan="8" class="text-muted text-center">${__("No revisions found.")}</td></tr>`}</tbody>
			</table>
		</div>`;
}

function renderBoqRevisionComparison(rows, currency) {
	const body = (rows || [])
		.map(
			(row) => `
				<tr>
					<td>${escapeBoqHtml(row.item_name || row.item || row.boq_item_key)}</td>
					<td>${escapeBoqHtml(row.status)}</td>
					<td style="text-align:right">${boqNumber(row.previous_qty).toFixed(2)}</td>
					<td style="text-align:right">${boqNumber(row.current_qty).toFixed(2)}</td>
					<td style="text-align:right">${boqNumber(row.qty_difference).toFixed(2)}</td>
					<td style="text-align:right">${formatBoqCurrency(row.previous_rate || 0, currency)}</td>
					<td style="text-align:right">${formatBoqCurrency(row.current_rate || 0, currency)}</td>
					<td style="text-align:right">${formatBoqCurrency(row.rate_difference || 0, currency)}</td>
					<td style="text-align:right">${formatBoqCurrency(row.amount_difference || 0, currency)}</td>
				</tr>`,
		)
		.join("");

	return `
		<div style="max-height:480px;overflow:auto">
			<table class="table table-bordered table-condensed">
				<thead>
					<tr>
						<th>${__("Item")}</th>
						<th>${__("Status")}</th>
						<th style="text-align:right">${__("Prev Qty")}</th>
						<th style="text-align:right">${__("Current Qty")}</th>
						<th style="text-align:right">${__("Qty Diff")}</th>
						<th style="text-align:right">${__("Prev Rate")}</th>
						<th style="text-align:right">${__("Current Rate")}</th>
						<th style="text-align:right">${__("Rate Diff")}</th>
						<th style="text-align:right">${__("Amount Diff")}</th>
					</tr>
				</thead>
				<tbody>${body || `<tr><td colspan="9" class="text-muted text-center">${__("No comparison rows found.")}</td></tr>`}</tbody>
			</table>
		</div>`;
}

function addBoqRevisionButtons(frm) {
	if (frm.is_new()) return;

	if (canManageBoqRevisions() && frm.doc.docstatus !== 2 && isSubmittedApprovedOrActiveBoq(frm)) {
		frm.add_custom_button(
			__("Create Revision"),
			function () {
				frappe.prompt(
					[
						{
							fieldname: "revision_reason",
							fieldtype: "Small Text",
							label: __("Revision Reason"),
							reqd: 1,
						},
					],
					function (values) {
						frappe.call({
							method: `${BOQ_METHOD}.create_revision`,
							args: {
								boq: frm.doc.name,
								revision_reason: values.revision_reason,
							},
							freeze: true,
							freeze_message: __("Creating BOQ Revision..."),
							callback: function (r) {
								if (!r.message) return;
								frappe.set_route("Form", "BOQ", r.message);
							},
						});
					},
					__("Create BOQ Revision"),
					__("Create"),
				);
			},
			__("Revision"),
		);
	}

	if (
		canManageBoqRevisions() &&
		frm.doc.docstatus === 1 &&
		!frm.doc.is_active_revision &&
		(frm.doc.revision_status === "Approved" || frm.doc.status === "Approved")
	) {
		frm.add_custom_button(
			__("Activate Revision"),
			function () {
				frappe.confirm(
					__("Activate this BOQ revision and supersede the other revisions in this chain?"),
					function () {
						frappe.call({
							method: `${BOQ_METHOD}.activate_revision`,
							args: {
								boq: frm.doc.name,
							},
							freeze: true,
							freeze_message: __("Activating BOQ Revision..."),
							callback: function () {
								frm.reload_doc();
							},
						});
					},
				);
			},
			__("Revision"),
		);
	}

	if (frm.doc.original_boq || frm.doc.parent_boq || (frm.doc.revisions || []).length) {
		frm.add_custom_button(
			__("View Revision History"),
			function () {
				frappe.call({
					method: `${BOQ_METHOD}.get_revision_history`,
					args: {
						boq: frm.doc.name,
					},
					callback: function (r) {
						frappe.msgprint({
							title: __("Revision History"),
							indicator: "blue",
							message: renderBoqRevisionHistory(r.message || []),
							wide: true,
						});
					},
				});
			},
			__("Revision"),
		);
	}

	if (frm.doc.parent_boq) {
		frm.add_custom_button(
			__("Compare with Previous Revision"),
			function () {
				frappe.call({
					method: `${BOQ_METHOD}.get_revision_comparison`,
					args: {
						boq: frm.doc.name,
					},
					callback: function (r) {
						frappe.msgprint({
							title: __("Revision Comparison"),
							indicator: "blue",
							message: renderBoqRevisionComparison(r.message || [], getBoqCurrency(frm)),
							wide: true,
						});
					},
				});
			},
			__("Revision"),
		);
	}
}

frappe.ui.form.on("BOQ", {
	setup: function (frm) {
		frm._boq_cat_state = {};
		frm._boq_sub_state = {};
		frm._boq_registered = [];
		frm.set_query("sales_order", function () {
			return { filters: getBoqSalesOrderFilters(frm) };
		});

		frm.boq_is_draft = function () {
			return frm.doc.docstatus === 0;
		};

		frm.boq_make_component_key = function () {
			return (
				"boq_item_" +
				Date.now().toString(36) +
				"_" +
				Math.random().toString(36).slice(2, 10)
			);
		};

		frm.boq_get_item_component_key = function (row) {
			return row.component_key || row.name;
		};

		frm.boq_matches_item_component = function (component, row) {
			if (!component || !row) return false;

			const key = frm.boq_get_item_component_key(row);

			return (
				component.boq_item === row.name ||
				component.boq_item === key ||
				component.boq_item === row.component_key ||
				component.boq_item === row.item ||
				component.item === row.item ||
				component.component_key === row.component_key ||
				component.component_key === key
			);
		};

		frm.boq_has_cost_breakdown = function (row) {
			return (frm.doc.cost_components || []).some((component) =>
				frm.boq_matches_item_component(component, row),
			);
		};

		frm.boq_prepare_component_keys = function () {
			const refs_to_migrate = {};

			(frm.doc.items || []).forEach((row) => {
				const oldRef = row.name;
				if (!row.component_key) {
					row.component_key = frm.boq_make_component_key();
				}
				if (!row.boq_item_key) {
					row.boq_item_key = row.component_key;
				}
				refs_to_migrate[oldRef] = row.component_key;
			});

			(frm.doc.cost_components || []).forEach((component) => {
				if (refs_to_migrate[component.boq_item]) {
					component.boq_item = refs_to_migrate[component.boq_item];
				}
			});

			frm.refresh_field("items");
			frm.refresh_field("cost_components");
		};

		frm.boq_get_item_price = async function (item) {
			let prices = [];

			try {
				prices = await frappe.db.get_list("Item Price", {
					filters: { item_code: item },
					fields: ["price_list_rate", "price_list", "valid_from", "modified"],
					order_by: "valid_from desc, modified desc",
					limit: 1,
				});
			} catch (error) {
				console.error("Unable to fetch BOQ Item Price", error);
			}

			if (prices && prices.length) {
				const price = parseFloat(prices[0].price_list_rate);
				if (!isNaN(price)) {
					return price;
				}
			}

			let itemRate = null;
			try {
				itemRate = await frappe.db.get_value("Item", item, "standard_rate");
			} catch (error) {
				console.error("Unable to fetch BOQ Item standard rate", error);
			}

			const standardRate = parseFloat(
				itemRate && itemRate.message && itemRate.message.standard_rate,
			);

			return isNaN(standardRate) ? 0 : standardRate;
		};

		// "Add item" dialog — called by the grid's Add item button
		frm.boq_add_item_dialog = function (subCatDoc, subCatName) {
			if (!frm.boq_is_draft()) {
				frappe.msgprint({
					title: __("Amend Required"),
					indicator: "orange",
					message: __("Please cancel and amend this BOQ before adding items."),
				});
				return;
			}

			var d;
			let itemFetchId = 0;
			d = new frappe.ui.Dialog({
				title: "Add Item — " + subCatName,
				fields: [
					{
						fieldname: "item",
						fieldtype: "Link",
						options: "Item",
						label: "Item",
						reqd: 1,
						onchange: async function () {
							const item = d.get_value("item");
							const fetchId = ++itemFetchId;

							if (!item) {
								d.set_value("item_name", "");
								d.set_value("uom", "Nos");
								d.set_value("unit_cost", 0);
								return;
							}

							let itemDetails = null;
							try {
								itemDetails = await frappe.db.get_value("Item", item, [
									"item_name",
									"stock_uom",
								]);
							} catch (error) {
								console.error("Unable to fetch BOQ item details", error);
							}

							if (fetchId !== itemFetchId) return;

							if (itemDetails && itemDetails.message) {
								d.set_value("item_name", itemDetails.message.item_name || item);
								d.set_value("uom", itemDetails.message.stock_uom || "Nos");
							}

							try {
								const unitCost = await frm.boq_get_item_price(item);

								if (fetchId !== itemFetchId) return;

								d.set_value("unit_cost", unitCost);
							} catch (error) {
								console.error("Unable to fetch BOQ item unit cost", error);
								if (fetchId === itemFetchId) {
									d.set_value("unit_cost", 0);
								}
							}
						},
					},
					{ fieldname: "item_name", fieldtype: "Data", label: "Item Name", reqd: 1 },
					{ fieldname: "col1", fieldtype: "Column Break" },
					{
						fieldname: "qty",
						fieldtype: "Float",
						label: "Quantity",
						reqd: 1,
						default: 1,
					},
					{
						fieldname: "uom",
						fieldtype: "Link",
						options: "UOM",
						label: "UOM",
						reqd: 1,
						default: "Nos",
					},
					{ fieldname: "sec1", fieldtype: "Section Break", label: "Rates" },
					{
						fieldname: "unit_cost",
						fieldtype: "Currency",
						label: "Unit Cost",
						default: 0,
						description:
							"Cost to contractor - fetched from Item Price or Item standard rate, editable",
					},
					{ fieldname: "col2", fieldtype: "Column Break" },
					{
						fieldname: "margin_percent",
						fieldtype: "Percent",
						label: "Margin %",
						default: boqNumber(frm.doc.global_margin_percent),
						description: "Your profit margin — hidden from client",
					},
					{ fieldname: "notes", fieldtype: "Small Text", label: "Notes" },
				],
				primary_action_label: "Add Item",
				primary_action: function (values) {
					const qty = parseFloat(values.qty) || 0;
					const margin = parseFloat(values.margin_percent) || 0;
					const unit_cost = parseFloat(values.unit_cost) || 0;
					const unit_rate = unit_cost * (1 + margin / 100);

					if (
						!validateBoqItemValues({
							item: values.item,
							item_name: values.item_name || values.item,
							qty: qty,
							unit_cost: unit_cost,
							margin_percent: margin,
							unit_rate: unit_rate,
						})
					) {
						return;
					}

					const newRow = frm.add_child("items");

					newRow.component_key = frm.boq_make_component_key();
					newRow.boq_item_key = newRow.component_key;
					newRow.boq_category = subCatDoc;
					newRow.item = values.item;
					newRow.item_name = values.item_name || values.item;

					newRow.qty = qty;
					newRow.uom = values.uom || "Nos";
					newRow.unit_cost = unit_cost;
					newRow.margin_percent = margin;

					newRow.unit_rate = unit_rate;
					calculateBoqRowAmounts(newRow);

					newRow.notes = values.notes || "";

					frm.refresh_field("items");
					frm.boq_render_grid();

					frappe.show_alert(
						{
							message: __("Item added. Click Save to keep changes."),
							indicator: "blue",
						},
						5,
					);

					d.hide();
				},
			});
			d.show();
		};
		// ── Cost breakdown dialog (click amount cell to open) ─────
		frm.boq_open_cost_breakdown = function (rowName) {
			const row = frm.doc.items.find((r) => r.name === rowName);
			if (!row) return;

			const isReadOnlyBreakdown = !frm.boq_is_draft();
			const rowComponentKey = frm.boq_get_item_component_key(row);
			const hasValidItem = !!(row.item && row.item.length > 0);

			const d = new frappe.ui.Dialog({
				title: `Cost Breakdown — ${row.item_name || row.item || "Item"}`,
				size: "large",
				fields: [
					{
						fieldname: "components_html",
						fieldtype: "HTML",
					},
					{
						fieldname: "save_as_default",
						fieldtype: "Check",
						label: hasValidItem
							? "Save this breakdown as default for this item (auto-fill in future BOQs)"
							: "Save as default (unavailable — this row has no valid Item link)",
						default: hasValidItem ? 1 : 0,
						read_only: hasValidItem && !isReadOnlyBreakdown ? 0 : 1,
					},
				],
				primary_action_label: isReadOnlyBreakdown ? "Close" : "Apply",
				primary_action: function (values) {
					if (isReadOnlyBreakdown) {
						d.hide();
						return;
					}

					const components = collectComponentsFromDialog();

					if (components.length === 0) {
						frappe.msgprint("Add at least one cost component before applying.");
						return;
					}

					const incomplete = components.some(
						(c) =>
							!c.component_type ||
							!c.description ||
							!c.uom ||
							(parseFloat(c.qty) || 0) <= 0 ||
							c.amount === "" ||
							c.amount === null ||
							c.amount === undefined,
					);
					if (incomplete) {
						frappe.msgprint(
							"Please fill in Type, Description, Quantity, UOM, and Rate for every row.",
						);
						return;
					}

					const total = components.reduce(
						(sum, c) => sum + (parseFloat(c.amount) || 0),
						0,
					);
					const itemRow = (frm.doc.items || []).find((r) => r.name === rowName);

					if (!itemRow) {
						frappe.msgprint(
							"BOQ Item row was not found. Please reload and try again.",
						);
						return;
					}

					if (!validateBoqCostBreakdownTotal(frm, itemRow, total)) {
						return;
					}

					const existingOtherComponents = (frm.doc.cost_components || [])
						.filter((c) => !frm.boq_matches_item_component(c, itemRow))
						.map((c) => ({
							boq_item: c.boq_item,
							component_type: c.component_type,
							description: c.description,
							qty: parseFloat(c.qty) || 1,
							uom: c.uom || "Nos",
							currency:
								getStoredRate(c, parseFloat(c.amount) || 0) ||
								(parseFloat(c.qty)
									? (parseFloat(c.amount) || 0) / parseFloat(c.qty)
									: 0),
							amount: parseFloat(c.amount) || 0,
						}));

					frm.clear_table("cost_components");

					existingOtherComponents.forEach((c) => {
						frm.add_child("cost_components", c);
					});

					components.forEach((c) => {
						frm.add_child("cost_components", {
							boq_item: rowComponentKey,
							component_type: c.component_type,
							description: c.description,
							qty: parseFloat(c.qty) || 1,
							uom: c.uom || "Nos",
							currency: parseFloat(c.rate) || 0,
							amount: parseFloat(c.amount) || 0,
						});
					});

					const newComponents = components.map((c) => ({
						component_type: c.component_type,
						description: c.description,
						qty: parseFloat(c.qty) || 1,
						uom: c.uom || "Nos",
						currency: parseFloat(c.rate) || 0,
						amount: parseFloat(c.amount) || 0,
					}));

					if (values.save_as_default && hasValidItem) {
						frappe.call({
							method: "construction_management.construction_management.api.save_item_default_cost_components",
							args: {
								item: row.item,
								components: JSON.stringify(newComponents),
							},
							callback: function (r) {
								if (r.message && r.message.status === "success") {
								}
							},
						});
					}

					frm.refresh_field("items");
					frm.refresh_field("cost_components");
					frm.boq_render_grid();

					frappe.show_alert(
						{
							message: __("Cost Breakdown updated. Click Save to keep changes."),
							indicator: "blue",
						},
						5,
					);

					d.hide();
				},
			});

			let dialogComponents = getPersistedComponents();

			function getPersistedComponents() {
				return (frm.doc.cost_components || [])
					.filter((c) => frm.boq_matches_item_component(c, row))
					.map((c) =>
						normalizeComponent({
							component_type: c.component_type || "Labour",
							description: c.description || "",
							qty: parseFloat(c.qty) || 1,
							uom: c.uom || "Nos",
							rate: c.rate,
							currency: c.currency,
							amount: parseFloat(c.amount) || 0,
						}),
					);
			}

			function getComponentNumber(value, fallback) {
				const parsed = parseFloat(value);
				return isNaN(parsed) ? fallback : parsed;
			}

			function getStoredRate(component, amount) {
				const rateValue =
					component.rate !== undefined &&
					component.rate !== null &&
					component.rate !== ""
						? component.rate
						: component.currency;
				const parsed = parseFloat(rateValue);

				if (isNaN(parsed)) {
					return null;
				}

				if (parsed === 0 && amount) {
					return null;
				}

				return parsed;
			}

			function getItemBreakdownAmount(itemRow) {
				return (frm.doc.cost_components || [])
					.filter((component) => frm.boq_matches_item_component(component, itemRow))
					.reduce((sum, component) => sum + (parseFloat(component.amount) || 0), 0);
			}

			function normalizeComponent(component) {
				const qty = getComponentNumber(component.qty, 1);
				const savedAmount = getComponentNumber(component.amount, 0);
				const storedRate = getStoredRate(component, savedAmount);
				const rate = storedRate !== null ? storedRate : qty ? savedAmount / qty : 0;
				const amount = qty * rate;

				return {
					component_type: component.component_type || "Labour",
					description: component.description || "",
					qty: qty,
					uom: component.uom || "Nos",
					rate: rate,
					amount: amount,
				};
			}

			function updateDialogComponent(idx, values) {
				if (!dialogComponents[idx]) return;
				dialogComponents[idx] = normalizeComponent({
					...dialogComponents[idx],
					...values,
				});
			}

			function escapeHtml(value) {
				return frappe.utils.escape_html(String(value || ""));
			}

			function buildComponentRow(component, idx) {
				const typeColors = {
					Labour: "#4f46e5",
					Material: "#16a34a",
					Equipment: "#d97706",
					Subcontract: "#db2777",
					Other: "#6b7280",
				};
				const componentGridColumns = "112px minmax(180px,1fr) 72px 82px 92px 104px 54px";
				const controlStyle =
					"height:34px;font-size:13px;width:100%;min-width:0;box-sizing:border-box;border:1px solid #d1d5db;border-radius:6px;background:#ffffff;padding:6px 10px;color:#111827;";
				const numberControlStyle = controlStyle + "text-align:right;";
				const normalized = normalizeComponent(component);
				const type = normalized.component_type;
				const qty = normalized.qty;
				const uom = normalized.uom;
				const rate = normalized.rate;
				const amount = normalized.amount;
				const disabledAttr = isReadOnlyBreakdown ? "disabled" : "";
				const borderColor = typeColors[type] || "#6b7280";
				const uomHtml = isReadOnlyBreakdown
					? `<span style="display:block;width:100%;height:34px;box-sizing:border-box;text-align:center;font-size:13px;background:#ffffff !important;color:#111827;border:1px solid #d1d5db;border-radius:6px;padding:6px 10px;">${escapeHtml(uom || "Nos")}</span>`
					: `<div class="uom-dropdown-field" style="position:relative;width:100%;min-width:0;">
    <div class="comp-uom-control" data-idx="${idx}" data-value="${escapeHtml(uom)}" style="width:100%;min-width:0;"></div>
    <span style="position:absolute;right:10px;top:50%;transform:translateY(-50%);color:#64748b;font-size:12px;pointer-events:none;z-index:2;">
        <i class="fa fa-chevron-down"></i>
    </span>
</div>`;

				return `
<div class="comp-row" data-idx="${idx}" data-uom="${escapeHtml(uom)}" style="
    display:grid;
    grid-template-columns:${componentGridColumns};
    gap:10px;
    align-items:center;
    padding:9px 10px;
    margin-bottom:8px;
    border-left:4px solid ${borderColor};
    background:#f5f6f8;
    border-radius:6px;
    box-sizing:border-box;
">
    <div style="position:relative;width:100%;min-width:0;">
        <select class="form-control comp-type" data-idx="${idx}" ${disabledAttr}
            style="${controlStyle}text-align:left;padding-right:30px;appearance:none;-webkit-appearance:none;-moz-appearance:none;">
            <option value="Labour" ${type === "Labour" ? "selected" : ""}>Labour</option>
            <option value="Material" ${type === "Material" ? "selected" : ""}>Material</option>
            <option value="Equipment" ${type === "Equipment" ? "selected" : ""}>Equipment</option>
            <option value="Subcontract" ${type === "Subcontract" ? "selected" : ""}>Subcontract</option>
            <option value="Other" ${type === "Other" ? "selected" : ""}>Other</option>
        </select>
        <span style="position:absolute;right:10px;top:50%;transform:translateY(-50%);color:#64748b;pointer-events:none;font-size:12px;">
            <i class="fa fa-chevron-down"></i>
        </span>
    </div>
    <input type="text" class="form-control comp-desc" data-idx="${idx}" ${disabledAttr}
        value="${escapeHtml(component.description)}"
        placeholder="Description"
        style="${controlStyle}text-align:left;">

    <input type="number" class="form-control comp-qty" data-idx="${idx}" ${disabledAttr}
        value="${qty}"
        placeholder="Qty"
        style="${numberControlStyle}">

    ${uomHtml}

    <input type="number" class="form-control comp-rate" data-idx="${idx}" ${disabledAttr}
        value="${rate}"
        placeholder="Rate"
        style="${numberControlStyle}">

    <input type="number" class="form-control comp-amount" data-idx="${idx}"
        value="${amount}"
        readonly
        style="${numberControlStyle}font-weight:600;background:#f1f5f9;">
    <button class="btn btn-xs comp-remove" data-idx="${idx}" title="Remove" ${disabledAttr}
        style="border:none;background:transparent;color:#ef4444;width:28px;height:28px;display:flex;align-items:center;justify-content:center;cursor:${isReadOnlyBreakdown ? "not-allowed" : "pointer"};margin:0 auto;padding:0;opacity:${isReadOnlyBreakdown ? "0.35" : "1"};">
        <i class="fa fa-times"></i>
    </button>
</div>`;
			}

			function updateDialogTotal() {
				const wrapper = d.fields_dict.components_html.$wrapper;
				const total = dialogComponents.reduce(
					(sum, component) => sum + (parseFloat(component.amount) || 0),
					0,
				);
				wrapper
					.find(".comp-total-value")
					.html(formatBoqCurrency(total, getBoqCurrency(frm)));
				
				// Update mismatch line
				const mismatchLineHtml = getCostBreakdownMismatchLine(
					getBoqItemAmount(row),
					total,
					getBoqCurrency(frm),
				);
				const existingMismatchLine = wrapper.find(".boq-cost-breakdown-mismatch-line");
				if (mismatchLineHtml) {
					if (existingMismatchLine.length) {
						existingMismatchLine.replaceWith(mismatchLineHtml);
					} else {
						wrapper.find(".boq-cost-breakdown-wrapper").append(mismatchLineHtml);
					}
				} else {
					existingMismatchLine.remove();
				}
			}

			function recalculateDialogRow(rowEl) {
				const idx = parseInt(rowEl.attr("data-idx"));
				const qty = parseFloat(rowEl.find(".comp-qty").val()) || 0;
				const rate = parseFloat(rowEl.find(".comp-rate").val()) || 0;
				const amount = qty * rate;

				updateDialogComponent(idx, { qty: qty, rate: rate, amount: amount });
				rowEl.find(".comp-amount").val(dialogComponents[idx].amount);
				updateDialogTotal();
			}

			function collectComponentsFromDialog() {
				return dialogComponents.map((component) => normalizeComponent(component));
			}

			function bindComponentEvents() {
				const wrapper = d.fields_dict.components_html.$wrapper;

				wrapper.off(".boq_cost_breakdown");
				initializeUomControls();

				wrapper.on("click.boq_cost_breakdown", "#add-component-btn", function () {
					if (!frm.boq_is_draft()) {
						frappe.msgprint({
							title: __("Amend Required"),
							indicator: "orange",
							message: __(
								"Please cancel and amend this BOQ before adding cost components.",
							),
						});
						return;
					}

					dialogComponents.push(
						normalizeComponent({
							component_type: "Labour",
							description: "",
							qty: 1,
							uom: "Nos",
							rate: 0,
							amount: 0,
						}),
					);
					renderComponentsTable();
					setTimeout(() => {
						d.fields_dict.components_html.$wrapper.find(".comp-desc").last().focus();
					}, 0);
				});

				wrapper.on("click.boq_cost_breakdown", ".comp-remove", function () {
					if (!frm.boq_is_draft()) {
						frappe.msgprint({
							title: __("Amend Required"),
							indicator: "orange",
							message: __(
								"Please cancel and amend this BOQ before removing cost components.",
							),
						});
						return;
					}

					const idx = parseInt($(this).closest(".comp-row").attr("data-idx"));
					dialogComponents.splice(idx, 1);
					renderComponentsTable();
				});

				wrapper.on(
					"input.boq_cost_breakdown change.boq_cost_breakdown",
					".comp-type, .comp-desc",
					function () {
						const rowEl = $(this).closest(".comp-row");
						const idx = parseInt(rowEl.attr("data-idx"));
						updateDialogComponent(idx, {
							component_type: rowEl.find(".comp-type").val(),
							description: rowEl.find(".comp-desc").val(),
						});
					},
				);

				wrapper.on(
					"input.boq_cost_breakdown change.boq_cost_breakdown",
					".comp-qty, .comp-rate",
					function () {
						recalculateDialogRow($(this).closest(".comp-row"));
					},
				);
			}

			function initializeUomControls() {
				if (isReadOnlyBreakdown) {
					return;
				}

				const wrapper = d.fields_dict.components_html.$wrapper;

				wrapper.find(".comp-uom-control").each(function () {
					const parent = $(this);
					const idx = parseInt(parent.data("idx"));
					const rowEl = parent.closest(".comp-row");
					const currentValue =
						(dialogComponents[idx] && dialogComponents[idx].uom) ||
						rowEl.attr("data-uom") ||
						parent.attr("data-value") ||
						"Nos";

					parent.empty();
					rowEl.attr("data-uom", currentValue);

					const control = frappe.ui.form.make_control({
						parent: parent,
						df: {
							fieldtype: "Link",
							options: "UOM",
							fieldname: "uom_" + idx,
							placeholder: "UOM",
							read_only: isReadOnlyBreakdown ? 1 : 0,
							onchange: function () {
								const value = control.get_value() || "Nos";
								rowEl.attr("data-uom", value);
								updateDialogComponent(idx, { uom: value });
							},
						},
						render_input: true,
					});

					control.refresh();

					control.$wrapper.css({
						width: "100%",
						minWidth: "0",
					});

					control.$input.css({
						width: "100%",
						height: "34px",
						fontSize: "13px",
						boxSizing: "border-box",
						textAlign: "center",
						border: "1px solid #d1d5db",
						borderRadius: "6px",
						background: "#ffffff",
						padding: "6px 28px 6px 10px",
						color: "#111827",
					});

					control.$input.attr(
						"style",
						(control.$input.attr("style") || "") +
							";background:#ffffff !important;color:#111827;border:1px solid #d1d5db;border-radius:6px;",
					);

					control.$wrapper.find(".control-input").css({
						display: "block",
						width: "100%",
					});

					setTimeout(() => {
						const value =
							(dialogComponents[idx] && dialogComponents[idx].uom) ||
							currentValue ||
							"Nos";
						const setValuePromise = control.set_value(value);
						if (control.$input) {
							control.$input.val(value);
						}
						Promise.resolve(setValuePromise).then(() => {
							if (control.$input) {
								control.$input.val(value);
							}
						});
						rowEl.attr("data-uom", value);
						updateDialogComponent(idx, { uom: value });
					}, 0);
				});
			}

			function renderComponentsTable() {
				const wrapper = d.fields_dict.components_html.$wrapper;
				const componentGridColumns = "112px minmax(180px,1fr) 72px 82px 92px 104px 54px";
				const headerStyle =
					"font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em;text-align:center;";
				dialogComponents = dialogComponents.map((c) => normalizeComponent(c));
				const components = dialogComponents;
				const rowsHtml = components.map((c, idx) => buildComponentRow(c, idx)).join("");
				const total = components.reduce((sum, c) => sum + (parseFloat(c.amount) || 0), 0);

				wrapper.html(`
	        <style>
	            .boq-cost-breakdown-wrapper .control-input {
	                display: block !important;
	                width: 100% !important;
	            }
	            .boq-cost-breakdown-wrapper .frappe-control {
	                margin-bottom: 0 !important;
	            }
	        </style>
	        <div class="boq-cost-breakdown-wrapper">
	            <div style="margin-bottom:10px;width:100%;">
	                <div style="
	                    display:grid;
	                    grid-template-columns:${componentGridColumns};
	                    gap:10px;
	                    align-items:center;
	                    padding:0 10px 10px 10px;
	                    margin-bottom:6px;
	                ">
	                    <div style="${headerStyle}">TYPE</div>
	                    <div style="${headerStyle}">DESCRIPTION</div>
	                    <div style="${headerStyle}">QTY</div>
	                    <div style="${headerStyle}">UOM</div>
	                    <div style="${headerStyle}">RATE</div>
	                    <div style="${headerStyle}">AMOUNT</div>
	                    <div style="${headerStyle}">REMOVE</div>
	                </div>

	                <div id="comp-rows-body">
	                    ${rowsHtml || '<div class="empty-components" style="text-align:center;color:var(--text-muted);font-size:13px;padding:28px 12px;border:1.5px dashed var(--border-color);border-radius:8px">No components yet. Click <b>+ Add Component</b> below to start.</div>'}
	                </div>
	            </div>

	            <div style="margin-top:12px;">
	                <button class="btn btn-sm btn-default" id="add-component-btn" ${isReadOnlyBreakdown ? "disabled" : ""}
	                    style="${isReadOnlyBreakdown ? "cursor:not-allowed;opacity:.55;" : ""}">
	                    <i class="fa fa-plus"></i>&nbsp; Add Component
	                </button>
	            </div>

	            <div style="
	                margin-top:14px;
	                padding:10px 14px;
	                background:var(--control-bg, #f5f6f8);
	                border-radius:6px;
	                display:flex;
	                justify-content:space-between;
	                align-items:center;
	            ">
	                <span style="font-size:12px;color:var(--text-muted)">Total Amount</span>
	                <span class="comp-total-value" style="font-size:16px;font-weight:600;color:var(--text-color)">
	                    ${formatBoqCurrency(total, getBoqCurrency(frm))}
	                </span>
	            </div>
	            ${getCostBreakdownMismatchLine(getBoqItemAmount(row), total, getBoqCurrency(frm))}
	        </div>
	    `);
				setTimeout(() => bindComponentEvents(), 0);
			}

			d.show();
			renderComponentsTable();
		};

		// ── Main grid render ──────────────────────────────────────────
		frm.boq_render_grid = function () {
			frm.fields_dict["items"].$wrapper.hide();

			let container = $(frm.wrapper).find("#boq-custom-grid");
			if (!container.length) {
				frm.fields_dict["items"].$wrapper
					.closest(".form-column")
					.append('<div id="boq-custom-grid" style="margin-top:16px"></div>');
				container = $(frm.wrapper).find("#boq-custom-grid");
			}

			const items = frm.doc.items || [];
			const CUR = getBoqCurrency(frm);
			const isDraft = frm.boq_is_draft();

			// Empty state - no items and no registered (pending) categories
			if (!items.length && !frm._boq_registered.length) {
				container.html(`
                    <div style="border:1px solid var(--border-color);border-radius:var(--border-radius);overflow:hidden">
                        <div style="padding:12px 16px;text-align:center;color:var(--text-muted);font-size:13px">
                            No items yet. Add an item directly or start with a category.
                        </div>
                        <div style="padding:10px 16px;border-top:1px solid var(--border-color)">
                            <button class="btn btn-xs btn-default boq-add-root-item-btn" style="width:100%;margin-bottom:8px" ${isDraft ? "" : "disabled"}>
                                <i class="fa fa-plus"></i> Add Item
                            </button>
                            <button class="btn btn-xs btn-default boq-add-cat-btn" style="width:100%" ${isDraft ? "" : "disabled"}>
                                <i class="fa fa-plus"></i> Add Category
                            </button>
                        </div>
                    </div>`);
				container
					.find(".boq-add-root-item-btn")
					.on("click", () => frm.boq_add_item_dialog("", __("BOQ")));
				container.find(".boq-add-cat-btn").on("click", () => frm._boq_show_add_cat());
				return;
			}

			// Collect unique category doc names from saved items for name lookup
			const catDocs = [...new Set(items.map((r) => r.boq_category).filter(Boolean))];

			frappe.db
				.get_list("BOQ Category", {
					filters: [["name", "in", catDocs.length ? catDocs : ["__none__"]]],
					fields: ["name", "category_name", "parent_node"],
					limit: 500,
				})
				.then((catList) => {
					const catMap = {};
					catList.forEach((c) => {
						catMap[c.name] = c;
					});

					// ── Build flexible structure ──────────────────────────
					// parentOrder: insertion-ordered array of parent doc keys
					// structure[pKey] = { name, directItems[], subcats: { subKey: { name, items[] } } }
					const parentOrder = [];
					const rootItems = [];
					const structure = {};

					function ensureParent(pKey, pName) {
						if (!structure[pKey]) {
							structure[pKey] = { name: pName, directItems: [], subcats: {} };
							parentOrder.push(pKey);
						}
					}

					function ensureSub(pKey, pName, subKey, subName) {
						ensureParent(pKey, pName);
						if (!structure[pKey].subcats[subKey]) {
							structure[pKey].subcats[subKey] = { name: subName, items: [] };
						}
					}

					// 1. Registered empty stubs (added via "Add category" / "Add sub-category")
					frm._boq_registered.forEach((reg) => {
						if (reg.subDoc !== "__placeholder__") {
							ensureSub(reg.parentDoc, reg.parentName, reg.subDoc, reg.subName);
						} else {
							ensureParent(reg.parentDoc, reg.parentName);
						}
					});

					// 2. Actual saved items
					items.forEach((row) => {
						if (!row.boq_category) {
							rootItems.push(row);
							return;
						}

						const info = catMap[row.boq_category] || {};
						const categoryName = info.category_name || row.boq_category;
						const parentDoc = info.parent_node || null;

						if (parentDoc) {
							const parentName =
								row.boq_parent_category ||
								(parentDoc && catMap[parentDoc] && catMap[parentDoc].category_name) ||
								parentDoc;

							ensureSub(parentDoc, parentName, row.boq_category, categoryName);
							structure[parentDoc].subcats[row.boq_category].items.push(row);
							return;
						}

						ensureParent(row.boq_category, categoryName);
						structure[row.boq_category].directItems.push(row);
					});

					// ── Formatters ─────────────────────────────────────────
					const fmt2 = (n) =>
						parseFloat(n || 0).toLocaleString("en-AE", {
							minimumFractionDigits: 2,
							maximumFractionDigits: 2,
						});

					function buildCostTooltip(row) {
						const components = (frm.doc.cost_components || []).filter((c) =>
							frm.boq_matches_item_component(c, row),
						);
						if (!components.length) {
							return "No cost breakdown — click to add";
						}
						const lines = components.map(
							(c) =>
								`${c.component_type}: ${c.description} = ${formatBoqCurrency(c.amount || 0, CUR)}`,
						);
						const total = components.reduce(
							(sum, c) => sum + (parseFloat(c.amount) || 0),
							0,
						);
						lines.push("---");
						lines.push(`Total: ${formatBoqCurrency(total, CUR)}`);
						return lines.join("\n");
					}

					const inlineNumberInputStyle =
						"width:70px;max-width:90%;height:26px;text-align:center;font-size:11px;padding:2px 4px;box-sizing:border-box;border:2px solid var(--border-color);border-radius:4px;background:var(--input-bg,#fff);color:var(--text-color);margin-left:13px";

					function getNumberValue(value) {
						const parsed = parseFloat(value);
						return isNaN(parsed) ? 0 : parsed;
					}

					function renderInlineNumber(row, className, value) {
						return `
    <input type="number"
        class="form-control ${className}"
        data-name="${row.name}"
        value="${getNumberValue(value)}"
        step="any"
        inputmode="decimal"
        style="${inlineNumberInputStyle}">`;
					}

					function renderQty(row) {
						if (!isDraft) {
							return fmt2(row.qty);
						}

						return renderInlineNumber(row, "boq-inline-qty", row.qty);
					}

					function renderUnitCost(row) {
						if (!isDraft) {
							return formatBoqCurrency(row.unit_cost, CUR);
						}

						return renderInlineNumber(row, "boq-unit-cost", row.unit_cost);
					}

					function renderMargin(row) {
						if (!isDraft) {
							return `${fmt2(row.margin_percent)}%`;
						}

						return renderInlineNumber(row, "boq-inline-margin", row.margin_percent);
					}

					function showInlineUpdateAlert() {
						frappe.show_alert(
							{
								message: __("Changes updated. Click Save to keep changes."),
								indicator: "blue",
							},
							5,
						);
					}

					function recalculateInlineRow(row) {
						calculateBoqRowAmounts(row);
					}

					function renderItemsTable(rows, indentPadding) {
						if (!rows.length) return "";

						let tableHtml = `
<table style="
    width:100%;
    border-collapse:collapse;
    table-layout:fixed;
    font-size:10px;
    line-height:1.2;
">

<thead>
<tr style="background:var(--control-bg);border-bottom:1px solid var(--border-color)">

<th style="width:5%;text-align:center;padding:8px;">S.NO</th>

<th style="width:25%;text-align:left;padding:8px;">
    DESCRIPTION
</th>

<th style="width:7%;text-align:center;padding:8px;">
    QTY
</th>

<th style="width:7%;text-align:center;padding:8px;">
    UOM
</th>

<th style="width:11%;text-align:center;padding:8px;">
    UNIT COST
</th>

<th style="width:8%;text-align:center;padding:8px;">
    MARGIN %
</th>

<th style="width:12%;text-align:center;padding:8px;">
    AMOUNT
</th>

<th style="width:14%;text-align:center;padding:8px;">
    Costing Amount
</th>

<th style="width:6%;text-align:center;padding:8px;">
    ACTION
</th>

</tr>
</thead>

<tbody>
`;

						rows.forEach((row, idx) => {
							tableHtml += `
<tr style="
    border-bottom:1px solid var(--border-color);
    height:42px;
">

<td style="text-align:center;padding:6px 4px;">
    ${idx + 1}
</td>

<td style="text-align:left;padding:6px 8px 6px ${indentPadding}px;word-break:break-word;">
    ${row.item_name || row.item || ""}
    ${row.notes ? `<div style="font-size:10px;color:var(--text-muted)">${row.notes}</div>` : ""}
</td>

<td style="text-align:center;white-space:nowrap;">
    ${renderQty(row)}
</td>

<td style="text-align:center;white-space:nowrap;">
    ${row.uom || ""}
</td>

<td style="
    text-align:center;
    white-space:nowrap;
">
    ${renderUnitCost(row)}
</td>

<td style="
    text-align:center;
    white-space:nowrap;
    font-size:11px;
    overflow:hidden;
    text-overflow:ellipsis;
">
    ${renderMargin(row)}
</td>

<td style="
    text-align:center;
    white-space:nowrap;
    font-weight:600;
    color:var(--primary);
    cursor:pointer;
"
class="boq-cost-breakdown-trigger"
data-name="${row.name}"
title="${buildCostTooltip(row).replace(/"/g, "&quot;")}">
    <span style="
        display:flex;
        justify-content:center;
        align-items:center;
        gap:6px;
    ">
        <span>${formatBoqCurrency(getBoqItemAmount(row), CUR)}</span>
	        ${
				frm.boq_has_cost_breakdown(row)
					? `<i class="fa fa-list-ul" style="font-size:10px;color:#3b82f6"></i>`
					: `<i class="fa fa-plus-circle" style="font-size:10px;color:#9ca3af"></i>`
			}
    </span>
</td>

<td style="
    text-align:center;
    white-space:nowrap;
    font-weight:600;
    color:var(--primary);
">
    ${formatBoqCurrency(getBoqAmountAfterMargin(row), CUR)}
</td>

<td style="text-align:center;white-space:nowrap;">
    <button class="boq-del-btn"
        data-name="${row.name}"
        style="
            background:none;
            border:none;
            color:#ef4444;
            cursor:pointer;
            display:inline-flex;
            align-items:center;
            justify-content:center;
            width:24px;
            height:24px;
        ">
        <i class="fa fa-times"></i>
    </button>
</td>

</tr>
`;
						});

						tableHtml += `
</tbody>
</table>
`;
						return tableHtml;
					}

					function renderSubtotal(label, amount, padding) {
						return `
<div style="
    display:grid;
    grid-template-columns:28px 1fr 160px 28px;
    padding:8px 14px 8px ${padding}px;
    background:#162d52;
    border-top:2px solid #c9a520;
    border-bottom:1px solid #1e3356;
    align-items:center;
">

    <span></span>

    <span style="
        font-size:10px;
        font-weight:600;
        color:#a0b0c8;
        letter-spacing:.4px;
        text-transform:uppercase;
    ">
        SUBTOTAL - ${label.toUpperCase()}
    </span>

    <div style="
        display:flex;
        justify-content:center;
        align-items:center;
        width:100%;
        font-size:13px;
        font-weight:700;
        color:#ffffff;
        white-space:nowrap;
        font-variant-numeric: tabular-nums;
    ">
        ${formatBoqCurrency(amount, CUR)}
    </div>

    <span></span>

</div>`;
					}

					// ── Build HTML ──────────────────────────────────────────
					let html = `<div style="border:1px solid var(--border-color);border-radius:var(--border-radius);overflow:hidden;font-family:var(--font-stack);font-size:12px">`;

					if (rootItems.length) {
						const rootTotal = rootItems.reduce(
							(a, r) => a + getBoqAmountAfterMargin(r),
							0,
						);
						html += `
                    <div style="display:flex;align-items:center;gap:8px;padding:9px 14px;background:#f8fafc;border-bottom:1px solid var(--border-color)">
                        <span style="font-weight:600;color:var(--text-color);font-size:12px;flex:1">BOQ Items</span>
                        <span style="font-weight:600;color:#c9a520;font-size:12px">${formatBoqCurrency(rootTotal, CUR)}</span>
                    </div>`;
						html += renderItemsTable(rootItems, 8);
					}

					html += `
                <div style="padding:8px 14px;background:var(--control-bg);border-bottom:1px solid var(--border-color)">
                    <button class="boq-add-item-btn"
                            data-subdoc=""
                            data-subname="${encodeURIComponent(__("BOQ"))}"
                            ${isDraft ? "" : "disabled"}
                            style="display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:500;color:var(--text-muted);background:none;border:none;cursor:pointer;padding:3px 6px;border-radius:4px">
                        <i class="fa fa-plus"></i> Add item
                    </button>
                </div>`;

					parentOrder.forEach((pKey) => {
						const cat = structure[pKey];
						const subKeys = Object.keys(cat.subcats);
						const directTotal = cat.directItems.reduce(
							(a, r) => a + getBoqAmountAfterMargin(r),
							0,
						);
						const subTotal = subKeys.reduce(
							(a, s) =>
								a +
								cat.subcats[s].items.reduce(
									(b, r) => b + getBoqAmountAfterMargin(r),
									0,
								),
							0,
						);
						const catTotal = directTotal + subTotal;
						const catOpen = frm._boq_cat_state[pKey] !== false;

						html += `
                    <div class="boq-cat-hd" data-pkey="${pKey}"
                         style="display:flex;align-items:center;gap:8px;padding:10px 14px;background:#0F1E38;cursor:pointer;border-bottom:1px solid #1a3057">
                        <i class="fa fa-chevron-down"
                           style="color:#a0b0c8;font-size:11px;transition:transform .2s;${catOpen ? "" : "transform:rotate(-90deg)"}"></i>
                        <span style="font-weight:600;color:#fff;font-size:12px;flex:1">${cat.name.toUpperCase()}</span>
                        <span style="font-weight:600;color:#c9a520;font-size:12px">${formatBoqCurrency(catTotal, CUR)}</span>
                    </div>`;

						if (catOpen) {
							if (cat.directItems.length) {
								html += renderItemsTable(cat.directItems, 16);
							}

							html += `
                        <div style="padding:8px 14px 8px 28px;background:var(--control-bg);border-bottom:1px solid var(--border-color)">
                            <button class="boq-add-item-btn"
                                    data-subdoc="${encodeURIComponent(pKey)}"
                                    data-subname="${encodeURIComponent(cat.name)}"
                                    ${isDraft ? "" : "disabled"}
                                    style="display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:500;color:var(--text-muted);background:none;border:none;cursor:pointer;padding:3px 6px;border-radius:4px">
                                <i class="fa fa-plus"></i> Add item
                            </button>
                        </div>`;

							subKeys.forEach((subKey) => {
								const sub = cat.subcats[subKey];
								const currentSubTotal = sub.items.reduce(
									(a, r) => a + getBoqAmountAfterMargin(r),
									0,
								);
								const subOpen = frm._boq_sub_state[subKey] !== false;

								html += `
                            <div class="boq-sub-hd" data-subkey="${subKey}"
                                 style="display:flex;align-items:center;gap:8px;padding:8px 14px 8px 28px;background:#1a2d48;cursor:pointer;border-bottom:1px solid #1e3356">
	                                <i class="fa fa-chevron-down"
	                                   style="color:#5b7fa6;font-size:10px;transition:transform .2s;${subOpen ? "" : "transform:rotate(-90deg)"}"></i>
	                                <span style="font-weight:600;color:#c8d8ec;font-size:11px;flex:1">${sub.name}</span>
	                                <span style="color:#7090b8;font-size:11px">${formatBoqCurrency(currentSubTotal, CUR)}</span>
	                            </div>`;

								if (subOpen) {
									html += renderItemsTable(sub.items, 28);
									html += renderSubtotal(sub.name, currentSubTotal, 28);

									// Add item button
									html += `
                                <div style="padding:8px 14px 8px 28px;background:var(--control-bg);border-bottom:1px solid var(--border-color)">
                                    <button class="boq-add-item-btn"
                                            data-subdoc="${encodeURIComponent(subKey)}"
                                            data-subname="${encodeURIComponent(sub.name)}"
                                            ${isDraft ? "" : "disabled"}
                                            style="display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:500;color:var(--text-muted);background:none;border:none;cursor:pointer;padding:3px 6px;border-radius:4px">
                                        <i class="fa fa-plus"></i> Add item
	                                    </button>
	                                </div>`;
								}
							});

							if (cat.directItems.length || subKeys.length) {
								html += renderSubtotal(cat.name, catTotal, 28);
							}

							// Add sub-category button
							html += `
                        <div style="padding:8px 14px 8px 28px;background:#f0f4ff;border-bottom:1px solid #c7d2fe">
                            <button class="boq-add-subcat-btn"
                                    data-pkey="${encodeURIComponent(pKey)}"
                                    data-pname="${encodeURIComponent(cat.name)}"
                                    ${isDraft ? "" : "disabled"}
                                    style="display:inline-flex;align-items:center;gap:4px;color:#3730A3;background:none;border:none;cursor:pointer;font-size:11px;font-weight:500;padding:3px 6px;border-radius:4px">
                                <i class="fa fa-plus"></i> Add sub-category to ${cat.name}
                            </button>
	                        </div>`;
						}
					});

					// Add category button
					html += `
	                <div style="padding:10px 16px">
	                    <button class="boq-add-cat-btn" ${isDraft ? "" : "disabled"}
                            style="width:100%;display:flex;align-items:center;justify-content:center;gap:6px;padding:8px;border:1.5px dashed var(--border-color);border-radius:var(--border-radius);background:transparent;color:var(--text-muted);font-size:12px;font-weight:500;cursor:${isDraft ? "pointer" : "not-allowed"};opacity:${isDraft ? "1" : ".55"}">
                        <i class="fa fa-plus"></i> Add Category
                    </button>
                </div>
                </div>`;

					container.html(html);

					container
						.find(".boq-inline-qty, .boq-unit-cost, .boq-inline-margin")
						.on("click", function (e) {
							e.stopPropagation();
						});

					container.find(".boq-inline-qty").on("change", function (e) {
						e.stopPropagation();
						if (!frm.boq_is_draft()) return;

						const rowName = $(this).data("name");
						const row = (frm.doc.items || []).find((r) => r.name === rowName);
						if (!row) return;

						const qty = getNumberValue($(this).val());
						if (!validateBoqItemValues({ ...row, qty: qty })) {
							$(this).val(getNumberValue(row.qty));
							return;
						}

						row.qty = qty;
						recalculateInlineRow(row);
						recalculateBoqTotals(frm);

						if (frm.dirty) {
							frm.dirty();
						}
						frm.refresh_field("items");
						frm.boq_render_grid();
						showInlineUpdateAlert();
					});

					container.find(".boq-unit-cost").on("change", function (e) {
						e.stopPropagation();
						if (!frm.boq_is_draft()) return;

						const rowName = $(this).data("name");
						const row = (frm.doc.items || []).find((r) => r.name === rowName);
						if (!row) return;

						const unitCost = getNumberValue($(this).val());
						const margin = getNumberValue(row.margin_percent);
						const unitRate = unitCost * (1 + margin / 100);
						if (
							!validateBoqItemValues({
								...row,
								unit_cost: unitCost,
								unit_rate: unitRate,
							})
						) {
							$(this).val(getNumberValue(row.unit_cost));
							return;
						}

						row.unit_cost = unitCost;
						recalculateInlineRow(row);
						recalculateBoqTotals(frm);

						if (frm.dirty) {
							frm.dirty();
						}
						frm.refresh_field("items");
						frm.boq_render_grid();
						showInlineUpdateAlert();
					});

					container.find(".boq-inline-margin").on("change", function (e) {
						e.stopPropagation();
						if (!frm.boq_is_draft()) return;

						const rowName = $(this).data("name");
						const row = (frm.doc.items || []).find((r) => r.name === rowName);
						if (!row) return;

						const margin = getNumberValue($(this).val());
						const unitCost = getNumberValue(row.unit_cost);
						const unitRate = unitCost * (1 + margin / 100);
						if (
							!validateBoqItemValues({
								...row,
								margin_percent: margin,
								unit_rate: unitRate,
							})
						) {
							$(this).val(getNumberValue(row.margin_percent));
							return;
						}

						row.margin_percent = margin;
						recalculateInlineRow(row);
						recalculateBoqTotals(frm);

						if (frm.dirty) {
							frm.dirty();
						}
						frm.refresh_field("items");
						frm.boq_render_grid();
					});

					// ── Toggle category ───────────────────────────────────
					container.find(".boq-cat-hd").on("click", function () {
						const pkey = $(this).data("pkey");
						frm._boq_cat_state[pkey] =
							frm._boq_cat_state[pkey] === false ? true : false;
						frm.boq_render_grid();
					});

					// ── Toggle sub-category ───────────────────────────────
					container.find(".boq-sub-hd").on("click", function () {
						const subkey = $(this).data("subkey");
						frm._boq_sub_state[subkey] =
							frm._boq_sub_state[subkey] === false ? true : false;
						frm.boq_render_grid();
					});

					// ── Delete row ────────────────────────────────────────
					container.find(".boq-del-btn").on("click", function (e) {
						if (!frm.boq_is_draft()) {
							frappe.msgprint({
								title: __("Amend Required"),
								indicator: "orange",
								message: __(
									"Please cancel and amend this BOQ before removing items.",
								),
							});
							return;
						}

						e.stopPropagation();
						const name = $(this).data("name");
						frappe.confirm("Remove this item?", () => {
							const index = (frm.doc.items || []).findIndex((r) => r.name === name);
							if (index > -1) {
								const row = frm.doc.items[index];
								frm.doc.items.splice(index, 1);

								if (row) {
									const otherComponents = (frm.doc.cost_components || [])
										.filter((c) => !frm.boq_matches_item_component(c, row))
										.map((c) => ({
											boq_item: c.boq_item,
											component_type: c.component_type,
											description: c.description,
											qty: parseFloat(c.qty) || 1,
											uom: c.uom || "Nos",
											amount: parseFloat(c.amount) || 0,
										}));

									frm.clear_table("cost_components");
									otherComponents.forEach((c) =>
										frm.add_child("cost_components", c),
									);
								}
								frm.refresh_field("items");
								frm.refresh_field("cost_components");
								frm.boq_render_grid();
							}
						});
					});

					// ── Cost breakdown (click on amount cell) ──────────
					container.find(".boq-cost-breakdown-trigger").on("click", function (e) {
						e.stopPropagation();
						const rowName = $(this).data("name");
						const row = frm.doc.items.find((r) => r.name === rowName);

						console.log("=== Cost Breakdown Debug ===");
						console.log("Row name:", rowName);
						console.log("Row item:", row ? row.item : "ROW NOT FOUND");
						console.log(
							"cost_components for this row:",
							row
								? (frm.doc.cost_components || []).filter((c) =>
										frm.boq_matches_item_component(c, row),
									)
								: "N/A",
						);
						console.log("Existing amount:", row ? getBoqItemAmount(row) : "N/A");
						console.log("============================");

						frm.boq_open_cost_breakdown(rowName);
					});

					// ── Add item ──────────────────────────────────────────
					container.find(".boq-add-item-btn").on("click", function (e) {
						e.stopPropagation();
						const subDoc = decodeURIComponent($(this).data("subdoc"));
						const subName = decodeURIComponent($(this).data("subname"));
						frm.boq_add_item_dialog(subDoc, subName);
					});

					// ── Add sub-category (registers state, no dummy row) ──
					container.find(".boq-add-subcat-btn").on("click", function (e) {
						e.stopPropagation();
						if (!frm.boq_is_draft()) {
							frappe.msgprint({
								title: __("Amend Required"),
								indicator: "orange",
								message: __(
									"Please cancel and amend this BOQ before adding sub-categories.",
								),
							});
							return;
						}
						const pKey = decodeURIComponent($(this).data("pkey"));
						const pName = decodeURIComponent($(this).data("pname"));
						frappe.prompt(
							[
								{
									fieldname: "subcat",
									fieldtype: "Link",
									options: "BOQ Category",
									label: "Sub-category",
									reqd: 1,
									filters: { is_group: 0, parent_node: pKey },
								},
							],
							(vals) => {
								frappe.db
									.get_value("BOQ Category", vals.subcat, "category_name")
									.then((r) => {
										const subName =
											(r && r.message && r.message.category_name) ||
											vals.subcat;
										frm._boq_registered.push({
											parentDoc: pKey,
											parentName: pName,
											subDoc: vals.subcat,
											subName: subName,
										});
										frm.boq_render_grid();
									});
							},
							"Add Sub-category to " + pName,
							"Add",
						);
					});

					// ── Add category (registers state, no dummy row) ──────
					container.find(".boq-add-cat-btn").on("click", function () {
						frm._boq_show_add_cat();
					});
				});
		};

		frm._boq_show_add_cat = function () {
			if (!frm.boq_is_draft()) {
				frappe.msgprint({
					title: __("Amend Required"),
					indicator: "orange",
					message: __("Please cancel and amend this BOQ before adding categories."),
				});
				return;
			}

			frappe.prompt(
				[
					{
						fieldname: "cat",
						fieldtype: "Link",
						options: "BOQ Category",
						label: "Category",
						reqd: 1,
						filters: { is_group: 1 },
					},
				],
				(vals) => {
					frappe.db.get_value("BOQ Category", vals.cat, "category_name").then((r) => {
						const catName = (r && r.message && r.message.category_name) || vals.cat;
						const alreadyExists = frm._boq_registered.some(
							(reg) =>
								reg.parentDoc === vals.cat && reg.subDoc === "__placeholder__",
						);
						if (!alreadyExists) {
							frm._boq_registered.push({
								parentDoc: vals.cat,
								parentName: catName,
								subDoc: "__placeholder__",
								subName: "",
							});
						}
						frm.boq_render_grid();
					});
				},
				"Add Category",
				"Add",
			);
		};
	},

	refresh: function (frm) {
		frm.fields_dict["items"].$wrapper.hide();
		if (!frm._boq_cat_state) frm._boq_cat_state = {};
		if (!frm._boq_sub_state) frm._boq_sub_state = {};
		if (!frm._boq_registered) frm._boq_registered = [];
		frm.boq_render_grid();
		addBoqRevisionButtons(frm);
		addGlobalMarginButton(frm);
	},

	validate: function (frm) {
		if (!validateGlobalMargin(frm)) {
			frappe.validated = false;
			return;
		}

		recalculateBoqTotals(frm);

		if (!validateAllBoqItemValues(frm)) {
			frappe.validated = false;
			return;
		}

		frm.boq_prepare_component_keys();
		if (!validateAllBoqCostBreakdowns(frm)) {
			frappe.validated = false;
			return;
		}
	},

	sales_order: function (frm) {
		if (frm._boq_skip_sales_order_apply) return Promise.resolve();
		return applySalesOrderToBoq(frm);
	},

	project: function (frm) {
		return autoSelectSalesOrderForProject(frm);
	},

	global_margin_percent: function (frm) {
		carryGlobalMarginToItems(frm);
	},

	after_save: function (frm) {
		frm.boq_render_grid();
	},
});

function resetBoqChildField(frm, cdt, cdn, fieldname, value) {
	Promise.resolve(frappe.model.set_value(cdt, cdn, fieldname, value)).then(() => {
		frm.refresh_field("items");
		if (frm.boq_render_grid) {
			frm.boq_render_grid();
		}
	});
}

function validateBoqChildField(frm, cdt, cdn, fieldname, resetValue) {
	const row = locals[cdt][cdn];
	if (!row) return false;

	const candidate = { ...row };
	if (fieldname === "unit_cost" || fieldname === "margin_percent") {
		const unitCost = boqNumber(row.unit_cost);
		const margin = boqNumber(row.margin_percent);
		candidate.unit_rate = unitCost * (1 + margin / 100);
	}

	if (!validateBoqItemValues(candidate)) {
		resetBoqChildField(frm, cdt, cdn, fieldname, resetValue);
		return false;
	}

	return true;
}

function recalculateBoqChildRow(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return;

	calculateBoqRowAmounts(row);
	recalculateBoqTotals(frm);
	frm.refresh_field("items");
	if (frm.boq_render_grid) {
		frm.boq_render_grid();
	}
}

frappe.ui.form.on("BOQ Item", {
	qty: function (frm, cdt, cdn) {
		if (validateBoqChildField(frm, cdt, cdn, "qty", 1)) {
			recalculateBoqChildRow(frm, cdt, cdn);
		}
	},

	unit_cost: function (frm, cdt, cdn) {
		if (validateBoqChildField(frm, cdt, cdn, "unit_cost", 0)) {
			recalculateBoqChildRow(frm, cdt, cdn);
		}
	},

	margin_percent: function (frm, cdt, cdn) {
		if (validateBoqChildField(frm, cdt, cdn, "margin_percent", 0)) {
			recalculateBoqChildRow(frm, cdt, cdn);
		}
	},

	unit_rate: function (frm, cdt, cdn) {
		validateBoqChildField(frm, cdt, cdn, "unit_rate", 0);
	},
});
