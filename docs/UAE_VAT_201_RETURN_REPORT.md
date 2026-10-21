# UAE VAT 201 Return

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
