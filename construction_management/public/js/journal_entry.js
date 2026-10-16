
frappe.ui.form.on("Journal Entry", {
    refresh(frm) {
        const grid = frm.fields_dict.accounts?.grid;
        const section = grid?.wrapper?.[0]?.closest(".form-section");
        const details = section?.closest(".tab-pane");

        if (!section || !details) return;

        // Apply styles only to Journal Entry
        details.classList.add("qatra-journal-details");
        section.classList.add("qatra-accounts-section");

        // Find existing fields without modifying their data
        const getFieldElement = (fieldname) =>
            frm.fields_dict[fieldname]?.$wrapper?.[0] || null;

        const debitField = getFieldElement("total_debit");
        const creditField = getFieldElement("total_credit");

        const referenceNumber =
            getFieldElement("cheque_no") ||
            getFieldElement("reference_number");

        const referenceDate =
            getFieldElement("cheque_date") ||
            getFieldElement("reference_date");

        // Mark totals section
        const totalsSection = debitField?.closest(".form-section");

        if (totalsSection && totalsSection.contains(creditField)) {
            totalsSection.classList.add("qatra-totals-section");

            const debitForm = debitField.closest("form");
            const creditForm = creditField.closest("form");

            if (debitForm && debitForm === creditForm) {
                debitForm.classList.add("qatra-totals-fields");
            }
        }

        // Mark reference section
        const referenceSection =
            referenceNumber?.closest(".form-section");

        if (
            referenceSection &&
            referenceDate &&
            referenceSection.contains(referenceDate)
        ) {
            referenceSection.classList.add(
                "qatra-reference-section"
            );

            const numberForm = referenceNumber.closest("form");
            const dateForm = referenceDate.closest("form");

            if (numberForm && numberForm === dateForm) {
                numberForm.classList.add(
                    "qatra-reference-fields"
                );
            }
        }

        // Create or update CSS
        const styleId = "qatra-journal-entry-grid-style";
        let style = document.getElementById(styleId);

        if (!style) {
            style = document.createElement("style");
            style.id = styleId;
            document.head.appendChild(style);
        }

        style.textContent = `
            /* 1. Unified page layout */

            .qatra-journal-details > .form-section {
                max-width: none !important;
                box-sizing: border-box !important;
            }

            /* 2. Accounting Entries grid */

            .qatra-accounts-section .section-body,
            .qatra-accounts-section .form-column,
            .qatra-accounts-section form,
            .qatra-accounts-section [data-fieldname="accounts"],
            .qatra-accounts-section .grid-field,
            .qatra-accounts-section .form-grid-container {
                width: 100% !important;
                max-width: none !important;
                box-sizing: border-box !important;
            }

            .qatra-accounts-section .grid-heading-row,
            .qatra-accounts-section .grid-body,
            .qatra-accounts-section .grid-row .data-row {
                width: 100% !important;
                min-width: 0 !important;
                max-width: 100% !important;
            }

            .qatra-accounts-section
            .grid-static-col[data-fieldname] {
                min-width: 0 !important;
                width: 0 !important;
                flex: 1 1 0 !important;
                overflow: hidden;
            }

            .qatra-accounts-section
            .grid-static-col[data-fieldname="account"] {
                flex: 2 1 0 !important;
            }

            .qatra-accounts-section
            .grid-static-col[data-fieldname="party_type"] {
                flex: 1.2 1 0 !important;
            }

            .qatra-accounts-section
            .grid-static-col[data-fieldname="party"] {
                flex: 1.5 1 0 !important;
            }

            .qatra-accounts-section
            .grid-static-col[data-fieldname="debit_in_account_currency"],
            .qatra-accounts-section
            .grid-static-col[data-fieldname="credit_in_account_currency"] {
                flex: 1.2 1 0 !important;
            }

            .qatra-accounts-section .grid-field {
                overflow-x: auto;
            }

            /* 3. Total Debit and Total Credit - left aligned */

            .qatra-totals-section .section-body {
                display: flex !important;
                justify-content: flex-start !important;
                align-items: flex-start !important;
                flex-wrap: wrap;
                gap: 20px;
            }

            .qatra-totals-section .section-body > .form-column {
                flex: 0 1 380px !important;
                width: calc(50% - 10px) !important;
                max-width: 380px !important;
                min-width: 0 !important;
            }

            .qatra-totals-section
            .section-body > .form-column:has(.qatra-totals-fields) {
                flex: 0 1 780px !important;
                width: 100% !important;
                max-width: 780px !important;
            }

            .qatra-totals-fields {
                display: grid !important;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 20px;
            }

            /* 4. Reference Number and Date - same row */

            .qatra-reference-section .section-body {
                display: flex !important;
                justify-content: flex-start !important;
                align-items: flex-start !important;
                flex-wrap: wrap;
                gap: 20px;
            }

            .qatra-reference-section .section-body > .form-column {
                flex: 0 1 380px !important;
                width: calc(50% - 10px) !important;
                max-width: 380px !important;
                min-width: 0 !important;
            }

            .qatra-reference-section
            .section-body > .form-column:has(.qatra-reference-fields) {
                flex: 0 1 780px !important;
                width: 100% !important;
                max-width: 780px !important;
            }

            .qatra-reference-fields {
                display: grid !important;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 20px;
            }

            /* 5. Small screens */

            @media (max-width: 767px) {
                .qatra-totals-section .section-body,
                .qatra-reference-section .section-body {
                    flex-direction: column !important;
                }

                .qatra-totals-section .section-body > .form-column,
                .qatra-reference-section .section-body > .form-column {
                    width: 100% !important;
                    max-width: 100% !important;
                    flex-basis: auto !important;
                }

                .qatra-totals-fields,
                .qatra-reference-fields {
                    grid-template-columns: 1fr !important;
                }
            }
                /* Same left alignment for all accounting columns */
.qatra-accounts-section .grid-static-col[data-fieldname],
.qatra-accounts-section .grid-static-col[data-fieldname] * {
    text-align: left !important;
    justify-content: flex-start !important;
}
        `;

        // Keep the same side margins across the page
        const resizeLayout = () => {
            if (!details.isConnected) return;

            const main = details.closest(".layout-main-section");
            if (!main) return;

            const mainRect = main.getBoundingClientRect();

            const sideGap = 40;
            const targetLeft = mainRect.left + sideGap;
            const targetRight = mainRect.right - sideGap;
            const targetWidth = targetRight - targetLeft;

            if (targetWidth <= 0) return;

            const sections = details.querySelectorAll(
                ":scope > .form-section"
            );

            sections.forEach((item) => {
                item.style.removeProperty("width");
                item.style.removeProperty("margin-left");

                const originalLeft =
                    item.getBoundingClientRect().left;

                const offset = targetLeft - originalLeft;

                item.style.setProperty(
                    "margin-left",
                    `${offset}px`,
                    "important"
                );

                item.style.setProperty(
                    "width",
                    `${targetWidth}px`,
                    "important"
                );
            });
        };

        if (frm._qatraResizeHandler) {
            window.removeEventListener(
                "resize",
                frm._qatraResizeHandler
            );
        }

        frm._qatraResizeHandler = resizeLayout;

        window.addEventListener("resize", resizeLayout);

        resizeLayout();
    }
});
