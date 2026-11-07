"""Synthetic acceptance fixtures: no production documents are read or written."""
import copy
import unittest
from decimal import Decimal
from unittest.mock import patch

import frappe

from construction_management.construction_management.report.uae_vat_201_return import automatic, engine


def split(amount, count):
	cents = int(engine.number(amount) * 100)
	q, remainder = divmod(cents, count)
	return [Decimal(q + (i < remainder)) / 100 for i in range(count)]


def fixture(approved=False, exclude_advances=False):
	sources, ledger, events, reviews, excluded = [], [], [], [], []
	groups = [("Sales Invoice", "Output", 13, "55062.68", "1101253.46"),
		("Purchase Invoice", "Input", 290, "36677.19", "733309.57"),
		("Purchase Invoice", "Input", 5, "-161.65", "-3000"),
		("Journal Entry", "Input", 13, "597.21", "12000"),
		("Journal Entry", "Output", 2, "49315.77", "986000")]
	for group, (dt, side, count, vat, base) in enumerate(groups):
		for index, (v, b) in enumerate(zip(split(vat, count), split(base, count))):
			name = f"SYNTHETIC-{group}-{index}"
			debit = v if side == "Input" else -v
			g = dict(name=name+"-GL", posting_date="2026-06-01", voucher_type=dt, voucher_no=name,
				account="SYNTHETIC-VAT", debit=max(debit, 0), credit=max(-debit, 0))
			s = dict(voucher_type=dt, voucher_no=name, source_row=g["name"] if dt == "Journal Entry" else name+"-TAX",
				posting_date=g["posting_date"], tax_account=g["account"], base=b, raw_vat=v, company="SYNTHETIC",
				currency="AED", source_emirate="Ras Al Khaimah", tax_rate=5, vat_rows_count=1,
				recovery_source_amount=0, gl_evidence=[g], is_return=int(v < 0))
			if dt == "Journal Entry":
				s.update(debit=g["debit"], credit=g["credit"], raw_vat=debit, journal_vat_role=side,
					journal_category="Recorded purchase VAT" if side == "Input" else "Customer-advance output VAT")
			ledger.append(g); sources.append(s)
			if dt == "Sales Invoice" or approved:
				rule = frappe._dict(box="9" if side == "Input" else "1f", tax_date=g["posting_date"], approved_by="Fixture Reviewer",
					reason="Synthetic supported treatment", supporting_reference="TEST-EVIDENCE", recovery_confirmed=1, recovery_percent=100)
				if exclude_advances and dt == "Journal Entry" and side == "Output":
					rule.box = "Outside VAT"
					event, error = engine.apply_rule(s, rule, "AED")
					excluded.append(event)
				else:
					event, error = engine.apply_rule(s, rule, "AED")
					events.append(event)
				if error:
					raise AssertionError(error)
			else:
				reviews.append(s)
	return dict(filters=frappe._dict(company="SYNTHETIC", from_date="2026-05-01", to_date="2026-07-31"),
		header=dict(base_currency="AED"), sources=sources, ledger_entries=ledger, events=events, reviews=reviews,
		excluded=excluded, warnings=[], reconciliation=[], source_headers={}, timing_events=[],
		opening_entries=[dict(debit=535.57,credit=0)], control_movement=-67265.7)


class TestHistoricalAcceptance(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe, "get_precision", return_value=2))

	def build(self, **kwargs):
		initial = fixture(**kwargs)
		settings = {"uae_vat_accounts": [frappe._dict(account="SYNTHETIC-VAT", custom_vat201_side="Both")]}
		with patch.object(engine, "build", return_value=copy.deepcopy(initial)), patch.object(engine, "settings_for", return_value=settings):
			result = automatic.build({"company":"SYNTHETIC"})
		self.assertEqual(len(result["ledger_entries"]), 323)
		self.assertEqual(result["ledger_summary"]["period_debit"], 37274.4)
		self.assertEqual(result["ledger_summary"]["period_credit"], 104540.1)
		self.assertEqual(result["ledger_summary"]["period_net_credit"], 67265.7)
		self.assertEqual(result["ledger_summary"]["opening_debit"], 535.57)
		self.assertEqual(result["ledger_summary"]["closing_credit"], 66730.13)
		self.assertEqual(result["tax_measures"]["classification_difference"], 0)
		self.assertEqual(result["tax_measures"]["residual_output"], 0)
		self.assertEqual(result["tax_measures"]["residual_input"], 0)
		covered = {name for row in result["audit_rows"] for name in row["gl_rows"].split(", ")}
		self.assertEqual(covered, {g["name"] for g in initial["ledger_entries"]})
		return result

	def test_unreviewed_purchase_and_journal_inputs_are_pending(self):
		r = self.build()
		self.assertEqual(r["tax_measures"]["pending_input"], 37112.75)
		self.assertEqual(r["tax_measures"]["known_nonclaimed"], 0)
		self.assertEqual(r["tax_measures"]["pending_output"], 49315.77)
		boxes = {b["box"]:b for b in r["boxes"]}
		self.assertEqual((boxes["1f"]["amount"], boxes["1f"]["vat_amount"]), (1101253.46,55062.68))
		self.assertEqual(boxes["13"]["amount"], 0)

	def test_scenario_a_all_supported_and_approved(self):
		r = self.build(approved=True)
		boxes = {b["box"]:b for b in r["boxes"]}
		self.assertEqual(boxes["12"]["amount"],104378.45)
		self.assertEqual(boxes["13"]["amount"],37112.75)
		self.assertEqual(boxes["14"]["amount"],67265.70)
		purchases = [e for e in r["events"] if e["voucher_type"] == "Purchase Invoice"]
		self.assertEqual(engine.money(sum(engine.number(e["amount"]) for e in purchases)),730309.57)
		self.assertTrue(all(e["adjustment"] == 0 for e in purchases))

	def test_scenario_b_documented_non_return_credits(self):
		r = self.build(approved=True, exclude_advances=True)
		boxes = {b["box"]:b for b in r["boxes"]}
		self.assertEqual(boxes["14"]["amount"],17949.93)
		self.assertEqual(engine.money(sum(engine.number(row["control_movement"]) for row in r["audit_rows"])), -49315.77)
