# Qatra Construction Management - Client Portal Technical Documentation

## 1. Executive Summary

This document describes the Client Portal implementation in `construction_management` as inspected from the repository source. The primary portal is the Qatra client portal mounted at `/client-portal` and routed in `construction_management/hooks.py`. It is a server-rendered website portal built from `construction_management/www/client_portal*.py`, `construction_management/www/client-portal*.html`, `construction_management/templates/client_portal/*`, `construction_management/public/js/qatra_client_portal*.js`, and `construction_management/public/css/qatra_client_portal.css`.

Implemented primary `/client-portal` pages are login, dashboard, projects, project detail, reports, report detail, documents placeholder, gallery placeholder, approvals placeholder, payments, and logout. BOQ, RA Bill, and Work Progress pages exist in the older Construction Portal route family (`/construction-portal`, `/boq`, `/ra-bill`, `/work-progress`, `/dprs`) and are documented as legacy/adjacent portal code because the new `/client-portal` navigation does not link to direct BOQ or RA Bill pages.

Authentication and customer resolution are centralized in `construction_management/portal_utils.py`. The new client portal requires a logged-in `Website User` linked to one or more Customers through Contact, Contact Email, Contact `user`, Customer Portal User, or ERPNext default customer lookup. Project, report, invoice, payment, and financial data are filtered by the resolved Customer list.

## 2. Client Portal Entry Point

Main entry route:

```text
/client-portal
```

Source:

- `construction_management/hooks.py`: `website_route_rules`
- `construction_management/www/client_portal.py`: login page controller
- `construction_management/www/client-portal.html`: login template
- `construction_management/public/js/qatra_client_portal_login.js`: login/reset behavior
- `construction_management/public/css/qatra_client_portal.css`: portal styling

Behavior:

- Guest users see the login form.
- Logged-in users with valid portal access are redirected to `/client-portal/dashboard`.
- Logged-in users without access remain on the login page and see `context.portal_error`.
- Password reset is handled by whitelisted method `construction_management.www.client_portal.reset_client_portal_password`.

## 3. Architecture Overview

The primary portal uses Frappe Website Pages:

```text
hooks.py website_route_rules
-> www/client_portal*.py get_context()
-> portal_utils.py data and authorization helpers
-> www/client-portal*.html Jinja templates
-> templates/client_portal/base.html + sidebar.html
-> public/js/qatra_client_portal.js for shell/filter/table behavior
```

Important architectural points:

- Most data is assembled server-side in `portal_utils.py`.
- The new portal does not expose a general JSON dashboard API; pages use `get_context`.
- Login uses `/api/method/login` directly from `qatra_client_portal_login.js`.
- Report tables, project filtering, CSV download, mobile navigation, sidebar collapse, and sign-out are handled client-side in `qatra_client_portal.js`.
- Older Construction Portal pages use `setup_portal_context()` and `require_portal_customer()` from `portal_utils.py`.

## 4. Authentication & Customer Resolution

Implemented in `construction_management/portal_utils.py`.

### New Qatra Client Portal

Function chain:

```text
setup_client_portal_context()
-> require_client_portal_user()
-> get_client_portal_access()
-> get_customers_for_portal_user()
-> get_portal_user_ids()
-> Contact / Contact Email / Dynamic Link / Portal User / ERPNext default customer
```

Rules:

- Guest users are redirected to `/client-portal`.
- `get_client_portal_access()` requires `User.user_type == "Website User"`.
- Access is allowed when at least one Customer is resolved.
- Multiple Customers are supported by `get_customers_for_portal_user()` and stored in `context.customers`.
- `context.customer` is set to the first resolved Customer for display compatibility.
- `ensure_customer_portal_user()` appends the logged-in user to Customer `portal_users` when legacy portal helpers resolve a single customer.

Customer resolution sources:

| Step | Function | Source |
|---|---|---|
| User identifiers | `get_portal_user_ids(user)` | User `name`, `email`, `username` |
| Contact user field | `get_customers_from_contact_user(user_id)` | `Contact.user` |
| Contact Email child table | `get_customers_from_contact_email(user_id)` | `Contact Email.email_id` |
| Contact email field | `get_customers_from_contact(user_id)` | `Contact.email_id` |
| Dynamic Link | `get_customers_from_contacts(contacts)` | `Dynamic Link.link_doctype = Customer` |
| Name fallback | `get_matching_customer_for_contact(contact)` | Customer name or `customer_name` matching Contact |
| Customer portal users | `get_customers_from_portal_user(user_id)` | Customer `Portal User` child table |
| ERPNext default | `get_default_customer_from_erpnext(user)` | `erpnext.utilities.get_default_customer` |

Failure behavior:

- Guest: redirect to `/client-portal` for new portal; PermissionError for legacy helpers.
- Non-Website User: access denied with message "This portal is reserved for client website users."
- No linked Customer: access denied with message "This account is not linked to a QATRA client record."

## 5. Navigation Structure

Source:

- `portal_utils.py`: `QATRA_CLIENT_PORTAL_ITEMS`
- `templates/client_portal/sidebar.html`
- `templates/client_portal/base.html`
- `public/js/qatra_client_portal.js`

Actual new portal navigation:

```text
Client Portal
|-- Dashboard        /client-portal/dashboard
|-- Projects         /client-portal/projects
|   `-- Project      /client-portal/project/<name>
|-- Reports          /client-portal/reports
|   `-- Report       /client-portal/report/<report-key-or-dpr-name>?project=<project>&date=<date>
|-- Documents        /client-portal/documents
|-- Gallery          /client-portal/gallery
|-- Approvals        /client-portal/approvals
|-- Payments         /client-portal/payments
|-- Logout           /client-portal/logout
```

Legacy/adjacent Construction Portal navigation:

```text
Construction Portal
|-- Dashboard                  /construction-portal
|-- Projects                   /construction-projects
|   `-- Project Detail          /construction-project-detail?name=<project>
|-- BOQ                         /boq
|   `-- BOQ Detail              /boq-detail?name=<boq>
|-- RA Bills                    /ra-bill
|   `-- RA Bill Detail          /ra-bill-detail?name=<ra_bill>
|-- Work Progress               /work-progress
|   `-- Work Progress Detail    /work-progress-detail?boq=<boq>
|-- Daily Progress Reports      /dprs
|   `-- DPR Detail              /dpr-detail?name=<dpr>
|-- Logout                      /?cmd=web_logout
```

Active menu state:

- New portal: `active_page` is set by `setup_client_portal_context(context, key)` and compared in `sidebar.html`.
- Legacy portal: `setup_portal_context()` sets sidebar items but active-state logic is inherited from Frappe website sidebar behavior and `public/js/portal.js`.

## 6. Complete Page Inventory

| Page | Route | Template | Controller | JS | Main Data Source | Access Rule |
|---|---|---|---|---|---|---|
| Login | `/client-portal` | `www/client-portal.html` | `www/client_portal.py` | `qatra_client_portal_login.js` | User login and reset | Guest allowed; logged-in valid client redirects |
| Dashboard | `/client-portal/dashboard` | `www/client-portal-dashboard.html` | `www/client_portal_dashboard.py` | `qatra_client_portal.js` | Project, Sales Order, RA Bill, Sales Invoice, Payment Entry, DPR | `Website User` linked to Customer |
| Projects | `/client-portal/projects` | `www/client-portal-projects.html` | `www/client_portal_projects.py` | `qatra_client_portal.js` | Project | Customer-filtered Project field |
| Project Detail | `/client-portal/project/<name>` | `www/client-portal-project.html` | `www/client_portal_project.py` | `qatra_client_portal.js` | Project plus financial summary | `get_authorized_customer_project()` |
| Reports | `/client-portal/reports` | `www/client-portal-reports.html` | `www/client_portal_reports.py` | `qatra_client_portal.js` | Virtual report cards, DPR, materials, financials | Authorized projects only |
| Report Detail | `/client-portal/report/<name>` | `www/client-portal-report.html` | `www/client_portal_report.py` | `qatra_client_portal.js` | Virtual reports or Daily Progress Report | `get_authorized_client_report()` |
| Documents | `/client-portal/documents` | `www/client-portal-documents.html` | `www/client_portal_documents.py` | `qatra_client_portal.js` | Placeholder page shell | Authenticated client |
| Gallery | `/client-portal/gallery` | `www/client-portal-gallery.html` | `www/client_portal_gallery.py` | `qatra_client_portal.js` | Placeholder page shell | Authenticated client |
| Approvals | `/client-portal/approvals` | `www/client-portal-approvals.html` | `www/client_portal_approvals.py` | `qatra_client_portal.js` | Client Approval Request list | Authenticated client, Customer/Project filtered |
| Payments | `/client-portal/payments` | `www/client-portal-payments.html` | `www/client_portal_payments.py` | `qatra_client_portal.js` | Sales Invoice, Payment Entry Reference, Payment Entry | Authorized project/customer |
| Logout | `/client-portal/logout` | `www/client-portal-logout.html` | `www/client_portal_logout.py` | inline template redirect | Logout endpoint | Any visitor |
| Legacy BOQ List | `/boq` | `www/boq.html` | `www/boq.py` | `portal.js` | BOQ | Single resolved portal Customer |
| Legacy BOQ Detail | `/boq-detail?name=` | `www/boq-detail.html` | `www/boq_detail.py` | `portal.js` | BOQ + BOQ Item | `validate_boq_customer()` |
| Legacy RA Bills | `/ra-bill` | `www/ra-bill.html` | `www/ra_bill.py` | `portal.js` | RA Bill | Single resolved portal Customer |
| Legacy RA Bill Detail | `/ra-bill-detail?name=` | `www/ra-bill-detail.html` | `www/ra_bill_detail.py` | `portal.js` | RA Bill + RA Bill Item | `validate_ra_bill_customer()` |
| Legacy Work Progress | `/work-progress` | `www/work-progress.html` | `www/work_progress.py` | `portal.js` | RA Bill Transaction or RA Bill Item + BOQ Item | Single resolved portal Customer |

## 7. Client Portal Dashboard

Controller: `www/client_portal_dashboard.py`

Main function:

- `get_context(context)` calls `setup_client_portal_context(context, "dashboard")`.
- It sets `context.dashboard = get_client_dashboard_data(project_name=frappe.form_dict.get("project"), customers=context.customers)`.

Dashboard cards and values:

| Card / Widget | Source | Formula / Logic |
|---|---|---|
| Selected project | `get_dashboard_selected_project()` | URL `project` if authorized; else first active/open project; else first project |
| Total Projects | `get_dashboard_project_summary()` | `len(projects)` |
| Active Projects | `get_dashboard_project_summary()` | statuses in `Open`, `In Progress`, `Active` |
| Total Contract Value | `get_dashboard_client_financial_summary()` | sum project contract values |
| Total Received | `get_dashboard_client_financial_summary()` | `received_against_invoices + advance_received` |
| Overall Progress | `get_project_work_progress_summary()` | average `completion_percent` from Work Progress Report utility; fallback to `Project.percent_complete` |
| Billing Progress | `get_project_financial_summary()` | `total_invoiced / contract_value * 100`, clamped 0-100 |
| Collection Progress | `get_project_financial_summary()` | `received_against_invoices / total_invoice_receivable * 100`, clamped 0-100 |
| Invoice Outstanding | `get_project_financial_summary()` | sum signed `Sales Invoice.outstanding_amount` |
| Reports count | `get_dashboard_counts_for_projects()` | count submitted, published, non-cancelled DPRs |
| Documents count | `get_empty_project_counts()` | currently always 0 |
| Pending approvals | `get_empty_project_counts()` | currently always 0 |
| Recent Activity | `get_dashboard_recent_activity()` | RA Bills, Sales Invoices, Payments, published DPRs sorted descending |

Charts:

- No chart library was found in the new portal files.
- Progress circles and bars are CSS-driven visualizations using inline custom property `--progress`.

## 8. Project Portal Logic

Project list source:

- `get_customer_projects(customers)`
- `get_dashboard_projects(customers)`

Customer field detection:

- `get_project_customer_field()` returns `Project.customer` if present, else `Project.client`, else `None`.

Project filters:

```python
filters = {customer_field: ["in", customers]}
```

Fields used:

- `name`
- `project_name`
- `status`
- detected customer field
- `percent_complete`
- `expected_start_date`
- `expected_end_date`
- `modified`
- optional `project_type`, `sales_order`, `company`
- optional location field among `project_location`, `location`, `site_location`
- optional stage field among `current_stage`, `project_stage`, `stage`, `construction_stage`

Project display fields:

- `display_name = project.project_name or project.name`
- `display_status = project.status or "Not specified"`
- `display_location = detected location field or "Not specified"`
- `display_manager = first Project User full_name/user or "Not specified"`
- `display_percent_complete = get_project_progress_summary(...).physical_progress`
- `detail_route = /client-portal/project/<name>`

Security:

- Project detail uses `get_authorized_customer_project(project_name, customers)`.
- If the URL project is not owned by one of the resolved Customers, it raises `frappe.PermissionError`.

## 9. BOQ Portal Logic

New `/client-portal`:

- No direct BOQ list/detail page exists in `QATRA_CLIENT_PORTAL_ITEMS`.
- BOQ affects financial/progress data indirectly through RA Bills and Work Progress helpers.

Legacy `/boq`:

- Controller: `www/boq.py`
- Customer field: `get_boq_customer_field()` returns `BOQ.client` if present else `BOQ.customer`.
- Filters: resolved single customer, `is_active_revision = 1`, `docstatus != 2`, optional project/status/revision.
- Detail route validates ownership with `validate_boq_customer(name, customer)` before `frappe.get_doc("BOQ", name)`.
- Detail also requires `is_active_revision` and not cancelled.

BOQ dependencies:

- BOQ
- BOQ Item
- BOQ Cost Component
- BOQ Revision
- BOQ Category
- Sales Order
- Project
- Customer

## 10. BOQ Calculations

Source:

- `doctype/boq/boq.py`, method `BOQ._calculate_totals()`
- `doctype/boq_item/boq_item.py`, method `BOQItem.calculate()`
- Client-side duplicate: `fixtures/client_script.json` and `client_script/boq_client_script.js`

Formulas:

| Value | Formula | Source |
|---|---|---|
| BOQ Item Unit Rate | `unit_cost * (1 + margin_percent / 100)` | `BOQ._calculate_totals()`, `BOQItem.calculate()` |
| BOQ Item Amount | `qty * unit_cost` | same |
| BOQ Item Amount After Margin | `qty * unit_rate` | same |
| Deleted Revision Item Qty | `0` if `is_deleted_in_revision` | `BOQ._calculate_totals()` |
| BOQ Total Cost | sum item `amount` | `BOQ._calculate_totals()` |
| BOQ Grand Total | sum item `amount_after_margin` | `BOQ._calculate_totals()` |
| BOQ Total Margin | `grand_total - total_cost` | `BOQ._calculate_totals()` |
| BOQ Margin % | `(grand_total - total_cost) / grand_total * 100` if `grand_total` else 0 | `BOQ._calculate_totals()` |
| Rate Per BUA | `grand_total / built_up_area` if built-up area else 0 | `BOQ._calculate_totals()` |
| Cost Breakdown Validation | sum matching `BOQ Cost Component.amount` must equal item `amount` within 0.01 | `validate_cost_breakdown_matches_amount()` |

Revision comparison:

- Previous BOQ is `parent_boq`.
- Previous items are matched by `previous_boq_item`.
- `qty_difference = current_qty - previous.qty`
- `rate_difference = current unit_rate - previous.unit_rate`
- `amount_difference = current amount_after_margin - previous amount_after_margin`
- Revision item status becomes `Added`, `Deleted`, `Modified`, or `Unchanged`.

## 11. Work Progress Logic

New `/client-portal` progress source:

- `get_project_work_progress_summary()` imports `average_field` and `get_work_progress_rows` from `construction_management.construction_management.report.report_utils`.
- It returns average `completion_percent` from those rows.
- If there are no rows or an exception occurs, it falls back to `Project.percent_complete`.

Legacy `/work-progress`:

- Controller: `www/work_progress.py`
- Preferred source: `RA Bill Transaction` if table exists and has `original_boq` and `boq_item_key`.
- Fallback source: submitted `RA Bill Item` rows.

Legacy formulas:

| Value | Formula | Source |
|---|---|---|
| Completed Qty | sum `RA Bill Transaction.current_qty`, or fallback calculated from submitted RA Bill Items | `get_work_progress_from_transactions()`, `get_work_progress_from_ra_bill_items()` |
| Completed Amount | sum `RA Bill Transaction.current_amount`, or fallback current amount | same |
| Remaining Qty | `max(0, boq_qty - completed_qty)` | `add_progress_values()` |
| Progress % | `completed_qty / boq_qty * 100` if `boq_qty` else 0 | `add_progress_values()` |

Filters:

- Customer via BOQ customer field.
- Active BOQ revisions only.
- Excludes cancelled BOQs and deleted revision items.
- Completion filters: complete, in-progress, not-started.

## 12. RA Bill Portal Logic

New `/client-portal`:

- RA Bills are surfaced in dashboard and project financial summaries.
- Payments page shows invoices, payments, advances, and statement rows, not a direct RA Bill detail page.

Legacy `/ra-bill`:

- Controller: `www/ra_bill.py`
- Filters by `RA Bill.customer = resolved_customer`, optional project/status/search.
- Detail validates with `validate_ra_bill_customer(name, customer)` before `frappe.get_doc("RA Bill", name)`.

Desk lifecycle:

- Controller: `doctype/ra_bill/ra_bill.py`
- Client script: `doctype/ra_bill/ra_bill.js`
- Status flow: Draft -> Submitted -> Approved -> Invoiced -> Cancelled.
- Submit creates `RA Bill Transaction` rows.
- Approval is a whitelisted document method `approve()`.
- Approved bills can create draft Sales Invoices through whitelisted document method `create_sales_invoice()`.

## 13. RA Bill Calculations

Sources:

- `RABill.validate()`
- `_fetch_boq_item_details()`
- `_fill_previous_work_summary()`
- `_calculate_row_totals()`
- `_validate_not_overbilling()`
- `_calculate_header_totals()`
- `calculate_taxes_and_grand_total()`
- `calculate_ra_bill_taxes()`

Formula table:

| Value | Formula | File | Function |
|---|---|---|---|
| BOQ Qty | copied from linked `BOQ Item.qty` | `ra_bill.py` | `_fetch_boq_item_details()` |
| BOQ Rate | copied from linked `BOQ Item.unit_rate` | `ra_bill.py` | `_fetch_boq_item_details()` |
| Current Qty | `boq_qty * (work_percent / 100)` | `ra_bill.py` | `_calculate_row_totals()` |
| Current Amount | `current_qty * boq_rate` | `ra_bill.py` | `_calculate_row_totals()` |
| Cumulative Qty | `prev_cumulative_qty + current_qty` | `ra_bill.py` | `_calculate_row_totals()` |
| Previous Qty | submitted previous qty from transactions/fallback items | `ra_bill.py` | `_get_previous_billed_qty()` |
| Previous % | `previous_qty / boq_qty * 100` | `ra_bill.py` | `_get_boq_item_billing_summary()` |
| Remaining Qty | `max(0, boq_qty - previous_qty)` | `ra_bill.py` | `_get_boq_item_billing_summary()` |
| Remaining % | `max(0, 100 - previous_percent)` | `ra_bill.py` | `_get_boq_item_billing_summary()` |
| Gross Amount | sum item `current_amount` | `ra_bill.py` | `_calculate_header_totals()` |
| Retention Amount | `gross_amount * retention_percent / 100` | `ra_bill.py` | `_calculate_header_totals()` |
| Net Payable | `gross_amount - retention_amount` | `ra_bill.py` | `_calculate_header_totals()` |
| Cumulative Billed | previous submitted gross for project + BOQ chain + current gross | `ra_bill.py` | `_calculate_header_totals()` |
| Net Total | `gross_amount` | `ra_bill.py` | `calculate_ra_bill_taxes()` |
| Tax Amount - Actual | entered `tax_amount` | `ra_bill.py` | `get_ra_bill_tax_amount()` |
| Tax Amount - On Net Total | `net_total * rate / 100` | `ra_bill.py` | `get_ra_bill_tax_amount()` |
| Tax Amount - Previous Row Amount | previous tax row `tax_amount * rate / 100` | `ra_bill.py` | `get_ra_bill_tax_amount()` |
| Tax Amount - Previous Row Total | previous tax row `total * rate / 100` | `ra_bill.py` | `get_ra_bill_tax_amount()` |
| Grand Total | running total after taxes | `ra_bill.py` | `calculate_ra_bill_taxes()` |
| Total Advance | actual advance recovered from `update_ra_bill_advance_fields()` or sum allocated advances | `ra_bill.py` | `calculate_taxes_and_grand_total()` |
| Outstanding Amount | `grand_total - total_advance` | `ra_bill.py` | `calculate_taxes_and_grand_total()` |

Client-side duplicate calculations:

- `ra_bill.js` computes row totals, previous/remaining caps, and tax totals for immediate UI feedback.
- Server-side validation/calculation in `ra_bill.py` is authoritative.

## 14. Previous / Current / Cumulative Billing

Previous RA Bill sequence is not based on bill number alone. It is based on submitted progress against the same BOQ lineage and BOQ item key.

Implemented chain:

```text
RA Bill row
-> BOQ Item
-> BOQ original_boq + boq_item_key
-> RA Bill Transaction submitted rows
-> fallback submitted RA Bill Item rows
```

Important functions:

- `_get_original_boq()`
- `_get_boq_chain_names()`
- `_get_boq_item_context()`
- `_get_previous_billed_qty()`
- `_get_previous_billed_qty_from_transactions()`
- `_get_previous_billed_qty_from_submitted_ra_bills()`
- `_get_boq_item_billing_summary()`

Submitted-only behavior:

- Transaction query joins `RA Bill` and requires `rb.docstatus = 1`.
- Fallback item query joins `RA Bill` and requires `rb.docstatus = 1`.
- Current RA Bill is excluded with `t.ra_bill != current_ra_bill` or `rb.name != current_ra_bill`.

Overbilling:

- Progress rows require `work_percent > 0` and `work_percent <= 100`.
- Current qty cannot be negative for normal progress rows.
- Current qty cannot exceed remaining qty plus tolerance `0.0001`.
- Adjustment rows can be negative or positive but cannot reduce cumulative progress below zero or raise it above BOQ qty.

Cancelled behavior:

- On RA Bill cancel, `_delete_ra_bill_transactions()` removes transaction rows.
- Portal financial summaries filter `docstatus = 1` and `status != "Cancelled"`.

## 15. Sales Invoice Integration

Source:

- `RABill.create_sales_invoice()` in `doctype/ra_bill/ra_bill.py`
- `construction_management/advance_management.py`
- `construction_management/overrides/sales_invoice.py`
- Hooks in `construction_management/hooks.py` for `Sales Invoice` validate/on_submit/on_cancel/on_update_after_submit

Creation rule:

- RA Bill must have `status == "Approved"`.
- RA Bill must not already have `sales_invoice`.
- Customer must exist.
- Gross amount must be greater than zero.
- A draft Sales Invoice is inserted with `ignore_permissions=True`.
- RA Bill is updated with `sales_invoice` and status `Invoiced`.

Mapping:

| RA Bill | Sales Invoice |
|---|---|
| `customer` | `customer` |
| default/user/global company | `company` |
| construction receivable account | `debit_to` |
| `project` | `project` |
| project cost center | `cost_center` |
| `currency` | `currency` |
| `posting_date` / derived posting date | `posting_date` |
| derived due date | `due_date` |
| `name` | `ra_bill` custom field |
| `boq` | `boq` custom field |
| source sales order | `sales_order` and item sales_order where supported |
| addresses/contacts | corresponding Sales Invoice fields when valid Dynamic Link exists |
| taxes template | `taxes_and_charges` |
| payment schedule | Sales Invoice `payment_schedule` where table exists |
| timesheets | Sales Invoice `timesheets` where table exists |

Invoice item behavior:

- Normal positive-progress rows create one Sales Invoice Item per positive RA Bill Item.
- If adjustment rows exist, a single summary item is created for the RA Bill gross amount.
- The code checks that RA Bill item totals match `gross_amount`.
- Retention remains tracked through RA Bill/Retention Record/deduction tax handling, not by reducing the certified Sales Invoice item total.

Duplicate prevention:

- `create_sales_invoice()` throws if `self.sales_invoice` is already set.

## 16. Payments & Outstanding

New portal payment page:

- Controller: `www/client_portal_payments.py`
- Data source: `get_project_financial_summary()`

Financial data sources:

- Sales Orders: submitted Sales Orders for authorized projects/customers.
- RA Bills: submitted, non-cancelled RA Bills.
- Sales Invoices: submitted Sales Invoices by project/customer, plus invoices linked through RA Bill and Sales Order relationships.
- Invoice payments: `Payment Entry Reference` rows referencing Sales Invoices, with parent Payment Entry `party` in customers, `payment_type = Receive`, `docstatus = 1`.
- Advance payments: `Payment Entry Reference` rows referencing Sales Orders with the same Payment Entry filters.

Portal formulas:

| Value | Formula |
|---|---|
| Contract Value | sum Sales Order `net_total`, or `base_net_total` if mixed currencies |
| Certified Work Value | sum RA Bill `gross_amount` |
| Total Invoiced | sum signed Sales Invoice `net_total` |
| Invoice Receivable | signed `rounded_total` if set else signed `grand_total` |
| Invoice Outstanding | sum signed `outstanding_amount` |
| Received Against Invoices | sum invoice Payment Entry Reference `allocated_amount` |
| Advance Received | sum Sales Order Payment Entry Reference `allocated_amount` |
| Total Received | received against invoices + advance received |
| Remaining Contract Value | `max(contract_value - total_invoiced, 0)` |
| Payment Progress | payments page uses `total_received / contract_value * 100` if contract value exists |

Statement:

- Invoices are debits.
- Advance receipts and invoice payments are credits.
- `get_payment_statement_rows()` computes a running balance in ascending source order, then returns rows sorted descending by posting date for display.

## 17. APIs and Backend Methods

| Method | File | Whitelisted | Inputs | Output | Used By | Security Filter |
|---|---|---:|---|---|---|---|
| `reset_client_portal_password` | `www/client_portal.py` | Yes, guest POST rate-limited | `user` | generic reset message | Login page | Checks `get_client_portal_access(user).allowed` before reset |
| `get_item_default_cost_components` | `construction_management/api.py` | Yes | `item` | item default cost components | BOQ desk | Item exists check |
| `save_item_default_cost_components` | `construction_management/api.py` | Yes | `item`, `components` | saved rows | BOQ desk | Item exists check |
| `boq_item_search` | `construction_management/api.py` | Yes search | link search args | BOQ Item search rows | Desk link search | SQL parameterized; desk permission context not portal-specific |
| `create_revision` | `doctype/boq/boq.py` | Yes | `boq`, `revision_reason` | new BOQ name | BOQ desk | role gate `require_revision_manager()` |
| `activate_revision` | `doctype/boq/boq.py` | Yes | `boq` | active BOQ name | BOQ desk | role gate |
| `get_revision_history` | `doctype/boq/boq.py` | Yes | `boq` | revision rows | BOQ desk | No explicit permission check found |
| `get_revision_comparison` | `doctype/boq/boq.py` | Yes | `boq` | comparison rows | BOQ desk | No explicit permission check found |
| `RABill.get_invoice_date_defaults` | `doctype/ra_bill/ra_bill.py` | Yes doc method | document | posting/due date | RA Bill desk | Document permission via form context |
| `RABill.approve` | `doctype/ra_bill/ra_bill.py` | Yes doc method | document | RA Bill name | RA Bill desk | Document method, status checks |
| `RABill.get_advances_received` | `doctype/ra_bill/ra_bill.py` | Yes doc method | document | advance rows/totals | RA Bill desk | Document method, customer/company checks |
| `RABill.create_sales_invoice` | `doctype/ra_bill/ra_bill.py` | Yes doc method | document | Sales Invoice name | RA Bill desk | Status and duplicate checks |
| `get_ra_bill_template_tax_rows` | `doctype/ra_bill/ra_bill.py` | Yes | template/company/boq | tax rows | RA Bill desk | Template/company validation |
| `get_boq_item_details_for_ra_bill` | `doctype/ra_bill/ra_bill.py` | Yes | `boq`, `boq_item` | BOQ item detail | RA Bill desk | `_get_permission_checked_boq()` |
| `get_boq_context_for_ra_bill` | `doctype/ra_bill/ra_bill.py` | Yes | `boq` | items/categories | RA Bill desk | `_get_permission_checked_boq()` |
| `get_customer_address_and_contact` | `doctype/ra_bill/ra_bill.py` | Yes | `customer` | address/contact fields | RA Bill desk | No explicit permission check found |
| `get_active_boq_for_project` | `doctype/ra_bill/ra_bill.py` | Yes | `project` | BOQ name | RA Bill desk | No explicit permission check found |
| `get_boq_item_billing_summary` | `doctype/ra_bill/ra_bill.py` | Yes | `boq`, `boq_item`, `current_ra_bill` | progress summary | RA Bill desk | `_get_permission_checked_boq()` |
| `get_boq_item_previous_work` | `doctype/ra_bill/ra_bill.py` | Yes | same | progress summary | RA Bill JS | `_get_permission_checked_boq()` |
| `search_ra_bill_categories` | `doctype/ra_bill/ra_bill.py` | Yes search | link search args | categories | RA Bill JS | `_get_permission_checked_boq()` |
| `search_ra_bill_subcategories` | `doctype/ra_bill/ra_bill.py` | Yes search | link search args | subcategories | RA Bill JS | `_get_permission_checked_boq()` |
| `search_boq_items_for_ra_bill` | `doctype/ra_bill/ra_bill.py` | Yes search | link search args | BOQ items | RA Bill JS | `_get_permission_checked_boq()` |
| `search_boq_adjustment_items_for_ra_bill` | `doctype/ra_bill/ra_bill.py` | Yes search | link search args | BOQ items with progress | RA Bill JS | `_get_permission_checked_boq()` |

## 18. Frontend JavaScript

`public/js/qatra_client_portal_login.js`:

- Handles login form submit.
- Calls `/api/method/login` with `cmd=login`, `usr`, `pwd`.
- Redirects to `/client-portal` after login; server then redirects to dashboard.
- Handles password reset form.
- Calls `/api/method/construction_management.www.client_portal.reset_client_portal_password`.
- Performs client-side required-field validation and error/success message display.

`public/js/qatra_client_portal.js`:

- Mobile sidebar open/close.
- Sidebar collapse state persisted in `localStorage` key `qatraClientPortalSidebarCollapsed`.
- Sign out buttons redirect to `/client-portal/logout`.
- Report table search, pagination, page-size changes, CSV download.
- Project card search/status filtering.
- Escape key closes mobile navigation.

`public/js/portal.js`:

- Legacy Construction Portal shell behavior and styling tweaks for routes like `/construction-portal`.

`doctype/ra_bill/ra_bill.js`:

- Desk-only RA Bill behavior, not public portal JS.
- Fetches BOQ item details and previous work.
- Calculates row totals and tax totals in the browser.
- Adds Approve and Create Sales Invoice actions.
- Enforces duplicate-item and overbilling checks client-side, with server-side validation repeated in Python.

## 19. Templates / Jinja

Primary layout:

- `templates/client_portal/base.html`: suppresses navbar/footer, includes CSS/JS, renders mobile header, topbar, sidebar, and main block.
- `templates/client_portal/sidebar.html`: logo, nav links, active class, user/customer display.
- `templates/client_portal/page_shell.html`: generic hero for placeholder pages.

Page templates:

- `client-portal-dashboard.html`: command hero, project switcher, portfolio metrics, summary cards, journey, snapshot, financial cards, activity.
- `client-portal-projects.html`: project summary hero, search/status toolbar, project cards, empty states.
- `client-portal-project.html`: project-specific financial and activity view, links to reports/documents/payments.
- `client-portal-reports.html`: report filters and report cards.
- `client-portal-report.html`: virtual/DPR report detail, sections, tables, attachments/photos.
- `client-portal-payments.html`: payment status, invoice/payment cards, statement.
- `client-portal-documents.html`, `client-portal-gallery.html`, `client-portal-approvals.html`: include `page_shell.html` only.
- `client-portal-logout.html`: sign-out page.

## 20. CSS / Responsive UI

Primary CSS:

- `public/css/qatra_client_portal.css`

Responsibilities:

- Login page layout and branding.
- Portal shell with sidebar, mobile header, topbar, backdrop, and content.
- Dashboard hero, cards, metrics, progress indicators, tables, report cards, payment cards.
- Responsive breakpoints for mobile and collapsed sidebar.

Legacy CSS:

- `public/css/portal.css` applies to older website portal pages through `web_include_css`.

Duplicate/conflicting styles:

- New and legacy portal CSS are separate files.
- No direct duplicate selector conflict was identified for the new portal because selectors are scoped under `.qatra-client-portal`.

## 21. Permissions & Security

Safe patterns:

- New client portal requires `Website User`.
- New portal project access uses Customer list and `get_authorized_customer_project()`.
- Report detail validates virtual report project ownership or DPR customer/docstatus/publish/status.
- Sales Invoice and Payment Entry data in portal utilities is filtered by authorized project and Customers.
- Legacy BOQ and RA Bill detail pages validate customer ownership before `get_doc()`.
- Legacy Work Progress filters by BOQ customer field and only active BOQ revisions.
- SQL found in portal utilities and RA Bill helpers uses parameter dictionaries/tuples for user values.

Needs Review:

- `get_authorized_client_report()` validates File attachments only by `attached_to_doctype/name` after DPR authorization. It returns private file URLs; actual file download permission depends on Frappe file serving rules.
- Several desk whitelisted BOQ methods (`get_revision_history`, `get_revision_comparison`) call `frappe.get_doc()`/`frappe.get_all()` without explicit `check_permission()` in the function.
- Desk whitelisted `get_customer_address_and_contact(customer)` accepts arbitrary Customer and does not explicitly check read permission.
- Desk whitelisted `get_active_boq_for_project(project)` accepts arbitrary Project and does not explicitly check project/customer ownership.
- Legacy `require_portal_customer()` supports only one Customer; new portal supports multiple. A multi-customer user using legacy routes sees only the first resolved Customer.

Potential Data Exposure:

- Desk whitelisted helper methods that accept Customer/Project/BOQ names should be reviewed for role/permission behavior in Frappe RPC context, especially if Website Users can call desk whitelisted methods.

Definite Data Exposure:

- None confirmed from repository inspection for the `/client-portal` routes.

## 22. DocType Dependency Map

```text
User
`-- Contact.user / Contact.email_id / Contact Email.email_id
    `-- Dynamic Link(parenttype=Contact, link_doctype=Customer)
        `-- Customer
            |-- Project.customer or Project.client
            |   |-- Project User(parent=Project)
            |   |-- Task(project)
            |   |-- Sales Order(project, customer)
            |   |   `-- Payment Entry Reference(reference_doctype=Sales Order)
            |   |       `-- Payment Entry(party=Customer)
            |   |-- BOQ.project + BOQ.client
            |   |   |-- BOQ Item(parent=BOQ)
            |   |   |   `-- BOQ Category
            |   |   |-- BOQ Cost Component(parent=BOQ)
            |   |   `-- BOQ Revision(parent=BOQ)
            |   |-- RA Bill.project + RA Bill.customer + RA Bill.boq
            |   |   |-- RA Bill Item(parent=RA Bill, boq_item=BOQ Item)
            |   |   |-- RA Bill Taxes and Charges(parent=RA Bill)
            |   |   |-- RA Bill Advance(parent=RA Bill)
            |   |   |-- RA Bill Payment Schedule(parent=RA Bill)
            |   |   |-- RA Bill Timesheet(parent=RA Bill)
            |   |   |-- RA Bill Transaction(ra_bill=RA Bill)
            |   |   `-- Sales Invoice(ra_bill=RA Bill)
            |   |       `-- Payment Entry Reference(reference_doctype=Sales Invoice)
            |   |           `-- Payment Entry(party=Customer)
            |   `-- Daily Progress Report(project, customer)
            |       |-- DPR Task Completed(parent=Daily Progress Report)
            |       |-- DPR Photo(parent=Daily Progress Report)
            |       `-- File(attached_to_doctype/name)
            `-- Portal User(parent=Customer)
```

## 23. Portal Data Flow

Login flow:

```text
Browser /client-portal
-> login form posts /api/method/login
-> Frappe session user
-> /client-portal get_context()
-> get_client_portal_access()
-> Contact / Dynamic Link / Portal User / default customer
-> /client-portal/dashboard
```

Project flow:

```text
Customer(s)
-> Project.customer/client filter
-> Project list/detail
-> financial summary
```

Billing flow:

```text
BOQ
-> RA Bill Item work_percent
-> RA Bill current/previous/cumulative calculations
-> RA Bill Transaction on submit
-> RA Bill approval
-> Sales Invoice draft
-> Payment Entry / Payment Entry Reference
-> Client Portal dashboard/payments
```

Report flow:

```text
Customer(s)
-> Authorized Projects
-> Daily Progress Report publish_to_portal=1
-> virtual report cards/details
-> tasks/photos/attachments
```

## 24. Complete User Flows

FLOW A - Customer Login:

1. User opens `/client-portal`.
2. If Guest, login page is rendered.
3. JS posts credentials to `/api/method/login`.
4. Frappe creates session.
5. `/client-portal` checks access.
6. If allowed, redirects to `/client-portal/dashboard`.

FLOW B - View Projects:

1. User opens `/client-portal/projects`.
2. `setup_client_portal_context()` resolves Customers.
3. `get_customer_projects()` filters Project by detected customer field.
4. Template renders cards.
5. Browser JS filters cards by search/status.

FLOW C - View BOQ:

Implemented in legacy portal only.

1. User opens `/boq`.
2. `require_portal_customer()` resolves a single Customer.
3. BOQs are filtered by `client/customer`, active revision, and not cancelled.
4. Detail route validates `validate_boq_customer()`.
5. Template displays BOQ and sorted items.

FLOW D - Work Progress:

Implemented in legacy portal and indirectly in new dashboard.

1. User opens `/work-progress`.
2. Customer is resolved.
3. If `RA Bill Transaction` exists, progress is summed from transactions.
4. Otherwise, progress is summed from submitted RA Bill Items.
5. Remaining qty and progress percent are calculated.

FLOW E - RA Bills:

Implemented in legacy portal and indirectly in new financial summaries.

1. RA Bill is created in Desk from project/BOQ.
2. BOQ fields populate customer, project, rate, and quantity.
3. Work percent calculates current qty and amount.
4. Previous submitted progress restricts overbilling.
5. Submit creates RA Bill Transaction rows.
6. Legacy portal lists/detail displays customer RA Bills.

FLOW F - Invoice:

1. Submitted RA Bill is approved.
2. User clicks Create Sales Invoice.
3. Draft Sales Invoice is generated and linked to RA Bill.
4. RA Bill status becomes Invoiced.
5. Client portal dashboard/payments can show submitted Sales Invoices after accounts submits them.

FLOW G - Payment:

1. Payment Entry is submitted against Sales Invoice or Sales Order.
2. Portal utilities read Payment Entry Reference rows.
3. Payment Entry parent must be Receive, submitted, and party in authorized Customers.
4. Payments page builds cards and statement.

## 25. File-by-File Inspection

| File | Purpose | Security / Notes |
|---|---|---|
| `construction_management/hooks.py` | Portal menu, route rules, web assets, session hook, permissions, doc events | Defines `/client-portal` route map and legacy `/construction-portal` menu |
| `construction_management/portal_utils.py` | Core portal auth, customer resolution, dashboard/report/payment helpers | Main authorization layer for new portal |
| `construction_management/www/client_portal.py` | Login page and password reset | Guest reset method uses generic response |
| `construction_management/www/client_portal_dashboard.py` | Dashboard context | Uses customer-filtered dashboard data |
| `construction_management/www/client_portal_projects.py` | Projects page context | Uses `get_customer_projects()` |
| `construction_management/www/client_portal_project.py` | Project detail context | Uses `get_authorized_customer_project()` |
| `construction_management/www/client_portal_reports.py` | Reports library context | Filters virtual reports by authorized projects |
| `construction_management/www/client_portal_report.py` | Report detail context | Uses `get_authorized_client_report()` |
| `construction_management/www/client_portal_payments.py` | Payments page context and statement formatting | Uses selected authorized project |
| `construction_management/www/client_portal_documents.py` | Placeholder page | Auth only |
| `construction_management/www/client_portal_gallery.py` | Placeholder page | Auth only |
| `construction_management/www/client_portal_approvals.py` | Approval list context | Customer/Project filtered Client Approval Request records |
| `construction_management/www/client_portal_logout.py` | Logout page context | Template performs sign-out behavior |
| `construction_management/www/client-portal*.html` | Primary portal templates | Server-rendered data |
| `construction_management/templates/client_portal/base.html` | Portal shell | Includes CSS and JS |
| `construction_management/templates/client_portal/sidebar.html` | Sidebar navigation | Active state from `active_page` |
| `construction_management/templates/client_portal/page_shell.html` | Placeholder hero | Used by documents/gallery/approvals |
| `construction_management/public/js/qatra_client_portal.js` | Portal shell, project filters, report table tooling | No backend calls |
| `construction_management/public/js/qatra_client_portal_login.js` | Login/reset AJAX | Calls login and reset endpoints |
| `construction_management/public/css/qatra_client_portal.css` | New portal styling | Scoped under `.qatra-client-portal` |
| `construction_management/www/boq.py` | Legacy BOQ list | Customer-filtered, active BOQ revisions |
| `construction_management/www/boq_detail.py` | Legacy BOQ detail | Validates BOQ customer before `get_doc()` |
| `construction_management/www/ra_bill.py` | Legacy RA Bill list | Filters by RA Bill customer |
| `construction_management/www/ra_bill_detail.py` | Legacy RA Bill detail | Validates RA Bill customer |
| `construction_management/www/work_progress.py` | Legacy work progress | Customer-filtered SQL |
| `construction_management/www/work_progress_detail.py` | Legacy work progress detail | Validates BOQ customer |
| `construction_management/www/dprs.py` | Legacy DPR list | Customer/published DPR filtering |
| `construction_management/www/dpr_detail.py` | Legacy DPR detail | Validates published customer DPR |
| `construction_management/www/construction_portal.py` | Legacy dashboard | Uses work progress and recent BOQ/RA Bill helpers |
| `construction_management/www/construction_projects.py` | Legacy project list | Customer project filtering |
| `construction_management/www/construction_project_detail.py` | Legacy project detail | Project customer validation |
| `construction_management/public/js/portal.js` | Legacy portal JS | Route-specific body/classes/sidebar behavior |
| `construction_management/public/css/portal.css` | Legacy portal CSS | Applies through `web_include_css` |
| `construction_management/construction_management/doctype/boq/boq.py` | BOQ controller | Formulas, revision lifecycle, whitelisted revision methods |
| `construction_management/construction_management/doctype/boq_item/boq_item.py` | BOQ Item child calculation | Mirrors BOQ item formulas |
| `construction_management/construction_management/doctype/ra_bill/ra_bill.py` | RA Bill controller | Core progress, tax, invoice integration |
| `construction_management/construction_management/doctype/ra_bill/ra_bill.js` | RA Bill desk client script | Client-side duplicate calculations and RPC calls |
| `construction_management/construction_management/advance_management.py` | Advance receipt/recovery helpers | Used by RA Bill and Sales Invoice integration |
| `construction_management/construction_management/overrides/sales_invoice.py` | Sales Invoice override for RA Bill retention/advance/payment breakdown | Hooked in `hooks.py` |
| `construction_management/construction_management/doctype/daily_progress_report/daily_progress_report.py` | DPR customer sync and portal permission conditions | Adds permission query and `has_permission` |

## 26. Calculation Reference

| Module | Value | Exact Formula | Source Field(s) | File | Function |
|---|---|---|---|---|---|
| BOQ | Unit Rate | `unit_cost * (1 + margin_percent / 100)` | `unit_cost`, `margin_percent` | `boq.py` | `_calculate_totals()` |
| BOQ | Amount | `qty * unit_cost` | `qty`, `unit_cost` | `boq.py` | `_calculate_totals()` |
| BOQ | Amount After Margin | `qty * unit_rate` | `qty`, `unit_rate` | `boq.py` | `_calculate_totals()` |
| BOQ | Total Cost | sum `amount` | BOQ Item | `boq.py` | `_calculate_totals()` |
| BOQ | Grand Total | sum `amount_after_margin` | BOQ Item | `boq.py` | `_calculate_totals()` |
| BOQ | Total Margin | `grand_total - total_cost` | totals | `boq.py` | `_calculate_totals()` |
| BOQ | Margin % | `(grand_total - total_cost) / grand_total * 100` | totals | `boq.py` | `_calculate_totals()` |
| BOQ | Rate per BUA | `grand_total / built_up_area` | `built_up_area` | `boq.py` | `_calculate_totals()` |
| RA Bill | Current Qty | `boq_qty * work_percent / 100` | RA Bill Item | `ra_bill.py` | `_calculate_row_totals()` |
| RA Bill | Current Amount | `current_qty * boq_rate` | RA Bill Item | `ra_bill.py` | `_calculate_row_totals()` |
| RA Bill | Cumulative Qty | `prev_cumulative_qty + current_qty` | RA Bill Item | `ra_bill.py` | `_calculate_row_totals()` |
| RA Bill | Previous % | `previous_qty / boq_qty * 100` | previous qty, BOQ qty | `ra_bill.py` | `_qty_to_percent()` |
| RA Bill | Remaining Qty | `max(0, boq_qty - previous_qty)` | previous qty, BOQ qty | `ra_bill.py` | `_get_boq_item_billing_summary()` |
| RA Bill | Remaining % | `max(0, 100 - previous_percent)` | previous percent | `ra_bill.py` | `_get_boq_item_billing_summary()` |
| RA Bill | Gross Amount | sum item `current_amount` | RA Bill Items | `ra_bill.py` | `_calculate_header_totals()` |
| RA Bill | Retention Amount | `gross_amount * retention_percent / 100` | header fields | `ra_bill.py` | `_calculate_header_totals()` |
| RA Bill | Net Payable | `gross_amount - retention_amount` | header fields | `ra_bill.py` | `_calculate_header_totals()` |
| RA Bill | Cumulative Billed | previous submitted gross + current gross | project, BOQ chain | `ra_bill.py` | `_calculate_header_totals()` |
| RA Bill | Net Total | `gross_amount` | header | `ra_bill.py` | `calculate_ra_bill_taxes()` |
| RA Bill | Tax On Net Total | `net_total * rate / 100` | tax row | `ra_bill.py` | `get_ra_bill_tax_amount()` |
| RA Bill | Grand Total | `net_total + sum(tax_amount)` running total | taxes | `ra_bill.py` | `calculate_ra_bill_taxes()` |
| RA Bill | Outstanding | `grand_total - total_advance` | totals | `ra_bill.py` | `calculate_taxes_and_grand_total()` |
| Portal Financials | Billing Progress | `total_invoiced / contract_value * 100`, clamped | Sales Invoice, Sales Order | `portal_utils.py` | `get_project_financial_summary()` |
| Portal Financials | Collection Progress | `received_against_invoices / total_invoice_receivable * 100`, clamped | Payment Entry Reference, Sales Invoice | `portal_utils.py` | `get_project_financial_summary()` |
| Portal Financials | Remaining Contract Value | `max(contract_value - total_invoiced, 0)` | Sales Order, Sales Invoice | `portal_utils.py` | `get_project_financial_summary()` |
| Work Progress | Progress % | `completed_qty / boq_qty * 100` | BOQ Item, RA Bill Transaction | `work_progress.py` | `add_progress_values()` |

## 27. Security Findings

CRITICAL:

- None confirmed.

HIGH:

- No confirmed high-risk `/client-portal` data exposure found.

MEDIUM:

- Desk whitelisted methods `get_revision_history()` and `get_revision_comparison()` do not explicitly call `check_permission()`.
- Desk whitelisted `get_customer_address_and_contact(customer)` accepts Customer input without explicit read/ownership validation.
- Desk whitelisted `get_active_boq_for_project(project)` accepts Project input without explicit read/ownership validation.

LOW:

- Legacy portal resolves one Customer, while new portal resolves multiple. This can be confusing for multi-customer contacts.
- Documents, Gallery, and Approvals are present in navigation but are placeholders with no data source yet.

INFORMATIONAL:

- New portal uses `ignore_permissions=True` in many server-side queries after its own Customer/project validation. This is acceptable if validation remains centralized and complete.
- Private file URLs are surfaced for authorized DPR attachments; serving behavior depends on Frappe file permission checks.

## 28. Performance Findings

- `get_client_dashboard_data()` loads projects, financials, counts, selected-project detail, activities, and report counts server-side; large customer portfolios may require pagination or caching.
- `get_project_sales_invoices()` calls `get_project_ra_bills()` more than once, creating repeated queries.
- `get_dashboard_financials_for_projects()` fetches all project rows and then groups in Python; acceptable for modest data volumes but may become heavy.
- Report detail `get_client_dpr_update_details()` calls `frappe.get_doc()` once per DPR row, which can become N+1 for long periods.
- Work Progress fallback SQL aggregates submitted RA Bill Items and can be heavy without indexes on RA Bill customer/docstatus and child item keys.

## 29. Dead / Duplicate / Legacy Code

- Legacy portal code is active through routes but separate from `/client-portal`.
- `/client-portal/documents`, `/client-portal/gallery`, and `/client-portal/approvals` are active placeholder pages.
- BOQ calculations are duplicated in Python and client script. Python is authoritative.
- RA Bill row/tax calculations are duplicated in Python and client script. Python is authoritative.
- `portal_menu_items` exposes only `/construction-portal`, not `/client-portal`.
- No new portal chart library was found.

## 30. Current Limitations

- The new `/client-portal` does not expose direct BOQ, RA Bill, or Work Progress pages.
- Approvals now query `Client Approval Request`; Documents/Gallery query `Project Portal File` and approved DPR sources.
- Customer resolution has multiple fallbacks; ambiguous contacts with multiple Customers are allowed but the display `context.customer` is only the first Customer.
- Project stage journey assumes fixed labels `Design`, `Procurement`, `Construction`, `Finishing`, `Handover` when the project stage matches one of them.
- Financial summaries use the first detected currency for display unless mixed currency logic switches contract totals to base amounts; mixed display remains a simplification.

## 31. Developer Maintenance Guide

- Add new client portal pages by adding `website_route_rules`, a `www/client_portal_x.py` controller, a `www/client-portal-x.html` template, and a `QATRA_CLIENT_PORTAL_ITEMS` entry if it belongs in navigation.
- Always call `setup_client_portal_context()` for new `/client-portal` pages.
- Validate URL project/report/document names on the server; do not rely on hidden fields or frontend filters.
- Prefer Customer-list filtering (`customers=context.customers`) for new portal pages.
- If direct BOQ/RA Bill pages are added to `/client-portal`, reuse `validate_boq_customer()`/`validate_ra_bill_customer()` or multi-customer equivalents.
- Keep BOQ and RA Bill formulas server-authoritative; client-side calculations should only improve UX.
- When adding payment/invoice data, filter both document name and Customer/party.
- Review every new whitelisted method for explicit permission checks.

## 32. Final Architecture Summary

The Qatra Client Portal is a Frappe website portal with centralized Customer resolution and mostly server-rendered pages. It presents project portfolio, project financials, reports, and payments for Customers linked to the logged-in Website User. BOQ and RA Bill logic is mature in the Desk DocTypes and older Construction Portal routes; the new client portal currently consumes billing and progress outputs rather than exposing direct BOQ/RA Bill detail pages. The core security model is Customer/project filtering in `portal_utils.py`, with legacy pages adding explicit document ownership validation before loading detail documents.

## Client Approval Request Workflow

`Client Approval Request` is the portal-facing approval lifecycle for `/client-portal/approvals` and `/client-portal/approval/<name>`.

Main backend helpers in `construction_management/portal_utils.py`:

```text
get_client_portal_approvals()
get_authorized_client_approval()
get_project_approval_counts()
is_client_approval_visible()
respond_to_client_approval()
download_client_approval_attachment()
```

Visibility requires `publish_to_client_portal = 1`, authorized Customer/Project, valid visibility window, and a non-Draft/non-Cancelled status. `Pending` requests are actionable; `Approved` and `Rejected` remain visible as history. Source documents are validated for project/customer relationship where possible but are not auto-mutated.

