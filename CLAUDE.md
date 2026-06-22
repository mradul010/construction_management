# Construction Management App — Claude Code Context

## Identity
- App name: construction_management
- Publisher: Vigisolvo Private Limited
- Built on: Frappe v16 / ERPNext v16
- Primary site: qatra
- Bench path: /home/mradul010/frappe-bench16
- App path: /home/mradul010/frappe-bench16/apps/construction_management/construction_management

## Stack rules — follow strictly
- Python 3.11+, MariaDB via Frappe ORM only — never raw SQL
- Use frappe.qb (Query Builder) if ORM is insufficient
- All monetary fields: fieldtype=Currency, options=currency
- All percentage fields: fieldtype=Percent
- All decimal fields: fieldtype=Float
- Calculated/read-only fields: set in Python validate() — never in JS
- Naming series format: MODULE-YYYY-.#### e.g. BOQ-YYYY-.####
- All hooks go in hooks.py — never monkey-patch ERPNext core
- Custom fields on ERPNext native doctypes go in fixtures/custom_fields.json
- Controller imports: from frappe.model.document import Document
- After every new DocType or field change: bench --site qatra migrate
- After every Python or client script change: bench --site qatra clear-cache

## App module
- Module name: Construction Management
- modules.txt already contains: Construction Management

## DocTypes built so far
(update this list as each doctype is created)
- Construction Settings (Single, module=Construction Management)
- BOQ Category (master, title_field=category_name, search_fields=category_name+category_code)
- BOQ Item (child table, istable=1, editable_grid, fields: boq_category/item/item_name/qty/uom/material_rate/labour_rate/margin_percent/unit_rate/amount/notes)
- BOQ Revision (child table, istable=1, fields: revision_no/revision_date/revised_by/remarks)
- BOQ (submittable, autoname=BOQ-YYYY-.####, title_field=project, track_changes, child tables: items→BOQ Item / revisions→BOQ Revision)
- BOQ Cost Component (child table, istable=1, fields: component_type Select/description Data/amount Currency — nested inside BOQ Item rows)
- Item Cost Template (child table, istable=1, identical fields — attached to ERPNext Item master via custom field)

## Coding conventions
- No raw frappe.db.sql() — use frappe.get_doc(), frappe.get_all(), frappe.db.get_value(), frappe.qb
- Child tables: never add manual foreign keys — Frappe handles parent/parentfield/parenttype/idx automatically
- Submittable DocTypes: docstatus is added by Frappe automatically — never add it manually
- Print formats: Jinja2 + HTML tables only — no flexbox, no CSS grid (wkhtmltopdf compatibility)
- Client scripts: frappe.ui.form.on() pattern only

## Build order for Phase 1 (BOQ module)
1. Construction Settings (Single DocType)
2. BOQ Category (Master)
3. BOQ Item (Child Table)
4. BOQ Revision (Child Table)
5. BOQ (Main transaction)
6. Custom fields on ERPNext Item master (via fixtures)
7. BOQ client script (custom category-grouped grid)
8. BOQ print format (Jinja2 HTML)

## Business context
- Construction contractors in UAE (AED) and India (INR)
- Currency is per-BOQ — not global
- BOQ = Bill of Quantities: work items grouped by category
- Each item: material_rate + labour_rate + margin% → unit_rate → amount
- Status flow: Draft → Submitted → Revised (via Amend)
- Amend creates Rev 2, Rev 3 etc — never overwrites previous revision
