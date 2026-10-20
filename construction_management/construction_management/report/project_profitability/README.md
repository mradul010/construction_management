# Project Profitability

This is the existing `Project Profitability` Report identity and route, rebound
to Construction Management. No accounting documents are changed. The setup hook
restores this binding after migration and preserves the existing Report roles.
Accounting views also require GL Entry read/report permission. The former HRMS
report remains available as the Timesheet Profitability view, with Customer and
Employee filters and the selected dates passed to its original implementation.

## Why It Was Empty

The original Report belonged to HRMS (`module=HR`, `ref_doctype=Timesheet`). Its
query inner-joins Timesheet, Salary Slip Timesheet, submitted Salary Slip, Sales
Invoice Timesheet, and submitted Sales Invoice. Qatra has zero Timesheets and
zero rows in both timesheet link tables. Construction invoices and purchases
therefore cannot appear in that query. It is not a GL join or date-filter bug.

## Accounting Rules

- Source: submitted (`docstatus=1`), uncancelled GL Entry postings.
- Accounts: accessible Income/Expense accounts with Profit and Loss report type.
- Income = credit minus debit; expenses = debit minus credit, including returns.
- Period Closing Vouchers are excluded, following standard ERPNext P&L.
  Opening entries follow Accounts Settings' reporting convention.
- Project attribution uses GL Entry.project only. Qatra's two Projects have no
  configured Cost Center mapping. Shared Cost Centers are never allocated by
  assumption. Untagged amounts are separately shown as excluded unmapped Income
  and Expenses within the company/date/account/Cost Center/finance book scope,
  including when an individual Project is selected.
- GL match conditions and accessible Project/Account lists constrain all queries.
  No accounting access is granted by adding or retaining Report roles.
- Company base currency and Frappe's GL Entry currency precision are used.
  Currency conversion to another reporting currency is not offered.

## Expense Classification

`Account.custom_profitability_classification` is an app-owned Select field:
blank, Direct, or Indirect. The nearest explicit classification is inherited
from account ancestors. Cost of Goods Sold account type also establishes Direct
classification for that account and its descendants. A child override takes
precedence. No example account names are embedded in the classification logic.

Other expenses remain Unclassified, with a visible warning. Net profit includes
all expenses. Gross profit remains unavailable when any selected posting uses
an unclassified expense account. Configure the Account or parent to resolve it.
This also prevents a net-zero unclassified balance from silently implying that
all expenses have been classified. No account classifications were guessed or
written to Qatra's existing accounts.

Gross profit = Income - Direct Expenses. Net profit = Income - all Expenses.
Margin = Net profit / Income * 100; zero income yields a zero margin.
Grand-total margin is calculated from grand-total Income and Net Profit.

## Views and Periods

Summary includes project financial totals and metric-based period columns.
Detailed Accounts includes Income, Direct, Indirect and Unclassified sections
as applicable, actual account hierarchy paths, section totals, and project and
grand totals with Gross and Net Profit columns. Cost Center Breakdown includes
each center's own postings plus account details. Parent aggregate values are
never summed with their children. Rows without accounting activity are omitted.
Detail and section rows are breakdowns, not additional values to add to project
totals; the backend produces the sole grand total from source postings.

Monthly, quarterly, and yearly boundaries use the Company's configured Fiscal
Year dates. Q1 starts at the fiscal-year start, not necessarily January.
Custom date ranges clip the first/last period and can span configured fiscal
years. A required missing fiscal-year configuration raises ERPNext's normal
validation error rather than inventing calendar-year boundaries.

## Drill-Down

The currency formatter wraps existing formatted numeric values, including zero,
without modifying report data. Capture handlers prevent DataTable selection.
`frappe.set_route("query-report", "General Ledger")` receives Company, dates,
Project arrays, Cost Center arrays, account arrays, Finance Book options, company
currency, and uncancelled-entry settings. Clicked periods pass their exact dates.
Income, expense, direct/indirect, gross/net, and account rows use the appropriate
account subset. GL shows debits and credits: credit minus debit reproduces
Income and profits; debit minus credit reproduces Expenses.

GL always expands group Cost Centers and cannot select a blank Cost Center or
exclude closing/opening entries in every supported scope. Where this prevents
an exact match, clicking opens an exact transaction breakdown with voucher links
instead. Out-of-range opening entries are detected before using GL routing.

## Verification on Qatra.local

Checked 2026-01-01 through 2026-12-31 against submitted GL and standard ERPNext P&L:

| Project | Income (AED) | Expenses (AED) | Gross / Net Profit (AED) | Margin |
| --- | ---: | ---: | ---: | ---: |
| PROJ-0015 | 1,100,180.16 | 1,308,325.45 | -208,145.29 | -18.92% |
| PROJ-0016 | 253,966.80 | 730,067.32 | -476,100.52 | -187.47% |
| Total | 1,354,146.96 | 2,038,392.77 | -684,245.81 | -50.53% |

All project expenses in this scope inherit Cost of Goods Sold classification.
Indirect expenses are zero because no project-tagged indirect expenses exist
in this dataset, not because every Expense account is treated as Direct.

Company P&L additionally includes unmapped Income 59,371.28 and Expenses
68,580.84. Adding those amounts to the project totals reconciles to company P&L:
Income 1,413,518.24; Expenses 2,106,973.61; Net Profit -693,455.37.

Runtime checks covered all three views, all four metrics, monthly/quarterly/yearly
period-total reconciliation, exact period GL filters, account GL filters, every
Cost Center breakdown row, and both projects' Income/Expenses/Gross/Net GL totals.
There are 27 Cost Centers shared by both projects; explicit Project dimensions
keep these separated. PROJ-0016 September has only Expenses (322,380.11);
January has no transactions and produces an explanation without fabricated
project rows. Only two Projects exist; an entirely unposted third Project was
not created for testing.

Five Python unit tests cover April-March fiscal periods across two years,
clipped dates, classification inheritance/overrides, unclassified costs,
three-decimal currencies, signs, margins, report access and empty-scope safety. Three Node tests
cover numeric currency links, zero, negative highlighting, exact period context,
mouse-event interception, saved date ranges and routing. UI interaction was exercised with handler
tests; no authenticated browser session was used.
