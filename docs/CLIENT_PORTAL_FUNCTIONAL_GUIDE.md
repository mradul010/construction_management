# Qatra Client Portal - Functional Guide

## 1. How Customer Logs In

The customer opens `/client-portal` and signs in with the email/password of a Frappe Website User. The account must be linked to a Customer record through Contact, Contact Email, Customer Portal User, or ERPNext default customer mapping.

If the account is valid, the user is sent to the dashboard. If the account is not a client portal user, the page shows an access message.

## 2. Portal Home

The portal home is `/client-portal/dashboard`.

It shows:

- Selected project overview
- Overall progress
- Current project stage
- Next milestone
- Total projects
- Active projects
- Total contract value
- Total received
- Published report count
- Financial snapshot
- Recent activity

## 3. Projects

The Projects page shows all projects linked to the client account. A client can search projects and filter by status.

Each project card shows:

- Project name
- Status
- Location
- Client
- Project manager
- Start date
- Expected end date
- Progress percentage

Opening a project shows a more detailed view with financial summary, project journey, activity, and quick links.

## 4. BOQ

Direct BOQ pages are available in the older Construction Portal at `/boq`, not in the new `/client-portal` sidebar.

BOQ means Bill of Quantities. It contains the approved project scope, item quantities, rates, categories, and total contract values. Only the active BOQ revision is shown in the legacy portal.

Important values:

- Unit Cost: contractor cost per unit
- Margin %: markup percentage
- Unit Rate: client-facing rate after margin
- Amount: quantity multiplied by unit cost
- Amount After Margin: quantity multiplied by unit rate
- Grand Total: total BOQ value after margin

## 5. Work Progress

Work progress is shown indirectly on the new dashboard as overall project progress.

The older `/work-progress` page shows BOQ item progress. It uses submitted RA Bill progress transactions where available. If those transaction records do not exist, it falls back to submitted RA Bill item rows.

Important values:

- BOQ Qty: original quantity from BOQ
- Completed Qty: quantity already certified
- Remaining Qty: BOQ Qty minus completed quantity
- Progress %: completed quantity divided by BOQ quantity

## 6. RA Bill

RA Bills are Running Account Bills. They certify the value of work completed for a billing period.

Direct RA Bill list/detail pages are available in the older Construction Portal at `/ra-bill`. The new portal shows RA Bill effects in dashboard activity and payment/financial summaries.

Important values:

- Previous Qty: already certified quantity from earlier submitted bills
- Current Qty: quantity certified in the current bill
- Cumulative Qty: previous quantity plus current quantity
- Remaining Qty: quantity still available to bill
- Gross Amount: total current certified value
- Retention Amount: amount held back as retention
- Net Payable: gross amount minus retention
- Grand Total: gross plus taxes/charges
- Outstanding Amount: grand total minus recovered advance

The system blocks normal overbilling. Adjustment rows are allowed only when there is previous certified progress and the adjustment does not move cumulative progress below zero or above 100%.

## 7. Invoice

After an RA Bill is submitted and approved, the team can create a draft Sales Invoice from it.

The Sales Invoice carries:

- Customer
- Project
- BOQ
- RA Bill reference
- Certified billing amount
- Taxes
- Retention/advance deduction handling
- Payment schedule when configured

The portal shows submitted Sales Invoices in the financial and payments views.

## 8. Payments

The Payments page shows the client’s account position for a selected project.

It includes:

- Payment status
- Latest invoice
- Latest payment
- Invoice cards
- Receipt cards
- Statement rows
- Outstanding balance

Payment data comes from submitted Payment Entries allocated against Sales Invoices or Sales Orders.

## 9. Documents and Gallery

Documents and Gallery entries are published through `Project Portal File` in the ERPNext desk. Uploading or attaching a public `File` to a Project by itself does not publish it to the Client Portal.

Manual publishing workflow:

1. Open `Project Portal File`.
2. Select the Project. Customer fills automatically from the selected Project and remains read-only.
3. Select Category: `Document` for document files, or `Gallery` for images.
4. Attach or choose the public File.
5. Enter Portal Title, Caption, Description, and Sort Order as needed.
6. Enable `Publish to Client Portal`.
7. Save. Optional Visible From and Visible Until dates control the portal visibility window.

Document files support common project document formats such as PDF, Office files, CSV, TXT, DWG, DXF, ZIP, RVT, and IFC. Gallery files must be JPG, JPEG, PNG, or WEBP images. Private File records are blocked from portal publishing.

The client portal shows published entries only to website users linked to the same Customer and authorized Project. Documents appear at `/client-portal/documents`, and image entries appear at `/client-portal/gallery`.

## 10. What Each Value Means

| Value | Meaning |
|---|---|
| Contract Value | Submitted Sales Order value for the project |
| Certified Work Value | Submitted RA Bill gross value |
| Total Invoiced | Submitted Sales Invoice value |
| Total Received | Invoice payments plus advance receipts |
| Outstanding | Amount still unpaid on submitted invoices |
| Billing Progress | Total invoiced compared with contract value |
| Collection Progress | Invoice collections compared with invoice receivable |
| Remaining Contract Value | Contract value not yet invoiced |

## 11. Common Portal Statuses

Project statuses can include Open, In Progress, Active, On Hold, Completed, and Closed.

RA Bill statuses include Draft, Submitted, Approved, Invoiced, and Cancelled.

Report statuses depend on the Daily Progress Report and virtual report availability. Published DPRs appear in client report views when `Show on Client Portal` is enabled.

## 12. Complete Business Flow

```text
Customer account is linked
-> Customer logs in
-> Portal shows authorized projects
-> Project has BOQ and Sales Order
-> Site work is recorded
-> RA Bill certifies current work
-> RA Bill updates cumulative progress
-> Approved RA Bill creates Sales Invoice
-> Payment Entry records receipt
-> Portal dashboard and payments show updated position
```

The portal is read-only for clients in the inspected implementation. Operational work such as BOQ creation, RA Bill approval, invoice creation, and payment posting happens in the Frappe/ERPNext desk.
