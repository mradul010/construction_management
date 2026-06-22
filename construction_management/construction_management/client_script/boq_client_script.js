frappe.ui.form.on("BOQ", {

    setup: function(frm) {
        frm._boq_cat_state  = {};
        frm._boq_sub_state  = {};
        frm._boq_registered = [];

        // Lookup price from the default BOQ price list set in Construction Settings
        frm.boq_get_price = function(item, currency, callback) {
            frappe.db.get_single_value("Construction Settings", "default_boq_price_list")
            .then(price_list => {
                if (!price_list) { callback(0); return; }
                frappe.db.get_value("Item Price", {
                    item_code: item,
                    price_list: price_list,
                    currency: currency || frm.doc.currency || "AED"
                }, "price_list_rate").then(r => {
                    callback((r && r.message && r.message.price_list_rate) || 0);
                });
            });
        };

        // "Add item" dialog — called by the grid's Add item button
        frm.boq_add_item_dialog = function(subCatDoc, subCatName) {
            var d;
            d = new frappe.ui.Dialog({
                title: "Add Item — " + subCatName,
                fields: [
                    {
                        fieldname: "item", fieldtype: "Link", options: "Item",
                        label: "Item", reqd: 1,
                        onchange: function() {
                            const item = d.get_value("item");
                            if (!item) return;
                            // Always fetch item metadata
                            frappe.db.get_value("Item", item, ["item_name", "stock_uom"]).then(r => {
                                if (r && r.message) {
                                    d.set_value("item_name", r.message.item_name || item);
                                    d.set_value("uom", r.message.stock_uom || "Nos");
                                }
                            });
                            // Try cost breakdown from Item master first; fall back to price list
                            frappe.call({
                                method: "construction_management.construction_management.api.get_item_default_cost_components",
                                args: { item: item },
                                callback: function(r) {
                                    if (r.message && r.message.length > 0) {
                                        const total = r.message.reduce((sum, c) => sum + (parseFloat(c.amount) || 0), 0);
                                        d.set_value("unit_cost", total);
                                        d._pending_cost_components = r.message;
                                        frappe.show_alert({
                                            message: `Cost breakdown auto-filled from item history (${r.message.length} components)`,
                                            indicator: "blue"
                                        }, 3);
                                    } else {
                                        d._pending_cost_components = null;
                                        // Fall back to price list if no cost breakdown stored
                                        frm.boq_get_price(item, frm.doc.currency, rate => {
                                            if (rate) {
                                                d.set_value("unit_cost", rate);
                                                frappe.show_alert({
                                                    message: "Rate " + rate + " fetched from price list",
                                                    indicator: "green"
                                                }, 3);
                                            }
                                        });
                                    }
                                }
                            });
                        }
                    },
                    { fieldname: "item_name", fieldtype: "Data", label: "Item Name", reqd: 1 },
                    { fieldname: "col1", fieldtype: "Column Break" },
                    { fieldname: "qty", fieldtype: "Float", label: "Quantity", reqd: 1, default: 1 },
                    { fieldname: "uom", fieldtype: "Link", options: "UOM", label: "UOM", reqd: 1, default: "Nos" },
                    { fieldname: "sec1", fieldtype: "Section Break", label: "Rates" },
                    {
                        fieldname: "unit_cost", fieldtype: "Currency",
                        label: "Unit Cost", default: 0,
                        description: "Cost to contractor — fetched from price list, editable"
                    },
                    { fieldname: "col2", fieldtype: "Column Break" },
                    {
                        fieldname: "margin_percent", fieldtype: "Percent",
                        label: "Margin %", default: 0,
                        description: "Your profit margin — hidden from client"
                    },
                    { fieldname: "notes", fieldtype: "Small Text", label: "Notes" }
                ],
                primary_action_label: "Add Item",
                primary_action: function(values) {
                    const newRow = frm.add_child("items");
                    newRow.boq_category   = subCatDoc;
                    newRow.item           = values.item;
                    newRow.item_name      = values.item_name || values.item;
                    newRow.qty            = values.qty || 1;
                    newRow.uom            = values.uom || "Nos";
                    newRow.unit_cost      = values.unit_cost || 0;
                    newRow.margin_percent = values.margin_percent || 0;
                    newRow.notes          = values.notes || "";
                    if (d._pending_cost_components && d._pending_cost_components.length) {
                        newRow.cost_components = d._pending_cost_components.map(c => ({
                            component_type: c.component_type,
                            description: c.description,
                            amount: c.amount
                        }));
                    }
                    frm.dirty();
                    frm.save().then(() => {
                        frm.boq_render_grid();
                    });
                    d.hide();
                }
            });
            d.show();
        };

        // ── Cost breakdown dialog (click unit cost cell to open) ─────
        frm.boq_open_cost_breakdown = function(rowName) {
            const row = frm.doc.items.find(r => r.name === rowName);
            if (!row) return;

            console.log("=== boq_open_cost_breakdown called ===");
            console.log("row.name:", rowName);
            const allComponents = frm.doc.cost_components || [];
            const rowComponents = allComponents.filter(c => c.boq_item === rowName);
            console.log("frm.doc.cost_components total:", allComponents.length);
            console.log("components for this row:", rowComponents.length);

            const existingComponents = rowComponents.map(c => ({
                component_type: c.component_type,
                description: c.description,
                amount: c.amount
            }));

            console.log("existingComponents built:", existingComponents);

            const hasValidItem = !!(row.item && row.item.length > 0);

            const d = new frappe.ui.Dialog({
                title: `Cost Breakdown — ${row.item_name || row.item || "Item"}`,
                size: "large",
                fields: [
                    {
                        fieldname: "components_html",
                        fieldtype: "HTML"
                    },
                    {
                        fieldname: "save_as_default",
                        fieldtype: "Check",
                        label: hasValidItem
                            ? "Save this breakdown as default for this item (auto-fill in future BOQs)"
                            : "Save as default (unavailable — this row has no valid Item link)",
                        default: hasValidItem ? 1 : 0,
                        read_only: hasValidItem ? 0 : 1
                    }
                ],
                primary_action_label: "Apply",
                primary_action: function(values) {
                    const components = d._components || [];

                    if (components.length === 0) {
                        frappe.msgprint("Add at least one cost component before applying.");
                        return;
                    }

                    const incomplete = components.some(
                        c => !c.component_type || !c.description || c.amount === "" || c.amount === null || c.amount === undefined
                    );
                    if (incomplete) {
                        frappe.msgprint("Please fill in Type, Description, and Amount for every row.");
                        return;
                    }

                    const total = components.reduce((sum, c) => sum + (parseFloat(c.amount) || 0), 0);

                    // Remove old components for this row, add the new ones
                    frm.doc.cost_components = (frm.doc.cost_components || []).filter(
                        c => c.boq_item !== rowName
                    );
                    components.forEach(c => {
                        frm.doc.cost_components.push({
                            doctype: "BOQ Cost Component",
                            boq_item: rowName,
                            component_type: c.component_type,
                            description: c.description,
                            amount: parseFloat(c.amount) || 0
                        });
                    });
                    row.unit_cost = total;

                    frm.dirty();

                    const newComponents = components.map(c => ({
                        component_type: c.component_type,
                        description: c.description,
                        amount: parseFloat(c.amount) || 0
                    }));

                    if (values.save_as_default && hasValidItem) {
                        frappe.call({
                            method: "construction_management.construction_management.api.save_item_default_cost_components",
                            args: {
                                item: row.item,
                                components: JSON.stringify(newComponents)
                            },
                            callback: function(r) {
                                if (r.message && r.message.status === "success") {
                                    frappe.show_alert({
                                        message: "Default cost breakdown saved for this item",
                                        indicator: "green"
                                    }, 3);
                                }
                            }
                        });
                    }

                    frm.save().then(() => {
                        frm.boq_render_grid();
                        frappe.show_alert({
                            message: "Cost breakdown saved",
                            indicator: "green"
                        }, 2);
                    }).catch((err) => {
                        console.error("Save failed:", err);
                        frappe.msgprint("Failed to save cost breakdown. Check console for details.");
                    });
                    d.hide();
                }
            });

            d._components = existingComponents.length ? existingComponents : [];

            function renderComponentsTable() {
                const wrapper = d.fields_dict.components_html.$wrapper;

                const typeColors = {
                    "Labour":      "#4f46e5",
                    "Material":    "#16a34a",
                    "Equipment":   "#d97706",
                    "Subcontract": "#db2777",
                    "Other":       "#6b7280"
                };

                let rowsHtml = "";

                d._components.forEach((c, idx) => {
                    const borderColor = typeColors[c.component_type] || "#6b7280";
                    rowsHtml += `
                    <div class="comp-row" data-idx="${idx}" style="
                        display:grid;
                        grid-template-columns:130px 1fr 130px 32px;
                        gap:10px;
                        align-items:center;
                        padding:10px 12px;
                        margin-bottom:6px;
                        border-left:3px solid ${borderColor};
                        background:var(--control-bg, #f5f6f8);
                        border-radius:6px;
                    ">
                        <select class="form-control comp-type" data-idx="${idx}" style="font-size:12px;height:32px">
                            <option value="Labour"      ${c.component_type === "Labour"      ? "selected" : ""}>Labour</option>
                            <option value="Material"    ${c.component_type === "Material"    ? "selected" : ""}>Material</option>
                            <option value="Equipment"   ${c.component_type === "Equipment"   ? "selected" : ""}>Equipment</option>
                            <option value="Subcontract" ${c.component_type === "Subcontract" ? "selected" : ""}>Subcontract</option>
                            <option value="Other"       ${c.component_type === "Other"       ? "selected" : ""}>Other</option>
                        </select>
                        <input type="text" class="form-control comp-desc" data-idx="${idx}"
                               value="${(c.description || "").replace(/"/g, "&quot;")}"
                               placeholder="Description" style="font-size:13px;height:32px">
                        <input type="number" class="form-control comp-amount" data-idx="${idx}"
                               value="${c.amount || ""}"
                               placeholder="0.00" style="font-size:13px;height:32px;text-align:right;font-weight:500">
                        <button class="btn btn-xs comp-remove" data-idx="${idx}" title="Remove"
                                style="border:none;background:none;color:var(--text-muted);height:32px;display:flex;align-items:center;justify-content:center">
                            <i class="fa fa-times"></i>
                        </button>
                    </div>`;
                });

                const total = d._components.reduce((sum, c) => sum + (parseFloat(c.amount) || 0), 0);

                wrapper.html(`
                    <div style="margin-bottom:10px">
                        <div style="display:grid;grid-template-columns:130px 1fr 130px 32px;gap:10px;padding:0 12px;margin-bottom:6px">
                            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">Type</span>
                            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">Description</span>
                            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;text-align:right">Amount</span>
                            <span></span>
                        </div>
                        <div id="comp-rows-body">
                            ${rowsHtml || '<div style="text-align:center;color:var(--text-muted);font-size:13px;padding:28px 12px;border:1.5px dashed var(--border-color);border-radius:8px">No components yet. Click <b>+ Add Component</b> below to start.</div>'}
                        </div>
                    </div>
                    <button class="btn btn-sm btn-default" id="add-component-btn" style="font-size:12px;font-weight:500">
                        <i class="fa fa-plus"></i>&nbsp; Add Component
                    </button>
                    <div style="margin-top:14px;padding:10px 14px;background:var(--control-bg, #f5f6f8);border-radius:6px;display:flex;justify-content:space-between;align-items:center">
                        <span style="font-size:12px;color:var(--text-muted)">Total Unit Cost</span>
                        <span style="font-size:16px;font-weight:600;color:var(--text-color)">${frappe.format(total, { fieldtype: "Currency" })}</span>
                    </div>
                `);

                wrapper.find("#add-component-btn").on("click", function() {
                    d._components.push({ component_type: "Labour", description: "", amount: "" });
                    renderComponentsTable();
                    setTimeout(() => { wrapper.find(".comp-desc").last().focus(); }, 30);
                });

                wrapper.find(".comp-remove").on("click", function() {
                    const idx = parseInt($(this).data("idx"));
                    d._components.splice(idx, 1);
                    renderComponentsTable();
                });

                wrapper.find(".comp-type").on("change", function() {
                    const idx = parseInt($(this).data("idx"));
                    d._components[idx].component_type = $(this).val();
                    renderComponentsTable();
                });

                wrapper.find(".comp-desc").on("change", function() {
                    const idx = parseInt($(this).data("idx"));
                    d._components[idx].description = $(this).val();
                });

                wrapper.find(".comp-amount").on("change", function() {
                    const idx = parseInt($(this).data("idx"));
                    d._components[idx].amount = $(this).val();
                    renderComponentsTable();
                });
            }

            d.show();
            renderComponentsTable();
        };

        // ── Main grid render ──────────────────────────────────────────
        frm.boq_render_grid = function() {
            frm.fields_dict["items"].$wrapper.hide();

            let container = $(frm.wrapper).find("#boq-custom-grid");
            if (!container.length) {
                frm.fields_dict["items"].$wrapper
                    .closest(".form-column")
                    .append('<div id="boq-custom-grid" style="margin-top:16px"></div>');
                container = $(frm.wrapper).find("#boq-custom-grid");
            }

            const items = frm.doc.items || [];
            const CUR   = frm.doc.currency || "AED";

            // Empty state — no items and no registered (pending) categories
            if (!items.length && !frm._boq_registered.length) {
                container.html(`
                    <div style="border:1px solid var(--border-color);border-radius:var(--border-radius);overflow:hidden">
                        <div style="padding:12px 16px;text-align:center;color:var(--text-muted);font-size:13px">
                            No items yet. Click below to add a category.
                        </div>
                        <div style="padding:10px 16px;border-top:1px solid var(--border-color)">
                            <button class="btn btn-xs btn-default boq-add-cat-btn" style="width:100%">
                                <i class="fa fa-plus"></i> Add Category
                            </button>
                        </div>
                    </div>`);
                container.find(".boq-add-cat-btn").on("click", () => frm._boq_show_add_cat());
                return;
            }

            // Collect unique category doc names from saved items for name lookup
            const catDocs = [...new Set(items.map(r => r.boq_category).filter(Boolean))];

            frappe.db.get_list("BOQ Category", {
                filters: [["name", "in", catDocs.length ? catDocs : ["__none__"]]],
                fields: ["name", "category_name", "parent_node"],
                limit: 500
            }).then(catList => {
                const catMap = {};
                catList.forEach(c => { catMap[c.name] = c; });

                // ── Build two-level structure ──────────────────────────
                // parentOrder: insertion-ordered array of parent doc keys
                // structure[pKey] = { name, subcats: { subKey: { name, items[] } } }
                const parentOrder = [];
                const structure   = {};

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
                frm._boq_registered.forEach(reg => {
                    if (reg.subDoc !== "__placeholder__") {
                        ensureSub(reg.parentDoc, reg.parentName, reg.subDoc, reg.subName);
                    } else {
                        ensureParent(reg.parentDoc, reg.parentName);
                    }
                });

                // 2. Actual saved items (FIX: translate boq_category doc name → human name)
                items.forEach(row => {
                    if (!row.boq_category) return;
                    const info    = catMap[row.boq_category] || {};
                    const subName = info.category_name  || row.boq_category;
                    const parentDoc  = info.parent_node || null;
                    const parentName = row.boq_parent_category
                        || (parentDoc && catMap[parentDoc] && catMap[parentDoc].category_name)
                        || subName;
                    const pKey = parentDoc || row.boq_category;

                    ensureSub(pKey, parentName, row.boq_category, subName);
                    structure[pKey].subcats[row.boq_category].items.push(row);
                });

                // ── Formatters ─────────────────────────────────────────
                const fmt0 = n => parseFloat(n || 0).toLocaleString("en-AE", { maximumFractionDigits: 0 });
                const fmt2 = n => parseFloat(n || 0).toLocaleString("en-AE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

                function buildCostTooltip(row) {
                    const components = (frm.doc.cost_components || []).filter(
                        c => c.boq_item === row.name
                    );
                    if (!components.length) {
                        return "No cost breakdown — click to add";
                    }
                    const lines = components.map(c =>
                        `${c.component_type}: ${c.description} = ${parseFloat(c.amount || 0).toLocaleString()}`
                    );
                    const total = components.reduce((sum, c) => sum + (parseFloat(c.amount) || 0), 0);
                    lines.push("---");
                    lines.push(`Total: ${total.toLocaleString()}`);
                    return lines.join("\n");
                }

                // ── Build HTML ──────────────────────────────────────────
                let html = `<div style="border:1px solid var(--border-color);border-radius:var(--border-radius);overflow:hidden;font-family:var(--font-stack);font-size:12px">`;

                parentOrder.forEach(pKey => {
                    const cat      = structure[pKey];
                    const subKeys  = Object.keys(cat.subcats);
                    const catTotal = subKeys.reduce(
                        (a, s) => a + cat.subcats[s].items.reduce((b, r) => b + (r.amount || 0), 0), 0
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
                        subKeys.forEach(subKey => {
                            const sub      = cat.subcats[subKey];
                            const subTotal = sub.items.reduce((a, r) => a + (r.amount || 0), 0);
                            const subCost  = sub.items.reduce((a, r) => a + ((r.unit_cost || 0) * (r.qty || 0)), 0);
                            const subOpen  = frm._boq_sub_state[subKey] !== false;

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
                                <div style="display:grid;grid-template-columns:28px 1fr 70px 56px 90px 70px 90px 28px;padding:6px 14px 6px 28px;background:var(--control-bg);border-bottom:1px solid var(--border-color)">
                                    <span></span>
                                    <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">Description</span>
                                    <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;text-align:right">Qty</span>
                                    <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;text-align:center">UOM</span>
                                    <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;text-align:right">Unit Cost</span>
                                    <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;text-align:right">Margin %</span>
                                    <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;text-align:right">Amount</span>
                                    <span></span>
                                </div>`;

                                // Item rows
                                sub.items.forEach((row, idx) => {
                                    const rowBg = idx % 2 === 0 ? "var(--bg-color)" : "var(--control-bg)";
                                    html += `
                                    <div class="boq-item-row" data-name="${row.name}"
                                         style="display:grid;grid-template-columns:28px 1fr 70px 56px 90px 70px 90px 28px;padding:0 14px 0 28px;background:${rowBg};border-bottom:1px solid var(--border-color);align-items:center">
                                        <span style="color:var(--text-muted);font-size:11px;text-align:center">${idx + 1}</span>
                                        <span style="padding:7px 4px;font-size:12px;font-weight:500;color:var(--text-color)">
                                            ${row.item_name || row.item || ""}
                                            ${row.notes ? `<div style="font-size:10px;color:var(--text-muted)">${row.notes}</div>` : ""}
                                        </span>
                                        <span style="padding:7px 4px;font-size:12px;color:var(--text-muted);text-align:right">${fmt2(row.qty)}</span>
                                        <span style="padding:7px 4px;font-size:11px;color:var(--text-muted);text-align:center">${row.uom || ""}</span>
                                        <span class="boq-cost-breakdown-trigger" data-name="${row.name}"
                                              style="padding:7px 4px;font-size:12px;color:var(--text-muted);text-align:right;cursor:pointer"
                                              title="${buildCostTooltip(row).replace(/"/g, '&quot;')}">
                                            ${fmt2(row.unit_cost)}
                                            ${(frm.doc.cost_components || []).some(c => c.boq_item === row.name)
                                                ? '<i class="fa fa-list-ul" style="font-size:9px;margin-left:4px;color:var(--primary)"></i>'
                                                : '<i class="fa fa-plus-circle" style="font-size:9px;margin-left:4px;color:var(--text-muted)"></i>'}
                                        </span>
                                        <span style="padding:7px 4px;font-size:12px;color:var(--text-muted);text-align:right">${fmt2(row.margin_percent)}%</span>
                                        <span style="padding:7px 4px;font-size:12px;font-weight:600;color:var(--primary);text-align:right">${CUR} ${fmt0(row.amount)}</span>
                                        <span style="text-align:center">
                                            <button class="boq-del-btn" data-name="${row.name}"
                                                    style="background:none;border:none;color:var(--text-muted);cursor:pointer;opacity:0.4;padding:2px 4px;font-size:12px">
                                                <i class="fa fa-times"></i>
                                            </button>
                                        </span>
                                    </div>`;
                                });

                                // Subtotal row
                                html += `
                                <div style="display:grid;grid-template-columns:28px 1fr 70px 56px 90px 70px 90px 28px;padding:7px 14px 7px 28px;background:#162d52;border-top:2px solid #c9a520;border-bottom:1px solid #1e3356">
                                    <span></span>
                                    <span style="font-size:10px;font-weight:600;color:#a0b0c8;letter-spacing:.4px;grid-column:span 3">SUBTOTAL — ${sub.name.toUpperCase()}</span>
                                    <span style="font-size:11px;color:#7090b8;text-align:right">${CUR} ${fmt0(subCost)}</span>
                                    <span></span>
                                    <span style="font-size:11px;font-weight:600;color:#fff;text-align:right">${CUR} ${fmt0(subTotal)}</span>
                                    <span></span>
                                </div>`;

                                // Add item button
                                html += `
                                <div style="padding:8px 14px 8px 28px;background:var(--control-bg);border-bottom:1px solid var(--border-color)">
                                    <button class="boq-add-item-btn"
                                            data-subdoc="${encodeURIComponent(subKey)}"
                                            data-subname="${encodeURIComponent(sub.name)}"
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
                                    style="display:inline-flex;align-items:center;gap:4px;color:#3730A3;background:none;border:none;cursor:pointer;font-size:11px;font-weight:500;padding:3px 6px;border-radius:4px">
                                <i class="fa fa-plus"></i> Add sub-category to ${cat.name}
                            </button>
                        </div>`;
                    }
                });

                // Add category button
                html += `
                <div style="padding:10px 16px">
                    <button class="boq-add-cat-btn"
                            style="width:100%;display:flex;align-items:center;justify-content:center;gap:6px;padding:8px;border:1.5px dashed var(--border-color);border-radius:var(--border-radius);background:transparent;color:var(--text-muted);font-size:12px;font-weight:500;cursor:pointer">
                        <i class="fa fa-plus"></i> Add Category
                    </button>
                </div>
                </div>`;

                container.html(html);

                // ── Toggle category ───────────────────────────────────
                container.find(".boq-cat-hd").on("click", function() {
                    const pkey = $(this).data("pkey");
                    frm._boq_cat_state[pkey] = frm._boq_cat_state[pkey] === false ? true : false;
                    frm.boq_render_grid();
                });

                // ── Toggle sub-category ───────────────────────────────
                container.find(".boq-sub-hd").on("click", function() {
                    const subkey = $(this).data("subkey");
                    frm._boq_sub_state[subkey] = frm._boq_sub_state[subkey] === false ? true : false;
                    frm.boq_render_grid();
                });

                // ── Delete row ────────────────────────────────────────
                container.find(".boq-del-btn").on("click", function(e) {
                    e.stopPropagation();
                    const name = $(this).data("name");
                    frappe.confirm("Remove this item?", () => {
                        const idx = frm.doc.items.findIndex(r => r.name === name);
                        if (idx > -1) {
                            frm.doc.items.splice(idx, 1);
                            frm.dirty();
                            frm.save();
                        }
                    });
                });

                // ── Cost breakdown (click on unit cost cell) ──────────
                container.find(".boq-cost-breakdown-trigger").on("click", function(e) {
                    e.stopPropagation();
                    const rowName = $(this).data("name");
                    const row = frm.doc.items.find(r => r.name === rowName);

                    console.log("=== Cost Breakdown Debug ===");
                    console.log("Row name:", rowName);
                    console.log("Row item:", row ? row.item : "ROW NOT FOUND");
                    console.log("cost_components for this row:", row ? (frm.doc.cost_components || []).filter(c => c.boq_item === rowName) : "N/A");
                    console.log("Existing unit_cost:", row ? row.unit_cost : "N/A");
                    console.log("============================");

                    frm.boq_open_cost_breakdown(rowName);
                });

                // ── Add item ──────────────────────────────────────────
                container.find(".boq-add-item-btn").on("click", function(e) {
                    e.stopPropagation();
                    const subDoc  = decodeURIComponent($(this).data("subdoc"));
                    const subName = decodeURIComponent($(this).data("subname"));
                    frm.boq_add_item_dialog(subDoc, subName);
                });

                // ── Add sub-category (registers state, no dummy row) ──
                container.find(".boq-add-subcat-btn").on("click", function(e) {
                    e.stopPropagation();
                    const pKey  = decodeURIComponent($(this).data("pkey"));
                    const pName = decodeURIComponent($(this).data("pname"));
                    frappe.prompt([{
                        fieldname: "subcat",
                        fieldtype: "Link",
                        options: "BOQ Category",
                        label: "Sub-category",
                        reqd: 1,
                        filters: { is_group: 0, parent_node: pKey }
                    }], vals => {
                        frappe.db.get_value("BOQ Category", vals.subcat, "category_name").then(r => {
                            const subName = (r && r.message && r.message.category_name) || vals.subcat;
                            frm._boq_registered.push({
                                parentDoc: pKey, parentName: pName,
                                subDoc: vals.subcat, subName: subName
                            });
                            frm.boq_render_grid();
                        });
                    }, "Add Sub-category to " + pName, "Add");
                });

                // ── Add category (registers state, no dummy row) ──────
                container.find(".boq-add-cat-btn").on("click", function() {
                    frm._boq_show_add_cat();
                });
            });
        };

        frm._boq_show_add_cat = function() {
            frappe.prompt([{
                fieldname: "cat",
                fieldtype: "Link",
                options: "BOQ Category",
                label: "Category",
                reqd: 1,
                filters: { is_group: 1 }
            }], vals => {
                frappe.db.get_value("BOQ Category", vals.cat, "category_name").then(r => {
                    const catName = (r && r.message && r.message.category_name) || vals.cat;
                    const alreadyExists = frm._boq_registered.some(
                        reg => reg.parentDoc === vals.cat && reg.subDoc === "__placeholder__"
                    );
                    if (!alreadyExists) {
                        frm._boq_registered.push({
                            parentDoc: vals.cat, parentName: catName,
                            subDoc: "__placeholder__", subName: ""
                        });
                    }
                    frm.boq_render_grid();
                });
            }, "Add Category", "Add");
        };
    },

    refresh: function(frm) {
        frm.fields_dict["items"].$wrapper.hide();
        if (!frm._boq_cat_state)  frm._boq_cat_state  = {};
        if (!frm._boq_sub_state)  frm._boq_sub_state  = {};
        if (!frm._boq_registered) frm._boq_registered = [];
        frm.boq_render_grid();
    },

    after_save: function(frm) {
        frm.boq_render_grid();
    }
});
