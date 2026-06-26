frappe.ui.form.on("BOQ", {
	setup: function (frm) {
		frm._boq_cat_state = {};
		frm._boq_sub_state = {};
		frm._boq_registered = [];

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

		frm.boq_recalculate_item_row = function (row, unitCost) {
			const cost = parseFloat(unitCost) || 0;
			const margin = parseFloat(row.margin_percent) || 0;
			const qty = parseFloat(row.qty) || 0;

			return {
				unit_cost: cost,
				unit_rate: cost * (1 + margin / 100),
				amount: qty * cost * (1 + margin / 100),
			};
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
						default: 0,
						description: "Your profit margin — hidden from client",
					},
					{ fieldname: "notes", fieldtype: "Small Text", label: "Notes" },
				],
				primary_action_label: "Add Item",
				primary_action: function (values) {
					const newRow = frm.add_child("items");

					newRow.component_key = frm.boq_make_component_key();
					newRow.boq_category = subCatDoc;
					newRow.item = values.item;
					newRow.item_name = values.item_name || values.item;

					const qty = parseFloat(values.qty) || 1;
					const margin = parseFloat(values.margin_percent) || 0;

					const unit_cost = parseFloat(values.unit_cost) || 0;

					newRow.qty = qty;
					newRow.uom = values.uom || "Nos";
					newRow.unit_cost = unit_cost;
					newRow.margin_percent = margin;

					newRow.unit_rate = unit_cost * (1 + margin / 100);
					newRow.amount = qty * newRow.unit_rate;

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
		// ── Cost breakdown dialog (click unit cost cell to open) ─────
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

                    const oldAmount = parseFloat(itemRow.amount) || 0;

                    const totals = frm.boq_recalculate_item_row(itemRow, total);
                    
                   
                    
					Promise.all([
						frappe.model.set_value(
							itemRow.doctype,
							itemRow.name,
							"unit_cost",
							totals.unit_cost,
						),
						frappe.model.set_value(
							itemRow.doctype,
							itemRow.name,
							"unit_rate",
							totals.unit_rate,
						),
						frappe.model.set_value(
							itemRow.doctype,
							itemRow.name,
							"amount",
							totals.amount,
						),
					]).then(() => {
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

						// 🔥 FIXED CALL
						showAmountMismatchWarning(oldAmount, total);
					});
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

			function showAmountMismatchWarning(oldItemAmount, breakdownAmount) {
				const itemAmount = parseFloat(oldItemAmount) || 0;

				const bdAmount = parseFloat(breakdownAmount) || 0;

				if (Math.abs(itemAmount - bdAmount) > 0.01) {
					frappe.msgprint({
						title: "Amount Mismatch Warning",
						message:
							"Previous Item Amount: " +
							itemAmount +
							"<br>New Breakdown Amount: " +
							bdAmount +
							"<br><br>Please review Cost Breakdown.",
						indicator: "orange",
					});
				}
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
					.html(frappe.format(total, { fieldtype: "Currency" }));
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
	                <span style="font-size:12px;color:var(--text-muted)">Total Unit Cost</span>
	                <span class="comp-total-value" style="font-size:16px;font-weight:600;color:var(--text-color)">
	                    ${frappe.format(total, { fieldtype: "Currency" })}
	                </span>
	            </div>
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
			const CUR = frm.doc.currency || "AED";
			const isDraft = frm.boq_is_draft();

			// Empty state — no items and no registered (pending) categories
			if (!items.length && !frm._boq_registered.length) {
				container.html(`
                    <div style="border:1px solid var(--border-color);border-radius:var(--border-radius);overflow:hidden">
                        <div style="padding:12px 16px;text-align:center;color:var(--text-muted);font-size:13px">
                            No items yet. Click below to add a category.
                        </div>
                        <div style="padding:10px 16px;border-top:1px solid var(--border-color)">
                            <button class="btn btn-xs btn-default boq-add-cat-btn" style="width:100%" ${isDraft ? "" : "disabled"}>
                                <i class="fa fa-plus"></i> Add Category
                            </button>
                        </div>
                    </div>`);
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

					// ── Build two-level structure ──────────────────────────
					// parentOrder: insertion-ordered array of parent doc keys
					// structure[pKey] = { name, subcats: { subKey: { name, items[] } } }
					const parentOrder = [];
					const structure = {};

					function ensureParent(pKey, pName) {
						if (!structure[pKey]) {
							structure[pKey] = { name: pName, subcats: {} };
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

					// 2. Actual saved items (FIX: translate boq_category doc name → human name)
					items.forEach((row) => {
						if (!row.boq_category) return;
						const info = catMap[row.boq_category] || {};
						const subName = info.category_name || row.boq_category;
						const parentDoc = info.parent_node || null;
						const parentName =
							row.boq_parent_category ||
							(parentDoc && catMap[parentDoc] && catMap[parentDoc].category_name) ||
							subName;
						const pKey = parentDoc || row.boq_category;

						ensureSub(pKey, parentName, row.boq_category, subName);
						structure[pKey].subcats[row.boq_category].items.push(row);
					});

					// ── Formatters ─────────────────────────────────────────
					const fmt0 = (n) =>
						parseFloat(n || 0).toLocaleString("en-AE", { maximumFractionDigits: 0 });
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
								`${c.component_type}: ${c.description} = ${parseFloat(c.amount || 0).toLocaleString()}`,
						);
						const total = components.reduce(
							(sum, c) => sum + (parseFloat(c.amount) || 0),
							0,
						);
						lines.push("---");
						lines.push(`Total: ${total.toLocaleString()}`);
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
							return fmt2(row.unit_cost);
						}

						return renderInlineNumber(row, "boq-inline-unit-cost", row.unit_cost);
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
						const unitCost = parseFloat(row.unit_cost) || 0;
						const margin = parseFloat(row.margin_percent) || 0;
						const qty = parseFloat(row.qty) || 0;

						row.unit_rate = unitCost * (1 + margin / 100);
						row.amount = qty * row.unit_rate;
					}

					// ── Build HTML ──────────────────────────────────────────
					let html = `<div style="border:1px solid var(--border-color);border-radius:var(--border-radius);overflow:hidden;font-family:var(--font-stack);font-size:12px">`;

					parentOrder.forEach((pKey) => {
						const cat = structure[pKey];
						const subKeys = Object.keys(cat.subcats);
						const catTotal = subKeys.reduce(
							(a, s) =>
								a + cat.subcats[s].items.reduce((b, r) => b + (r.amount || 0), 0),
							0,
						);
						const catOpen = frm._boq_cat_state[pKey] !== false;

						html += `
                    <div class="boq-cat-hd" data-pkey="${pKey}"
                         style="display:flex;align-items:center;gap:8px;padding:10px 14px;background:#0F1E38;cursor:pointer;border-bottom:1px solid #1a3057">
                        <i class="fa fa-chevron-down"
                           style="color:#a0b0c8;font-size:11px;transition:transform .2s;${catOpen ? "" : "transform:rotate(-90deg)"}"></i>
                        <span style="font-weight:600;color:#fff;font-size:12px;flex:1">${cat.name.toUpperCase()}</span>
                        <span style="font-weight:600;color:#c9a520;font-size:12px">${CUR} ${fmt0(catTotal)}</span>
                    </div>`;

						if (catOpen) {
							subKeys.forEach((subKey) => {
								const sub = cat.subcats[subKey];
								const subTotal = sub.items.reduce(
									(a, r) => a + (r.amount || 0),
									0,
								);
								const subCost = sub.items.reduce(
									(a, r) => a + (r.unit_cost || 0) * (r.qty || 0),
									0,
								);
								const subOpen = frm._boq_sub_state[subKey] !== false;

								html += `
                            <div class="boq-sub-hd" data-subkey="${subKey}"
                                 style="display:flex;align-items:center;gap:8px;padding:8px 14px 8px 28px;background:#1a2d48;cursor:pointer;border-bottom:1px solid #1e3356">
                                <i class="fa fa-chevron-down"
                                   style="color:#5b7fa6;font-size:10px;transition:transform .2s;${subOpen ? "" : "transform:rotate(-90deg)"}"></i>
                                <span style="font-weight:600;color:#c8d8ec;font-size:11px;flex:1">${sub.name}</span>
                                <span style="color:#7090b8;font-size:11px">${CUR} ${fmt0(subTotal)}</span>
                            </div>`;

								if (subOpen) {
									// Column header
									html += `
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

<th style="width:32%text-align:left;padding:8px;">
    DESCRIPTION
</th>

<th style="width:8%;text-align:center;padding:8px;">
    QTY
</th>

<th style="width:8%;text-align:center;padding:8px;">
    UOM
</th>

<th style="width:12%;text-align:center;padding:8px;">
    UNIT COST
</th>

<th style="width:11%;text-align:center;padding:8px;">
    MARGIN %
</th>

<th style="width:15%;text-align:center;padding:8px;">
    AMOUNT
</th>

<th style="width:7%;text-align:center;padding:8px;">
    ACTION
</th>

</tr>
</thead>

<tbody>
`;

									// Item rows
									sub.items.forEach((row, idx) => {
										const rowBg =
											idx % 2 === 0
												? "var(--bg-color)"
												: "var(--control-bg)";

										html += `
<tr style="
    border-bottom:1px solid var(--border-color);
    height:42px;
">

<td style="text-align:center;padding:6px 4px;">
    ${idx + 1}
</td>

<td style="text-align:left;padding:6px 8px;word-break:break-word;">
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
        ${renderUnitCost(row)}

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
">
    ${CUR} ${fmt0(row.amount)}
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
									html += `
</tbody>
</table>
`;

									// Subtotal row
									html += `
<div style="
    display:grid;
    grid-template-columns:28px 1fr 160px 28px;
    padding:8px 14px 8px 28px;
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
        SUBTOTAL — ${sub.name.toUpperCase()}
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
        ${CUR} ${fmt0(subTotal)}
    </div>

    <span></span>

</div>`;

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
						.find(".boq-inline-qty, .boq-inline-unit-cost, .boq-inline-margin")
						.on("click", function (e) {
							e.stopPropagation();
						});

					container.find(".boq-inline-qty").on("change", function (e) {
						e.stopPropagation();
						if (!frm.boq_is_draft()) return;

						const rowName = $(this).data("name");
						const row = (frm.doc.items || []).find((r) => r.name === rowName);
						if (!row) return;

						row.qty = getNumberValue($(this).val());
						row.amount = row.qty * (parseFloat(row.unit_rate) || 0);

						if (frm.dirty) {
							frm.dirty();
						}
						frm.refresh_field("items");
						frm.boq_render_grid();
						showInlineUpdateAlert();
					});

					container.find(".boq-inline-unit-cost").on("change", function (e) {
						e.stopPropagation();
						if (!frm.boq_is_draft()) return;

						const rowName = $(this).data("name");
						const row = (frm.doc.items || []).find((r) => r.name === rowName);
						if (!row) return;

						row.unit_cost = getNumberValue($(this).val());
						recalculateInlineRow(row);

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

						row.margin_percent = getNumberValue($(this).val());
						recalculateInlineRow(row);

						if (frm.dirty) {
							frm.dirty();
						}
						frm.refresh_field("items");
						frm.boq_render_grid();
						showInlineUpdateAlert();
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

					// ── Cost breakdown (click on unit cost cell) ──────────
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
						console.log("Existing unit_cost:", row ? row.unit_cost : "N/A");
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
	},

	validate: function (frm) {
		frm.boq_prepare_component_keys();
	},

	after_save: function (frm) {
		frm.boq_render_grid();
	},
});
