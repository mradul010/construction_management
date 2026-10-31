# UAE VAT 201 Return

## Simple Saved-Record Workflow: 2026-10-31

This section supersedes the report review/action instructions below. Users select
Company and period, Refresh, and view/export the calculated report. Report-level
Review/Resolve/Override controls, recovery dialogs, policy shortcut buttons and the
Needs Attention tab have been removed from the JavaScript implementation, not
hidden with CSS. The report no longer returns an unused `can_review` UI capability.
Historical classifications, settings and audit records remain intact; existing
valid supported decisions/settings still feed the original calculation engine.
No new approval, policy or report was introduced.

The screen shows official VAT boxes, compact recorded-versus-return reconciliation
and the same eight-column linked Sales/Purchases/Journal Entries details. Raw
balances, voucher-type breakdown and full bridge remain expandable. Routine rows
use factual source labels. Source limitations appear as concise transaction notes,
not mandatory actions: **Recovery not specified in source.** or **Output not
allocated to an Emirate** where applicable. Workbook/PDF now use Source Notes in
place of Needs Attention/Review sections. Recovery provenance and complete source
references remain in the audit exports.

The calculation description is **Calculated from saved ERPNext records**. The
status additionally states incomplete return allocation where source information
is unavailable. Numeric known subtotals retain component-level provisional flags
and explanations; removing the review UI does not turn unknown entitlement into
zero or claim that the return is final, verified or ready for filing.

### Current Local Evidence

ACC-PINV-2026-00293-1 still reads its saved standard AED recovery amount directly:
source base 1,557.50, recorded VAT 77.88, claim 10.00 and recorded VAT not claimed
67.88. Bill number/date remain the structured 16937 / 2026-07-16. Zero/partial/full
recovery, signed returns, currency semantics and duplicate protection are unchanged.

ACC-JV-2026-00007-1 still produces four supported groups: 96.00/4.80,
936.50/46.82, 300.00/15.00 and 1,042.37/52.12, totalling base 2,374.87 and posted
VAT 118.74. Expense descriptions/project/cost center remain separated. No saved
JE/account/company recovery field, approved JE classification or recovery rule
exists locally. The broader expense-JV recorded input of 597.21 therefore remains
unspecified, not confirmed non-recoverable or automatically claimed. Existing
supported settings continue to resolve automatically when present; they were
verified with isolated in-memory full/partial/zero settings, never saved.

ACC-JV-2026-00001 and ACC-JV-2026-00002 contain no saved transaction Emirate, explicit
invoice references, linked submitted sales-advance allocations/JE adjustments or
attached original tax documents. They remain recorded output of 26,532.14 and
22,783.63 respectively. The missing reporting Emirate cannot be established from
Company/Customer address, project or free text. No structured overlap link was
found; that is not proof that unlinked original tax invoices do not exist.

Live period 2026-05-01 through 2026-07-31 remains:

| Measure | AED |
| --- | ---: |
| Recorded output VAT | 104,378.45 |
| Recorded net input VAT | 37,112.75 |
| Period net ledger credit movement | 67,265.70 |
| Return-allocated output | 55,062.68 |
| Saved eligible input claim | 10.00 |
| Purchase invoice VAT unclaimed per saved amounts | 36,505.54 |
| Expense-JV recovery unspecified | 597.21 |
| Output not allocated to an Emirate | 49,315.77 |
| Known net return calculation, incomplete | 55,052.68 |
| Opening debit / Closing credit | 535.57 / 66,730.13 |

All 315 current vouchers reconcile with native GL, period debit 37,274.40 and credit
104,540.10; bridge residuals remain zero. Three untaxed foreign-purchase item rows
also lack sufficient source import/reverse-charge treatment. These 22 unavailable
source rows remain traceable without an intrusive review workflow or invented tax.
Recorded balances are not substituted for statutory claims or payable.

### Checks and Delivery

Changes are confined to construction_management: `automatic.py`, `policy.py`,
`reconciliation.py`, `uae_vat_201_return.py`, `uae_vat_201_return.js`,
`return_print.html`, related regression tests and this document. The existing
read-only API/export service and submitted-source permission filters are reused.
Refresh bypasses prepared results; screen/context, standard Excel and custom
workbook values agree, and PDF generation preserves the same figures/status.
Read-only snapshots cover invoices, journal/GL rows, recovery values, policies,
classifications, settings, Versions and Comments. No financial/audit data changed.
No authenticated browser verification or production deployment is claimed.
Final checks passed 155 Python tests and nine JavaScript tests. Live standard
Excel/custom workbook amounts, PDF output, native GL comparison and read-only
snapshots passed. No routine approval controls remain in the report source.

Deploy the updated construction_management app using the existing Frappe Cloud
workflow, with its normal Python process reload. Use supported Cloud tooling for
the actual site identifier; no shared-bench shell access is assumed. No schema
setup, migrate or extra asset-bundle build is required for this change. Clear the
site cache and hard-refresh Desk. Local command:

```bash
bench --site Qatra.local clear-cache
```

## Structured Expense Journal Recovery: 2026-10-31

The report reuses the existing **VAT 201 Recovery Policy** table for Expense
Journal rules. No second policy system, new verification field or schema change
was added. Purchase Invoice recovery remains the saved AED Currency amount and is
not routed through journal rules.

The generator belongs to qatra_custom (`journal_entry.py` and its form JavaScript).
It creates same-side VAT rows from configured source rows and copies project/cost
center; it does not currently save a source-row link. The report resolver in
construction_management prefers explicit links where available, then reconciles
saved generator amounts by VAT account, project, cost center, side, rate and
inclusive/exclusive split. Actual saved VAT and active GL remain authoritative;
the calculated generator expectation is only a matching check. Posted rounding,
including 936.50 / 46.82, is preserved. A blank Party does not exclude petty cash.

When one-to-one matching is ambiguous but the entire expense dimension group
reconciles, the report now retains one supported group total with all original
base/tax/GL references. It does not invent per-line allocations or repeat the
group base on each tax row. Conflicting explicit links, non-expense transfers,
unreconciled currency amounts and unsupported groups remain unresolved. Previously
saved decisions/restrictions on any grouped GL member cannot silently become a
different group decision; a group-bound renewed decision is needed where relevant.
The source-ledger audit recognizes every grouped GL reference once.

Previously, even an approved matching Expense Journal rule additionally demanded
bill number/date and an attachment on each JE header. This prevented rules from
resolving structured petty-cash journals. The approved company rule now supplies
the reusable eligibility basis; these header fields are not repeated approval gates.
The rule still requires existing manager approval, exact expense-account scope,
effective dates, percentage, payment condition, business-use basis and supporting
policy reference. Existing explicit manual restrictions take precedence. A rule
limited to paid invoices cannot assume invoice paid status for a journal. No rule
or ambiguous/conflicting rules leave recovery unresolved without erasing base/VAT.

The eight report columns are unchanged. Remarks now includes the expense account,
saved project/cost center, description, recoverable amount and rule identity.
Resolved rows need no per-voucher action; genuine exceptions retain their action.
Managers can use **Settings > Journal Recovery Rules** to open the same UAE VAT
Settings configuration. No supplier, recovery percentage or original tax amount is
invented. Zero-recovery rules retain recorded VAT and have no Box 9 claim label.

Read-only Qatra.local verification for ACC-JV-2026-00007-1:

| Source base | Posted VAT | Full-rule claim (test only) |
| ---: | ---: | ---: |
| 96.00 | 4.80 | 4.80 |
| 936.50 | 46.82 | 46.82 |
| 300.00 | 15.00 | 15.00 |
| 1,042.37 | 52.12 | 52.12 |
| **2,374.87** | **118.74** | **118.74** |

Full/50%/zero rule scenarios were exercised against the actual source evidence
strictly in memory: journal claims 118.74 / 59.37 / 0; Site Misc Tools claims
52.12 / 26.06 / 0. Source VAT, all 315 voucher reconciliations and Purchase Invoice
saved recovery 10 remained unchanged. Standard Excel and custom workbook matched;
PDF generation and unchanged accounting/settings/audit snapshots passed.
The final regression suite passes 154 Python tests and nine JavaScript tests,
including grouping, explicit-link conflicts, zero-VAT exclusion, reversal/FX
matching, GL aliases, manual restriction precedence and policy provenance.

The local Company still has zero approved recovery rules. An authorized manager
must configure appropriate Expense Journal rows in the existing company table,
covering the actual expense accounts (Printing & Stationary and Cost Of Construction
Projects here), with narrower project/cost-center scopes where required and the
company's approved eligible percentages/basis. No blanket 100% rule was saved.
Without that configuration, the recorded 118.74 remains visible and only recovery
is unresolved. The broader live report retains 22 unresolved source rows and a
provisional liability. Customer advances and their missing-Emirate issues remain
separate; no output VAT was converted into an input claim.

Changes: `journal.py`, `policy.py`, `review.py`, `engine.py`, `reconciliation.py`,
`automatic.py`, report JavaScript, regression tests and this document, all inside
construction_management. No qatra_custom/core files, JEs, GL entries, recovery
decisions or submitted documents were changed. No migrate or build is required;
deploy the app through its existing workflow, reload Python normally, clear site
cache and hard-refresh Desk. No production or authenticated-browser verification
is claimed. Verification artifacts: `/tmp/qatra-vat201-journal-rules.xlsx`,
`/tmp/qatra-vat201-journal-rules.pdf`, and
`/tmp/qatra-vat201-journal-rules-verification.json`.

## Saved Invoice Recovery: 2026-10-31

This section supersedes the recovery-policy/default-zero requirements below for
ordinary Purchase Invoices. Installed UAE metadata defines
`recoverable_standard_rated_expenses` as Currency, labelled **Recoverable Standard
Rated Expenses (AED)**, default zero, with no percentage semantics. The installed
native report sums this amount directly; its foreign-currency tests maintain this
AED amount independently of the invoice currency. The UAE controller disallows a
nonzero standard recovery amount on reverse-charge purchases, which instead use
the existing separate reverse-charge percentage. No core code was changed.

For standard-rated purchases, the saved invoice amount now owns recovery. Zero is
zero, not an incomplete decision; partial and full amounts remain their saved AED
values. No custom recovery flags, policy match, Version-history query, separate
approval, reason or attachment is required to read it. Historical report approvals
and policies remain stored but cannot override this field for ordinary invoices.
Ordinary standard-rated purchase rows expose no Review/Override action, and the report's Recovery Policies
button was removed. Existing supported journal decisions/policies and reverse-charge
treatment remain separate and unchanged.

The existing engine calculates the claim using Decimal arithmetic and framework
AED precision. For multiple disjoint VAT rows, the single saved invoice amount is
allocated proportionately to their recorded VAT with cumulative currency rounding,
so each source row contributes once and allocations sum to the saved rounded
amount. Duplicate source identities cannot duplicate claims. Unsupported/mixed-sign
allocations, missing values, nonfinite values, wrong signs, excessive recovery,
unsupported taxable bases and source/GL mismatches remain explicit data errors.
Saved taxable bases and VAT are never reconstructed by dividing rounded VAT by a
rate. Negative return claims retain their saved signs. Foreign invoice amounts use
saved Company-base amounts; the recovery field is already AED and is not multiplied
by the transaction conversion rate again. Non-AED Companies still require supported
Company-to-AED tax-point evidence; no rate is invented.

The eight detail columns remain Date, Voucher Number, Party, Taxable Amount, VAT
Amount, VAT Treatment, VAT Box, Remarks. Source taxable amount and recorded VAT stay
visible at zero recovery. Zero-claim rows say **No input VAT claimed** and have no
Box 9 label. Remarks shows recovery basis and structured supplier invoice number/
bill date; stale free-text invoice dates are not parsed. Missing/invalid supplier
TRN is a concise source-quality note, not a gate that replaces saved recovery.
Saved values are not described as independently verified by the report.

The primary cards show recorded output/input, recoverable purchases, recorded input
not claimed, adjustments and the provisional net calculation. Detailed raw balances
and the recorded-to-return bridge are collapsible; the compact reconciliation and
genuinely unresolved source rows remain available. A deliberate partial/zero-claim
difference is explained in the bridge rather than treated as a recovery exception.

### Verified Local Results

Read-only Qatra.local verification for 2026-05-01 through 2026-07-31:

| Source / measure | AED |
| --- | ---: |
| ACC-PINV-2026-00293-1 source taxable amount | 1,557.50 |
| Recorded VAT | 77.88 |
| Existing saved recovery / Box 9 VAT claim | 10.00 |
| Recorded VAT not claimed for that invoice | 67.88 |
| Period recorded output VAT | 104,378.45 |
| Period recorded net input VAT | 37,112.75 |
| Period input VAT claimed | 10.00 |
| Recorded input less current claim, including pending journal VAT | 37,102.75 |
| Known recorded input not claimed | 36,505.54 |
| Journal input recovery still unresolved | 597.21 |
| Advance output allocation still unresolved | 49,315.77 |
| Known net return subtotal (provisional) | 55,052.68 |

The invoice already had recovery 10 when this task began. It was not edited. Its
structured bill number is 16937 and bill date 2026-07-16. The obsolete custom fields
remain zero without suppressing the claim. ACC-PINV-2026-00210-1 retains taxable
323.00, VAT 16.15 and saved zero recovery, with no recovery warning or Box 9 label.

All 315 current voucher amounts match native GL: debit 37,274.40, credit 104,540.10,
net credit movement 67,265.70, opening debit 535.57 and closing credit 66,730.13.
Recorded-to-claim bridge residuals are zero. There are 22 remaining source exceptions:
17 matched purchase-journal tax rows lacking saved supported entitlement, two
customer advances lacking authoritative reporting Emirate, and three untaxed
foreign-purchase item rows needing import/treatment review. These are not 22 unique
vouchers. No journal recovery or Emirate was fabricated and the net return remains
provisional, not forced to the ledger movement or balance.

Refresh bypasses stale prepared data. Standard Excel, custom workbook and PDF use
the same existing live calculation service. Verification compares screen/context
amounts and workbook values and checks unchanged source, GL, Version, Comment,
classification, settings and policy snapshots. Artifacts are
`/tmp/qatra-vat201-saved-recovery.xlsx`, `/tmp/qatra-vat201-saved-recovery.pdf` and
`/tmp/qatra-vat201-saved-recovery-verification.json`. No accounting data, recovery
value, historical custom-field data or approval was modified.

### Changed Files and Deployment

This simplification changes `automatic.py`, `engine.py`, `reconciliation.py`,
`policy.py` (journal exception wording only), `uae_vat_201_return.py`,
`uae_vat_201_return.js`, relevant Python/JavaScript regression tests and this document
inside construction_management. The prior shared live API/export implementation is
retained. No new field, DocType, policy or migration is required by this change.

Deploy the updated custom app through the existing Frappe Cloud workflow, with its
normal Python process reload, then clear the actual site's cache and hard-refresh
Desk. Do not assume shell access on a shared cloud bench. Local cache command:

```bash
bench --site Qatra.local clear-cache
```

On production use the actual site identifier with the authorized Cloud console or
operator. No migrate or additional asset-bundle build is required for this change.
No production deployment or authenticated-browser verification is claimed.
Regression verification passed 149 Python tests and nine JavaScript tests,
including direct saved-value precedence, zero/partial/full recovery, source
quality versus data errors, return signs, AED field semantics on foreign invoices,
multi-tax-row allocation/deduplication and removal of purchase approval controls.

## Source-Based Recovery Policies and Live Exports: 2026-10-31

This section supersedes the earlier requirement for individual approvals on every
ordinary purchase. The existing Construction Management report now applies a
uniquely matching approved company recovery policy, or an eligible saved nonzero
AED recovery amount, through its existing calculation engine. Default zero alone
does not establish intent; retained valid manual decisions, including explicit
zero, take precedence. No source recovery value or approval is written by Refresh.

UAE VAT Settings now supports an app-owned **VAT 201 Recovery Policy** child table.
Accounts Managers/System Managers approve dated policies scoped to an exact expense
account plus invoice Tax Category and/or Purchase Tax Template. Optional Project
and Cost Center restrictions, eligible percentage, payment condition, business-use
basis and supporting policy reference are maintained once. Conflicting matches
remain exceptions. Policy identity and approval provenance are exported separately
from individual review approval; policy-derived events are not labelled reviewed
by an accountant. Settings changes retain the existing parent audit trail.

Ordinary domestic positive-recovery policies require saved supplier invoice
number/date and a valid supplier TRN, an evidenced UAE supplier country, supported
taxable-base allocation and matching posted VAT. Supplier master TRN, primary
address and country are read only where the invoice lacks the corresponding
source, subject to permissions; linked invoice evidence takes precedence. Saved
item-wise tax details can resolve separate taxable bases only when their saved
tax reconciles; overlapping bases are not counted twice. Signed returns, partial
recovery, non-recoverable policies, discounts and existing reverse-charge/FX paths
are retained. Journal policies additionally require the existing structured
expense/tax-row match and saved original bill evidence. No VAT rate/account-name
heuristic creates entitlement.

Resolved routine inputs require no review popup. An optional authorized override
asks only eligible recovery and reason when source date/base/currency are already
known; genuine exceptions expose only relevant additional fields. The existing
eight transaction columns remain unchanged. Source taxable base and recorded VAT
stay visible independently of return claims, including zero-recovery cases.

The previous standard Excel path exported only the visible box grid. A supported
API hook now routes this report's standard Excel/CSV export to its existing full
preparation exporter. Other reports delegate unchanged to Frappe. Refresh bypasses
prepared results and uses one request-local calculation for the grid and context;
exports freshly read the same selected filters through the same calculation service.
There is no cross-request calculation cache or separate export arithmetic. The
standard workbook and custom workbook match, including the recorded bridge, source
audit and opening/closing balances. PDF uses that same report service.

### Local Verification and Remaining Configuration

Qatra.local: Frappe 16.31.0 / ERPNext 16.32.1. Local targeted setup added only the
policy child DocType/table field and refreshed this report's metadata. No migrate,
accounting changes or policy approvals were performed. There are **zero configured
policies**. An authorized manager must establish actual company policy; no full
recovery policy was assumed or saved for testing.

For 2026-05-01 through 2026-07-31, all 315 voucher audit totals reconcile with native
General Ledger. Recorded output is AED 104,378.45; net recorded input AED 37,112.75;
period debit AED 37,274.40; period credit AED 104,540.10; net credit movement
AED 67,265.70. Opening debit is AED 535.57 and closing credit AED 66,730.13.
Allocated output remains AED 55,062.68 and claimed input zero; this is an incomplete
return subtotal, not a final liability. All recorded-to-claim bridge residuals are
zero because unresolved amounts remain explicitly pending.

There are 317 source exceptions: 295 purchase tax rows without an approved recovery
policy/decision, 17 matched purchase-journal tax rows, two customer advances missing
authoritative reporting Emirate, and three untaxed foreign-purchase item rows needing
treatment review. A read-only hypothetical-policy check found 244 purchase rows with
simple expense/tax scope: 193 lack the required saved supplier invoice identity/date
or valid supplier TRN; 51 lack a supported UAE country/address. No actual purchase
qualified for automatic full recovery in that check. Policy setup alone therefore
does not resolve the missing original-source evidence. These counts are source
rows, not unique invoices, and no supplier/invoice correction was made.

Tests: 144 Python and nine JavaScript tests pass, including eligible full/partial/
zero policies, signed returns, manual precedence, source evidence, policy conflicts,
permissions, shared live result and standard export routing. Runtime checks confirm
fresh calculation timestamps, identical standard/custom workbook amounts, eight
transaction columns and unchanged accounting/configuration snapshots. No
authenticated-browser verification or production deployment is claimed.

The supplied GL workbook also has 315 vouchers and the same debit/credit totals,
but seven voucher identities differ from the current local database. The audit
matches current native GL by exact voucher identity; the older workbook is not
silently matched by equal amounts or assumed amendment lineage. The differences
are retained in `/tmp/qatra-vat201-export-voucher-differences.json`. PDF generation
passed with six A4 pages including the preparation/reconciliation appendices.

### Deployment

All changes are in construction_management. Deploy the app through the existing
Frappe Cloud workflow, including its normal Python process reload. Then have an
authorized operator run the targeted setup on the actual site name (not the URL):

```bash
bench --site <site-name> execute construction_management.construction_management.report.uae_vat_201_return.configuration.setup_recovery_policy
bench --site <site-name> reload-doc construction_management report uae_vat_201_return
bench --site <site-name> clear-cache
```

No additional asset-bundle build is required for these directly loaded report files.
The targeted setup was already performed on Qatra.local; production remains
undeployed/unverified. Do not assume shell access on a shared Frappe Cloud bench.

## Recorded Ledger Reconciliation: 2026-10-31

This section supersedes the saved-zero-as-confirmed-exclusion policy in earlier
notes. The report remains owned by `construction_management`; no parallel engine
was created in `qatra_custom`. Confirmed local site is `Qatra.local`, Frappe
16.31.0 / ERPNext 16.32.1, with HRMS, Print Designer and both custom apps installed.

### Root Causes and Correction

The old first summary card showed Sales Invoice VAT only (55,062.68), despite the
audit already containing advance output VAT (49,315.77). Recorded accounting roles
were therefore more complete than the main summary. A default invoice recovery
amount of zero was also treated as a confirmed exclusion, concealing the absence
of an approved recovery decision. There were no missing period voucher amounts.

`engine.py` retains permission-aware submitted/uncancelled source reads and now
provides separate opening GL evidence and validated out-of-period tax-date events.
`reconciliation.py` partitions recorded VAT into return claims, pending decisions,
approved exclusions, supported timing differences and unexplained residuals.
Raw debit/credit stays separate from normalized output/input signs. Purchase
credit notes reduce input VAT; they do not become output merely because of credit.
Each source/tax/GL identity is counted once. Reconciliation residuals and scope
limitations remain visible; return claims are never forced to equal closing GL.

The same final backend result supplies summary cards, eight-column transaction
details, reconciliation, Excel/CSV and PDF. New ledger/bridge/category/decision
sheets supplement the existing workbook sheets. The PDF now has five intentional
pages: three preparation pages, review notes, and the recorded/return bridge.
Known statutory payable remains explicitly provisional when evidence is missing.

### Recovery Semantics and Audited Review

Installed UAE metadata defines `recoverable_standard_rated_expenses` as a manual
Currency amount in AED with default 0, not a checkbox or percentage. Native UAE
report queries sum this maintained amount and filter positive values; regional
validation disallows nonzero ordinary recovery for reverse-charge purchases.
No installed controller automatically fills this amount. Custom verification
checkbox/percentage fields are hidden historical controls, not entitlement proof;
they remain untouched and are not used as approval prerequisites.

A saved proposal, including zero or a copied amendment value, does not itself
approve entitlement in this preparation report. Only existing valid approved
`VAT 201 Classification` decisions grant recovery. States distinguish pending,
verified full, partial and non-recoverable (explicit approved 0% with reason),
and no recorded VAT. Signed claims derive from posted VAT and the approved
percentage. A nonzero saved AED recovery proposal inconsistent with a single-row
approved allocation is flagged, not silently replaced. A default zero can be
explicitly superseded by a reasoned register decision without changing the invoice.
Actual source taxable base and VAT remain visible even while claims are pending.
Verified zero rows have no visible claim box; their source tax remains recorded.

Managers with report/source read and UAE VAT Settings write permission can use
Review VAT in transaction/attention rows. It reuses `review_source` / `decide`,
not a new invoice-update endpoint. Approval requires box, reviewed tax date,
reason/evidence and explicit input-recovery review. The existing register stamps
reviewer/time; native UAE VAT Settings `track_changes=1` preserves audit versions.
New fingerprints bind recovery proposals, source identity, amounts and evidence;
stale dialogs cannot approve changed sources. Existing valid legacy fingerprints
remain accepted. Amended voucher/row IDs cannot inherit another source's approval.
Concurrent settings saves retain normal timestamp protection; existing records
must be selected instead of appending duplicate decisions. No ignored permissions,
direct SQL updates, manual commits or automatic approvals were added.

The existing return-state validation now uses the final preparation pipeline
instead of the intermediate engine. Unresolved recovery/allocation, scope and
residual problems block approval/filing state changes. No filing integration is
added, and previously filed records are not rewritten.

This explicit approval requirement is an application control, not a claim that
the FTA mandates these custom fields or UI. Statutory eligibility/tax-period
conditions remain subject to accountant evidence under the
[FTA VAT Returns User Guide](https://tax.gov.ae/DataFolder/Files/Pdf/VAT%20Returns%20User%20GuideEnglishV40%2015%2008%202021%20SEP2021.pdf).

### Verified May-July Control Totals

Read-only comparison against standard ERPNext General Ledger, same Company,
VAT 5% - QBC, inclusive 2026-05-01 through 2026-07-31:

| Measure | AED |
| --- | ---: |
| Opening debit / credit | 535.57 / 0.00 |
| Period debit / credit | 37,274.40 / 104,540.10 |
| Period net credit movement | 67,265.70 |
| Closing debit / credit | 0.00 / 66,730.13 |
| Recorded output VAT | 104,378.45 |
| Recorded net input VAT | 37,112.75 |
| Output allocated to boxes | 55,062.68 |
| Output awaiting allocation | 49,315.77 |
| Approved input claim | 0.00 |
| Input awaiting verification | 37,112.75 |
| Confirmed non-recoverable input | 0.00 |
| Source/GL and unexplained bridge residuals | 0.00 |
| Known statutory net subtotal, provisional | 55,062.68 |

All 315 current voucher/account rows match standard GL individually. PI raw debit
36,677.19 less return credits 161.65 yields 36,515.54 net input. Journal VAT adds
597.21 input and 49,315.77 output; SI output remains 55,062.68. Closing balance
includes opening and is not the statutory payable. 67,265.70 is only the conditional
return net if all recorded inputs are approved and output treatment is resolved
without further differences; it is not automatically used as final payable.

The supplied GL workbook also has 315 vouchers and identical control totals, but
seven exported identities are absent from the current scope and seven current
identities are absent from that snapshot:

| Export-only voucher | VAT | Current-only voucher with same amount |
| --- | ---: | --- |
| ACC-SINV-2026-00050-2 | 47.62 output | ACC-SINV-2026-00050 |
| ACC-PINV-2026-00046-1 | 18.10 input | ACC-PINV-2026-00046 |
| ACC-PINV-2026-00072-1 | 148.24 input | ACC-PINV-2026-00072 |
| ACC-PINV-2026-00335-1 | 4.20 input | ACC-PINV-2026-00335 |
| ACC-PINV-2026-00447 | 291.60 input | ACC-PINV-2026-00087 |
| ACC-JV-2026-00004-2 | 28.52 input | ACC-JV-2026-00004-1 |
| ACC-JV-2026-00008-1 | 66.55 input | ACC-JV-2026-00008 |

This is a snapshot identity difference, not established amendment/rename lineage:
equal amounts alone do not prove a relationship. No identities were rewritten or
amounts deduplicated to force agreement. The full difference register is
`/tmp/qatra-vat201-export-voucher-differences.json`.

### Exact Decisions Still Needed

There are 317 review source rows: 295 purchase tax rows, 17 purchase-journal rows,
two advance rows and three untaxed foreign-supplier item rows. No decisions were
approved during implementation.

- Ordinary purchase invoices: 36,515.54 net recorded VAT needs recovery approval,
  including ACC-PINV-2026-00293-1 (base 1,557.50 / VAT 77.88) and
  ACC-PINV-2026-00210-1 (323.00 / 16.15). Saved values remain 0; no claim is granted.
  The Review and Recovery Decisions workbook sheets contain every source ID.
- Expense journals: ACC-JV-2026-00003 359.92; 00004-1 28.52; 00006 23.48;
  00007-1 118.74; 00008 66.55. Generator bases/tax rows reconcile, but recovery
  entitlement for the 17 individual GL sources is not approved.
- Advances ACC-JV-2026-00001 26,532.14 and 00002 22,783.63: authoritative reporting
  Emirate and original advance tax invoice / later-invoice overlap evidence.
  Structured invoice links are not established by the QTI text references.
- ACC-PINV-2026-00344, 00345, 00346: original supply/import and potential
  reverse-charge obligation; a foreign address does not establish treatment.

### Files, Checks and Local Commands

Changed report modules: `automatic.py`, `engine.py`, `reconciliation.py`,
`review.py`, `configuration.py`, `uae_vat_201_return.py`, its JavaScript,
`return_print.html`, `test_automatic.py`, `test_completeness.py`, `test_review.py`,
`test_uae_vat_201_return.js`, and new `test_recorded_bridge.py`, plus this document.
No new schema, fixtures, patches or custom verification fields are required.

125 Python tests and eight Node tests passed, including existing return/journal/
reverse-charge/currency/overlap checks and new pending-versus-approved zero,
full/partial recovery, proposal conflicts, raw signs, opening separation, timing,
duplicate-source, stale-dialog and permission tests. Live native-GL voucher checks,
numeric workbook parity, source/base/GL tracing and five-page PDF generation passed.
Full before/after snapshots of invoices, JVs, GL and classification/settings data
were unchanged. No authenticated browser interaction or production deployment is
claimed; approval persistence is covered using isolated fixtures, not mutation of
real accounting or eligibility decisions.

Local review artifacts: `/tmp/qatra-vat201-recorded-reconciliation.xlsx` and
`/tmp/qatra-vat201-recorded-reconciliation.pdf`. Report files need no asset build
or migration. Reload the browser after `bench --site Qatra.local clear-cache`.
Neither restart nor production deployment is required for local report verification.

## Complete Local Audit: 2026-10-28

This is the current implementation/evidence summary; older dated sections below
are retained as historical notes where they differ. The implementation is complete
as a preparation report, not a completed or submitted tax return. Qatra.local is
available and was checked directly; no production deployment was performed.

### Basis and Source Policy

Official references checked: [FTA VAT Returns Guide (2021)](https://tax.gov.ae/DataFolder/Files/Pdf/VAT%20Returns%20User%20GuideEnglishV40%2015%2008%202021%20SEP2021.pdf)
and [FTA filing guidance](https://tax.gov.ae/en/content/filing.vat.returns.and.making.payments.aspx).
Standard-rated outputs use the Emirate boxes; zero/exempt supplies remain separate;
imports and their corrections use 6/7, reverse-charge recovery uses 10, and ordinary
eligible inputs use 9. Specific adjustments are separate from ordinary credit notes.
12/13 sum the relevant VAT and adjustment amounts; 14 subtracts recoverable inputs
from output liability. Recorded VAT is not itself proof of recovery entitlement.

The software policies are explicitly separate: saved Sales Invoice `vat_emirate`
is accepted without the obsolete custom supply-verification fields; this does not
independently prove the underlying statutory place-of-supply facts. The installed
UAE `recoverable_standard_rated_expenses` is a manual AED Currency amount, not a
percentage/checkbox. Saved zero means no input claim, not incomplete recovery.
Recorded source amounts remain visible; partial and negative return amounts are
preserved. Reverse charge uses its own percentage/GL evidence. Neither custom
recovery fields, Version history nor a custom recovery-update action is required.
No hidden historical field data or database columns were deleted.

### Pipeline and Presentation

The report uses one final `automatic.build()` result for screen, print and Excel.
`engine.py` extracts permission-filtered submitted/active evidence; `journal.py`
matches structured generator bases/taxes/GL, `automatic.py` derives supported
treatments, `reconciliation.py` audits final claims against recorded accounting,
and `completeness.py` propagates only relevant box/component dependencies.
Formatting never changes eligibility or totals. Cancelled/amended originals and
POS records without their own active GL do not duplicate submitted accounting.
Unallocated/mixed taxable-base allocations remain explicit rather than inferred
from VAT divided by a rate. Existing valid reviewed classifications remain usable.

Preparation statuses are Draft, Requires Review and Ready for Review. The screen
has a prominent Company/TRN/period header, grouped actionable review items and a
recorded-versus-claimed ledger table. Native grid row numbers remain enabled.
Transaction tables retain exactly Date, Voucher Number, Party, Taxable Amount,
VAT Amount, VAT Treatment, VAT Box and Remarks. Source amounts are numeric and
right-aligned; dates use the user format, with concise saved-recovery notes.

Excel contains eight sheets: VAT 201 Preparation, Transactions, Review,
Completeness, Reconciliation, Source Ledger Audit, Invoice GL Checks, and Taxpayer
and Notes. Transactions has exactly eight columns, typed dates, numeric AED cells,
voucher hyperlinks, usable widths/filtering and frozen identifiers. Provisional
summary cells have comments/colour, not replacement strings. The PDF has three
preparation pages and an intentional fourth review appendix, visually inspected
after rendering; there is no orphaned continuation of warning text. It is labelled
preparation only, without an FTA submission/approval claim.

### Current Recalculation

Company QATRA BUILDING CONTG LLC; period 2026-05-01 through 2026-07-31:

| Measure | AED | Meaning |
| --- | ---: | --- |
| Box 1f taxable base | 1,101,253.46 | Unchanged known subtotal, provisional allocation |
| Box 1f VAT / Box 12 known due-tax subtotal | 55,062.68 | Unchanged; not all unallocated outputs included |
| Box 13 known recoverable input claim | 0.00 | Provisional, not an assumption of zero journal entitlement |
| Box 14 known net subtotal | 55,062.68 | Provisional, not final payable VAT |
| All adjustment components | 0.00 | No actual unresolved adjustment source |
| Recorded output VAT in GL | 104,378.45 | Includes the correctly positive advance credits |
| Output VAT awaiting allocation | 49,315.77 | Two advances, excluded from official box subtotals |
| Recorded input VAT in GL | 37,112.75 | Invoice VAT plus matched petty-cash VAT |
| Recorded invoice VAT excluded by saved zero recovery | 36,515.54 | Legitimate saved-data claim convention, not missing source VAT |
| Journal VAT with unresolved recovery | 597.21 | No automatic recovery grant |
| Raw VAT-control debit minus credit | -67,265.70 | Accounting sign, not payable/refundable VAT |

The prior Box 1f result is unchanged. Reconciliation changed because it now uses
the final resolved VAT roles, not intermediate classification: output ledger VAT
includes 49,315.77 of advances and input ledger VAT includes 597.21 of petty-cash
tax. No journal tax posting remains role-unallocated in this inspected scope, but
return allocation/entitlement remains unresolved. The 315 voucher/account audit
records and 308 invoice/account checks all have source-to-GL difference zero.
The register separately retains source/base/GL row IDs, posting/tax dates,
recorded/claimed VAT, known exclusions, overlap warnings and raw accounting signs.

### Exact Accounts Review Items

The current review count is **22 source rows**, not a hardcoded 19:

- 17 journal input-VAT rows across ACC-JV-2026-00003, 00004-1, 00006, 00007-1 and
  00008: original petty-cash tax evidence and eligible recovery remain required.
- ACC-JV-2026-00001 and 00002: authoritative transaction/linked-document Emirate
  and original advance-tax-invoice/adjustment overlap evidence are still required.
  Their positive base/VAT amounts remain visible; QTI cheque text is not a link.
- ACC-PINV-2026-00344, 00345 and 00346: linked supplier addresses are in India,
  with no recorded VAT or established reverse-charge treatment. Review original
  supplies and any import/customs evidence. These are potential obligation issues,
  not missing recovery decisions; no reverse-charge tax or recovery is fabricated.

1a-1g and 8/12/14 remain provisional for output allocation. 9/11/13/14 remain
provisional for journal recovery. The foreign untaxed purchases additionally affect
possible 3/6/10 and their dependent totals. 2/4/5/7 remain complete numeric zeros
for the inspected scope; adjustments remain complete zero independently. Signatory
and Arabic legal-name fields remain unprovided, printed as Not Configured.

### Maintained Filing Calendar

The saved first period remains May-July, cycle quarter 2, due **2026-08-31**.
The nominal 28-day date is August 28. [FAHR Circular 11/2026](https://www.fahr.gov.ae/wp-content/uploads/2026/08/Circular-No.-11-of-2026-Regarding-The-Holiday-of-the-Prophet-Mohammads-Birthday-1448-AH.pdf)
confirms that day as a federal holiday; the [official federal workweek](https://u.ae/en/information-and-services/jobs/working-in-uae-government-sector/working-hours-in-the-public-sector)
has Saturday/Sunday weekends. Applying the FTA next-business-day rule gives August
31. This evidenced interval is maintained in `filing_calendar_evidence.json`, not
guessed from lunar dates or transaction posting dates. The initial nominal-date
mismatch warning was resolved by checking this evidence. Other unsupported date
exceptions/provisional future dates still require calendar confirmation. Frequency,
cycle/quarter, registration boundary and overlapping period checks are read-only.
No Company/UAE VAT Settings/filing-period records were changed.

### Verification and Limits

113 Python tests and eight JavaScript tests cover the calculation/recovery/sign,
scope, grouping, duplication, return, currency/precision, calendar, completeness,
permissions and export paths. Native report execution, both requested saved-zero
invoices, both advances, petty-cash source pairs, real empty January, all numeric
screen/XLSX components and four-page PDF rendering passed. Exotic/reversal/partial
cases use isolated fixtures, not fabricated accounting documents. Full source,
accounting, Company/settings and classification snapshots were unchanged. Browser
Desk visual interaction was not authenticated/tested; print visuals were inspected.
No core edit, migrate, bulk source update or FTA submission was performed.

## Box/Component Completeness: 2026-10-27

This supersedes earlier summary/export notes that replace known numbers with
Pending Verification. The root cause was global preliminary status being reused
by the grid, summary cards, XLSX and print formatter to mask zeros/net totals;
every unresolved journal was also treated as an unresolved adjustment.

`completeness.py` now tracks source dependencies separately for Amount, VAT Amount
and Adjustment. Known box/card values remain numeric even when provisional.
Screen warnings and cell tooltips explain the affected components; XLSX has the
same numeric box totals plus a separate Box Component Completeness register and
the same summary cards. PDF/print uses the same numeric values with a provisional
marker. The eight transaction-detail columns and accounting calculations remain
unchanged. Unknown source bases remain unknown; an empty known subtotal marked
provisional is never an assertion of confirmed no activity or zero entitlement.

For the first configured period, 2026-05-01 through 2026-07-31:

| Box / component | Known subtotal | Completeness / reason |
| --- | --- | --- |
| 1f Amount / VAT | AED 1,101,253.46 / 55,062.68 | Provisional: two advances still lack Emirate allocation |
| Other 1a-1g Amount / VAT | AED 0.00 | Provisional: either advance could belong to that Emirate |
| 8 Amount / VAT | AED 1,101,253.46 / 55,062.68 | Provisional: depends on output allocations |
| 9 / 11 Amount and VAT | AED 0.00 / 0.00 | Provisional: 17 matched journal purchase-VAT rows lack recovery entitlement |
| 12 Amount | AED 55,062.68 | Provisional: depends on output VAT plus output adjustments |
| 13 Amount | AED 0.00 | Provisional: depends on eligible input VAT plus input adjustments |
| 14 Amount | AED 55,062.68 | Provisional known net subtotal, not final liability |
| 2, 3, 4, 5, 6, 7, 10 | AED 0.00 | Complete no-activity components for this inspected scope |
| All Adjustment components | AED 0.00 | Complete: no actual unresolved adjustment source |

The two advances remain separately identified in details and warnings: taxable
AED 986,315.40 and positive output VAT AED 49,315.77, excluded from official box
subtotals until allocation/overlap evidence supports inclusion. The 17 purchase
journal rows retain recorded VAT AED 597.21 and their matched source bases; none
is silently granted full recovery or treated as a confirmed zero decision.
Actual missing Emirate and recovery evidence is still required. No company,
Customer address or remarks assign an Emirate, and no source is counted twice.

Confirmed Purchase Invoice zero recovery remains zero with no source warning,
blank VAT Box and visible source base/VAT. Reconciliation separately explains AED
36,515.54 of first-period recorded invoice VAT excluded by saved zero recovery;
it does not force claims to match the ledger or mark unrelated boxes incomplete.
Needs Attention exports use positive output-role VAT for normal advance credits
and expose the original negative debit-minus-credit GL movement separately.
Reversal signs remain negative rather than using absolute values.

Dependencies propagate through 8/11 component sums, 12/13 VAT-plus-adjustment sums,
and 14's output-minus-input total. Only an actual unresolved adjustment affects
Adjustment components. Genuinely unclassified tax postings retain their possible
category scope; inaccessible/unconfigured source scope cannot claim confirmed
no activity. Filing/header warnings and ledger differences are not themselves a
reason to mask numeric box figures.

Verification: 102 Python and seven JavaScript tests; native report execution;
numeric screen/XLSX component agreement; print-template rendering; real empty
January with complete numeric zeros; saved-zero invoices; all 19 unresolved rows;
partial recovery, returns, reverse charge and currency fixtures; and all 308
invoice/account GL checks. Source/accounting/classification snapshots remain
unchanged. No core edit, business-document update, new mandatory verification
field or migrate was performed. Browser visual testing is not claimed.

## Customer-Advance Output VAT: 2026-10-27

The journal resolver now distinguishes customer advances from petty-cash input VAT.
The prior resolver only recognized expense accounts and otherwise left both base
and VAT using debit-minus-credit signs, making normal advance credits appear
negative and leaving their purpose unresolved.

A matched configured company customer-advance account, saved Customer party,
generator rate/tax rows and the same customer's balancing gross receivable establish
the advance pattern. Neither an income account nor `is_advance = Yes` is required.
The installed configuration maps both `default_customer_advance_account` and
`default_advance_received_account` to Customer Advances - QBC. Existing generation,
currency, project/cost-center, precision and unique-row reconciliation are reused.

Output base and recorded VAT use credit-minus-debit: ordinary output credits are
positive, while debit reversals are negative. Input VAT retains debit-minus-credit
signs. Accounting debit/credit and raw tax evidence are retained unchanged; no
absolute-value conversion is applied to reporting signs. Role-incompatible input/
output classifications are rejected. Gross receivables only validate the pattern;
they never replace the source advance base.

Read-only Qatra results (also verified in the eight-column workbook):

| Journal | Taxable base AED | Recorded output VAT AED |
| --- | ---: | ---: |
| ACC-JV-2026-00002 | +455,672.60 | +22,783.63 |
| ACC-JV-2026-00001 | +530,642.80 | +26,532.14 |
| Total | +986,315.40 | +49,315.77 |

Both have the precise remaining issue: reporting VAT Emirate is missing or invalid
on the transaction or an authoritative linked document. No Journal Entry Emirate
field exists locally, and neither journal has a verified submitted Sales Invoice
or later-adjustment link. Company/Customer addresses, project names and QTI cheque
text are not used as Emirate or invoice-link authority. The actual base/VAT and
Customer remain visible; VAT Box stays blank until the required source evidence
exists. These amounts are not silently added to Emirate box totals.

Duplicate checks follow structured journal-to-invoice references, submitted Sales
Invoice Advance allocations back to the journal, and submitted journal references
for later adjustments, with parent permissions and company/submission scope.
Linked cases require explicit VAT-overlap reconciliation before automatic inclusion;
no equality-of-amount, remarks or cheque-number matching claims to prove a link.
No links found in permitted records does not prove that an external advance tax
invoice is absent. Existing verified control-only treatments remain separate;
ordinary VAT credits without the advance pattern are not classified as advances.

88 Python and seven JavaScript tests passed. Both journals and the petty-cash
example were verified read-only; output reversal and VAT settlement use isolated
fixtures, not created business documents. Tests also cover output box/reversal
totals and linked duplicate safeguards. All 308 invoice/GL comparisons and full
source/accounting/classification snapshots remain unchanged. The eight columns
are unchanged. No new field, journal/GL update, core edit or migrate was performed.

## Saved Journal VAT Rows: 2026-10-27

The generator belongs to `qatra_custom/journal_entry.py` and its Journal Entry
client script. It calculates VAT from each configured base row, splits inclusive
amounts using saved gross/last-net state, and appends a marked tax row on the same
side with the same project/cost center. The installed generator saves no direct
base-row link and no recovery decision. Neither generator was changed.

The old report used a generated-remark suffix plus exact amount matching to infer
one base. It ignored project/cost-center identity and inclusive/currency state,
and only stored the inference in `derived_base`; the visible canonical `base`
remained unknown. The report now reconciles saved configured bases, generated tax
rows and active GL in separate allocation stages. Explicit base/GL row links are
preferred where present; otherwise account, project, cost center, sign, saved rate
and amounts must establish a unique exhaustive allocation. Remarks are not a key.
Grouped tax rows/merged GL are supported when uniquely reconcilable. A saved base
or generated tax row cannot be consumed twice. Ambiguous/oversized allocations
remain explicit issues rather than guessed matches. VAT-to-GL totals must match
exactly; generator rounding allows one company-currency minor unit per generated
tax target, preserving saved VAT such as 46.82 rather than recalculating it.

Source taxable base is the signed saved expense amount, never the journal header
total or VAT divided by a rate. Inclusive rows require the saved split state;
foreign-account rows require saved exchange rates and reconciliation with company
amounts. An inconsistent historical currency split is flagged, not repaired.
No current exchange rate or current Account tax rate replaces historical inputs.
No Supplier is required: Party remains blank without a saved party.

Read-only `ACC-JV-2026-00007-1` verification:

| Base row | Generated tax row | Taxable AED | Recorded VAT AED |
| --- | --- | ---: | ---: |
| 7s7i3iiaq2 | 3s9aj8uo4r | 1,042.37 | 52.12 |
| 7s7i3ba3vm | 3s9adk0pvt | 96.00 | 4.80 |
| 7s7i1dke2r | 3s9a6ebt00 | 936.50 | 46.82 |
| 7s7iemk8cj | 3s9ae7c389 | 300.00 | 15.00 |
| Total | Four unique active GL rows | 2,374.87 | 118.74 |

These are recorded purchase-VAT amounts, not automatic input claims. Account root
type establishes expense evidence, but shared VAT account mapping Both does not
establish entitlement. No installed journal recovery field or approved decision
establishes eligibility for these four pairs. Their VAT Box remains blank and the
only specific remaining issue is recovery entitlement; the taxable base no longer
shows Pending Verification. Existing valid reviewed recovery percentages continue
to use the normal calculation engine, including partial/zero recovery and signs.
Invoice-referenced journals cannot generate duplicate expense input claims;
unconfigured VAT settlements/transfers do not become purchases from debit direction.
Saved control-only classifications retain their existing separate treatment.

The eight visible detail/export columns are unchanged. The recoverable-input
summary is pending when identified journal purchase VAT has unresolved eligibility;
the included Box 9/Box 13 subtotal is still zero, not an assertion of zero journal
entitlement. Recorded invoice totals and all 308 invoice/GL checks remain unchanged.
81 Python and seven JavaScript tests passed, including explicit links, ambiguity,
grouping, rounding, inclusive/credit/foreign amounts, transfers, invoice duplication,
existing reviewed recovery and eight-column Excel values. Full source/accounting/
classification snapshots were unchanged. No journal, GL, recovery decision, core
file or generator was edited; no migrate ran. Browser visual testing is unverified.

## Final Saved-Data Purchase Behaviour: 2026-10-27

This is the current behaviour. All earlier dated implementation notes below are
historical where they conflict with this section.

The installed UAE field `recoverable_standard_rated_expenses` is a saved **AED
Currency amount**, not a percentage or checkbox. The report reads that amount:
zero means zero recovery, signed nonzero/partial amounts retain their eligible
claim, and recorded VAT does not automatically grant recovery. No explicit-zero
decision, audit comment, Version history or custom recovery field is required.
Missing/invalid values and genuine tax/GL discrepancies retain their safeguards.
Reverse charge retains its separate saved percentage and output/input treatment.

The custom **Update VAT Recovery** script, server endpoint, submit-update hook,
metadata setup and associated action tests have been removed. The report has no
invoice-writing action. Historical custom fields, saved values and audit comments
are not deleted; no invoice data or existing metadata was updated during this fix.
Legacy custom recovery controls remain hidden without being used in calculations.

Exactly eight detail/export columns remain: Date, Voucher Number, Party,
Taxable Amount, VAT Amount, VAT Treatment, VAT Box, Remarks. Source taxable base
and recorded VAT remain visible in AED irrespective of recovery. A saved-zero
purchase is labelled **No input VAT claimed**, has a blank VAT Box and contributes
no event to Box 9 or its drilldown. Remarks states the saved zero recovery basis;
there is no incomplete/unconfirmed recovery warning.

Read-only local verification:

| Invoice | Taxable AED | Recorded VAT AED | Saved recovery / claim AED | VAT Box |
| --- | ---: | ---: | ---: | --- |
| ACC-PINV-2026-00293-1 | 1,557.50 | 77.88 | 0.00 / 0.00 | Blank |
| ACC-PINV-2026-00210-1 | 323.00 | 16.15 | 0.00 / 0.00 | Blank |

For 2026-05-01 through 2026-07-31, recorded sales VAT remains AED 55,062.68 and
recorded purchase VAT AED 36,515.54. Saved eligible Box 9 base/VAT and Box 13 are
zero. At that stage the Recoverable Purchase VAT card was numeric zero; the newer
journal section above supersedes this when journal recovery is unresolved. All 308
invoice/account VAT-to-GL checks match. The 19 unresolved journal source rows
still make adjustments and final liability pending; no final nil liability is
asserted. Source/accounting snapshots are unchanged. Seventy-one Python tests and
seven JavaScript tests passed, covering zero/partial/full recovery, returns,
reverse charge, source columns, claims and eight-column Excel output. No migrate,
core edit, invoice cancellation/amendment or business-data update was performed.
Authenticated browser visual verification was not performed.

## Historical Implementation Notes

## Simplified Purchase Details and Recovery: 2026-10-27

This section supersedes the earlier extra-column layout and acceptance of every
saved zero as confirmed non-recoverable VAT. Installed UAE metadata defines
`recoverable_standard_rated_expenses` as a manual **Currency amount in AED**,
default zero, not a percentage or checkbox. No installed controller or regional
hook automatically populates it. The native VAT report sums the maintained amount;
its tests explicitly assign recovery, including for foreign-currency invoices.
Reverse charge uses the separate `recoverable_reverse_charge` percentage.

The custom report reuses those fields and semantics, retaining permission-aware
source reads, saved after-discount/base-currency amounts, signed returns and
separate reverse-charge output/input evidence. It does not reuse native aggregate
queries blindly: their positive-amount predicate excludes negative return claims.
No custom recovery verification/percentage or Version-history gate is used.

Transaction Details and its Excel section now have exactly eight columns:
Date, Voucher Number, Party, Taxable Amount, VAT Amount, VAT Treatment, VAT Box,
Remarks. The two monetary columns show actual source amounts in AED; claims stay
internal to official box totals. Remarks explains eligible recovery or missing
configuration. Duplicate recovery/return amount columns have been removed.

Populated partial/full recovery amounts are used within the recorded VAT bounds.
Historical default zeros cannot establish whether eligibility was assessed: they
are flagged incomplete, not silently claimed or treated as confirmed zero.
Existing valid reviewed allocations remain supported. An intentional zero can be
recorded through the existing manager-only **Update VAT Recovery** action, which
stores the reason and a structured decision in its audit comment for the current
invoice revision. No new eligibility field is introduced. Only permitted source
invoices' zero decisions are bulk-read; changed invoices need renewed decisions.
The action retains normal accounting validation. Report execution never saves
invoices, changes recovery amounts or creates decisions.

Read-only verification: `ACC-PINV-2026-00293-1` retains taxable AED 1,557.50 and VAT
77.88; `ACC-PINV-2026-00210-1` retains taxable AED 323.00 and VAT 16.15. Both retain
saved recovery zero, with incomplete-configuration warnings. If an accountant
confirms full eligibility, an authorised manager must save **77.88** / **16.15** in
the existing AED field using Update VAT Recovery with a reason. Partial eligibility
requires the eligible AED amount; intentional zero requires a documented decision.
No such invoice correction or blanket recovery grant was made during this fix.

First-period source VAT remains output AED 55,062.68 and purchase AED 36,515.54.
All 308 invoice/account GL checks reconcile at currency precision. Recovery and
final liability remain pending, not nil, while evidence is unresolved. Tests cover
full, partial, explicit zero, default/unconfigured zero, no VAT, signed returns,
reverse-charge zero/partial/full, eight-column exports and JavaScript rendering.
Verification passed: 79 Python tests, seven JavaScript tests, eight-column Excel
checks, both live examples and unchanged source/accounting snapshots. The local
site cache was cleared; no build or restart was needed for these report files.
No authenticated browser visual verification is claimed. No core edits, migration,
cancellation, amendment or accounting-data changes were made.

## Source Amounts Versus Recovery Claims: 2026-10-27

Transaction Details, box drilldowns and Excel/CSV now distinguish source amounts
from return claims. The former display selected event `amount` and `vat_amount`,
which are return contributions, under generic taxable/VAT headings. Zero recovery
correctly reduced the claim to zero, but misleadingly appeared to erase the
invoice's taxable base and recorded VAT. The source reader still retained those
values in `base` and `raw_vat`; the accounting data was never zeroed.

Events now also expose independent numeric `invoice_taxable_amount` and
`recorded_vat_amount`, before applying any recovery factor, plus a separate
`recoverable_vat_amount`. AED conversion follows the existing saved-rate path,
not the recovery percentage. Missing source-base allocations stay unknown rather
than borrowing a reviewed claim allocation. Existing `amount`, `vat_amount` and
`adjustment` still drive official box totals unchanged.

The detail table labels Taxable Amount, Recorded VAT, Recoverable VAT, VAT Return
Taxable Amount, VAT Return VAT and VAT Return Adjustment separately. The same
separation appears in preparation exports, with numeric amounts and an explicit
Recovery Basis. Purchase treatment states the saved Recoverable Standard Rated
Expenses (AED) amount and whether recovery is zero, partial or full; the generic
"Automatic source evidence" wording is no longer used for calculated events.

Read-only Qatra.local verification with saved recovery zero:

| Invoice | Source Taxable (AED) | Recorded VAT (AED) | Recoverable VAT (AED) | Box 9 Claim Base/VAT |
| --- | ---: | ---: | ---: | --- |
| ACC-PINV-2026-00293-1 | 1,557.50 | 77.88 | 0.00 | 0.00 / 0.00 |
| ACC-PINV-2026-00210-1 | 323.00 | 16.15 | 0.00 | 0.00 / 0.00 |

First-period recorded Sales VAT remains 55,062.68; recorded Purchase VAT remains
36,515.54. Box 9 and Box 13 recoverable claims remain zero. The Recoverable Purchase
VAT summary card is zero, while adjustments and final net liability remain Pending
Verification because journal issues are unresolved. No final payable amount is
asserted. All 308 invoice tax/GL checks match. Both examples passed normal report,
context/drilldown and workbook checks. 75 Python tests and seven report JavaScript
tests passed, covering zero/partial/full recovery, returns, independent source
columns, unchanged claims and export values. Full accounting/source/history hashes
were unchanged; no invoice, GL or recovery value was edited and no migrate ran.

## Saved Zero and Audited Updates: 2026-10-27

This section supersedes the source-history zero gate described below. The existing
`recoverable_standard_rated_expenses` is an AED Currency amount: the installed field
metadata says Currency/default 0, the UAE controller disallows a nonzero standard
recovery amount for reverse-charge purchases, and the standard UAE VAT report sums
this field as recoverable VAT. It is neither a percentage nor a checkbox.

The report now reads its saved value directly. Zero means zero recovery, partial
amounts remain partial, and missing/null amounts still raise a missing-value issue.
No Version/source-history query or custom recovery verification/percentage is a
prerequisite. Recorded VAT does not grant recovery. Reverse-charge recovery uses
its separate saved standard percentage, retaining existing GL matching safeguards.

Submitted Purchase Invoices expose Actions > Update VAT Recovery to Accounts
Managers/System Managers with document write permission. Enter an AED amount and
a mandatory reason. A supported Property Setter enables allow-on-submit solely
for the existing recovery field; no database column or core file is changed.
The server checks role/document permissions, submitted status, fresh timestamp,
currency precision, VAT sign/limit, AED Company and non-reverse-charge treatment.
It validates a detached candidate with the full invoice controller/hooks and
rejects any recalculated posting amounts. This avoids persisting historical
display-flag recalculations. The actual document then uses normal doc.save with
update-after-submit checks and Version enabled, plus a reason comment. No ignored
permission, validation, version or update-after-submit flags are used.

Verified on paid ACC-PINV-2026-00293-1: saved recovery remains 0.00, report recovery
is 0.00 without the unconfirmed-zero warning, and recorded VAT remains 77.88.
The actual save/audit/report path was tested at 77.88, 20 and 0 within a database
savepoint; all changes and test audit records were rolled back. Full recovery gave
Box 9 base 1,557.50 and VAT 77.88; partial recovery gave 20.00. GL, paid status,
outstanding balance and final accounting/history snapshots were unchanged. Saving
77.88 permanently requires an authorised user's confirmation; none was inferred
from this request. No cancellation, amendment, bulk grant or migrate was performed.

## Standard Purchase Recovery Amount: 2026-10-27

The live Purchase Invoice field `recoverable_standard_rated_expenses` is Currency,
labelled Recoverable Standard Rated Expenses (AED), with default zero. ERPNext's
standard UAE report sums this field as recoverable VAT, not as a checkbox,
percentage or expense base. The custom report now uses that saved AED amount
directly for ordinary Box 9 recovery; it never infers full recovery from recorded
VAT. Full recovery of AED 77.88 requires a saved recoverable amount of 77.88;
values 20 and 1 mean AED 20 and AED 1 respectively. Return amounts retain their
signs, and invalid/excessive amounts or unresolved multiple-row allocations are
not automatically claimed.

The custom verification checkbox and custom recovery percentage are no longer
created, queried or required by the report. Existing redundant controls are hidden
without deleting their definitions, columns or historical values. Purchase recovery
uses no new mandatory verification field.

Blank/null recovery is reported as missing. A saved zero alone is ambiguous because
the standard field defaults to zero. A matching latest change from a nonzero amount
to zero in the invoice's existing Version history establishes explicit zero recovery;
that source produces zero recoverable VAT, not an unconfirmed-recovery warning.
Default zero without that source evidence remains unconfirmed. Creation-time intent
cannot be reconstructed where neither a field change nor valid retained reviewed
evidence exists. Audit reads are bulk-scoped to already permitted submitted invoices;
no history or eligibility is fabricated. Reverse-charge purchases continue to use
the separate standard recoverable_reverse_charge percentage and matching input/output
GL evidence; default 100% still requires source evidence rather than VAT alone.

Verified actual submitted invoice ACC-PINV-2026-00293-1: taxable amount AED 1,557.50,
recorded VAT AED 77.88, saved recoverable amount 0.00 with no explicit-zero source
change. Its eligibility was not altered. Replacing only its source amount in memory
with 77.88 produced Box 9 taxable amount 1,557.50 and recoverable VAT 77.88, without
the custom verification warning; partial amounts 20 and 1 also passed through normal
report generation. All 308 first-period invoice tax/GL checks still match. Accounting
documents, GL and classification history were hashed before/after and remained
unchanged. No invoice cancellation/amendment, bulk eligibility update, core edit or
migrate was performed. Earlier implementation sections below are historical where
they describe the superseded custom recovery controls.

## Saved Sales VAT Emirate: 2026-10-27

For standard-rated sales, the report now uses saved Sales Invoice `vat_emirate`
as its sole Emirate source, including returns and retained standard-rated history.
Every valid UAE Emirate maps to its corresponding Box 1a-1g regardless of whether
the value was fetched from the company address. No supply-verification checkbox
or separate verified-supply Emirate is required or queried. Missing/invalid values
produce "VAT Emirate is missing or invalid" only when Emirate classification is
required; explicit zero/exempt treatments remain independent of that field.

The two obsolete controls are hidden through an idempotent metadata-only helper.
Setup no longer creates them. Their field definitions, columns and historical data
are retained. No migrate, invoice amendment/cancellation or accounting update was
performed. Purchase recovery, journal review, saved tax amounts, currency handling,
return signs and submitted-document filtering remain unchanged.

Local verification: all 13 first-period sales now contribute Output VAT AED
55,062.68, matching GL with difference 0.00. All 308 invoice-to-GL checks still
match. Remaining issues concern 295 purchase tax rows and 19 journal GL rows, not
sales Emirate verification. The return remains preliminary for those other issues.
The requested `ACC-SINV-2026-00050-2` is absent locally; its supplied values are
covered by an isolated test. Actual submitted invoice `ACC-SINV-2026-00050` has
Ras Al Khaimah, taxable amount AED 952.38 and VAT AED 47.62, and reports in Box 1f.
The sections below retain earlier implementation and investigation history.

## Simple Report History: 2026-10-21

The report now uses automatic source evidence rather than a classification user
workflow. This section supersedes the review-screen instructions retained below.
Select Company and Filing Period, then Refresh. The only other visible filters
are From Date and To Date; changing dates clears the maintained-period selection.

Four summary cards show recorded Sales VAT, recoverable Purchase VAT, VAT
Adjustments and net VAT. Official boxes use five visible columns. Transaction
Details has Sales, Purchases, Journal Entries and Needs Attention tabs, with
voucher links and source-specific recommended actions. No review, suggestion,
approval, rejection or classification-status controls remain in the report.

`automatic.py` reads submitted source rows through the existing permission-aware
reader and calculates eligible events in memory. No classification record or
approval is generated. Useful valid historical verified decisions remain usable;
all 354 existing child records and their audit data are retained unchanged.

Ordinary invoice calculation uses saved signed VAT, saved taxable bases and the
mapped VAT account. A supported transaction-specific sales Emirate or explicit
zero/exempt item flag establishes the output box. For purchases, the standard
nonzero recoverable VAT amount or documented source verification establishes
recovery; default zero is not treated as either full recovery or proven exclusion.
Documented reverse-charge recovery additionally requires saved matching input
and output GL evidence. No rate-based invention of tax or taxable bases is used.
Unresolved journal purpose, tax differences, missing supply/recovery evidence and
unsupported treatments remain Needs Attention. Journal debit/credit direction
alone never determines the VAT treatment.

Optional app-owned source fields record verified supply Emirate/evidence on Sales
Invoice and documented recovery percentage/evidence on Purchase Invoice. These
are not automatically populated, have no allow-on-submit override, and do not
modify any historical submitted source. Use normal source-document correction
procedures where necessary. No per-invoice classification approval is required.

Local first-period recalculation: recorded Sales VAT AED 55,062.68, recorded
Purchase VAT AED 36,515.54, unallocated journal debit-minus-credit AED -48,718.56.
All 308 VAT-bearing invoice vouchers match GL individually. Details contain 354
source rows; 327 need attention (13 sales, 295 VAT purchase rows, 19 journal rows).
The other 27 purchase item rows have no recorded VAT and generate no input claim.
These are source-row counts, not unique invoice counts. Qatra's saved sales
Emirate is company-address-derived, purchase recovery is default zero, and journal
evidence is unresolved. Consequently net liability and recovery remain Pending
Verification, not a nil return. The four configured filing periods, confirmed first
due date and subsequent provisional due dates are preserved.

Excel/CSV contain transaction details, Needs Attention and reconciliation. The
three-A4-page PDF and report show PRELIMINARY - VERIFICATION REQUIRED when
unresolved issues exist. No FTA filing is performed. See the latest verification
section in [Local Completion Report](UAE_VAT_201_LOCAL_COMPLETION.md).

Latest local implementation and evidence workflow: [Local Completion Report](UAE_VAT_201_LOCAL_COMPLETION.md).
It supersedes the earlier pending-work/configuration limitations below, documents
the actual remaining accounting evidence gaps, provisional future due dates,
audited review/status actions, runtime verification and future deployment commands.

## Confirmed Configuration Update: 2026-10-21

Qatra.local now has UAE VAT Settings for QATRA BUILDING CONTG LLC. The user-confirmed
TRN 105452509000003 is stored in standard Company.tax_id. The Company name/ID,
addresses, submitted invoices and GL entries were not renamed or rewritten.
Three missing settings fields were added by the existing app setup hook:
custom_vat201_legal_name_english (QATRA BUILDING CONTG LLC OPC),
custom_vat201_registration_date (2026-05-01), and
custom_vat201_registered_emirate (Ras Al Khaimah). Existing filing-period fields
continue to store frequency, stagger and Profit Margin Scheme; no duplicate
TRN/frequency/scheme fields or VAT accounts were created.

One existing VAT 5% - QBC account is mapped as Both. Legacy separate Input/Output
rows for the same account are merged in memory to Both; they do not duplicate
ledger scans or tax events. Invoice document type establishes the side; returns
retain their saved signs. Journals/payments need approved source-GL classifications,
not a debit/credit guess. Reverse charge retains its specific document treatment.

Configured quarterly calendar, February-January cycle:

| Start | End | Cycle Quarter | Due Date |
| --- | --- | --- | --- |
| 2026-05-01 | 2026-07-31 | 2 | 2026-08-31 (user confirmed) |
| 2026-08-01 | 2026-10-31 | 3 | Not yet confirmed |
| 2026-11-01 | 2027-01-31 | 4 | Not yet confirmed |
| 2027-02-01 | 2027-04-30 | 1 | Not yet confirmed |

All four records have Profit Margin Scheme No. Quarter number denotes the cycle,
not the sequence since registration: the first registered return is cycle Q2.
No February-April 2026 return was created before registration. Later due dates
were not guessed from calendar/holiday assumptions. Future periods can be added
using the same existing table. No submission or finalized status was asserted.

Opening the report without explicit dates selects the first configured return;
explicit custom/quarterly selections remain authoritative. Dates/quarter/TRN/stagger
are synchronized with refresh suppressed, avoiding cascading requests. The first
return header includes registration details and Quarterly frequency; Excel/PDF
use the same registered legal name and maintained period details.

### Actual First-Period Reconciliation

Read-only runtime verification for 2026-05-01 through 2026-07-31:

| Evidence | AED | Result |
| --- | ---: | --- |
| Sales invoice VAT / Output GL | 55,062.68 | Invoice tax rows match GL |
| Purchase invoice VAT / Input GL | 36,515.54 | Invoice tax rows match GL |
| Unallocated journal debit minus credit | -48,718.56 | Not approved as Input/Output |

All 308 VAT-bearing invoice vouchers (13 sales, 295 purchases) reconcile individually
at currency precision. Seven actual purchase credit notes across the available
data were checked against GL with their negative signs. Sales-credit-note behavior
is covered by isolated fixtures; no submitted sales return was found in this period.
Duplicate Input/Output mappings were tested in memory and did not change totals,
source counts or reconciliation. Standard report execution and workbook generation
passed, as did 25 Python and four JavaScript tests.

The live return remains **Needs Review**, with 354 candidate rows (13 sales,
322 purchase tax/item rows, 19 journal GL rows). No classifications were auto-created
or approved. Classified boxes therefore remain zero with explicit nonzero ledger
differences; this is NOT a nil return or a reconciled final VAT liability.

The original Not Configured fields resulted from absent UAE VAT Settings and a
blank Company.tax_id. October's default date selection also had no submitted VAT
transactions: sales VAT ends in July and purchase VAT postings end in September.
Selecting the confirmed first return now exposes its actual evidence and warnings.

Box 1a is the unchanged official Abu Dhabi row, not an existing saved approved
classification (there were none). All 13 first-period sales invoices store
vat_emirate = Ras Al Khaimah. That does not by itself prove the applicable Emirate
for each supply; no company-address rule or automatic migration to Box 1f was added.
An accountant must confirm the closely connected establishment/place-of-supply
basis and the appropriate Emirate with supporting evidence.

Journal ACC-JV-2026-00001 references QTI/0001 and ACC-JV-2026-00002 references
QTI0002/advance payment for Villa 167. Their combined VAT credits are 49,315.77;
remaining first-period journal VAT debits are 597.21. These are evidence leads,
not approved return amounts. Review original advance tax invoices, avoid overlap
with subsequent invoicing, and establish petty-cash VAT recoverability/taxable-base
allocations before approving source GL rows. Signatory details, Arabic legal name,
future due dates and supporting accounting classifications remain unprovided.

The investigation below describes the earlier, unconfigured baseline and is
retained as historical context; the configuration above supersedes its readiness
statements. This update does not perform FTA submission.

## Investigation Before Implementation

Environment inspected: Qatra.local; Frappe 16.31.0, ERPNext 16.32.1.
Installed apps: frappe, erpnext, hrms, print_designer, construction_management,
qatra_custom. No additional VAT localization app is installed on this site.

ERPNext already supplies UAE VAT 201, UAE VAT Settings, UAE VAT Account,
Sales Invoice.vat_emirate, item zero-rated/exempt flags, purchase reverse-charge
and recovery fields. Its standard report is reused as a reference for Emirate
ordering, not as the calculation engine: it lacks the complete box structure,
adjustments, explicit tax-point review, and a complete reconciliation. Some of
its returned financial values are formatted strings.

Qatra is UAE-based with AED base currency. Company.tax_id is empty. UAE VAT
Settings and its account mappings are empty. Sales and Purchase templates exist
for VAT 5%, Zero, Exempt and Excise; Tax Category VAT 5% exists; no Tax Rules
exist. Account names and rates are not sufficient classification evidence.

Submitted invoice tax rows include actual retention/advance deductions, which
must not be mistaken for VAT. Sales VAT uses On Net Total and On Previous Row
Total. Purchase tax rows also include retention deductions. VAT 5% - QBC is
shared by sales/purchases. Existing VAT-account postings: Sales Invoice output
55,062.68; Purchase Invoice input 98,346.18; Journal Entry signed debit-minus-credit
-48,182.99. These are diagnostic ledger totals, not an approved VAT return.

No explicit filing calendar, legal tax-point review, recoverability approvals,
or import/customs classification was found. Existing Sales Invoice.vat_emirate
values cannot alone establish that the legally applicable place of supply was
reviewed. Journal Entry Account has custom VAT fields but no VAT 201 box or
approved adjustment evidence. Payment Entries are not automatically VAT events.

The client PDF `/home/ts/Downloads/VAT 201 Return.pdf` was inspected as text and
rendered pages. It has three pages. Box labels and page grouping are used as the
layout reference; its dates, stagger, zero amounts and identifiers are not data.
The PDF's sample due date is not used as a filing-deadline rule.

Official cross-check: [FTA VAT Returns User Guide](https://tax.gov.ae/-/media/Files/EN/PDF/Guides/VAT-Returns-User-Guide.pdf).
Boxes 12 and 13 include the tax and adjustment totals in outputs/inputs;
Box 14 is due tax less recoverable tax. No deadline is guessed.

## Report and Data Sources

Route: `query-report/UAE VAT 201 Return`, module Construction Management.
This is a new Script Report; Project Profitability is unchanged.

Submitted, uncancelled GL entries establish accounting evidence and ledger
reconciliation. Submitted Sales Invoice, Purchase Invoice and POS Invoice tax
rows supply actual posted tax details. Invoice items support zero-rated/exempt
and otherwise untaxed source review. POS records without their own GL postings
are excluded to avoid counting them together with consolidated Sales Invoices.
Journal Entry and Payment Entry VAT events require an explicit classification
of the actual tax-account GL row. Other tax-ledger voucher types are flagged.
Retention and advance-recovery charges are not classified as VAT by name or rate.

Parent documents and GL queries use Frappe permissions. Child rows are bulk-read
only for permitted parent invoices. Restricted source documents produce an
incomplete-scope warning. Report, Company, GL read and export/print permissions
are checked on the server. Guest access was verified to fail.

## Configuration

The existing **UAE VAT Settings** is extended rather than adding a second Company
settings master. Two child tables are added: **VAT 201 Filing Period** and
**VAT 201 Classification**. They inherit the parent settings' audit trail.
Accounts Managers/System Managers can maintain settings; Accounts Users/Auditors
can read them. Only managers may approve, change, remove or revoke approvals.

1. Maintain the Company's real TRN in Company.tax_id and its linked Address.
2. Create UAE VAT Settings for the Company. Map actual VAT accounts and their
   ledger side: Output, Input or Both. Do not add Excise/non-VAT accounts just
   because their Account Type is Tax. Both supports shared VAT control accounts.
3. Maintain filing-period start/end, filing frequency, explicit VAT quarter number,
   due date, stagger, tax-year end and Profit Margin Scheme answer. Quarter numbers
   are maintained explicitly; missing quarters are not renumbered. Periods cannot
   overlap. No sample PDF dates or deadline calculations are inserted.
4. Maintain Arabic legal name and available authorized-signatory details in the
   same settings. Missing information prints as Not Configured. Submission Date
   is an explicitly recorded value, never a claim of submission integration.
5. Review the report's source rows and enter a classification for each eligible
   tax event. Supply its voucher type/number, Source Row ID, box, reviewed tax date,
   reason/place-of-supply basis and supporting evidence reference.
6. For input VAT, explicitly confirm recoverability and enter its percentage,
   including zero for non-recoverable VAT. No 100% recovery default is assumed.
7. A manager approves the record. Approval identity/time are stamped by the server.
   Draft or incomplete classifications do not contribute to return boxes.

Source Row ID is the invoice tax-row name for nonzero tax, invoice item-row name
for untaxed/zero-rated/exempt lines, or GL Entry.name for journal/payment events.
The review table and export expose these IDs. The server verifies that the row
belongs to the submitted supporting voucher in the selected Company.

Use **Outside VAT** only for evidence-supported exclusions, including non-VAT
taxes and ineligible/zero-rated/exempt purchases that do not belong in input boxes.
These remain in the audit export. A configured VAT-account posting cannot be
excluded this way, and an exclusion cannot coexist with a VAT classification of
the same source. Correct an erroneous accounting posting through normal ERPNext
processes rather than suppressing it in this report.

## Filters and Periods

- Company is mandatory; TRN and VAT Stagger are read-only context fields.
- Custom Date Range accepts exact From/To dates and is marked analytical unless
  it exactly matches a maintained filing-period record.
- Monthly uses Year/Month with real month ends, including leap years. It does not
  imply that the Company has a monthly filing obligation.
- Quarterly requires a maintained period matching the selected start-date Year
  and explicit VAT Quarter Number. February-April and May-July are supported;
  accounting Fiscal Year and calendar quarters are not used to infer periods.
- Summary shows every official box by default. Detailed adds expandable evidence
  below boxes. Include Adjustments controls the Adjustment column events; turning
  it off marks the result analytical. Box 7 remains a separate official box.
- Show Zero-Value Boxes can hide inactive leaf boxes, while totals remain visible.
- Profit Margin Scheme has no silent default. Yes blocks generation because that
  special calculation scheme is not implemented. No must be explicitly declared.

Tax-date selection uses approved classifications. Posting date is used only to
find unreviewed candidates and to reconcile the GL. A reviewed tax event can be
reported in a different period from its accounting posting, producing a visible
timing difference rather than silently moving the GL entry.

## VAT 201 Box Mapping

| Boxes | Evidence / calculation |
| --- | --- |
| 1a-1g | Approved standard-rated outputs with reviewed Emirate/place-of-supply basis |
| 2 | Approved negative tourist-refund postings and negative taxable bases |
| 3 | Approved reverse-charge output liability; no automatic import assumption |
| 4 | Explicit zero-rated supply classification with no posted VAT |
| 5 | Explicit exempt supply classification with no posted VAT |
| 6 | Import VAT evidence with a reviewed customs base and supporting reference |
| 7 | Justified import corrections in Amount/VAT columns, not the Adjustment column |
| 8 | Sum of output Amount, VAT and Adjustment columns, including negative refunds |
| 9 | Reviewed standard-rated inputs and eligible recovery |
| 10 | Reviewed recoverable reverse-charge/import VAT |
| 11 | Sum of input Amount, VAT and Adjustment columns |
| 12 | Box 8 VAT plus Box 8 adjustments |
| 13 | Box 11 VAT plus Box 11 adjustments |
| 14 | Box 12 less Box 13; credit positions remain negative |

Box descriptions and page grouping follow the provided three-page PDF.
No address alone determines the Emirate, no zero tax alone determines exemption,
and no fixed 5% calculation substitutes for the saved tax amount.

## Amounts, Recovery, Returns and Adjustments

Saved base_tax_amount_after_discount_amount is used, with the stored deduction
sign. The taxable base comes from saved base_net_total or the referenced tax
row's base_total for On Previous Row Total. Actual charges, mixed treatments and
multiple VAT rows require a reviewed taxable-base allocation. There is no
last-row balancing or header forcing.

Returns use signed stored amounts. Source IDs and VAT sides prevent duplicate
counting. Reverse charge can have one output event and one input event for the
same purchase tax row; each generic journal/payment GL row has only one treatment.
Recovery percentages affect input VAT, not output liability. Partially recoverable
inputs retain the reviewed full eligible base. With zero entitlement both return
base and recoverable VAT are zero; source base/full tax/non-recoverable tax remain
available in the audit evidence.

Ordinary corrections use VAT Amount. The Adjustment column accepts reviewed
bad-debt/property treatments on outputs (negative amounts), and bad-debt,
annual-apportionment/capital-assets treatments on inputs. The guide's specific
adjustment rules were checked; eligibility and any disclosure obligations must
be assessed by the accountant. Import corrections belong in Box 7.

## Currency and Reconciliation

AED is the reporting currency. Foreign-currency invoices use recorded Company
base values, not transaction-currency totals. For a non-AED Company, each approved
tax event needs an evidenced tax-point exchange rate expressed as AED per Company
base currency. The ledger is converted only where a unique approved rate exists
for its voucher/account; otherwise that side is unavailable and Needs Review.
No current-market rate is silently fetched or substituted. Framework AED precision
is used for monetary values and PDF/Excel formatting.

Reconciliation compares classified output/recoverable input VAT plus adjustments
with configured posting-date tax ledgers. Shared accounts separate sales, purchases
and approved journal sides; reverse-charge debit/credit sides are kept separate.
Unallocated tax postings are shown separately. Missing mappings never produce a
false zero-difference assertion. Recoverability exclusions, tax-date timing,
manual entries and FX limitations can explain nonzero differences; none are forced
to zero. Non-VAT exclusions are documented and retained in the audit export.

## UI, Drill-Down and Exports

All financial report values remain numeric. Click a box amount to see permitted
supporting transactions, amounts, classification, Emirate, source accounts and
evidence. Voucher links open their ERPNext documents. General Ledger links pass
Company, exact posting date, voucher and tax account. The tax period may differ
from the posting date, so a tax-period total is not claimed to match one GL date
range automatically.

Use the report's **Export** buttons for complete Excel/CSV preparation exports:
taxpayer/period header, warnings/status, all official boxes, transaction details,
review rows, approved non-VAT exclusions and reconciliation. Formula-like strings
are escaped; numeric values remain numbers. The normal framework export of the
current grid is still available but is not the complete audit workbook.

**PDF: VAT 201 Preparation** generates three A4 pages: taxpayer information and
1a-1e; 1f-8 and inputs; net VAT, scheme, signatory and reconciliation. It has no
FTA logos or certification claim. Needs Review figures are prominently provisional.
Missing header/signatory values are Not Configured. No filing or submission is
performed.

## Verification and Current Qatra Readiness

For 2026-01-01 through 2026-12-31, the unconfigured live report correctly returns
Needs Review with 471 candidate source rows: 13 sales, 436 purchase (including
untaxed items needing review), and 22 journal rows. No production classifications
were inserted or approved. The boxes contain only classified events; their zero
classified subtotals are **not an assertion that Qatra owes zero VAT**.

An isolated in-memory configuration, explicitly marked TEST ONLY, classified the
existing 13 sales and 395 purchase VAT rows for calculation/reconciliation testing.
It was not saved and does not establish legal place of supply or recoverability.
Output VAT 55,062.68 and Input VAT 98,346.18 each matched their invoice GL postings
with difference 0.00. Invoice-only net was -43,283.50. Manual journal VAT net
-48,182.99 remained unallocated rather than being guessed as output/input tax.
Without mappings, live output/input ledger comparisons are unavailable; combined
unallocated tax-account debit-minus-credit is -4,899.49.

Verified normal Frappe report execution, summary/detail reconciliation, monthly,
test-configured non-calendar quarterly and custom dates, empty January, explicit
scheme blocking, real Guest denial and CSV/Excel/PDF download functions. The PDF
was generated, inspected as three A4 pages and visually reviewed. The quarterly
calendar used in testing existed only in memory, not as Qatra's legal calendar.

22 Python tests cover individual boxes, totals, Emirates, zero/exempt separation,
credit notes, reverse charge, imports, zero/partial/full recovery, source tax amounts,
currencies/precision, adjustments, non-VAT exclusions, periods, scheme rejection,
access and Excel contents. Three Node tests cover numeric/zero currency links,
period controls and captured click behavior. Exotic scenarios use isolated memory
fixtures, not fabricated accounting postings. No authenticated browser session
was used; UI behavior was exercised through handler tests.

## Preparation Procedure and Remaining Limitations

An accountant must supply Qatra's real TRN, VAT ledger mappings, filing calendar,
due dates, scheme answer, place-of-supply evidence, recovery assessments and
signatory details. Review and approve each affected source, rerun the report,
resolve reconciliation differences, and export the preparation workbook/PDF.
Open/Under Review/Finalized are preparation-calendar states, not FTA submission
states. A fresh report always reads current submitted accounting evidence.

Imports and reverse-charge amounts require actual ERP tax/GL support and reviewed
customs evidence; there is no automated FTA/customs import feed. The report does
not determine legal eligibility for a claim or voluntary disclosure. Profit Margin
Scheme calculations and FTA submission integration are intentionally unsupported
and cannot be represented as completed returns. Multi-Finance-Book duplicate
postings require accountant reconciliation; no book is silently assumed. Large
classification registers use standard child-table configuration; no automatic
mass approval or transaction rewriting is provided.
