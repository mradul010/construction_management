const boqItemLabels = {};
const boqCategoryLabels = {};

frappe.form.link_formatters["BOQ Item"] = function (value, doc) {
	return (doc && doc.item_name) || boqItemLabels[value] || value;
};

frappe.form.link_formatters["BOQ Category"] = function (value, doc) {
	return (doc && doc.category_name) || boqCategoryLabels[value] || value;
};

if (frappe.ui.form.ControlLink && !frappe.ui.form.ControlLink.prototype.boq_item_label_only) {
	const originalAwesompleteFilter = frappe.ui.form.ControlLink.prototype.custom_awesomplete_filter;

	frappe.ui.form.ControlLink.prototype.custom_awesomplete_filter = function (awesomplete) {
		if (originalAwesompleteFilter) {
			originalAwesompleteFilter.call(this, awesomplete);
		}

		if (!["BOQ Item", "BOQ Category"].includes(this.get_options())) return;

		const control = this;

		awesomplete.item = function (item) {
			const d = this.get_item(item.value);
			if (!d.label) {
				d.label = d.value;
			}
			if (control.get_options() === "BOQ Item" && boqItemLabels[d.value]) {
				d.label = boqItemLabels[d.value];
				d.html = `<strong>${frappe.utils.escape_html(d.label)}</strong>`;
			}
			if (control.get_options() === "BOQ Category" && boqCategoryLabels[d.value]) {
				d.label = boqCategoryLabels[d.value];
				d.html = `<strong>${frappe.utils.escape_html(d.label)}</strong>`;
			}

			const label = frappe.utils.escape_html(control.get_translated(d.label));
			const html = d.html || `<strong>${label}</strong>`;

			return $(`<div role="option">`)
				.on("click", (event) => {
					control.awesomplete.select(event.currentTarget, event.currentTarget);
					control.show_link_and_clear_buttons();
				})
				.data("item.autocomplete", d)
				.prop("aria-selected", "false")
				.html(`<p title="${label}">${html}</p>`)
				.get(0);
		};
	};

	frappe.ui.form.ControlLink.prototype.boq_item_label_only = true;
}

function setBoqItemDetails(frm, cdt, cdn, options = {}) {
	const row = locals[cdt][cdn];

	if (!row || !row.boq_item) return Promise.resolve();

	return frappe.db
		.get_value("BOQ Item", row.boq_item, [
			"item_name",
			"qty",
			"unit_rate",
			"uom",
			"boq_category",
			"boq_parent_category",
		])
		.then((r) => {
			if (!r.message) return;

			boqItemLabels[row.boq_item] = r.message.item_name || row.boq_item;
			frm._ra_bill_row_state = frm._ra_bill_row_state || {};
			frm._ra_bill_row_state[row.name] = {
				category: null,
				subcategory: r.message.boq_category,
			};

			frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name);

			if (!options.labelOnly) {
				frappe.model.set_value(cdt, cdn, "boq_qty", r.message.qty);
				frappe.model.set_value(cdt, cdn, "boq_rate", r.message.unit_rate);
				frappe.model.set_value(cdt, cdn, "uom", r.message.uom);
			}

			frm.refresh_field("items");
		});
}

function hydrateBoqItemLabels(frm) {
	const rows = (frm.doc.items || []).filter((row) => row.boq_item);

	rows.forEach((row) => {
		if (row.item_name) {
			boqItemLabels[row.boq_item] = row.item_name;
			return;
		}

		setBoqItemDetails(frm, row.doctype, row.name, { labelOnly: true });
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

		frm.set_query("boq_item", "items", function () {
			return {
				filters: {
					parent: frm.doc.boq,
				},
			};
		});

		frm._ra_bill_row_state = {};

		frm.ra_bill_is_editable = function () {
			return frm.doc.docstatus === 0;
		};

		frm.ra_bill_get_number = function (value) {
			const parsed = parseFloat(value);
			return isNaN(parsed) ? 0 : parsed;
		};

		frm.ra_bill_format_number = function (value, digits = 2) {
			return frm.ra_bill_get_number(value).toLocaleString("en-AE", {
				minimumFractionDigits: digits,
				maximumFractionDigits: digits,
			});
		};

		frm.ra_bill_format_currency = function (value) {
			return frappe.format(frm.ra_bill_get_number(value), {
				fieldtype: "Currency",
				options: frm.doc.currency,
			});
		};

		frm.ra_bill_get_row_completion = function (row) {
			const boqQty = frm.ra_bill_get_number(row.boq_qty);
			const currentQty = frm.ra_bill_get_number(row.current_qty);

			if (boqQty) {
				return (currentQty / boqQty) * 100;
			}

			return currentQty * 100;
		};

		frm.ra_bill_recalculate_row = function (row, completionPct) {
			const pct = Math.max(0, Math.min(100, frm.ra_bill_get_number(completionPct)));
			const boqQty = frm.ra_bill_get_number(row.boq_qty);
			const boqRate = frm.ra_bill_get_number(row.boq_rate);
			const prevQty = frm.ra_bill_get_number(row.prev_cumulative_qty);
			const currentQty = boqQty ? (boqQty * pct) / 100 : pct / 100;

			row.current_qty = currentQty;
			row.cumulative_qty = prevQty + currentQty;
			row.completion_pct = boqQty ? (row.cumulative_qty / boqQty) * 100 : pct;
			row.current_amount = currentQty * boqRate;
		};

		frm.ra_bill_set_dirty = function () {
			if (frm.dirty) {
				frm.dirty();
			}
		};

		frm.ra_bill_load_boq_context = function () {
			if (!frm.doc.boq) {
				frm._ra_bill_boq_items = [];
				frm._ra_bill_category_map = {};
				frm._ra_bill_parent_category_names = [];
				frm._ra_bill_subcategory_names = [];
				frm._ra_bill_context_boq = null;
				return Promise.resolve();
			}

			if (frm._ra_bill_context_boq === frm.doc.boq && frm._ra_bill_boq_items) {
				return Promise.resolve();
			}

			return frappe.db
				.get_list("BOQ Item", {
					filters: {
						parent: frm.doc.boq,
						parenttype: "BOQ",
						parentfield: "items",
					},
					fields: [
						"name",
						"boq_category",
						"boq_parent_category",
						"item",
						"item_name",
						"qty",
						"unit_rate",
						"uom",
					],
					limit: 1000,
					order_by: "idx asc",
				})
				.then((items) => {
					frm._ra_bill_boq_items = items || [];
					frm._ra_bill_boq_items.forEach((item) => {
						boqItemLabels[item.name] = item.item_name || item.item || item.name;
					});

					const subcategoryNames = [
						...new Set(
							frm._ra_bill_boq_items
								.map((item) => item.boq_category)
								.filter(Boolean),
						),
					];

					if (!subcategoryNames.length) {
						frm._ra_bill_category_map = {};
						frm._ra_bill_parent_category_names = [];
						frm._ra_bill_subcategory_names = [];
						frm._ra_bill_context_boq = frm.doc.boq;
						return [];
					}

					return frappe.db
						.get_list("BOQ Category", {
							filters: [["name", "in", subcategoryNames]],
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
										fields: ["name", "category_name", "parent_node"],
										limit: 1000,
									})
								: Promise.resolve([]);

							return parentPromise.then((parents) => {
								const categoryMap = {};

								[...(subcategories || []), ...(parents || [])].forEach((category) => {
									categoryMap[category.name] = category;
									boqCategoryLabels[category.name] =
										category.category_name || category.name;
								});

								frm._ra_bill_category_map = categoryMap;
								frm._ra_bill_parent_category_names = [
									...new Set(
										(subcategories || []).map(
											(category) => category.parent_node || category.name,
										),
									),
								];
								frm._ra_bill_subcategory_names = subcategoryNames;
								frm._ra_bill_context_boq = frm.doc.boq;
							});
						});
				});
		};

		frm.ra_bill_get_row_category_state = function (row) {
			frm._ra_bill_row_state = frm._ra_bill_row_state || {};
			const state = frm._ra_bill_row_state[row.name] || {};

			if (row.boq_item) {
				const boqItem = (frm._ra_bill_boq_items || []).find(
					(item) => item.name === row.boq_item,
				);

				if (boqItem) {
					state.subcategory = boqItem.boq_category || state.subcategory;
				}
			}

			const subcategory = state.subcategory;
			const subcategoryDoc = frm._ra_bill_category_map
				? frm._ra_bill_category_map[subcategory]
				: null;
			const category = state.category || (subcategoryDoc && subcategoryDoc.parent_node) || null;

			frm._ra_bill_row_state[row.name] = {
				category: category,
				subcategory: subcategory,
			};

			return frm._ra_bill_row_state[row.name];
		};

		frm.ra_bill_get_subcategories_for_category = function (category) {
			return (frm._ra_bill_subcategory_names || []).filter((name) => {
				const subcategory = frm._ra_bill_category_map[name];
				if (!subcategory) return false;
				return (subcategory.parent_node || subcategory.name) === category;
			});
		};

		frm.ra_bill_get_items_for_subcategory = function (subcategory) {
			return (frm._ra_bill_boq_items || []).filter(
				(item) => item.boq_category === subcategory,
			);
		};

		frm.ra_bill_make_link_control = function (parent, fieldname, options, value, getQuery, onChange) {
			let isInitializing = true;
			const control = frappe.ui.form.make_control({
				parent: parent.get ? parent.get(0) : parent,
				df: {
					fieldtype: "Link",
					fieldname: fieldname,
					options: options,
					placeholder: __("Select"),
					get_query: getQuery,
					onchange: function () {
						if (isInitializing) return;
						onChange(control.get_value());
					},
				},
				render_input: true,
				only_input: true,
			});

			control.get_query = getQuery;
			control.refresh();
			control.set_value(value || "");
			setTimeout(() => {
				isInitializing = false;
			}, 0);
			return control;
		};

		frm.ra_bill_apply_boq_item = function (row, boqItemName) {
			const boqItem = (frm._ra_bill_boq_items || []).find((item) => item.name === boqItemName);

			if (!boqItem) return;

			frm._ra_bill_row_state[row.name] = {
				category:
					(frm._ra_bill_category_map[boqItem.boq_category] || {}).parent_node || null,
				subcategory: boqItem.boq_category,
			};

			row.boq_item = boqItem.name;
			row.item_name = boqItem.item_name || boqItem.item;
			row.boq_qty = boqItem.qty;
			row.boq_rate = boqItem.unit_rate;
			row.uom = boqItem.uom;
			frm.ra_bill_recalculate_row(row, frm.ra_bill_get_row_completion(row));
			frm.ra_bill_set_dirty();
			frm.refresh_field("items");
			frm.trigger("recalculate_totals");
			frm.ra_bill_render_items_grid();
		};

		frm.ra_bill_render_items_grid = function () {
			if (!frm.fields_dict.items || !frm.fields_dict.items.$wrapper) return;

			frm.fields_dict.items.$wrapper.hide();

			let container = $(frm.wrapper).find("#ra-bill-custom-items-grid");
			if (!container.length) {
				frm.fields_dict.items.$wrapper
					.closest(".form-column")
					.append('<div id="ra-bill-custom-items-grid" style="margin-top:16px"></div>');
				container = $(frm.wrapper).find("#ra-bill-custom-items-grid");
			}

			const isEditable = frm.ra_bill_is_editable();
			const rows = frm.doc.items || [];
			const total = rows.reduce(
				(sum, row) => sum + frm.ra_bill_get_number(row.current_amount),
				0,
			);

			if (!frm.doc.boq) {
				container.html(`
					<div style="border:1px solid var(--border-color);border-radius:6px;padding:14px;color:var(--text-muted);font-size:13px">
						Select a BOQ to add billed items.
					</div>
				`);
				return;
			}

			frm.ra_bill_load_boq_context().then(() => {
				let html = `
					<style>
						#ra-bill-custom-items-grid {
							width: 100%;
							max-width: 100%;
							overflow: visible;
						}
						#ra-bill-custom-items-grid .ra-bill-table-shell {
							border: 1px solid var(--border-color);
							border-radius: 6px;
							font-family: var(--font-stack);
							font-size: 13px;
							width: 100%;
							max-width: 100%;
							box-sizing: border-box;
							overflow: visible;
						}
						#ra-bill-custom-items-grid table {
							width: 100%;
							border-collapse: collapse;
							table-layout: fixed;
							box-sizing: border-box;
						}
						#ra-bill-custom-items-grid th,
						#ra-bill-custom-items-grid td {
							text-align: center;
							vertical-align: middle;
							white-space: nowrap;
							box-sizing: border-box;
						}

						#ra-bill-custom-items-grid th {
							padding: 8px 4px;
							font-size: 10px;
							font-weight: 700;
							text-transform: uppercase;
							color: #374151;
							background: var(--control-bg);
							border-bottom: 1px solid var(--border-color);
						}

						#ra-bill-custom-items-grid td {
							height: 48px;
							padding: 7px 4px;
							overflow: hidden;
							text-overflow: ellipsis;
							font-size: 12px;
							font-weight: 500;
							color: #374151;
						}

						#ra-bill-custom-items-grid .frappe-control,
						#ra-bill-custom-items-grid .form-group {
							margin-bottom: 0;
						}
						#ra-bill-custom-items-grid .control-label {
							display: none;
						}
						#ra-bill-custom-items-grid .control-input-wrapper {
							margin-top: 0;
						}
						#ra-bill-custom-items-grid .link-field,
						#ra-bill-custom-items-grid .form-control {
							width: 100%;
							max-width: 100%;
							min-height: 32px;
							height: 32px;
							font-size: 13px;
							font-weight: 500;
							text-align: center;
							color: #374151;
							box-sizing: border-box;
						}
						#ra-bill-custom-items-grid .ra-work-complete {
							width: 70px;
							max-width: 100%;
							margin: 0 auto;
							text-align: center;
							display: block;
						}
						#ra-bill-custom-items-grid .awesomplete,
						#ra-bill-custom-items-grid .awesomplete > input {
							width: 100%;
							max-width: 100%;
							box-sizing: border-box;
							text-align: center;
						}
						#ra-bill-custom-items-grid .awesomplete > ul {
							z-index: 1060;
							text-align: left;
							white-space: normal;
						}
						#ra-bill-custom-items-grid td.ra-currency-cell {
							text-align: center;
							padding-left: 0;
							padding-right: 0;
						}
						#ra-bill-custom-items-grid .ra-currency-value {
							display: flex;
							align-items: center;
							justify-content: center;
							width: 100%;
							font-variant-numeric: tabular-nums;
							text-align: center;
						}
						#ra-bill-custom-items-grid td.ra-amount-cell {
							font-weight: 700;
							color: var(--primary);
						}

						#ra-bill-custom-items-grid td.ra-action-cell {
							text-align: center;
							padding: 0;
							overflow: hidden;
						}

						#ra-bill-custom-items-grid .ra-action-btn {
							width: 22px;
							height: 22px;
							padding: 0;
							margin: 0 auto;
							display: inline-flex;
							align-items: center;
							justify-content: center;
						}
					</style>
					<div class="ra-bill-table-shell">
						<table>
							<colgroup>
								<col style="width:5%">
								<col style="width:16%">
								<col style="width:16%">
								<col style="width:17%">
								<col style="width:8%">
								<col style="width:10%">
								<col style="width:6%">
								<col style="width:8%">
								<col style="width:10%">
								<col style="width:4%">
							</colgroup>
							<thead>
								<tr>
									<th>S.NO</th>
									<th>CATEGORY NAME</th>
									<th>SUB CATEGORY</th>
									<th>ITEM</th>
									<th>BOQ QTY</th>
									<th>BOQ RATE</th>
									<th>UOM</th>
									<th>WORK %</th>
									<th>AMOUNT</th>
									<th>ACTION</th>
								</tr>
							</thead>
							<tbody>
				`;

				if (!rows.length) {
					html += `
						<tr>
							<td colspan="10" style="padding:14px;text-align:center;color:var(--text-muted)">
								No billed items yet.
							</td>
						</tr>
					`;
				}

				rows.forEach((row, index) => {
					const completion = frm.ra_bill_get_row_completion(row);
					const categoryState = frm.ra_bill_get_row_category_state(row);

					html += `
						<tr data-row-name="${row.name}" style="border-bottom:1px solid var(--border-color);background:${index % 2 === 0 ? "var(--bg-color)" : "var(--control-bg)"}">
							<td>${index + 1}</td>
							<td><div class="ra-category-cell" data-row-name="${row.name}"></div></td>
							<td><div class="ra-subcategory-cell" data-row-name="${row.name}"></div></td>
							<td><div class="ra-item-cell" data-row-name="${row.name}"></div></td>
							<td>${frm.ra_bill_format_number(row.boq_qty)}</td>
							<td class="ra-currency-cell">
								<span class="ra-currency-value">${frm.ra_bill_format_currency(row.boq_rate)}</span>
							</td>
							<td>${row.uom || "Nos"}</td>
							<td>
								${
									isEditable
										? `<input type="number" class="form-control ra-work-complete" data-row-name="${row.name}" value="${frm.ra_bill_format_number(completion)}" min="0" max="100" step="any" style="padding:2px 4px">`
									: `${frm.ra_bill_format_number(completion)}%`
								}
							</td>
							<td class="ra-currency-cell ra-amount-cell">
								<span class="ra-currency-value">${frm.ra_bill_format_currency(row.current_amount)}</span>
							</td>
							<td class="ra-action-cell">
								<button class="btn btn-xs btn-default ra-row-delete ra-action-btn" data-row-name="${row.name}" title="Delete" ${isEditable ? "" : "disabled"}>
									<i class="fa fa-trash" style="color:#ef4444"></i>
								</button>
							</td>
						</tr>
					`;

				});

				html += `
							</tbody>
						</table>
						<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;background:#0F1E38;color:#fff;border-top:2px solid #c9a520">
							<button class="btn btn-xs btn-default ra-add-row" ${isEditable ? "" : "disabled"} style="display:inline-flex;align-items:center;gap:6px">
								<i class="fa fa-plus"></i> Add Row
							</button>
							<div style="display:flex;align-items:center;gap:12px;font-weight:600">
								<span style="color:#a0b0c8;font-size:11px;text-transform:uppercase">Total Amount</span>
								<span style="font-size:14px;color:#fff">${frm.ra_bill_format_currency(total)}</span>
							</div>
						</div>
					</div>
				`;

				container.html(html);

				rows.forEach((row) => {
					const state = frm.ra_bill_get_row_category_state(row);
					const categoryCell = container.find(`.ra-category-cell[data-row-name="${row.name}"]`);
					const subcategoryCell = container.find(`.ra-subcategory-cell[data-row-name="${row.name}"]`);
					const itemCell = container.find(`.ra-item-cell[data-row-name="${row.name}"]`);

					if (!isEditable) {
						categoryCell.text(boqCategoryLabels[state.category] || "");
						subcategoryCell.text(boqCategoryLabels[state.subcategory] || "");
						itemCell.text(boqItemLabels[row.boq_item] || row.item_name || "");
						return;
					}

					frm.ra_bill_make_link_control(
						categoryCell,
						`ra_category_${row.name}`,
						"BOQ Category",
						state.category,
						function () {
							return {
								filters: [["BOQ Category", "name", "in", frm._ra_bill_parent_category_names || ["__none__"]]],
							};
						},
						function (value) {
							frm._ra_bill_row_state[row.name] = {
								category: value,
								subcategory: null,
							};
							row.boq_item = null;
							row.item_name = null;
							row.boq_qty = 0;
							row.boq_rate = 0;
							row.uom = null;
							frm.ra_bill_recalculate_row(row, 0);
							frm.ra_bill_set_dirty();
							frm.refresh_field("items");
							frm.trigger("recalculate_totals");
							frm.ra_bill_render_items_grid();
						},
					);

					frm.ra_bill_make_link_control(
						subcategoryCell,
						`ra_subcategory_${row.name}`,
						"BOQ Category",
						state.subcategory,
						function () {
							const subcategories = state.category
								? frm.ra_bill_get_subcategories_for_category(state.category)
								: frm._ra_bill_subcategory_names || [];
							return {
								filters: [["BOQ Category", "name", "in", subcategories.length ? subcategories : ["__none__"]]],
							};
						},
						function (value) {
							const subcategoryDoc = frm._ra_bill_category_map[value] || {};
							frm._ra_bill_row_state[row.name] = {
								category: subcategoryDoc.parent_node || state.category || value,
								subcategory: value,
							};
							row.boq_item = null;
							row.item_name = null;
							row.boq_qty = 0;
							row.boq_rate = 0;
							row.uom = null;
							frm.ra_bill_recalculate_row(row, 0);
							frm.ra_bill_set_dirty();
							frm.refresh_field("items");
							frm.trigger("recalculate_totals");
							frm.ra_bill_render_items_grid();
						},
					);

					frm.ra_bill_make_link_control(
						itemCell,
						`ra_item_${row.name}`,
						"BOQ Item",
						row.boq_item,
						function () {
							const subcategory =
								(frm._ra_bill_row_state[row.name] || {}).subcategory || state.subcategory;
							return {
								filters: [
									["BOQ Item", "parent", "=", frm.doc.boq],
									["BOQ Item", "parenttype", "=", "BOQ"],
									["BOQ Item", "parentfield", "=", "items"],
									["BOQ Item", "boq_category", "=", subcategory || "__none__"],
								],
							};
						},
						function (value) {
							if (!value) {
								row.boq_item = null;
								row.item_name = null;
								row.boq_qty = 0;
								row.boq_rate = 0;
								row.uom = null;
								frm.ra_bill_recalculate_row(row, 0);
								frm.ra_bill_set_dirty();
								frm.refresh_field("items");
								frm.trigger("recalculate_totals");
								frm.ra_bill_render_items_grid();
								return;
							}
							frm.ra_bill_apply_boq_item(row, value);
						},
					);
				});

				container.find(".ra-work-complete").on("change", function () {
					if (!frm.ra_bill_is_editable()) return;

					const rowName = $(this).data("row-name");
					const row = (frm.doc.items || []).find((item) => item.name === rowName);
					if (!row) return;

					frm.ra_bill_recalculate_row(row, $(this).val());
					frm.ra_bill_set_dirty();
					frm.refresh_field("items");
					frm.trigger("recalculate_totals");
					frm.ra_bill_render_items_grid();
				});

				container.find(".ra-add-row").on("click", function () {
					if (!frm.ra_bill_is_editable()) return;

					const row = frm.add_child("items", {
						current_qty: 0,
						current_amount: 0,
						completion_pct: 0,
					});
					frm._ra_bill_row_state[row.name] = {
						category: null,
						subcategory: null,
					};
					frm.ra_bill_set_dirty();
					frm.refresh_field("items");
					frm.ra_bill_render_items_grid();
				});

				container.find(".ra-row-delete").on("click", function () {
					if (!frm.ra_bill_is_editable()) return;

					const rowName = $(this).data("row-name");
					const index = (frm.doc.items || []).findIndex((item) => item.name === rowName);
					if (index === -1) return;

					frm.doc.items.splice(index, 1);
					delete frm._ra_bill_row_state[rowName];
					frm.ra_bill_set_dirty();
					frm.refresh_field("items");
					frm.trigger("recalculate_totals");
					frm.ra_bill_render_items_grid();
				});

				container.find(".ra-row-edit").on("click", function () {
					if (!frm.ra_bill_is_editable()) return;

					const rowName = $(this).data("row-name");
					const gridRow = frm.fields_dict.items.grid.grid_rows_by_docname[rowName];
					if (gridRow) {
						gridRow.toggle_view(true);
					}
				});
			});
		};
	},

	refresh: function (frm) {
		hydrateBoqItemLabels(frm);
		frm.ra_bill_render_items_grid();

		if (frm.doc.status === "Submitted" && frm.doc.docstatus === 1) {
			frm.add_custom_button(
				"Approve",
				function () {
					frappe.confirm("Are you sure you want to approve this RA Bill?", function () {
						frappe.db.set_value("RA Bill", frm.doc.name, "status", "Approved").then(() => {
							frm.reload_doc();
							frappe.show_alert(
								{
									message: "RA Bill Approved",
									indicator: "green",
								},
								3,
							);
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
					frappe.confirm(
						`Create Sales Invoice for ${frappe.format(frm.doc.net_payable, {
							fieldtype: "Currency",
							options: frm.doc.currency,
						})}?`,
						function () {
							frappe.call({
								method: "create_sales_invoice",
								doc: frm.doc,
								callback: function (r) {
									if (r.message) {
										frm.reload_doc();
									}
								},
							});
						},
					);
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

	project: function (frm) {
		if (frm.doc.boq) {
			frm.set_value("boq", null);
			frm.clear_table("items");
			frm.refresh_field("items");
			frm.ra_bill_render_items_grid();
		}
	},

	boq: function (frm) {
		if (frm.doc.items && frm.doc.items.length > 0) {
			frappe.confirm("Changing the BOQ will clear all current items. Continue?", function () {
				frm.clear_table("items");
				frm.refresh_field("items");
				frm.ra_bill_render_items_grid();
			});
		}
		frm._ra_bill_boq_items = null;
		frm._ra_bill_category_map = {};
		frm._ra_bill_row_state = {};
		frm.ra_bill_render_items_grid();
	},

	retention_percent: function (frm) {
		frm.trigger("recalculate_totals");
	},

	recalculate_totals: function (frm) {
		let gross = 0;

		(frm.doc.items || []).forEach((row) => {
			gross += row.current_amount || 0;
		});

		const retention = gross * ((frm.doc.retention_percent || 0) / 100);

		frappe.model.set_value(frm.doctype, frm.docname, "gross_amount", gross);
		frappe.model.set_value(frm.doctype, frm.docname, "retention_amount", retention);
		frappe.model.set_value(frm.doctype, frm.docname, "net_payable", gross - retention);
		frm.ra_bill_render_items_grid();
	},
});

frappe.ui.form.on("RA Bill Item", {
	boq_item: function (frm, cdt, cdn) {
		setBoqItemDetails(frm, cdt, cdn).then(() => frm.ra_bill_render_items_grid());
	},

	current_qty: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const currentQty = row.current_qty || 0;
		const prevQty = row.prev_cumulative_qty || 0;
		const boqQty = row.boq_qty || 0;
		const cumulativeQty = prevQty + currentQty;
		const amount = currentQty * (row.boq_rate || 0);

		frappe.model.set_value(cdt, cdn, "cumulative_qty", cumulativeQty);
		frappe.model.set_value(cdt, cdn, "completion_pct", boqQty ? (cumulativeQty / boqQty) * 100 : 0);
		frappe.model.set_value(cdt, cdn, "current_amount", amount);
		frm.trigger("recalculate_totals");
		frm.ra_bill_render_items_grid();
	},

	items_remove: function (frm) {
		frm.trigger("recalculate_totals");
		frm.ra_bill_render_items_grid();
	},
});
