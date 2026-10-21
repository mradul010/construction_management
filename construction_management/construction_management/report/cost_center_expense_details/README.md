# Cost Center Expense Details

Cost Spent links use the same GL selection as Cost Center Transaction Analysis.
The old General Ledger route did not implement its Account Type filter, so
payables, bank and other balancing postings appeared alongside expenses.

Default classification is Account.root_type = Expense, not account-name matching.
Net Cost is debit minus credit, including negative expense reversals. Explicit
Account and Account Type selections retain their original scope, including
stock/WIP/asset scopes; this report does not invent inventory allocations.

Company, dates, project, account, account type, voucher, Finance Book, default-book
settings and accounting dimensions are forwarded. Parent summary rows represent
each Cost Center's direct postings, even when the original selection includes
children. Therefore a clicked row uses that center without children. Standalone
detail selections can include children. Transaction-row clicks also filter by
the exact GL Entry. Back navigation restores the original parent filters.

Only submitted, non-cancelled postings are shown. If excluding draft/cancelled
postings changes the source amount at currency precision, the report throws
instead of presenting a misleading total. The parent calculations are unchanged.
Standard report roles, GL permissions and GL match conditions apply. Voucher
numbers are Dynamic Links; opening documents uses normal document permissions.
Standard report totals and numeric Excel export are used. Currency comes from
the company (AED for Qatra), without currency conversion or balancing adjustments.

## Runtime verification

Read-only verification on Qatra.local, 2026-10-21, for 2026-09-21 to 2026-10-21:

| Cost Center | Parent / detail AED | Entries | With PROJ-0016 AED | Entries |
| --- | ---: | ---: | ---: | ---: |
| Concrete - QBC | 0.00 | 0 | 0.00 | 0 |
| Steel - QBC | 54,799.31 | 2 | 0.00 | 0 |
| Tools & Consumables - QBC | 5,115.46 | 7 | 4,119.46 | 6 |
| Scaffolding & Forms - QBC | 10,000.00 | 1 | 10,000.00 | 1 |

All eight differences were zero. Every default detail account had root_type
Expense; all entries were submitted and uncancelled, with valid voucher targets.
Also verified group selection without double counting, single-GL-row navigation,
Asset scope, default-book switch, numeric Excel export, standard report runner,
Guest denial, and a real negative expense reversal (ACC-GLE-2026-00545).
All three parent views were compared with the committed implementation and their
financial data was unchanged. Nine Python and four JavaScript tests passed.
Client-style omission of unchecked filters and the Accounting Summary's All
account scope were also verified without changing the parent report filters.
No authenticated browser/end-to-end click verification was performed.
