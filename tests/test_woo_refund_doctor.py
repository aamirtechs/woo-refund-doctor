"""Tests for woo_refund_doctor."""

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import woo_refund_doctor as wrd


def row(**overrides):
    """A clean refund row, with optional field overrides."""
    base = {"refund_id": "R-1", "order_id": "5001",
            "product": "Canvas Tote Bag", "variation": "Natural",
            "customer_email": "a@example.com",
            "order_date": "2026-10-01", "refund_date": "2026-10-03",
            "refund_amount": "10.00", "order_total": "25.00",
            "reason": "Changed my mind", "status": "completed"}
    base.update(overrides)
    return base


def rules(findings):
    """Return the sorted rule names of a findings list."""
    return sorted(f.rule for f in findings)


def audit_single(overrides, **kwargs):
    """Audit one row with defaults for the summary-level checks."""
    kwargs.setdefault("max_rate", 20.0)
    kwargs.setdefault("max_days", 30)
    kwargs.setdefault("high_value", Decimal("100"))
    findings, _ = wrd.audit([row(**overrides)], **kwargs)
    return findings


class TestAuditRow(unittest.TestCase):
    def test_clean_refund(self):
        self.assertEqual(audit_single({}), [])

    def test_partial_refund_is_clean(self):
        findings = audit_single({"refund_amount": "24.99",
                                 "order_total": "25.00"})
        self.assertEqual(findings, [])

    def test_refund_over_total_is_error(self):
        findings = audit_single({"refund_amount": "150.00",
                                 "order_total": "120.00"})
        self.assertEqual(rules(findings), ["refund-over-total"])
        self.assertEqual(findings[0].severity, "error")

    def test_full_refund_high_value_is_error(self):
        findings = audit_single({"refund_amount": "120.00",
                                 "order_total": "120.00"})
        self.assertEqual(rules(findings), ["full-refund-high-value"])
        self.assertEqual(findings[0].severity, "error")

    def test_full_refund_below_high_value_is_clean(self):
        findings = audit_single({"refund_amount": "25.00",
                                 "order_total": "25.00"})
        self.assertEqual(findings, [])

    def test_high_value_flag_raises_threshold(self):
        findings = audit_single({"refund_amount": "120.00",
                                 "order_total": "120.00"},
                                high_value=Decimal("200"))
        self.assertEqual(findings, [])

    def test_refund_before_order_is_error(self):
        findings = audit_single({"order_date": "2026-10-14",
                                 "refund_date": "2026-10-10"})
        self.assertEqual(rules(findings), ["refund-before-order"])
        self.assertEqual(findings[0].severity, "error")

    def test_late_refund_warning(self):
        findings = audit_single({"order_date": "2026-08-01",
                                 "refund_date": "2026-10-15"})
        self.assertEqual(rules(findings), ["late-refund"])
        self.assertEqual(findings[0].severity, "warning")
        self.assertIn("75 days", findings[0].message)

    def test_very_late_refund_is_error(self):
        findings = audit_single({"order_date": "2026-06-01",
                                 "refund_date": "2026-10-20"})
        self.assertEqual(rules(findings), ["late-refund"])
        self.assertEqual(findings[0].severity, "error")

    def test_refund_on_max_days_is_clean(self):
        findings = audit_single({"order_date": "2026-09-01",
                                 "refund_date": "2026-10-01"})
        self.assertEqual(findings, [])

    def test_max_days_flag(self):
        findings = audit_single({"order_date": "2026-08-01",
                                 "refund_date": "2026-10-15"},
                                max_days=90)
        self.assertEqual(findings, [])

    def test_same_day_refund_is_clean(self):
        findings = audit_single({"refund_date": "2026-10-01"})
        self.assertEqual(findings, [])

    def test_duplicate_refund_id(self):
        findings, _ = wrd.audit(
            [row(), row(refund_id="R-1", order_id="5002")],
            20.0, 30, Decimal("100"))
        self.assertIn("duplicate-refund-id", rules(findings))
        self.assertIn("5001", [f.message for f in findings
                               if f.rule == "duplicate-refund-id"][0])

    def test_missing_refund_id(self):
        findings = audit_single({"refund_id": ""})
        self.assertEqual(rules(findings), ["missing-refund-id"])

    def test_missing_order_id(self):
        findings = audit_single({"order_id": ""})
        self.assertEqual(rules(findings), ["missing-order-id"])

    def test_missing_product(self):
        findings = audit_single({"product": ""})
        self.assertEqual(rules(findings), ["missing-product"])

    def test_missing_customer_email_is_warning(self):
        findings = audit_single({"customer_email": ""})
        self.assertEqual(rules(findings), ["missing-customer-email"])
        self.assertEqual(findings[0].severity, "warning")

    def test_missing_reason_is_warning(self):
        findings = audit_single({"reason": ""})
        self.assertEqual(rules(findings), ["missing-reason"])
        self.assertEqual(findings[0].severity, "warning")

    def test_invalid_refund_amount(self):
        findings = audit_single({"refund_amount": "not-a-number"})
        self.assertEqual(rules(findings), ["invalid-refund-amount"])

    def test_invalid_order_total(self):
        findings = audit_single({"order_total": "abc"})
        self.assertEqual(rules(findings), ["invalid-order-total"])

    def test_negative_refund_amount(self):
        findings = audit_single({"refund_amount": "-5.00"})
        self.assertEqual(rules(findings), ["negative-refund-amount"])

    def test_negative_order_total(self):
        findings = audit_single({"order_total": "-25.00"})
        self.assertEqual(rules(findings),
                         ["negative-order-total", "refund-over-total"])

    def test_invalid_order_date(self):
        findings = audit_single({"order_date": "not-a-date"})
        self.assertEqual(rules(findings), ["invalid-order-date"])

    def test_invalid_refund_date(self):
        findings = audit_single({"refund_date": "32/13/2026"})
        self.assertEqual(rules(findings), ["invalid-refund-date"])

    def test_day_first_date_parses(self):
        findings = audit_single({"order_date": "01/10/2026",
                                 "refund_date": "03/10/2026"})
        self.assertEqual(findings, [])

    def test_dollar_sign_and_commas_parse(self):
        findings = audit_single({"refund_amount": "$1,200.00",
                                 "order_total": "$1,200.00"},
                                high_value=Decimal("2000"))
        self.assertEqual(findings, [])

    def test_decimal_math_is_exact(self):
        self.assertEqual(wrd.parse_money("0.10", "R-1", "refund_amount")
                         + wrd.parse_money("0.20", "R-1",
                                           "refund_amount"),
                         Decimal("0.30"))

    def test_money_format(self):
        self.assertEqual(wrd.money_str(Decimal("25")), "$25.00")
        self.assertEqual(wrd.money_str(Decimal("999.98")), "$999.98")


class TestSummaryChecks(unittest.TestCase):
    def test_product_over_max_rate(self):
        rows = [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                    customer_email="c%d@example.com" % i)
                for i in range(4)]
        rows.append(row(refund_id="R-9", order_id="5999",
                        product="Other Product",
                        customer_email="z@example.com"))
        findings, report = wrd.audit(rows, 20.0, 30, Decimal("100"))
        self.assertIn("product-over-max-rate", rules(findings))
        flagged = [f for f in findings
                   if f.rule == "product-over-max-rate"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].code, "Canvas Tote Bag")
        self.assertEqual(flagged[0].severity, "error")
        self.assertEqual(report["products"][0]["product"],
                         "Canvas Tote Bag")
        self.assertEqual(report["products"][0]["share"], "80.0%")

    def test_product_at_threshold_is_not_flagged(self):
        rows = [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                    customer_email="c%d@example.com" % i,
                    product="Product %d" % i,
                    reason="Reason %d" % i)
                for i in range(5)]
        findings, _ = wrd.audit(rows, 20.0, 30, Decimal("100"))
        self.assertNotIn("product-over-max-rate", rules(findings))

    def test_max_rate_flag(self):
        rows = [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                    customer_email="c%d@example.com" % i)
                for i in range(4)]
        rows.append(row(refund_id="R-9", order_id="5999",
                        product="Other Product",
                        customer_email="z@example.com"))
        findings, _ = wrd.audit(rows, 90.0, 30, Decimal("100"))
        self.assertNotIn("product-over-max-rate", rules(findings))

    def test_repeat_refunder_two_is_warning(self):
        rows = [row(refund_id="R-1", order_id="5001"),
                row(refund_id="R-2", order_id="5002")]
        findings, _ = wrd.audit(rows, 20.0, 30, Decimal("100"))
        flagged = [f for f in findings if f.rule == "repeat-refunder"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].severity, "warning")

    def test_repeat_refunder_three_is_error(self):
        rows = [row(refund_id="R-%d" % i, order_id=str(5000 + i))
                for i in range(1, 4)]
        findings, _ = wrd.audit(rows, 20.0, 30, Decimal("100"))
        flagged = [f for f in findings if f.rule == "repeat-refunder"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].severity, "error")
        self.assertIn("3 times", flagged[0].message)

    def test_reason_cluster_flagged(self):
        rows = [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                    customer_email="c%d@example.com" % i,
                    reason="Defective stitching")
                for i in range(4)]
        rows.append(row(refund_id="R-9", order_id="5999",
                        product="Other Product",
                        customer_email="z@example.com",
                        reason="Changed my mind"))
        findings, report = wrd.audit(rows, 20.0, 30, Decimal("100"))
        flagged = [f for f in findings if f.rule == "reason-cluster"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].code, "defective")
        self.assertEqual(flagged[0].severity, "warning")
        self.assertEqual(report["clusters"][0]["keyword"], "defective")
        self.assertEqual(report["clusters"][0]["share"], "80.0%")

    def test_reason_cluster_at_threshold_is_not_flagged(self):
        rows = [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                    customer_email="c%d@example.com" % i,
                    reason="Defective stitching")
                for i in range(1, 3)]
        rows += [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                     customer_email="c%d@example.com" % i,
                     reason="Changed my mind")
                 for i in range(3, 5)]
        rows += [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                     customer_email="c%d@example.com" % i,
                     reason="Late delivery")
                 for i in range(5, 7)]
        rows += [row(refund_id="R-%d" % i, order_id=str(5000 + i),
                     customer_email="c%d@example.com" % i,
                     reason="Damaged in transit")
                 for i in range(7, 9)]
        findings, _ = wrd.audit(rows, 20.0, 30, Decimal("100"))
        self.assertNotIn("reason-cluster", rules(findings))

    def test_cluster_reason_keywords(self):
        self.assertEqual(wrd.cluster_reason("Damaged in transit"),
                         "damaged")
        self.assertEqual(wrd.cluster_reason("Defective zipper"),
                         "defective")
        self.assertEqual(wrd.cluster_reason("Wrong item sent"),
                         "wrong-item")
        self.assertEqual(wrd.cluster_reason("Too small"),
                         "size-fit")
        self.assertEqual(wrd.cluster_reason("Late delivery"), "late")
        self.assertEqual(wrd.cluster_reason("Poor quality"), "quality")
        self.assertEqual(wrd.cluster_reason("Changed my mind"),
                         "changed-mind")
        self.assertEqual(wrd.cluster_reason("Duplicate charge"),
                         "duplicate")
        self.assertEqual(wrd.cluster_reason("Something else"), "other")
        self.assertIsNone(wrd.cluster_reason(""))
        self.assertIsNone(wrd.cluster_reason(None))

    def test_cluster_first_match_wins(self):
        self.assertEqual(
            wrd.cluster_reason("Too small, wrong size"), "wrong-item")

    def test_variation_table(self):
        rows = [row(refund_id="R-1", order_id="5001"),
                row(refund_id="R-2", order_id="5002",
                    variation="Black"),
                row(refund_id="R-3", order_id="5003",
                    product="Other Product", variation="",
                    customer_email="z@example.com")]
        _, report = wrd.audit(rows, 20.0, 30, Decimal("100"))
        keys = [v["variation"] for v in report["variations"]]
        self.assertIn("Canvas Tote Bag / Natural", keys)
        self.assertIn("Canvas Tote Bag / Black", keys)
        self.assertNotIn("Other Product / ", keys)

    def test_total_refunded_excludes_invalid_amounts(self):
        rows = [row(refund_id="R-1", order_id="5001"),
                row(refund_id="R-2", order_id="5002",
                    refund_amount="not-a-number",
                    customer_email="b@example.com")]
        _, report = wrd.audit(rows, 20.0, 30, Decimal("100"))
        self.assertEqual(report["total_refunded"], "10.00")

    def test_status_filter(self):
        rows = [row(),
                row(refund_id="R-2", order_id="5002", status="pending",
                    refund_amount="150.00", order_total="120.00",
                    customer_email="b@example.com")]
        findings, report = wrd.audit(rows, 20.0, 30, Decimal("100"),
                                     status_filter="completed")
        self.assertEqual(report["refunds"], 1)
        self.assertEqual(findings, [])

    def test_summary_counts(self):
        findings, report = wrd.audit(
            [row(), row(refund_id="R-2", order_id="5002",
                        refund_amount="150.00", order_total="120.00",
                        customer_email="b@example.com")],
            20.0, 30, Decimal("100"))
        summary = wrd.summarize(findings, report)
        self.assertEqual(summary["refunds"], 2)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["warnings"], 0)
        self.assertEqual(summary["total_refunded"], "160.00")

    def test_text_output(self):
        findings, report = wrd.audit(
            [row(refund_id="R-2", order_id="5002",
                 refund_amount="150.00", order_total="120.00",
                 customer_email="b@example.com")],
            20.0, 30, Decimal("100"))
        text = wrd.format_text(findings, report,
                               wrd.summarize(findings, report))
        self.assertIn("refund-over-total", text)
        self.assertIn("errors: 1", text)
        self.assertIn("Refund rate by product", text)
        self.assertIn("Total refunded: $150.00", text)

    def test_clean_text_output(self):
        findings, report = wrd.audit([row()], 20.0, 30, Decimal("100"))
        text = wrd.format_text(findings, report,
                               wrd.summarize(findings, report))
        self.assertIn("All refunds clean.", text)


class TestCli(unittest.TestCase):
    def run_cli(self, args, content):
        """Run main() against a temp CSV file, capturing stdout."""
        with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                        delete=False) as handle:
            handle.write(content)
            path = handle.name
        try:
            saved = sys.stdout
            sys.stdout = io.StringIO()
            try:
                code = wrd.main([path] + args)
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = saved
            return code, output
        finally:
            os.unlink(path)

    HEADER = ("refund_id,order_id,product,variation,customer_email,"
              "order_date,refund_date,refund_amount,order_total,"
              "reason,status\n")
    CLEAN_CSV = HEADER + ("R-1,5001,Canvas Tote Bag,Natural,"
                          "a@example.com,2026-10-01,2026-10-03,10.00,"
                          "25.00,Changed my mind,completed\n")
    BAD_CSV = HEADER + ("R-1,5001,Canvas Tote Bag,Natural,"
                        "a@example.com,2026-10-01,2026-10-03,150.00,"
                        "120.00,Changed my mind,completed\n")
    WARN_CSV = HEADER + ("R-1,5001,Canvas Tote Bag,Natural,"
                         "a@example.com,2026-10-01,2026-10-03,10.00,"
                         "25.00,,completed\n")

    def test_cli_clean_exit_zero(self):
        code, output = self.run_cli([], self.CLEAN_CSV)
        self.assertEqual(code, 0)
        self.assertIn("All refunds clean.", output)

    def test_cli_check_fails_on_error(self):
        code, output = self.run_cli(["--check"], self.BAD_CSV)
        self.assertEqual(code, 1)
        self.assertIn("refund-over-total", output)

    def test_cli_check_passes_on_warnings_only(self):
        code, output = self.run_cli(["--check"], self.WARN_CSV)
        self.assertEqual(code, 0)
        self.assertIn("missing-reason", output)

    def test_cli_strict_fails_on_warning(self):
        code, output = self.run_cli(["--check", "--strict"],
                                    self.WARN_CSV)
        self.assertEqual(code, 1)

    def test_cli_json_flag(self):
        code, output = self.run_cli(["--json"], self.BAD_CSV)
        self.assertEqual(code, 0)
        parsed = json.loads(output)
        self.assertEqual(parsed["summary"]["errors"], 1)
        self.assertEqual(parsed["findings"][0]["rule"],
                         "refund-over-total")
        self.assertEqual(parsed["products"][0]["product"],
                         "Canvas Tote Bag")
        self.assertEqual(parsed["summary"]["total_refunded"],
                         "150.00")

    def test_cli_max_rate_flag(self):
        code, output = self.run_cli(["--max-rate", "90"], self.CLEAN_CSV)
        self.assertEqual(code, 0)
        self.assertIn("All refunds clean.", output)

    def test_cli_bad_max_rate(self):
        code, output = self.run_cli(["--max-rate", "150"],
                                    self.CLEAN_CSV)
        self.assertEqual(code, 2)

    def test_cli_bad_max_days(self):
        code, output = self.run_cli(["--max-days", "-1"],
                                    self.CLEAN_CSV)
        self.assertEqual(code, 2)

    def test_cli_out_flag(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                        delete=False) as handle:
            handle.write(self.CLEAN_CSV)
            path = handle.name
        out_path = path + ".out"
        try:
            code = wrd.main([path, "--out", out_path])
            self.assertEqual(code, 0)
            with open(out_path, encoding="utf-8") as handle:
                self.assertIn("All refunds clean.", handle.read())
        finally:
            os.unlink(path)
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_cli_missing_file(self):
        code = wrd.main(["/nonexistent/refunds.csv"])
        self.assertEqual(code, 2)

    def test_cli_bom_header(self):
        code, output = self.run_cli([], "\ufeff" + self.CLEAN_CSV)
        self.assertEqual(code, 0)
        self.assertIn("All refunds clean.", output)


if __name__ == "__main__":
    unittest.main()
