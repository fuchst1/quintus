(() => {
    "use strict";

    const formSelector = "[data-core-ledger-loading-form]";
    const submitSelector = "[data-core-ledger-submit]";

    const setSubmitting = (form, submitButton) => {
        if (form.dataset.coreLedgerSubmitting === "true") {
            return false;
        }

        form.dataset.coreLedgerSubmitting = "true";
        form.setAttribute("aria-busy", "true");

        if (submitButton) {
            submitButton.dataset.coreLedgerOriginalAriaLabel =
                submitButton.getAttribute("aria-label") || "";
            submitButton.classList.add("is-loading");
            submitButton.setAttribute("aria-busy", "true");
            submitButton.setAttribute(
                "aria-label",
                submitButton.dataset.coreLedgerLoadingLabel ||
                    `${submitButton.textContent.trim()} – wird ausgeführt`,
            );
            submitButton.setAttribute("aria-disabled", "true");

            if (submitButton.name) {
                const submittedValue = document.createElement("input");
                submittedValue.type = "hidden";
                submittedValue.name = submitButton.name;
                submittedValue.value = submitButton.value;
                submittedValue.dataset.coreLedgerSubmittedValue = "true";
                form.append(submittedValue);
            }
            submitButton.disabled = true;
        }

        const modal = form.closest(".core-ledger-modal");
        if (modal) {
            modal.classList.add("is-submitting");
        }

        return true;
    };

    const resetSubmitting = (form) => {
        delete form.dataset.coreLedgerSubmitting;
        form.removeAttribute("aria-busy");

        form.querySelectorAll(submitSelector).forEach((submitButton) => {
            submitButton.classList.remove("is-loading");
            submitButton.removeAttribute("aria-busy");
            submitButton.removeAttribute("aria-disabled");
            submitButton.disabled = false;

            const originalLabel = submitButton.dataset.coreLedgerOriginalAriaLabel;
            if (originalLabel) {
                submitButton.setAttribute("aria-label", originalLabel);
            } else {
                submitButton.removeAttribute("aria-label");
            }
            delete submitButton.dataset.coreLedgerOriginalAriaLabel;
        });

        form.querySelectorAll('[data-core-ledger-submitted-value="true"]').forEach(
            (submittedValue) => submittedValue.remove(),
        );

        const modal = form.closest(".core-ledger-modal");
        if (modal) {
            modal.classList.remove("is-submitting");
        }
    };

    document.querySelectorAll(formSelector).forEach((form) => {
        form.addEventListener("submit", (event) => {
            const submitButton =
                event.submitter && event.submitter.matches(submitSelector)
                    ? event.submitter
                    : form.querySelector(submitSelector);

            if (!setSubmitting(form, submitButton)) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll(".core-ledger-modal").forEach((modal) => {
        modal.addEventListener("hide.bs.modal", (event) => {
            if (modal.classList.contains("is-submitting")) {
                event.preventDefault();
            }
        });
    });

    const openInvalidModals = () => {
        if (!window.bootstrap || !window.bootstrap.Modal) {
            return;
        }

        document
            .querySelectorAll('[data-core-ledger-modal-invalid="true"]')
            .forEach((modal) => {
                window.bootstrap.Modal.getOrCreateInstance(modal).show();
            });
    };

    openInvalidModals();

    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            document.querySelectorAll(formSelector).forEach(resetSubmitting);
        }
    });
})();
