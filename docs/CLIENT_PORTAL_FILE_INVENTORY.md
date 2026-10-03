# Client Portal File Inventory

| # | File | Type | Purpose | Used By | Status |
|---|---|---|---|---|---|
| 1 | `construction_management/hooks.py` | Hook config | Routes, assets, portal menu, session hook, doc events | Frappe app | Active |
| 2 | `construction_management/portal_utils.py` | Python utility | Auth, customer resolution, portal data, reports, payments | New and legacy portals | Active |
| 3 | `construction_management/www/client_portal.py` | Page controller | `/client-portal` login and reset | Login page | Active |
| 4 | `construction_management/www/client-portal.html` | Template | Login page | `/client-portal` | Active |
| 5 | `construction_management/www/client_portal_dashboard.py` | Page controller | Dashboard context | `/client-portal/dashboard` | Active |
| 6 | `construction_management/www/client-portal-dashboard.html` | Template | Dashboard UI | `/client-portal/dashboard` | Active |
| 7 | `construction_management/www/client_portal_projects.py` | Page controller | Projects context | `/client-portal/projects` | Active |
| 8 | `construction_management/www/client-portal-projects.html` | Template | Project list/cards | `/client-portal/projects` | Active |
| 9 | `construction_management/www/client_portal_project.py` | Page controller | Project detail context | `/client-portal/project/<name>` | Active |
| 10 | `construction_management/www/client-portal-project.html` | Template | Project detail | `/client-portal/project/<name>` | Active |
| 11 | `construction_management/www/client_portal_reports.py` | Page controller | Report library context | `/client-portal/reports` | Active |
| 12 | `construction_management/www/client-portal-reports.html` | Template | Report library | `/client-portal/reports` | Active |
| 13 | `construction_management/www/client_portal_report.py` | Page controller | Report detail context | `/client-portal/report/<name>` | Active |
| 14 | `construction_management/www/client-portal-report.html` | Template | Report detail | `/client-portal/report/<name>` | Active |
| 15 | `construction_management/www/client_portal_payments.py` | Page controller | Payment view and statement | `/client-portal/payments` | Active |
| 16 | `construction_management/www/client-portal-payments.html` | Template | Payments UI | `/client-portal/payments` | Active |
| 17 | `construction_management/www/client_portal_documents.py` | Page controller | Documents placeholder | `/client-portal/documents` | Active |
| 18 | `construction_management/www/client-portal-documents.html` | Template | Placeholder shell | `/client-portal/documents` | Active |
| 19 | `construction_management/www/client_portal_gallery.py` | Page controller | Gallery placeholder | `/client-portal/gallery` | Active |
| 20 | `construction_management/www/client-portal-gallery.html` | Template | Placeholder shell | `/client-portal/gallery` | Active |
| 21 | `construction_management/www/client_portal_approvals.py` | Page controller | Approval list context | `/client-portal/approvals` | Active |
| 22 | `construction_management/www/client-portal-approvals.html` | Template | Approval list UI | `/client-portal/approvals` | Active |
| 22A | `construction_management/www/client_portal_approval.py` | Page controller | Approval detail context | `/client-portal/approval/<name>` | Active |
| 22B | `construction_management/www/client-portal-approval.html` | Template | Approval detail and response UI | `/client-portal/approval/<name>` | Active |
| 22C | `construction_management/construction_management/doctype/client_approval_request/` | DocType | Portal-facing client approval lifecycle | Desk and Client Portal | Active |
| 23 | `construction_management/www/client_portal_logout.py` | Page controller | Logout page context | `/client-portal/logout` | Active |
| 24 | `construction_management/www/client-portal-logout.html` | Template | Logout/sign-out page | `/client-portal/logout` | Active |
| 25 | `construction_management/templates/client_portal/base.html` | Template | Client portal layout shell | All new client portal pages | Active |
| 26 | `construction_management/templates/client_portal/sidebar.html` | Template | Sidebar navigation | All new client portal pages | Active |
| 27 | `construction_management/templates/client_portal/page_shell.html` | Template | Generic placeholder hero | Documents/Gallery/Approvals | Active |
| 28 | `construction_management/public/js/qatra_client_portal.js` | JavaScript | Sidebar, filters, table CSV/pagination | New client portal pages | Active |
| 29 | `construction_management/public/js/qatra_client_portal_login.js` | JavaScript | Login and password reset | `/client-portal` | Active |
| 30 | `construction_management/public/css/qatra_client_portal.css` | CSS | New client portal visual system | New client portal pages | Active |
| 31 | `construction_management/public/images/qatra-logo.svg` | Image | Portal fallback logo | New client portal | Active |
| 32 | `construction_management/www/construction_portal.py` | Page controller | Legacy Construction Portal dashboard | `/construction-portal` | Legacy |
| 33 | `construction_management/www/construction-portal.html` | Template | Legacy dashboard | `/construction-portal` | Legacy |
| 34 | `construction_management/www/construction_projects.py` | Page controller | Legacy project list | `/construction-projects` | Legacy |
| 35 | `construction_management/www/construction-projects.html` | Template | Legacy project list | `/construction-projects` | Legacy |
| 36 | `construction_management/www/construction_project_detail.py` | Page controller | Legacy project detail | `/construction-project-detail` | Legacy |
| 37 | `construction_management/www/construction-project-detail.html` | Template | Legacy project detail | `/construction-project-detail` | Legacy |
| 38 | `construction_management/www/boq.py` | Page controller | Legacy BOQ list | `/boq` | Legacy |
| 39 | `construction_management/www/boq.html` | Template | Legacy BOQ list | `/boq` | Legacy |
| 40 | `construction_management/www/boq_detail.py` | Page controller | Legacy BOQ detail | `/boq-detail` | Legacy |
| 41 | `construction_management/www/boq-detail.html` | Template | Legacy BOQ detail | `/boq-detail` | Legacy |
| 42 | `construction_management/www/ra_bill.py` | Page controller | Legacy RA Bill list | `/ra-bill` | Legacy |
| 43 | `construction_management/www/ra-bill.html` | Template | Legacy RA Bill list | `/ra-bill` | Legacy |
| 44 | `construction_management/www/ra_bill_detail.py` | Page controller | Legacy RA Bill detail | `/ra-bill-detail` | Legacy |
| 45 | `construction_management/www/ra-bill-detail.html` | Template | Legacy RA Bill detail | `/ra-bill-detail` | Legacy |
| 46 | `construction_management/www/work_progress.py` | Page controller | Legacy work progress | `/work-progress` | Legacy |
| 47 | `construction_management/www/work-progress.html` | Template | Legacy work progress | `/work-progress` | Legacy |
| 48 | `construction_management/www/work_progress_detail.py` | Page controller | Legacy work progress detail | `/work-progress-detail` | Legacy |
| 49 | `construction_management/www/work-progress-detail.html` | Template | Legacy work progress detail | `/work-progress-detail` | Legacy |
| 50 | `construction_management/www/dprs.py` | Page controller | Legacy DPR list | `/dprs` | Legacy |
| 51 | `construction_management/www/dprs.html` | Template | Legacy DPR list | `/dprs` | Legacy |
| 52 | `construction_management/www/dpr_detail.py` | Page controller | Legacy DPR detail | `/dpr-detail` | Legacy |
| 53 | `construction_management/www/dpr-detail.html` | Template | Legacy DPR detail | `/dpr-detail` | Legacy |
| 54 | `construction_management/templates/includes/construction_portal/header.html` | Template include | Legacy portal header | Legacy portal templates | Legacy |
| 55 | `construction_management/templates/includes/construction_portal/empty.html` | Template include | Empty state | Legacy portal templates | Legacy |
| 56 | `construction_management/templates/includes/construction_portal/table_empty.html` | Template include | Table empty state | Legacy portal templates | Legacy |
| 57 | `construction_management/public/js/portal.js` | JavaScript | Legacy portal route helpers | Legacy portal pages | Legacy |
| 58 | `construction_management/public/css/portal.css` | CSS | Legacy portal styles | Legacy portal pages | Legacy |
| 59 | `construction_management/construction_management/doctype/boq/boq.py` | DocType controller | BOQ calculations and revisions | BOQ, RA Bill | Active |
| 60 | `construction_management/construction_management/doctype/boq/boq.js` | Desk JS | BOQ form behavior | BOQ desk | Active |
| 61 | `construction_management/construction_management/doctype/boq/boq.json` | DocType metadata | BOQ fields | BOQ | Active |
| 62 | `construction_management/construction_management/doctype/boq_item/boq_item.py` | Child controller | BOQ item calculation | BOQ Item | Active |
| 63 | `construction_management/construction_management/doctype/boq_item/boq_item.json` | DocType metadata | BOQ item fields | BOQ | Active |
| 64 | `construction_management/construction_management/doctype/boq_cost_component/boq_cost_component.json` | DocType metadata | BOQ cost component fields | BOQ | Active |
| 65 | `construction_management/construction_management/doctype/boq_revision/boq_revision.json` | DocType metadata | BOQ revision child fields | BOQ | Active |
| 66 | `construction_management/construction_management/doctype/boq_category/boq_category.json` | DocType metadata | Category tree | BOQ/RA Bill | Active |
| 67 | `construction_management/construction_management/doctype/ra_bill/ra_bill.py` | DocType controller | RA Bill lifecycle, calculations, Sales Invoice creation | RA Bill | Active |
| 68 | `construction_management/construction_management/doctype/ra_bill/ra_bill.js` | Desk JS | RA Bill form behavior and client calculations | RA Bill desk | Active |
| 69 | `construction_management/construction_management/doctype/ra_bill/ra_bill.json` | DocType metadata | RA Bill fields | RA Bill | Active |
| 70 | `construction_management/construction_management/doctype/ra_bill_item/ra_bill_item.json` | DocType metadata | RA Bill item fields | RA Bill | Active |
| 71 | `construction_management/construction_management/doctype/ra_bill_transaction/ra_bill_transaction.json` | DocType metadata | Submitted progress ledger | RA Bill/Work Progress | Active |
| 72 | `construction_management/construction_management/doctype/ra_bill_taxes_and_charges/ra_bill_taxes_and_charges.json` | DocType metadata | RA Bill tax rows | RA Bill | Active |
| 73 | `construction_management/construction_management/doctype/ra_bill_advance/ra_bill_advance.json` | DocType metadata | RA Bill advance allocation | RA Bill | Active |
| 74 | `construction_management/construction_management/doctype/ra_bill_payment_schedule/ra_bill_payment_schedule.json` | DocType metadata | Payment schedule | RA Bill/Sales Invoice | Active |
| 75 | `construction_management/construction_management/doctype/ra_bill_timesheet/ra_bill_timesheet.json` | DocType metadata | Timesheet rows | RA Bill/Sales Invoice | Active |
| 76 | `construction_management/construction_management/advance_management.py` | Python utility | Sales Order advances and RA Bill recovery | RA Bill/Sales Invoice/Payment Entry hooks | Active |
| 77 | `construction_management/construction_management/overrides/sales_invoice.py` | Python override | RA Bill Sales Invoice retention/advance/payment breakdown | Sales Invoice hooks | Active |
| 78 | `construction_management/construction_management/doctype/daily_progress_report/daily_progress_report.py` | DocType controller | DPR customer sync and portal permission | Reports | Active |
| 79 | `construction_management/construction_management/doctype/daily_progress_report/daily_progress_report.json` | DocType metadata | DPR fields | Reports | Active |
| 80 | `construction_management/construction_management/doctype/dpr_task_completed/dpr_task_completed.json` | DocType metadata | DPR task rows | Reports | Active |
| 81 | `construction_management/construction_management/doctype/dpr_photo/dpr_photo.json` | DocType metadata | DPR photo rows | Reports | Active |
| 82 | `construction_management/construction_management/api.py` | Python API | BOQ item/cost component helpers | Desk BOQ scripts | Possibly Active |
| 83 | `construction_management/construction_management/client_script/boq_client_script.js` | Client script source | BOQ calculations/UI | Fixture/client script | Active |
| 84 | `construction_management/fixtures/client_script.json` | Fixture | Installed BOQ client script | Frappe fixtures | Active |

