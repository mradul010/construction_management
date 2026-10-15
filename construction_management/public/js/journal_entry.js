frappe.ui.form.on("Journal Entry", {
    refresh(frm) {
        const grid = frm.fields_dict.accounts?.grid;
        if (!grid) return;

        const styleId = "qatra-journal-entry-grid-style";

        if (!document.getElementById(styleId)) {
            const style = document.createElement("style");
            style.id = styleId;
            style.textContent = `
                .qatra-journal-entry-grid .grid-body,
                .qatra-journal-entry-grid .grid-heading-row {
                    min-width: 900px;
                }

                .qatra-journal-entry-grid .grid-static-col[data-fieldname] {
                    min-width: 140px;
                }
            `;
            document.head.appendChild(style);
        }

        grid.wrapper.addClass("qatra-journal-entry-grid");
        grid.wrapper.css("overflow-x", "auto");
    }
});
