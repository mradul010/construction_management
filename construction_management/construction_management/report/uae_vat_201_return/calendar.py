"""Read-only checks of the maintained calendar, not an FTA deadline calculator."""
import json
from pathlib import Path
from frappe.utils import add_days, add_months, getdate


def validate(header, settings):
	issues = []
	if header.get("period_kind") != "Configured filing period":
		return ["Analytical dates do not match a maintained VAT filing period; this is a draft analysis"]
	start, end = getdate(header["from_date"]), getdate(header["to_date"])
	frequency = header.get("filing_frequency")
	months = {"Monthly":1,"Quarterly":3}.get(frequency)
	if not months or start.day != 1 or getdate(add_days(add_months(start, months), -1)) != end:
		issues.append("Maintained VAT period dates do not match their filing frequency; confirm the FTA-assigned period")
	registration = header.get("registration_date")
	if registration and start < getdate(registration):
		issues.append("Maintained VAT period starts before VAT registration; confirm the first FTA-assigned period")
	if frequency == "Quarterly" and header.get("tax_year_end"):
		offset = (start.month - getdate(header["tax_year_end"]).month - 1) % 12
		if offset % 3 or header.get("quarter_number") != offset // 3 + 1:
			issues.append("Maintained VAT quarter number/dates do not match the configured tax-year-end cycle")
	for period in settings.get("custom_vat201_periods", []):
		if str(period.from_date) == str(start) and str(period.to_date) == str(end):
			continue
		if getdate(period.from_date) <= end and getdate(period.to_date) >= start:
			issues.append("Maintained VAT filing periods overlap; accounts must review the calendar")
			break
	nominal = getdate(add_days(end, 28))
	header["nominal_due_date"] = str(nominal)
	expected = nominal
	with Path(__file__).with_name("filing_calendar_evidence.json").open() as stream:
		evidence = json.load(stream)
	for interval in evidence["closed_intervals"]:
		if getdate(interval["from_date"]) <= nominal <= getdate(interval["to_date"]):
			expected = getdate(interval["next_working_day"])
			header["calendar_basis"] = interval["basis"]
			header["calendar_sources"] = "; ".join(interval["sources"])
			break
	header["expected_due_date"] = str(expected)
	if not header.get("due_date"):
		issues.append("VAT filing due date is not maintained; confirm it against the FTA calendar")
	elif getdate(header["due_date"]) != expected:
		issues.append("Maintained due date " + str(header["due_date"]) + " differs from the checked date " + str(expected) + " (nominal 28-day date " + str(nominal) + ")" +
			". Confirm any FTA direction, weekend or national-holiday extension; settings have not been changed")
	if header.get("due_date_basis") != "Confirmed":
		issues.append("VAT due date is provisional or lacks a confirmed basis; verify the FTA-assigned calendar")
	return list(dict.fromkeys(issues))
