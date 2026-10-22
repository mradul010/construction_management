# UAE VAT 201: Local Implementation and Verification

## Latest Simplification Verification

The simple automatic report supersedes the classification interface documented
in the historical sections below. Changes are local to Qatra.local; no production
deployment occurred. Backup completed before this change:
`sites/Qatra.local/private/backups/20261021_164645-Qatra_local-database.sql.gz`.

Implemented four summary cards, five visible official-box columns and Sales,
Purchases, Journal Entries and Needs Attention tabs. Removed all classification
review/action/status UI from the report. Source evidence produces in-memory
financial events without creating or approving classification records. Existing
valid verified history is supported; all 354 historical child records are intact.

Runtime first-period verification recalculated Sales VAT 55,062.68, Purchase VAT
36,515.54 and unallocated journal movement -48,718.56 AED. All 308 invoice/account
checks matched GL. Details include 354 sources, 327 needing attention: 13 sales
with company-derived rather than verified supply Emirate, 295 purchase tax rows
without established recovery, and 19 unresolved journal GL rows. The remaining
27 purchase item sources have no recorded VAT. Seven real purchase returns retain
negative VAT signs. No sales return was found; fixture tests cover that behavior.

Therefore the report correctly remains PRELIMINARY - VERIFICATION REQUIRED.
Recorded VAT is visible, but recoverable purchase VAT, journal adjustments and
final net VAT are Pending Verification. Internal included subtotals are zero
because no current source treatment is sufficiently established; this is not a
nil return. Invoice VAT/GL agreement does not prove legal recovery or Emirate.

Verified normal Frappe report execution, all four maintained filing periods,
first due date 2026-08-31, later provisional dates, TRN/legal name/account mapping,
CSV/XLSX/PDF downloads, workbook formula escaping, and Guest denial. PDF has three
A4 pages and was visually checked. Python tests cover automatic evidence,
returns, deduplication, legacy history, all official boxes and reconciliation;
All 56 Python tests and five Node tests passed. Node tests cover simplified
filters, period selection, formatting and drilldowns.
Local build and site cache clearing completed. Authenticated browser verification
requires a user-provided authenticated session or explicit temporary-session
authorization; the safety check blocked automatic Administrator impersonation.
No privileged test session was created.

Database verification compared full child-record hashes before/after and the
active VAT GL snapshot: 430 rows, debit 99,680.06, credit 104,579.55, latest modified
2026-09-28 18:32:02.185140. All unchanged. Optional source-evidence custom fields
were installed, but no submitted invoice, journal, GL entry or balance was edited.

Verified on Qatra.local on 2026-10-21. No production connection or deployment was
performed. Technical functionality is implemented; the return is **Needs Review**,
not approved, filed, or a nil return. All reported amounts below were recalculated
from submitted, uncancelled local transactions, not hardcoded in the engine.

## Backup and Data Safety

Before configuration changes, Bench created:

`sites/Qatra.local/private/backups/20261021_145607-Qatra_local-database.sql.gz`

The accompanying site-configuration backup is in the same private directory.
Only app-owned metadata, UAE VAT Settings and its child configuration/review rows
were changed. No Sales/Purchase Invoice, Journal Entry, GL Entry, account structure
or accounting balance was modified. No fake transactions or approvals were made.

The VAT ledger snapshot was unchanged after verification: 430 active submitted GL
rows across all available dates, debit AED 99,680.06, credit AED 104,579.55, latest
modified timestamp 2026-09-28 18:32:02.185140. The first-period movement alone is
AED -67,265.70 (debit minus credit), not an approved VAT liability.

## Saved Configuration

- Company: QATRA BUILDING CONTG LLC; legal name QATRA BUILDING CONTG LLC OPC.
- Standard Company.tax_id: 105452509000003.
- Effective registration date: 2026-05-01; registered Emirate: Ras Al Khaimah.
- Existing VAT 5% - QBC account mapped once as Both. No duplicate accounts.
- Quarterly February-January cycle; Profit Margin Scheme No.

| Period | Quarter | Due Date | Basis |
| --- | --- | --- | --- |
| 2026-05-01 to 2026-07-31 | 2 | 2026-08-31 | Confirmed; unchanged |
| 2026-08-01 to 2026-10-31 | 3 | 2026-11-28 | Provisional: period end + 28 days |
| 2026-11-01 to 2027-01-31 | 4 | 2027-02-28 | Provisional: period end + 28 days |
| 2027-02-01 to 2027-04-30 | 1 | 2027-05-28 | Provisional: period end + 28 days |

Provisional dates are labelled and warn in the report. They are not asserted as
holiday/weekend-adjusted FTA deadlines. Existing confirmed dates are never replaced.

## Source Investigation

Inspected Company, Account, UAE VAT Settings, classifications and filing periods;
submitted Sales/Purchase Invoice headers, items and tax rows; returns; all seven
first-period VAT Journal Entries and their complete account rows/GL; Customer,
Supplier, Address, Tax Category, Sales/Purchase Tax Templates; construction Project,
RA Bill and invoice links; and the installed construction/journal VAT generators.

Key findings:

1. Sales Invoice.vat_emirate is fetched from company_address.emirate in the installed
   ERPNext localization. All 13 first-period sales invoices store Ras Al Khaimah,
   but this is not proof of each supply's legally applicable Emirate. The engine
   suggests Box 1f with that caveat; it does not auto-approve or change Box 1a.
2. All 317 first-period Purchase Invoice headers have the default zero
   recoverable_standard_rated_expenses and reverse_charge N. Zero is not proof of
   either zero or full recovery entitlement. Supplier/invoice TRNs are not populated.
   The default reverse-charge recovery percentage 100 is not treated as approval.
3. Saved tax rows, their preceding-row taxable bases, signs, and active invoice GL
   are read directly. No base is invented by dividing VAT by 5%. Retention and
   advance deductions are not treated as VAT merely by their rate or description.
4. The qatra_custom journal generator writes explicit base-row VAT account/rate
   and auto-tax-row metadata. All 19 first-period VAT GL rows uniquely match a saved
   base row using that evidence. This supplies review evidence only, not legal
   recovery/place-of-supply approval. qatra_custom itself was not modified.

Complete journal evidence was saved privately:
`sites/Qatra.local/private/files/vat201-journal-investigation-2026-05-01.json`.
All seven journals had no accessible supporting attachments or structured invoice
references. Their business purposes remain Unresolved rather than being inferred
from debit/credit direction.

| Journal | VAT Rows | Debit AED | Credit AED | Unresolved Evidence |
| --- | ---: | ---: | ---: | --- |
| ACC-JV-2026-00001 | 1 | 0.00 | 26,532.14 | Advance-tax reference QTI/0001; verify original invoice, tax point and supply Emirate |
| ACC-JV-2026-00002 | 1 | 0.00 | 22,783.63 | QTI0002; structured Project PROJ-0015 conflicts with remarks naming Villa 167 / PROJ-0016 |
| ACC-JV-2026-00003 | 5 | 359.92 | 0.00 | Saved construction-cost base rows; supporting invoices/recovery assessment missing |
| ACC-JV-2026-00004-1 | 2 | 28.52 | 0.00 | Saved cost base rows; supporting invoices/recovery assessment missing |
| ACC-JV-2026-00006 | 3 | 23.48 | 0.00 | Saved expense base rows; supporting invoices/recovery assessment missing |
| ACC-JV-2026-00007-1 | 4 | 118.74 | 0.00 | Saved cost/stationery base rows; supporting invoices/recovery assessment missing |
| ACC-JV-2026-00008 | 3 | 66.55 | 0.00 | Saved cost base rows; supporting invoices/recovery assessment missing |

No journal was asserted to be a VAT settlement/payment/correction without proof.

## Review Workflow Implemented

The existing UAE VAT 201 Return has a Classification Review view, not a separate
application or replacement report. It shows original voucher/source IDs, posting
date, party, project, VAT account, saved taxable base/VAT, debit/credit, suggested
box, status, origin, journal treatment, reason and remarks. Filters cover configured
filing period, Company, dates, return/classification status, voucher type, box,
party and Project. Review filters narrow the evidence view, not whole-return totals.

Manager actions: Generate Review Suggestions; Review; Save Review; Approve;
Reject; edit classification/remarks; add another VAT-side classification (for
reviewed reverse charge); and change return status. Other saved classifications
of the same source can be reopened individually. There is no unsafe bulk approval.

354 system-derived pending records were created locally, without approving any:
13 suggested Box 1f, 295 suggested Box 9, 27 untaxed purchase items without sufficient
box evidence, and 19 unresolved journal GL rows. Repeating generation creates no
duplicates. Untouched system evidence can refresh; approvals, rejections and manual
decisions are preserved. Rejecting a suggestion does not remove its ledger amount
or manufacture an Outside VAT exclusion.

Approvals validate source permissions, active submitted status, exact source row,
VAT account side, supporting reference/reason, tax date, recoverability, base,
adjustment treatment and current source fingerprint. Changes in source evidence
invalidate its use and require renewed review. Parent settings use Version/audit
tracking; approval identity/time are stamped server-side.

Mapped VAT postings cannot simply be hidden as Outside VAT. An explicitly reviewed
journal/payment classified VAT settlement, VAT payment or VAT reclassification may
be excluded from return boxes, while its movement remains visible in control
reconciliation. Taxable corrections/adjustments still use their appropriate VAT
box/adjustment rules. None of the actual unresolved journals was auto-excluded.

Ready for Approval requires clear configuration/reconciliation and no pending
classifications. Manager approval is explicit. Filed additionally requires prior
approval, actual submission date and filing receipt reference. No FTA submission
is made by these actions. The actual unresolved first return was tested and its
attempted approval was correctly rejected without changing saved status.

## Calculations and Reconciliation

| First-period measure | AED | Meaning |
| --- | ---: | --- |
| Recorded invoice sales VAT | 55,062.68 | Matches invoice VAT GL individually |
| Recorded invoice purchase VAT | 36,515.54 | Matches invoice VAT GL; not established as recoverable |
| Journal debit minus credit | -48,718.56 | Unallocated pending source review |
| Mapped control-account movement | -67,265.70 | Ledger movement, not a return calculation |
| Approved recoverable input VAT | Undetermined | No recovery approvals were fabricated |
| Approved journal tax adjustment | Undetermined | Journals remain unresolved |
| Net VAT payable/refundable | Undetermined | Not an approved nil return |

All 308 VAT-bearing invoice vouchers reconcile individually with difference zero.
VAT-account mapping duplicates were tested in memory and do not duplicate sources,
ledger or amounts. Source-side classifications distinguish Sales/Purchases and
returns; journal/payment sides require explicit treatment. Signed credit notes,
reverse-charge sides, tax-point differences and recovery exclusions are retained.

VAT 201 boxes include only approved tax events. Pending-only boxes display Pending
review, not a misleading 0.00; return summary cards/PDF show Undetermined for the
unresolved liability. Accounting reconciliation still transparently exposes the
numeric approved subtotal zero versus ledger differences: output -55,062.68 and
input -36,515.54. No amounts were forced to reconcile.

The review, audit export and PDF expose the actual recorded amounts separately.
Invoice tax/GL checks and mapped VAT control movement are part of reconciliation.
Net-box drilldowns have signed Contribution values so output less input matches
the clicked cell; other box measures use their actual amount/VAT/adjustment field.

## Verification

- 39 Python tests: original 25 and 14 review-workflow tests.
- Six JavaScript tests: period initialization, source-key review actions, pending
  display, decimal links and captured click behavior.
- Actual Qatra.local standard report runner: Summary, Detailed, Classification Review.
- Actual configured period selection, Company context, saved reviews, repeat sync,
  Project conflict, source-to-GL checks and unchanged control-account snapshot.
- XLSX, CSV and PDF download functions; numeric values, formula-injection escaping,
  taxpayer details and evidence exported. PDF verified as three A4 pages.
- Guest cannot read the report or generate reviews.
- Failed intermediate development tests were fixed; final suites have no failures.
- No authenticated browser end-to-end verification or production verification is
  claimed. Client navigation/dialog behavior is covered by handler tests.

Local report:
`http://127.0.0.1:8000/desk/query-report/UAE%20VAT%20201%20Return`

Private generated PDF:
`sites/Qatra.local/private/files/vat201-first-return-preparation.pdf`

## Files Changed

Within construction_management only:

- `construction_management/construction_management/doctype/vat_201_classification/vat_201_classification.json`
- `construction_management/construction_management/doctype/vat_201_filing_period/vat_201_filing_period.json`
- `construction_management/construction_management/report/uae_vat_201_return/configuration.py`
- `construction_management/construction_management/report/uae_vat_201_return/engine.py`
- `construction_management/construction_management/report/uae_vat_201_return/review.py`
- `construction_management/construction_management/report/uae_vat_201_return/uae_vat_201_return.py`
- `construction_management/construction_management/report/uae_vat_201_return/uae_vat_201_return.js`
- `construction_management/construction_management/report/uae_vat_201_return/return_print.html`
- `construction_management/construction_management/report/uae_vat_201_return/test_review.py`
- `construction_management/construction_management/report/uae_vat_201_return/test_uae_vat_201_return.js`
- This completion report and the existing report documentation.

## Future Deployment Commands: NOT EXECUTED

Current local branch is test-pankaj. Commit/push only the reviewed VAT files:

```bash
cd /home/ts/frappe_setup/my-bench/apps/construction_management
git add construction_management/construction_management/report/uae_vat_201_return construction_management/construction_management/doctype/vat_201_classification construction_management/construction_management/doctype/vat_201_filing_period docs/UAE_VAT_201_LOCAL_COMPLETION.md docs/UAE_VAT_201_RETURN_REPORT.md
git diff --cached --check
git commit -m "Complete local UAE VAT 201 evidence and review workflow"
git rev-parse HEAD
git push origin test-pankaj
```

The production Bench path/site were not supplied. Set these three values to the
actual deployment target and the reviewed commit SHA printed above. These are
commands for later authorized execution, not a production action taken here:

```bash
export PROD_BENCH="/actual/production/bench"
export PROD_SITE="actual-production-site"
export VERIFIED_VAT_COMMIT="reviewed-commit-sha"
cd "$PROD_BENCH"
bench --site "$PROD_SITE" backup --with-files
git -C apps/construction_management fetch origin test-pankaj
git -C apps/construction_management merge --ff-only "$VERIFIED_VAT_COMMIT"
bench --site "$PROD_SITE" migrate
bench build --app construction_management
bench --site "$PROD_SITE" clear-cache
bench restart
```

The fast-forward merge intentionally fails rather than resetting an incompatible
or dirty production worktree. Code/schema deployment does not transfer local
database settings, approvals or evidence. Never restore the local test database
onto production. Production accounting/configuration requires its own authorized
inspection and verification before representing that site's return as ready.
