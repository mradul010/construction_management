(function () {
	function ready(fn) {
		if (window.frappe && frappe.ready) {
			frappe.ready(fn);
		} else if (document.readyState !== "loading") {
			fn();
		} else {
			document.addEventListener("DOMContentLoaded", fn);
		}
	}

	ready(function () {
		const form = document.getElementById("qatra-client-login-form");
		const resetForm = document.getElementById("qatra-client-reset-form");
		if (!form || !resetForm) {
			return;
		}

		const email = document.getElementById("qatra-login-email");
		const password = document.getElementById("qatra-login-password");
		const button = form.querySelector(".qatra-sign-in-button");
		const resetEmail = document.getElementById("qatra-reset-email");
		const resetButton = resetForm.querySelector(".qatra-sign-in-button");
		const errorMessage = document.querySelector(".qatra-form-message--error");
		const successMessage = document.querySelector(".qatra-form-message--success");
		const showResetButton = document.querySelector("[data-qatra-show-reset]");
		const showLoginButton = document.querySelector("[data-qatra-show-login]");
		const defaultLabel = button ? button.dataset.defaultLabel || "Sign in" : "Sign in";
		const resetDefaultLabel = resetButton ? resetButton.dataset.defaultLabel || "Send reset link" : "Send reset link";

		form.addEventListener("submit", async function (event) {
			event.preventDefault();
			clearMessages();
			clearFieldErrors(form);

			const usr = (email.value || "").trim();
			const pwd = password.value || "";
			let hasError = false;

			if (!usr) {
				showFieldError("usr", "Email Address is required.");
				hasError = true;
			}

			if (!pwd) {
				showFieldError("pwd", "Password is required.");
				hasError = true;
			}

			if (hasError) {
				return;
			}

			setSubmitting(true);
			let isRedirecting = false;

			try {
				const response = await postForm("/api/method/login", {
					cmd: "login",
					usr: usr,
					pwd: pwd
				});

				if (response.message === "Logged In" || response.message === "No App") {
					isRedirecting = true;
					window.location.href = "/client-portal";
					return;
				}

				if (response.message === "Password Reset" && response.redirect_to) {
					isRedirecting = true;
					window.location.href = response.redirect_to;
					return;
				}

				showError(getLoginResponseMessage(response));
				password.focus();
			} catch (error) {
				showError(getErrorMessage(error));
				password.focus();
			} finally {
				if (!isRedirecting) {
					setSubmitting(false);
				}
			}
		});

		resetForm.addEventListener("submit", async function (event) {
			event.preventDefault();
			clearMessages();
			clearFieldErrors(resetForm);

			const user = (resetEmail.value || "").trim();
			if (!user) {
				showResetFieldError("user", "Email Address is required.");
				return;
			}

			setResetSubmitting(true);

			try {
				const response = await postForm(
					"/api/method/construction_management.www.client_portal.reset_client_portal_password",
					{
						user: user
					}
				);
				showSuccess(
					(response.message && response.message.message) ||
					"If this email is registered as a QATRA client portal user, password reset instructions have been sent."
				);
			} catch (error) {
				showError(getResetErrorMessage(error));
				resetEmail.focus();
			} finally {
				setResetSubmitting(false);
			}
		});

		[email, password].forEach(function (field) {
			field.addEventListener("input", function () {
				clearMessages();
				clearFieldErrors(form);
			});
		});

		resetEmail.addEventListener("input", function () {
			clearMessages();
			clearFieldErrors(resetForm);
		});

		if (showResetButton) {
			showResetButton.addEventListener("click", function () {
				clearMessages();
				clearFieldErrors(form);
				form.hidden = true;
				resetForm.hidden = false;
				resetEmail.value = email.value || "";
				resetEmail.focus();
			});
		}

		if (showLoginButton) {
			showLoginButton.addEventListener("click", function () {
				clearMessages();
				clearFieldErrors(resetForm);
				resetForm.hidden = true;
				form.hidden = false;
				email.focus();
			});
		}

		function clearMessages() {
			[errorMessage, successMessage].forEach(function (message) {
				if (message) {
					message.hidden = true;
					message.textContent = "";
				}
			});
		}

		function clearFieldErrors(targetForm) {
			targetForm.querySelectorAll(".qatra-field--invalid").forEach(function (field) {
				field.classList.remove("qatra-field--invalid");
			});

			targetForm.querySelectorAll(".qatra-field-error").forEach(function (error) {
				error.textContent = "";
			});
		}

		function showFieldError(fieldName, text) {
			const error = form.querySelector('[data-field-error="' + fieldName + '"]');
			if (error) {
				error.textContent = text;
				error.closest(".qatra-field").classList.add("qatra-field--invalid");
			}
		}

		function showResetFieldError(fieldName, text) {
			const error = resetForm.querySelector('[data-reset-field-error="' + fieldName + '"]');
			if (error) {
				error.textContent = text;
				error.closest(".qatra-field").classList.add("qatra-field--invalid");
			}
		}

		function showError(text) {
			if (!errorMessage) {
				return;
			}

			errorMessage.hidden = false;
			errorMessage.textContent = text;
		}

		function showSuccess(text) {
			if (!successMessage) {
				return;
			}

			successMessage.hidden = false;
			successMessage.textContent = text;
		}

		function setSubmitting(isSubmitting) {
			if (!button) {
				return;
			}

			button.disabled = isSubmitting;
			button.querySelector("span").textContent = isSubmitting ? "Signing in..." : defaultLabel;
		}

		function setResetSubmitting(isSubmitting) {
			if (!resetButton) {
				return;
			}

			resetButton.disabled = isSubmitting;
			resetButton.querySelector("span").textContent = isSubmitting ? "Sending..." : resetDefaultLabel;
		}

		async function postForm(url, args) {
			const headers = {
				Accept: "application/json",
				"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
			};
			if (window.frappe && frappe.csrf_token && frappe.csrf_token !== "None") {
				headers["X-Frappe-CSRF-Token"] = frappe.csrf_token;
			}

			const body = new URLSearchParams();
			Object.keys(args || {}).forEach(function (key) {
				if (args[key] !== undefined && args[key] !== null) {
					body.append(key, args[key]);
				}
			});

			const response = await fetch(url, {
				method: "POST",
				credentials: "same-origin",
				headers: headers,
				body: body
			});
			const data = await parseResponse(response);

			if (!response.ok) {
				const error = new Error((data && data.message) || response.statusText);
				error.status = response.status;
				error.data = data;
				throw error;
			}

			return data;
		}

		async function parseResponse(response) {
			const contentType = response.headers.get("content-type") || "";
			if (contentType.indexOf("application/json") !== -1) {
				return response.json();
			}

			return {
				message: await response.text()
			};
		}

		function getLoginResponseMessage(response) {
			const message = response && response.message;
			if (typeof message === "string" && message.toLowerCase().includes("invalid")) {
				return "The email or password is incorrect.";
			}

			return "The email or password is incorrect.";
		}

		function getErrorMessage(xhr) {
			const status = xhr && xhr.status;
			if (status === 401) {
				return "The email or password is incorrect.";
			}
			if (status === 429) {
				return "Too many sign-in attempts. Please try again later.";
			}

			const serverMessage = getServerMessage(xhr);
			if (serverMessage) {
				return serverMessage;
			}

			if (!navigator.onLine) {
				return "You appear to be offline. Check your connection and try again.";
			}

			return "We could not complete sign in. Please try again.";
		}

		function getResetErrorMessage(xhr) {
			const status = xhr && xhr.status;
			if (status === 429) {
				return "Too many password reset requests. Please try again later.";
			}

			const serverMessage = getServerMessage(xhr);
			if (serverMessage) {
				return serverMessage;
			}

			if (!navigator.onLine) {
				return "You appear to be offline. Check your connection and try again.";
			}

			return "We could not send the reset link. Please try again.";
		}

		function getServerMessage(xhr) {
			const response = xhr && (xhr.responseJSON || xhr.data);
			if (!response || !response._server_messages) {
				return typeof (response && response.message) === "string" ? response.message : "";
			}

			try {
				return JSON.parse(response._server_messages)
					.map(function (item) {
						try {
							return JSON.parse(item).message || item;
						} catch (error) {
							return item;
						}
					})
					.join(" ");
			} catch (error) {
				return "";
			}
		}
	});
})();
