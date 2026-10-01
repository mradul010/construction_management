# Qatra Client Portal - Client Concerns & Technical Responses

## Purpose

This document records Client Portal concerns raised by the client, technical investigation, confirmed behavior, root cause, proposed correction, implementation status, and verification results.

---

# Concern 1 - Cancelled Invoice Included in Portal Calculations

## Client Concern

> A cancelled invoice is currently still being included in the Client Portal calculations/totals. Ahmed confirmed that cancelled invoices should be completely excluded from the calculations.

## Investigation Status

NOT REPRODUCED FROM SOURCE

## Expected Behaviour

Only submitted Sales Invoices should contribute to active Client Portal financial calculations.

Expected eligibility rule:

```text
Sales Invoice.docstatus == 1
```

Excluded invoices:

- Draft invoices: `docstatus == 0`
- Cancelled invoices: `docstatus == 2`

Cancelled invoices should contribute zero to Client Portal totals, progress percentages, invoice cards, latest invoice, recent activity, and payment statements unless a future business requirement explicitly asks for cancelled historical visibility.

## Current Behaviour

The current source code for the primary `/client-portal` consistently filters Sales Invoices with `docstatus = 1` before using them in calculations and UI lists.

The investigation did not find a current `/client-portal` code path where a cancelled Sales Invoice can enter active portal financial calculations.

Important distinction:

- The primary Client Portal source is safe in the inspected code.
- An adjacent internal report utility, `construction_management/construction_management/report/report_utils.py`, contains a query with `si.docstatus != 2`, which excludes cancelled invoices but can include draft invoices. That path was not found feeding the primary `/client-portal` dashboard, project detail, payments page, or virtual monthly client report.

## Source Code Investigation

### File

`construction_management/portal_utils.py`

### Function

`get_dashboard_financials_for_projects(project_names, customers)`

### Current Query / Filter

The dashboard bulk financial path queries Sales Invoices directly:

```python
invoices = frappe.get_all(
    "Sales Invoice",
    filters={
        "project": ["in", project_names],
        "customer": ["in", customers],
        "docstatus": 1,
    },
    ...
)
```

Source lines inspected:

- `construction_management/portal_utils.py:629-638`

### Current Calculation

`build_dashboard_financials()` receives only the filtered `invoices` list and calculates:

```python
total_invoiced = sum(get_signed_amount(row, "net_total") for row in invoices)
total_invoice_receivable = sum(get_invoice_receivable_amount(row) for row in invoices)
invoice_outstanding = sum(get_signed_amount(row, "outstanding_amount") for row in invoices)
received_against_invoices = sum(row.allocated_amount for invoice payment refs)
remaining_contract_value = max(contract_value - total_invoiced, 0)
billing_progress = total_invoiced / contract_value * 100
collection_progress = received_against_invoices / total_invoice_receivable * 100
```

Source lines inspected:

- `construction_management/portal_utils.py:728-768`

### File

`construction_management/portal_utils.py`

### Function

`get_project_sales_invoices(project_name, customers)`

### Current Query / Filter

This is the main project-level invoice source used by project detail, payments page, recent activity, and virtual monthly reports.

Direct project/customer invoice names are collected with:

```python
filters={
    "project": project_name,
    "customer": ["in", customers],
    "docstatus": 1,
}
```

RA Bill and Sales Order indirect invoice names are also collected, but the final Sales Invoice fetch rechecks:

```python
filters={
    "name": ["in", list(names)],
    "customer": ["in", customers],
    "docstatus": 1,
}
```

Source lines inspected:

- Direct Sales Invoice source: `construction_management/portal_utils.py:2294-2306`
- RA Bill linked invoice names: `construction_management/portal_utils.py:2307-2313`
- Sales Order header invoice source: `construction_management/portal_utils.py:2317-2329`
- Sales Invoice Item sales order source: `construction_management/portal_utils.py:2331-2339`
- RA Bill custom field invoice source: `construction_management/portal_utils.py:2341-2353`
- Final Sales Invoice recheck: `construction_management/portal_utils.py:2380-2390`

### Current Calculation

`get_project_financial_summary()` consumes `get_project_sales_invoices()` and calculates:

```python
total_invoiced = sum(get_signed_amount(row, "net_total") for row in invoices)
total_invoice_receivable = sum(get_invoice_receivable_amount(row) for row in invoices)
invoice_outstanding = sum(get_signed_amount(row, "outstanding_amount") for row in invoices)
received_against_invoices = sum(row.allocated_amount for invoice_payments)
remaining_contract_value = max(contract.contract_value - total_invoiced, 0)
billing_progress = total_invoiced / contract.contract_value * 100
collection_progress = received_against_invoices / total_invoice_receivable * 100
```

Source lines inspected:

- `construction_management/portal_utils.py:2107-2175`

## Calculation Impact

| Portal Value | Affected? | Why |
|---|---:|---|
| Total Invoiced | No | Uses `invoices` from `docstatus = 1` Sales Invoice queries. |
| Invoice Receivable | No | Computed only from the submitted invoice list. |
| Invoice Outstanding | No | Computed only from the submitted invoice list. |
| Total Received | No for invoice payments tied to invoices; advance receipts are Sales Order based | Invoice payments are collected only for `invoice_names` from submitted invoices. Sales Order advance receipts are separate and do not depend on cancelled Sales Invoice inclusion. |
| Billing Progress | No | Derived from submitted-only `total_invoiced`. |
| Collection Progress | No | Derived from submitted-only invoice receivable and submitted Payment Entries allocated to submitted invoices. |
| Remaining Contract Value | No | Derived from submitted-only `total_invoiced`. |
| Financial Snapshot | No | Dashboard/project/payment templates display values from submitted-only financial summaries. |
| Latest Invoice | No | Payments page sorts `financial_summary.invoices`, which comes from `get_project_sales_invoices()`. |
| Recent Activity | No | Invoice activity uses `financial_summary.invoices` or `get_project_sales_invoices()`. |
| Payment Statement | No | Statement invoice debit rows come from submitted-only invoices; invoice payment credit rows come from references to those submitted invoice names. |

## Indirect Invoice Collection

The project-level helper intentionally gathers Sales Invoice names through multiple relationships:

```text
Project + Customer
-> Sales Invoice

RA Bill
-> RA Bill.sales_invoice
-> Sales Invoice

Sales Order
-> Sales Invoice.sales_order
-> Sales Invoice

Sales Order
-> Sales Invoice Item.sales_order
-> Sales Invoice parent

RA Bill
-> Sales Invoice.ra_bill custom field
-> Sales Invoice
```

The important safety control is the final Sales Invoice query:

```python
"docstatus": 1
```

This final recheck prevents a cancelled invoice name collected through RA Bill or Sales Order relationships from entering the returned invoice list.

## Payment Entry Consideration

Invoice payment calculations use `get_project_invoice_payments()`.

Current path:

```text
get_project_financial_summary()
-> invoices = get_project_sales_invoices()
-> get_project_invoice_payments(project, customers, invoices=invoices)
-> invoice_names = [invoice.name for invoice in invoices]
-> Payment Entry Reference where reference_doctype = Sales Invoice and reference_name in invoice_names
-> Payment Entry where party in customers, payment_type = Receive, docstatus = 1
```

Because `invoice_names` comes from submitted-only Sales Invoices, a Payment Entry Reference against a cancelled Sales Invoice is excluded from invoice-payment totals in the inspected `/client-portal` code.

Sales Order advance receipts are separate:

```text
Payment Entry Reference.reference_doctype = Sales Order
```

Those are included as `Advance Receipt` when the Sales Order is submitted and belongs to the customer/project. They are not evidence that a cancelled Sales Invoice is included.

## Dashboard Recent Activity

Recent Activity uses:

- RA Bills from submitted, non-cancelled RA Bills.
- Sales Invoices from `financial_summary.invoices` or `get_project_sales_invoices()`.
- Payments from `financial_summary.advance_payments + financial_summary.invoice_payments` or helper calls that use the same submitted invoice list.
- Published DPRs with `docstatus = 1`, `publish_to_portal = 1`, and status not Cancelled.

Source lines inspected:

- `construction_management/portal_utils.py:1850-1936`

Conclusion:

- Cancelled invoices are not included in Recent Activity from the current `/client-portal` source.
- Cancelled invoice visibility as historical UI records is not implemented in the inspected client portal path.

## Root Cause

No root cause was reproduced in the current `/client-portal` source because the active code already applies `Sales Invoice.docstatus = 1` at the invoice source level.

If the client saw a cancelled invoice included on a running site, likely possibilities outside this source-only finding are:

1. The running site is not on this inspected code version.
2. The observed total came from a different report/page outside the primary `/client-portal`.
3. Browser/server cache or stale generated data was observed.
4. A custom report or desk report using `docstatus != 2` was mistaken for the Client Portal.
5. The invoice was not actually cancelled in ERPNext (`docstatus` still 1) even if its textual `status` looked unexpected.

Adjacent code note:

`construction_management/construction_management/report/report_utils.py:get_invoice_rows_for_ra_bills()` uses:

```sql
AND si.`docstatus` != 2
```

This excludes cancelled invoices but can include draft invoices. It was not found in the primary `/client-portal` financial path. If this internal report is exposed later in the Client Portal, it should be reviewed.

## Correct Fix Location

No production code change is recommended from this source-only investigation because the primary Client Portal already applies the desired submitted-only filter.

If a mismatch is found in the deployed site, the safest centralized correction points are:

Primary file:

`construction_management/portal_utils.py`

Primary functions:

- `get_project_sales_invoices(project_name, customers)`
- `get_dashboard_financials_for_projects(project_names, customers)`

Reason:

These are the shared data-source functions that feed dashboard totals, project detail financials, payment page invoices, latest invoice, payment statement, recent activity, and virtual monthly client reports.

## Recommended Change

No current code change for `/client-portal` is recommended from this inspection.

Desired principle, already present in the inspected portal source:

```python
filters={
    ...
    "docstatus": 1,
}
```

If deployed code differs, align it to:

```text
Sales Invoices matching project/customer/RA Bill/Sales Order relationships
AND Sales Invoice.docstatus = 1
```

Avoid relying on:

```text
status != "Cancelled"
docstatus != 2
missing docstatus filter
```

for active Client Portal calculations.

## Secondary Defensive Checks

Recommended if/when implementation work is authorized:

1. Keep `docstatus = 1` in every Sales Invoice source query in `get_project_sales_invoices()`.
2. Keep the final Sales Invoice fetch in `get_project_sales_invoices()` with `docstatus = 1` because it protects indirect RA Bill and Sales Order name collection.
3. Keep `get_dashboard_financials_for_projects()` bulk dashboard query with `docstatus = 1`.
4. Consider adding explicit comments/tests around `get_project_invoice_payments()` to make it clear that invoice payment references are intentionally limited by the already-filtered invoice list.
5. Review `report_utils.py:get_invoice_rows_for_ra_bills()` separately if that internal report is ever exposed through `/client-portal`.

## Regression Test Plan

| Case | Scenario | Expected Result |
|---|---|---|
| 1 | Submitted invoice | Included in Total Invoiced, Invoice Receivable, Outstanding, latest invoice, invoice cards, statement, recent activity. |
| 2 | Draft invoice | Excluded from all Client Portal financial calculations and invoice UI lists. |
| 3 | Cancelled invoice | Excluded from all Client Portal financial calculations and invoice UI lists. |
| 4 | Submitted invoice with payment | Invoice included; submitted Receive Payment Entry allocation included in received-against-invoices and statement credit. |
| 5 | Invoice submitted, payment made, invoice later cancelled | Cancelled invoice excluded; payment allocation against that cancelled invoice excluded from invoice-payment totals. Confirm whether related Sales Order advance treatment is still correct separately. |
| 6 | RA Bill linked to cancelled Sales Invoice | Cancelled invoice excluded by final `Sales Invoice.docstatus = 1` recheck. |
| 7 | Sales Order linked to cancelled Sales Invoice | Cancelled invoice excluded by final `Sales Invoice.docstatus = 1` recheck. |
| 8 | Mixed invoices: submitted, cancelled, draft | Only submitted invoice contributes to Total Invoiced, Invoice Receivable, Outstanding, Billing Progress, Collection Progress, Remaining Contract Value, Payments page, Dashboard, and Project Detail. |

Views to verify:

- `/client-portal/dashboard`
- `/client-portal/project/<project>`
- `/client-portal/payments?project=<project>`
- `/client-portal/reports` monthly project performance card
- `/client-portal/report/monthly-project-performance-report?project=<project>`

## Runtime Verification

### Environment

Site:
`Qatra.local`

Branch:
`test-pankaj`

Commit:
`866c382 Fix the ra bill floting point precision problem`

Working Tree:
Modified

Observed uncommitted state:

```text
 M .gitignore
 M construction_management/desktop_icon/construction.json
?? docs/
```

No pull, checkout, reset, stash, commit, migration, cache clear, restart, or data mutation was performed.

### Running Code Version Check

The checked running bench source under `apps/construction_management/` still contains submitted-only Sales Invoice filters.

Confirmed source references:

- Dashboard bulk invoice query: `construction_management/portal_utils.py:629-638`
- Dashboard payment references: `construction_management/portal_utils.py:661-725`
- Dashboard financial calculations: `construction_management/portal_utils.py:728-768`
- Project financial summary: `construction_management/portal_utils.py:2107-2175`
- Project invoice direct and indirect selection: `construction_management/portal_utils.py:2289-2406`
- Project invoice payments: `construction_management/portal_utils.py:2409-2437`
- Payment row parent Payment Entry filter: `construction_management/portal_utils.py:2466-2510`
- Project statement construction: `construction_management/portal_utils.py:2513-2551`
- Recent activity helper: `construction_management/portal_utils.py:1850-1936`
- Payments page context: `construction_management/www/client_portal_payments.py:18-37`
- Payment statement rows: `construction_management/www/client_portal_payments.py:86-111`
- Dashboard page context: `construction_management/www/client_portal_dashboard.py:9-14`
- Project detail page context: `construction_management/www/client_portal_project.py:18-36`

Confirmed filter pattern:

```python
"docstatus": 1
```

### Site-Wide Invoice Counts

Runtime Sales Invoice counts on `Qatra.local`:

| Docstatus | Meaning | Count |
|---:|---|---:|
| 0 | Draft | 0 |
| 1 | Submitted | 13 |
| 2 | Cancelled | 1 |

Status breakdown:

| Docstatus | Status | Count |
|---:|---|---:|
| 1 | Paid | 12 |
| 1 | Overdue | 1 |
| 2 | Cancelled | 1 |

### Projects With Cancelled Invoices

| Project | Customer | Submitted Count | Cancelled Count | Submitted Net Total | Cancelled Net Total |
|---|---|---:|---:|---:|---:|
| `PROJ-0015` | `BUILDING EVOLUTION CONTRACTING L.L.C` | 3 | 1 | 1,106,180.16 | 201,000.00 |

### Runtime Test Project

Project:
`PROJ-0015`

Project Name:
`Emerald Hills Villa 95`

Customer:
`BUILDING EVOLUTION CONTRACTING L.L.C`

Sales Order:
`SAL26/0006`

Portal ownership evidence:

- `tabProject.customer = BUILDING EVOLUTION CONTRACTING L.L.C`
- Customer Portal User rows include `Administrator` and `mradulmishra010@gmail.com`
- Customer Contact `Mradul Customer` is linked to `mradulmishra010@gmail.com`

### Invoice Dataset

| Invoice | Docstatus | Status | Net Total | Receivable Amount | Outstanding | RA Bill | Sales Order | Portal Eligible? |
|---|---:|---|---:|---:|---:|---|---|---|
| `ACC-SINV-2026-00034` | 1 | Paid | 253,440.10 | 199,584.03 | 0.00 | `RA-YYYY-0020-2` | `SAL26/0006` | Yes |
| `ACC-SINV-2026-00036` | 1 | Paid | 765,652.06 | 602,951.00 | 0.00 | `RA-YYYY-0022` | `SAL26/0006` | Yes |
| `ACC-SINV-2026-00037` | 1 | Overdue | 87,088.00 | 91,442.40 | 0.40 | `RA-YYYY-0023` | `SAL26/0006` | Yes |
| `ACC-SINV-2026-00033` | 2 | Cancelled | 201,000.00 | 158,287.50 | 40,200.00 | `RA-YYYY-0020-1` | `SAL26/0006` | No |

### Manual Expected Calculation

Submitted-only expected values using the same signed invoice logic as `portal_utils.py`:

| Value | Manual Submitted-Only |
|---|---:|
| Invoice Count | 3 |
| Total Invoiced | 1,106,180.16 |
| Invoice Receivable | 893,977.43 |
| Invoice Outstanding | 0.40 |

Submitted plus cancelled comparison, for investigation only:

| Value | Submitted + Cancelled |
|---|---:|
| Invoice Count | 4 |
| Total Invoiced | 1,307,180.16 |
| Invoice Receivable | 1,052,264.93 |
| Invoice Outstanding | 40,200.40 |

Difference if the cancelled invoice were incorrectly included:

| Value | Difference |
|---|---:|
| Total Invoiced | 201,000.00 |
| Invoice Receivable | 158,287.50 |
| Invoice Outstanding | 40,200.00 |

### Portal Helper Result

Runtime helper called:

```python
from construction_management.portal_utils import get_project_financial_summary

get_project_financial_summary(
    "PROJ-0015",
    ["BUILDING EVOLUTION CONTRACTING L.L.C"],
)
```

Comparison:

| Value | Manual Submitted-Only | Portal Helper | Match? |
|---|---:|---:|---|
| Total Invoiced | 1,106,180.16 | 1,106,180.16 | Yes |
| Invoice Receivable | 893,977.43 | 893,977.43 | Yes |
| Invoice Outstanding | 0.40 | 0.40 | Yes |

Other helper values observed:

| Value | Portal Helper |
|---|---:|
| Contract Value | 2,653,214.00 |
| Certified Work Value | 1,106,180.35 |
| Received Against Invoices | 893,977.03 |
| Advance Received | 530,642.80 |
| Total Received | 1,424,619.83 |
| Remaining Contract Value | 1,547,033.84 |
| Billing Progress | 41.6921% |
| Collection Progress | 99.99996% |

### Difference

No runtime difference was found between the submitted-only manual calculation and the portal helper calculation.

If the cancelled invoice were included, `total_invoiced` would be `1,307,180.16`. The runtime portal helper returned `1,106,180.16`.

### Cancelled Invoice Returned by `get_project_sales_invoices()`

No.

Expected submitted invoices:

```text
ACC-SINV-2026-00034
ACC-SINV-2026-00036
ACC-SINV-2026-00037
```

Returned by helper:

```text
ACC-SINV-2026-00034
ACC-SINV-2026-00036
ACC-SINV-2026-00037
```

Cancelled invoice:

```text
ACC-SINV-2026-00033
```

Cancelled invoice returned by helper:
No

Draft invoice returned by helper:
No draft invoices existed in the selected project or site-wide dataset.

### Dashboard Bulk Result

Runtime helper called:

```python
get_dashboard_financials_for_projects(
    ["PROJ-0015"],
    ["BUILDING EVOLUTION CONTRACTING L.L.C"],
)
```

Dashboard bulk values for `PROJ-0015`:

| Value | Dashboard Bulk Result |
|---|---:|
| Total Invoiced | 1,106,180.16 |
| Invoice Receivable | 893,977.43 |
| Invoice Outstanding | 0.40 |
| Received Against Invoices | 893,977.03 |
| Advance Received | 530,642.80 |
| Total Received | 1,424,619.83 |
| Billing Progress | 41.6921% |
| Collection Progress | 99.99996% |

Conclusion:
The cancelled invoice did not enter the dashboard bulk path.

### Payment Reference Result

No `Payment Entry Reference` rows were found for cancelled invoice `ACC-SINV-2026-00033`.

| Cancelled Invoice | Payment Entry | Reference Amount | Portal Includes Payment? |
|---|---|---:|---|
| `ACC-SINV-2026-00033` | None found | 0.00 | No |

Invoice payments returned by the portal helper were only against submitted invoices:

| Payment Entry | Submitted Invoice | Allocated Amount |
|---|---|---:|
| `ACC-PAY-2026-00027` | `ACC-SINV-2026-00034` | 199,584.00 |
| `ACC-PAY-2026-00030` | `ACC-SINV-2026-00034` | 0.03 |
| `ACC-PAY-2026-00031` | `ACC-SINV-2026-00036` | 602,951.00 |
| `ACC-PAY-2026-00031` | `ACC-SINV-2026-00037` | 91,442.00 |

Advance receipt returned separately:

| Payment Entry | Sales Order | Allocated Amount |
|---|---|---:|
| `ACC-PAY-2026-00026` | `SAL26/0006` | 530,642.80 |

### Payment Statement Result

Cancelled invoice shown as invoice debit:
No

Cancelled invoice shown as payment credit:
No

Cancelled invoice shown as latest invoice:
No

Cancelled invoice shown in statement rows:
No

Statement rows included only submitted invoice references `QTI0003`, `QTI0012`, `QTI0012 (2)`, their invoice payments, and the Sales Order advance receipt `SAL26/0006`.

### Recent Activity Result

Cancelled invoice shown:
No

Recent activity included submitted invoice activity for:

```text
QTI0003
QTI0012
QTI0012 (2)
```

It did not include cancelled invoice `ACC-SINV-2026-00033`.

### Actual Page Context

The current page controllers consume the same helper functions tested above:

- `/client-portal/dashboard` calls `get_client_dashboard_data()` from `www/client_portal_dashboard.py`.
- `/client-portal/project/<name>` calls `get_project_financial_summary()` and `get_dashboard_recent_activity()` from `www/client_portal_project.py`.
- `/client-portal/payments` calls `get_project_financial_summary()` and then builds the payment view from that summary in `www/client_portal_payments.py`.

No separate invoice query was found in these page controllers.

### Cache / Stale Data Check

No application-level cached financial summary was found in the primary `/client-portal` calculation path.

Observed:

- Client portal page controllers are marked `no_cache = 1`.
- Financial values are computed through `portal_utils.py` helper calls.
- Search did not find `frappe.cache`, `redis_cache`, or a stored cached `financial_summary` used for these portal totals.

Conclusion:
No application-level cached financial summary found.

### Other Page / Report Possibility

An adjacent desk report path exists outside the primary `/client-portal`:

- `construction_management/construction_management/report/project_construction_report/project_construction_report.py`
- `construction_management/construction_management/report/ra_bill_sales_invoice_report/ra_bill_sales_invoice_report.py`
- Shared helper: `construction_management/construction_management/report/report_utils.py:get_invoice_rows_for_ra_bills()`

The shared helper uses:

```sql
AND rb.`docstatus` != 2
AND si.`docstatus` != 2
```

This excludes cancelled invoices but can include draft invoices. This path was not found feeding the primary `/client-portal` dashboard, project detail, payments page, payment statement, or recent activity. It may be relevant only if the client was looking at a desk report or a non-primary report page and describing it as portal totals.

Another desk page, `construction_management/construction_management/page/construction_project_progress_report/construction_project_progress_report.py`, also uses `si.docstatus != 2` for invoice totals. This is a desk page path, not the primary `/client-portal`.

### Runtime Conclusion

NOT REPRODUCED AT RUNTIME

Verified:

- `Qatra.local` has one cancelled Sales Invoice: `ACC-SINV-2026-00033`.
- That cancelled invoice belongs to `PROJ-0015` and customer `BUILDING EVOLUTION CONTRACTING L.L.C`.
- The same project has three submitted invoices, making it a valid comparison project.
- Manual submitted-only totals match the runtime portal helper totals.
- `get_project_sales_invoices()` did not return the cancelled invoice.
- `get_dashboard_financials_for_projects()` did not include the cancelled invoice.
- Payment helper results did not include any payment against the cancelled invoice.
- Payment statement rows did not include the cancelled invoice.
- Recent activity did not include the cancelled invoice.

Possible, not verified as fact:

- The originally observed value may have come from another desk report/page rather than the primary `/client-portal`.
- The originally observed environment may have been on a different deployed code version.
- The originally observed browser/page may have been stale.
- The invoice observed by the client may not have been cancelled at the time of observation.
- The client may have been comparing a value based on invoice receivable/grand total with a value based on net total.

### Root Cause

No runtime root cause was reproduced in the primary Client Portal path.

The verified runtime behavior matches the intended source behavior: only submitted Sales Invoices with `docstatus = 1` are included in active portal financial calculations.

### Recommended Correction

No production code correction is recommended for the primary `/client-portal` based on this runtime verification.

If a separate issue is reported with screenshots or a specific URL, inspect that exact page/report next. If the issue is in a desk report using `si.docstatus != 2`, the safer conceptual correction would be to use submitted-only invoice filtering:

```sql
AND si.`docstatus` = 1
```

That report-path change was not implemented in this task.

## Implementation Status

Not Implemented

No code change was made in this task.

## Verification Status

Runtime Verified

This investigation verified both source logic and runtime data on `Qatra.local`. It did not run migrations, modify data, restart services, clear caches, or create test invoices.

## Client Response

We verified both the source logic and actual Qatra runtime data. The portal currently includes only submitted Sales Invoices in its financial calculations, and the tested cancelled invoice was excluded from invoice totals, outstanding, billing progress, payments, statement calculations, and recent activity. We are now checking whether the originally observed value came from another report/page, an older deployed version, or a stale view.

---

# Concern 2 - Documents & Gallery Upload Process

## Client Concern

> Could you please explain the correct process for uploading documents and images from ERPNext so that they appear in the Documents and Gallery sections of the Client Portal?
>
> I tested uploading a public file and attaching it to the project, but it did not appear in the Documents section.

## Investigation Status

CONFIRMED

The client's original test result was expected because public Project attachments are not automatically published to the Client Portal. The current implementation now uses a dedicated `Project Portal File` DocType plus published DPR sources so approved files can appear on `/client-portal/documents` and `/client-portal/gallery`.

## Expected Behaviour

A completed Documents/Gallery feature should allow approved customer-visible files to be uploaded or linked in ERPNext and then shown only to authorized Client Portal users for the matching Customer and Project.

Expected security chain:

```text
Website User
-> linked Customer
-> authorized Project
-> explicitly portal-published File or document record
```

Project attachments should not automatically become customer-visible unless the business intentionally approves that rule.

### UX Simplification Update

The Documents/Gallery workflow now uses the dedicated `Project Portal File` DocType for approved client-visible uploads. On the Desk form, the user selects the Project first; Customer is required and read-only, but it is automatically derived from the selected Project before mandatory validation runs. This removes the generic "Customer is required" save failure while still enforcing the Project-to-Customer security chain.

The manual publishing form now shows the business fields first: Project, Customer, Category, File, Portal Title, Caption, Description, Publish to Client Portal, Sort Order, and optional visibility dates. Internal source fields (`Source DocType`, `Source Type`, and `Source Document`) are kept hidden/read-only because the portal aggregation helpers also use source metadata for DPR-origin files and future source tracking.

Runtime verification was performed with `PROJ-0015`; the form derived Customer `BUILDING EVOLUTION CONTRACTING L.L.C`, saved a published document/gallery file without manual Customer entry, and the portal helpers returned the files for the matching project before the temporary verification records were removed.

## Current Implementation

### Documents

Status:
IMPLEMENTED

Route:
`/client-portal/documents`

Current behavior:
The page renders published `Project Portal File` document rows for the authorized Customer and Project. It also supports published DPR document attachments when that aggregation source is enabled.

Runtime context keys checked for portal user `mradulmishra010@gmail.com`:

```text
active_page
body_class
customer
customer_name
customer_names
customers
full_name
full_width
hide_login
no_breadcrumbs
no_header
page_kicker
page_subtitle
page_title
qatra_client_portal_asset_version
qatra_company_name
qatra_fallback_logo
qatra_logo
qatra_portal_nav_items
show_sidebar
title
```

Not present:

```text
documents
files
images
gallery_items
attachments
```

### Gallery

Status:
IMPLEMENTED

Route:
`/client-portal/gallery`

Current behavior:
The page displays only the generic portal page shell with title/subtitle metadata. It does not render images, thumbnails, DPR photos, Project image attachments, or a gallery grid.

Runtime context keys checked for portal user `mradulmishra010@gmail.com` are the same generic page/navigation keys listed above. No image/gallery data key is present.

## Source Code Investigation

### Documents Route

File:
`construction_management/hooks.py:44`

Route mapping:

```python
{"from_route": "/client-portal/documents", "to_route": "client-portal-documents"}
```

Controller:
`construction_management/www/client_portal_documents.py:1-8`

Controller behavior:

```python
from construction_management.portal_utils import setup_client_portal_context

no_cache = 1

def get_context(context):
    setup_client_portal_context(context, "documents")
```

Template:
`construction_management/www/client-portal-documents.html:1-5`

Template behavior:

```jinja
{% extends "construction_management/templates/client_portal/base.html" %}

{% block portal_content %}
{% include "construction_management/templates/client_portal/page_shell.html" %}
{% endblock %}
```

Backend helper:
None found. No `get_project_documents()`, `get_client_portal_documents()`, `get_files()`, or Project `File` query exists for this route.

Data source:
None.

Project filtering:
None.

Customer filtering:
Only the base portal user/customer context is established. No file/document query uses it.

File filtering:
None.

Public/private filtering:
None.

Supported file types:
None implemented.

Pagination:
None implemented.

Empty state:
Only the generic hero/page shell. No document-specific empty state.

Does `/client-portal/documents` currently query `File`?
No.

Does it query Project attachments?
No.

Does it query attachments from related transactions?
No.

Does it contain a placeholder/empty-state message?
It contains a generic page shell, not a document-specific list or empty state.

### Gallery Route

File:
`construction_management/hooks.py:45`

Route mapping:

```python
{"from_route": "/client-portal/gallery", "to_route": "client-portal-gallery"}
```

Controller:
`construction_management/www/client_portal_gallery.py:1-8`

Controller behavior:

```python
from construction_management.portal_utils import setup_client_portal_context

no_cache = 1

def get_context(context):
    setup_client_portal_context(context, "gallery")
```

Template:
`construction_management/www/client-portal-gallery.html:1-5`

Template behavior:

```jinja
{% extends "construction_management/templates/client_portal/base.html" %}

{% block portal_content %}
{% include "construction_management/templates/client_portal/page_shell.html" %}
{% endblock %}
```

Backend helper:
None found. No `get_project_gallery()`, `get_client_portal_gallery()`, image `File` query, or DPR photo query exists for this route.

Data source:
None.

Project filtering:
None.

Customer filtering:
Only the base portal user/customer context is established. No image/gallery query uses it.

File filtering:
None.

Public/private filtering:
None.

Supported file types:
None implemented.

Pagination:
None implemented.

Empty state:
Only the generic hero/page shell. No gallery-specific empty state.

Does Gallery query `File`?
No.

Does it query images?
No.

Does it use DPR photos?
No.

Does it use Project attachments?
No.

Does it use another custom DocType?
No.

Does it require image file extensions?
No implemented logic exists.

Does it require public files?
No implemented logic exists.

## Runtime File Investigation

Site:
`Qatra.local`

Branch:
`test-pankaj`

Commit:
`866c382 Fix the ra bill floting point precision problem`

Working tree:
Modified

Observed uncommitted state:

```text
 M .gitignore
 M construction_management/desktop_icon/construction.json
?? docs/
```

Runtime `File` records attached directly to `Project`:

| Count Type | Count |
|---|---:|
| Total Project attachments | 0 |
| Public Project attachments | 0 |
| Private Project attachments | 0 |
| Image Project attachments | 0 |
| Non-image Project attachments | 0 |

Attached `File` records by DocType at runtime:

| Attached DocType | File Count | Public | Private |
|---|---:|---:|---:|
| Data Import | 5 | 3 | 2 |
| Insights Dashboard v3 | 2 | 0 | 2 |
| Company | 1 | 1 | 0 |

Runtime image files exist, but they are not Project attachments used by the Client Portal Documents/Gallery pages. Examples include public/unattached files such as `/files/Cinderella Castle at Dusk.png` and `/files/Qatra Logo.png`.

Project:
No runtime `File` record attached to `Project` was found on `Qatra.local` during verification.

File:
No Project-attached File available to select.

Public/Private:
Not applicable for Project attachments because none exist at runtime.

Attached To:
Not applicable.

Portal Result:
No Project File appears in Documents or Gallery because the pages do not query `File` at all.

Would the current `/client-portal/documents` controller ever retrieve a Project-attached File if one existed?
No.

Exact reason:
The controller only calls `setup_client_portal_context(context, "documents")`. It never queries `File`, never calls a document helper, and never sets `context.documents`, `context.files`, or `context.attachments`.

## Public File vs Portal Published File

A public Frappe File means the file URL is stored under a public path such as `/files/...` and may be directly accessible by URL depending on Frappe permissions and deployment configuration.

A public File does not mean the file is published to the Qatra Client Portal.

Current source findings:

- No `File.is_private` check exists in the Documents page implementation.
- No `File.is_private` check exists in the Gallery page implementation.
- No `publish_to_portal`, `show_in_portal`, or `custom_publish_to_client_portal` field exists on `File` in runtime `Custom Field` records.
- No portal publication rule for Project attachments exists in the current Documents/Gallery pages.

Does making a File public automatically make it visible in Client Portal?
No.

Why:
The Documents/Gallery pages do not query File records at all. Public/private status only affects file URL accessibility; it is not currently wired to portal visibility.

## Attachment Relationship Check

| Attached DocType | Used by Documents? | Used by Gallery? | Portal Rule |
|---|---|---|---|
| Project | No | No | No implemented File query or publication rule. |
| Daily Progress Report | No for Documents page; Yes only inside Report Detail attachments | No for Gallery page; DPR photos render only inside report detail | DPR must be submitted, `publish_to_portal = 1`, non-cancelled, and customer/project authorized. Attachments are shown on `/client-portal/report/<dpr>`, not `/client-portal/documents`. |
| DPR Photo child table | No | No for Gallery page; Yes only inside Report Detail photo section | Photos are read from the `photos` child table when viewing a published DPR report detail. |
| BOQ | No | No | No implemented document/gallery file rule. |
| RA Bill | No | No | No implemented document/gallery file rule. |
| Sales Invoice | No | No | No implemented document/gallery file rule. |
| Sales Order | No | No | No implemented document/gallery file rule. |
| Drawing / Design DocTypes | No | No | Design-related attachment doctypes exist, but no Documents/Gallery portal integration was found. |

## DPR / Site Photo Integration

DPR implementation exists separately from Gallery.

Relevant source:

- `construction_management/construction_management/doctype/daily_progress_report/daily_progress_report.json:84-88` defines `publish_to_portal` as `Show on Client Portal`.
- `construction_management/construction_management/doctype/daily_progress_report/daily_progress_report.json:123-133` defines the `photos` child table.
- `construction_management/construction_management/doctype/dpr_photo/dpr_photo.json:15-19` defines `photo` as an `Attach Image` field.
- `construction_management/portal_utils.py:1190-1251` authorizes and builds published DPR report detail data.
- `construction_management/portal_utils.py:1306-1314` reads DPR photo child rows.
- `construction_management/portal_utils.py:1748-1758` reads `File` attachments for a Daily Progress Report detail page.
- `construction_management/www/client-portal-report.html:349-367` renders DPR photos on report detail pages.
- `construction_management/www/client-portal-report.html:371-391` renders DPR attachments on report detail pages.

Runtime data:
No `Daily Progress Report`, `DPR Photo`, or Daily Progress Report `File` attachment rows were returned in the sampled runtime checks.

Conclusion:
Gallery does not currently consume DPR photos. DPR photos, when present on a published DPR, are displayed only inside report detail pages, not in `/client-portal/gallery`.

## Project Ownership Security

Existing helpers that should be reused if Documents/Gallery are implemented:

- `setup_client_portal_context(context, active_page)` establishes portal user/customer context.
- `get_customers_for_portal_user(user)` resolves Customers linked to a Website User.
- `get_customer_projects(customers)` lists projects for authorized customers.
- `get_authorized_customer_project(project_name, customers)` verifies that a requested project belongs to the portal user's Customer.
- `validate_project_in_customers(project_name, customers)` validates project/customer ownership.

Required security rule for future implementation:

```text
Portal user
-> resolved Customers
-> authorized Projects only
-> explicitly published/allowed files only
```

A user must not be able to access another customer's Project files by changing a `?project=PROJ-XXXX` URL parameter.

## Why Client Test Did / Did Not Work

The client test did not work because the Documents page is not implemented as a File browser.

Verified technical reason:

- `/client-portal/documents` maps to `client_portal_documents.py`.
- `client_portal_documents.py` only calls `setup_client_portal_context(context, "documents")`.
- The template only includes `page_shell.html`.
- No query exists for `File` where `attached_to_doctype = "Project"`.
- No `context.documents`, `context.files`, or `context.attachments` is created.
- Therefore attaching a public file to a Project cannot make it appear in the Documents page.

The same applies to Gallery: no image/File/DPR photo data source is loaded.

## Current Correct Upload Process

No functional upload-to-portal process currently exists for the Documents or Gallery sections.

There is currently no ERPNext upload process that can make a normal Project attachment appear in `/client-portal/documents` or `/client-portal/gallery`, because those pages do not yet load `File` records.

Current related functionality that does exist:

- Published Daily Progress Reports can appear in the Reports section when `publish_to_portal = 1`, submitted, non-cancelled, and customer/project authorized.
- DPR photos and DPR attachments can render inside `/client-portal/report/<report>` for a published DPR.
- This is not the same as the standalone Documents or Gallery sections.

## Recommended Portal Behaviour

Documents and Gallery should be implemented as explicit, secure, project-aware portal features.

Recommended behavior:

- Show a project selector or support all authorized projects.
- Verify each selected project through `get_authorized_customer_project()` or derive project list from `get_customer_projects()`.
- Load only customer-authorized project files.
- Require explicit portal publication approval before a File becomes visible to the client.
- Split files into Documents and Gallery by file type.
- Keep DPR report photos available in report detail, and optionally aggregate selected published DPR photos into Gallery if the business wants progress photos there.

## Recommended ERPNext Upload Workflow

Recommended future workflow:

```text
ERPNext user opens Project or supported project transaction
-> attaches File
-> marks it as approved for Client Portal publication
-> selects category/type if needed
-> portal helper verifies Customer -> Project access
-> Documents or Gallery displays the file under the correct section
```

Recommended supported sources:

- Project attachments for general project documents and images.
- Daily Progress Report photos for site progress gallery, if explicitly approved for aggregation.
- Daily Progress Report attachments for report-specific files, if the business wants them also surfaced in Documents.

## Recommended Security / Publication Control

Do not automatically expose every internal Project attachment to clients.

Options considered:

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Custom field on `File`, for example `custom_publish_to_client_portal` | Simple and close to the actual attachment record | Needs Custom Field, permission review, and careful UI training. |
| B | Dedicated Project child table for portal documents | Clear project-level workflow and metadata | Requires Project customization and sync/validation with File records. |
| C | Dedicated `Portal Document` / `Project Portal File` DocType | Best auditability, metadata, categorization, project/customer rules, and future expansion | More development than a simple File custom field. |
| D | Use all Project attachments with an allowlist by extension only | Fastest | Risky; may expose internal files accidentally. Not recommended. |

Recommended approach:
Use a dedicated `Project Portal File` or similar DocType, or a Project child table backed by File links, with explicit publish/visibility fields.

Recommended fields:

```text
project
customer
file
file_url
file_name
category: Document / Gallery
publish_to_client_portal
portal_title
caption
description
sort_order
visible_from
visible_until
```

This fits the existing Qatra architecture better than exposing every Project attachment automatically because the portal already uses explicit publication concepts for DPRs (`publish_to_portal`).

## Recommended File Classification

Documents:

```text
.pdf
.doc
.docx
.xls
.xlsx
.csv
.txt
.dwg
.dxf
.zip
.rvt
.ifc
```

Gallery:

```text
.jpg
.jpeg
.png
.webp
```

PDFs should stay in Documents only unless a separate preview/thumbnail feature is intentionally built.

Optional Gallery source:
Published DPR photos can be included in Gallery if the business wants Gallery to represent site progress photos. If used, only photos from submitted, non-cancelled, `publish_to_portal = 1` DPRs for authorized projects should be included.

## Required Development

Exact files/functions likely needing modification or creation:

Backend:

- Add `get_project_documents()` in `construction_management/portal_utils.py`.
- Add `get_project_gallery()` in `construction_management/portal_utils.py`.
- Reuse `get_customer_projects()`, `get_authorized_customer_project()`, and/or `validate_project_in_customers()`.
- Add file classification helpers for document vs image extensions.
- Add publication/security helper, for example `is_file_published_to_client_portal()`.

Documents page:

- Update `construction_management/www/client_portal_documents.py` to load authorized projects, selected project, and document rows.
- Replace placeholder content in `construction_management/www/client-portal-documents.html` with a real document list/grid, filters, download/view actions, and empty states.

Gallery page:

- Update `construction_management/www/client_portal_gallery.py` to load authorized projects, selected project, and gallery image rows.
- Replace placeholder content in `construction_management/www/client-portal-gallery.html` with a real responsive image gallery, captions, full image links, and empty states.

Data model / configuration:

- Add a safe publication mechanism, preferably a dedicated portal file DocType or Project child table.
- Alternatively add a controlled custom field on `File`, but only after confirming permission and workflow requirements.

Frontend styling/behavior:

- Extend `construction_management/public/css/qatra_client_portal.css` for document and gallery views.
- Extend `construction_management/public/js/qatra_client_portal.js` only if client-side filtering, pagination, lightbox, or download behavior is needed.

Dashboard/project counts:

- Update `get_dashboard_counts_for_projects()` and `get_client_portal_project_counts()` if Documents count should reflect published portal files.

Tests / verification:

- Authorized project file visible.
- Unauthorized project file hidden.
- Unpublished file hidden.
- Private published file access behavior confirmed.
- Public unpublished file hidden.
- Document extension routes to Documents.
- Image extension routes to Gallery.
- DPR photo inclusion rule verified if included.

## Implementation Status

Implemented

The current implementation includes the `Project Portal File` DocType, portal document/gallery routes, project counts, dashboard/project quick links, and explicit publish-to-client controls. Migration, cache clear, and asset build were run for `Qatra.local`.

## Verification Status

Runtime Verified

Runtime verification on `Qatra.local` confirmed `PROJ-0015` derives Customer `BUILDING EVOLUTION CONTRACTING L.L.C`, saves published document/gallery records without manual Customer entry, exposes them through portal helpers, and removes the temporary verification records afterward.

## Client Response

The Client Portal Documents and Gallery sections now use an explicit publish-to-client workflow. Uploading a public File and attaching it to a Project is still not enough by itself; the file must be published through `Project Portal File` or come from an approved published DPR source. This keeps visibility project-aware and customer-secure while giving ERPNext users a clear workflow for approved client documents and gallery images.

