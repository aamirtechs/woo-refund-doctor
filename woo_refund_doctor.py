"""WooCommerce refunds audit CLI.

Reads a WooCommerce refunds CSV export and audits every refund for
the patterns that point at a product, listing, or fulfilment
problem: one product taking a large share of all refunds, the same
customer refunding again and again, refunds that arrive long after
the purchase, full refunds on high-value orders, refunds larger
than the order total, and refund reasons that cluster around one
keyword.

Each problem is a finding with a code, a rule name, a severity
(error or warning), and a message. Errors are the ones that cost
money or break the books; warnings are patterns worth
investigating. --check exits 1 when any error is found, and
--strict also fails on warnings.

Money is handled with Decimal throughout, so refund totals are
exact to the cent and never float-rounded.

Zero dependencies, Python 3.10 or newer, standard library only.

Usage:
    python3 woo_refund_doctor.py examples/refunds.csv
    python3 woo_refund_doctor.py refunds.csv --json --check
"""

import argparse
import csv
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

__version__ = "1.0.0"

CENT = Decimal("0.01")
DEFAULT_MAX_RATE = 20.0
DEFAULT_MAX_DAYS = 30
DEFAULT_HIGH_VALUE = Decimal("100")
LATE_ERROR_DAYS = 90
CLUSTER_THRESHOLD = 25.0

# Keyword clusters for refund reasons, checked in order. The first
# matching bucket wins, so "damaged in transit" counts as damaged
# even though it also mentions transit.
REASON_KEYWORDS = (
    ("damaged", ("damag", "broken", "torn", "ripped", "cracked",
                 "shattered")),
    ("defective", ("defect", "faulty", "not work", "does not work",
                   "stopped working")),
    ("wrong-item", ("wrong item", "wrong colour", "wrong color",
                    "wrong size", "wrong product", "incorrect item")),
    ("size-fit", ("size", "too small", "too big", "too large",
                  "does not fit", "doesnt fit", "tight", "loose")),
    ("late", ("late", "slow", "delay", "never arrived",
              "did not arrive")),
    ("quality", ("quality", "poor", "cheap", "faded", "flimsy",
                 "bad material")),
    ("changed-mind", ("changed my mind", "no longer want",
                      "do not want", "dont want", "not needed")),
    ("duplicate", ("duplicate", "charged twice", "double charge")),
)


class Finding:
    """One audit finding for one refund, product, or pattern."""

    def __init__(self, code, rule, severity, message):
        self.code = code
        self.rule = rule
        self.severity = severity
        self.message = message

    def as_dict(self):
        """Return the finding as a plain dict."""
        return {"code": self.code, "rule": self.rule,
                "severity": self.severity, "message": self.message}

    def __str__(self):
        return "%s [%s] %s: %s" % (self.severity.upper(), self.rule,
                                   self.code, self.message)


def parse_date(value, code, rule):
    """Parse a date string, or return None when blank.

    Accepts ISO dates (2026-10-05) and day-first forms
    (05/10/2026, 05-10-2026). Raises ValueError on anything else.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("refund %s: %s has an unparseable date: %r"
                     % (code, rule, value))


def parse_money(value, code, field):
    """Parse a money value as Decimal, or return None when blank.

    Strips a leading $ and thousands separators. Raises
    ValueError on anything else.
    """
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError("refund %s: %s is not a money value: %r"
                         % (code, field, value))


def money_str(amount):
    """Format a Decimal as dollars and cents, for example $25.00."""
    return "$%s" % amount.quantize(CENT)


def percent_str(part, whole):
    """Format part over whole as a percent with one decimal."""
    if whole == 0:
        return "0.0%"
    return "%.1f%%" % (100.0 * part / whole)


def cluster_reason(reason):
    """Return the keyword bucket for a refund reason, or 'other'."""
    text = (reason or "").strip().lower()
    if not text:
        return None
    for keyword, words in REASON_KEYWORDS:
        for word in words:
            if word in text:
                return keyword
    return "other"


def audit_row(row, seen_refund_ids, max_days, high_value):
    """Audit one CSV row. Returns a list of Finding objects."""
    findings = []
    refund_id = str(row.get("refund_id") or "").strip()
    display = refund_id if refund_id else "(missing refund id)"

    if not refund_id:
        findings.append(Finding(display, "missing-refund-id", "error",
                                "refund_id is empty"))
    else:
        if refund_id in seen_refund_ids:
            findings.append(Finding(
                refund_id, "duplicate-refund-id", "error",
                "refund_id duplicates order %s"
                % seen_refund_ids[refund_id]))
        else:
            seen_refund_ids[refund_id] = str(
                row.get("order_id") or "").strip()

    order_id = str(row.get("order_id") or "").strip()
    if not order_id:
        findings.append(Finding(display, "missing-order-id", "error",
                                "order_id is empty"))

    product = str(row.get("product") or "").strip()
    if not product:
        findings.append(Finding(display, "missing-product", "error",
                                "product is empty"))

    customer = str(row.get("customer_email") or "").strip()
    if not customer:
        findings.append(Finding(
            display, "missing-customer-email", "warning",
            "customer_email is empty, so repeat-refunder checks "
            "cannot see this refund"))

    reason = str(row.get("reason") or "").strip()
    if not reason:
        findings.append(Finding(display, "missing-reason", "warning",
                                "no refund reason given"))

    try:
        refund_amount = parse_money(row.get("refund_amount"),
                                    display, "refund_amount")
    except ValueError as exc:
        findings.append(Finding(display, "invalid-refund-amount",
                                "error", str(exc)))
        refund_amount = None
    try:
        order_total = parse_money(row.get("order_total"), display,
                                  "order_total")
    except ValueError as exc:
        findings.append(Finding(display, "invalid-order-total",
                                "error", str(exc)))
        order_total = None
    if refund_amount is not None and refund_amount < 0:
        findings.append(Finding(
            display, "negative-refund-amount", "error",
            "refund_amount %s is negative"
            % money_str(refund_amount)))
    if order_total is not None and order_total < 0:
        findings.append(Finding(
            display, "negative-order-total", "error",
            "order_total %s is negative" % money_str(order_total)))
    if refund_amount is not None and order_total is not None:
        if refund_amount > order_total:
            findings.append(Finding(
                display, "refund-over-total", "error",
                "refunded %s on an order totalling %s"
                % (money_str(refund_amount),
                   money_str(order_total))))
        elif refund_amount == order_total and order_total > 0 \
                and order_total >= high_value:
            findings.append(Finding(
                display, "full-refund-high-value", "error",
                "full refund of %s on a high-value order"
                % money_str(refund_amount)))

    try:
        order_date = parse_date(row.get("order_date"), display,
                                "order_date")
    except ValueError as exc:
        findings.append(Finding(display, "invalid-order-date", "error",
                                str(exc)))
        order_date = None
    try:
        refund_date = parse_date(row.get("refund_date"), display,
                                 "refund_date")
    except ValueError as exc:
        findings.append(Finding(display, "invalid-refund-date",
                                "error", str(exc)))
        refund_date = None
    if order_date is not None and refund_date is not None:
        if refund_date < order_date:
            findings.append(Finding(
                display, "refund-before-order", "error",
                "refunded on %s, before the order date %s"
                % (refund_date, order_date)))
        else:
            gap = (refund_date - order_date).days
            if gap > LATE_ERROR_DAYS:
                findings.append(Finding(
                    display, "late-refund", "error",
                    "refunded %d days after purchase" % gap))
            elif gap > max_days:
                findings.append(Finding(
                    display, "late-refund", "warning",
                    "refunded %d days after purchase" % gap))
    return findings


def audit(rows, max_rate, max_days, high_value, status_filter=None):
    """Audit all CSV rows.

    Returns (findings, report) where report holds the per-product
    table, the per-variation table, the reason clusters, and the
    refund totals.
    """
    findings = []
    seen_refund_ids = {}
    refunds_seen = 0
    total_refunded = Decimal("0")
    products = {}
    variations = {}
    customers = {}
    clusters = {}
    reasons_seen = 0

    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status_filter and status != status_filter:
            continue
        refunds_seen += 1
        findings.extend(audit_row(row, seen_refund_ids, max_days,
                                  high_value))

        product = str(row.get("product") or "").strip()
        variation = str(row.get("variation") or "").strip()
        try:
            refund_amount = parse_money(row.get("refund_amount"),
                                        "", "refund_amount")
        except ValueError:
            refund_amount = None
        if product:
            entry = products.setdefault(
                product, {"refunds": 0, "refunded": Decimal("0")})
            entry["refunds"] += 1
            if refund_amount is not None and refund_amount > 0:
                entry["refunded"] += refund_amount
        if product and variation:
            key = "%s / %s" % (product, variation)
            entry = variations.setdefault(
                key, {"refunds": 0, "refunded": Decimal("0")})
            entry["refunds"] += 1
            if refund_amount is not None and refund_amount > 0:
                entry["refunded"] += refund_amount
        if refund_amount is not None and refund_amount > 0:
            total_refunded += refund_amount

        customer = str(row.get("customer_email") or "").strip()
        if customer:
            customers[customer] = customers.get(customer, 0) + 1

        reason = str(row.get("reason") or "").strip()
        if reason:
            reasons_seen += 1
            bucket = cluster_reason(reason)
            clusters[bucket] = clusters.get(bucket, 0) + 1

    # Products above the --max-rate threshold, by share of refunds.
    # Rates from fewer than 5 refunds are noise, so they are not
    # flagged.
    for product in sorted(products):
        entry = products[product]
        share = 100.0 * entry["refunds"] / refunds_seen \
            if refunds_seen else 0.0
        if refunds_seen >= 5 and share > max_rate:
            findings.append(Finding(
                product, "product-over-max-rate", "error",
                "%d of %d refunds (%s) are for this product, "
                "above the %.1f%% threshold"
                % (entry["refunds"], refunds_seen,
                   percent_str(entry["refunds"], refunds_seen),
                   max_rate)))

    # Repeat refunders: 2 refunds is a warning, 3 or more an error.
    for customer in sorted(customers):
        count = customers[customer]
        if count >= 3:
            findings.append(Finding(
                customer, "repeat-refunder", "error",
                "this customer has refunded %d times" % count))
        elif count == 2:
            findings.append(Finding(
                customer, "repeat-refunder", "warning",
                "this customer has refunded %d times" % count))

    # Dominant reason clusters, by share of refunds with a reason.
    # A cluster needs at least 5 refunds with a reason before it
    # counts as a pattern.
    for keyword in sorted(clusters):
        count = clusters[keyword]
        share = 100.0 * count / reasons_seen if reasons_seen else 0.0
        if reasons_seen >= 5 and share > CLUSTER_THRESHOLD:
            findings.append(Finding(
                keyword, "reason-cluster", "warning",
                "%d of %d refunds with a reason (%s) are about %s"
                % (count, reasons_seen,
                   percent_str(count, reasons_seen), keyword)))

    product_rows = [{
        "product": product,
        "refunds": products[product]["refunds"],
        "refunded": str(products[product]["refunded"].quantize(CENT)),
        "share": percent_str(products[product]["refunds"],
                             refunds_seen),
    } for product in sorted(
        products,
        key=lambda p: (-products[p]["refunds"], p))]
    variation_rows = [{
        "variation": key,
        "refunds": variations[key]["refunds"],
        "refunded": str(variations[key]["refunded"].quantize(CENT)),
        "share": percent_str(variations[key]["refunds"],
                             refunds_seen),
    } for key in sorted(
        variations,
        key=lambda k: (-variations[k]["refunds"], k))]
    cluster_rows = [{
        "keyword": keyword,
        "refunds": clusters[keyword],
        "share": percent_str(clusters[keyword], reasons_seen),
    } for keyword in sorted(
        clusters, key=lambda k: (-clusters[k], k))]

    report = {
        "refunds": refunds_seen,
        "total_refunded": str(total_refunded.quantize(CENT)),
        "products": product_rows,
        "variations": variation_rows,
        "clusters": cluster_rows,
    }
    return findings, report


def summarize(findings, report):
    """Count findings by severity."""
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return {"refunds": report["refunds"],
            "total_refunded": report["total_refunded"],
            "findings": len(findings), "errors": errors,
            "warnings": warnings}


def format_text(findings, report, summary):
    """Render findings, tables, and the summary as text."""
    lines = [str(f) for f in findings]
    lines.append("")
    lines.append("Refund rate by product (share of all refunds):")
    for row in report["products"]:
        lines.append("  %-22s %3d %s  %9s  %s"
                     % (row["product"][:22], row["refunds"],
                        "refund" if row["refunds"] == 1 else "refunds",
                        "$" + row["refunded"], row["share"]))
    repeated = [v for v in report["variations"]
                if v["refunds"] >= 2]
    if repeated:
        lines.append("")
        lines.append("Refunds by variation (2 or more):")
        for row in repeated:
            lines.append("  %-32s %3d %s  %9s  %s"
                         % (row["variation"][:32], row["refunds"],
                            "refund" if row["refunds"] == 1
                            else "refunds",
                            "$" + row["refunded"], row["share"]))
    if report["clusters"]:
        lines.append("")
        lines.append("Refund reasons by keyword "
                     "(share of refunds with a reason):")
        for row in report["clusters"]:
            lines.append("  %-14s %3d %s  %s"
                         % (row["keyword"], row["refunds"],
                            "refund" if row["refunds"] == 1
                            else "refunds",
                            row["share"]))
    lines.append("")
    lines.append("Refunds: %d, findings: %d, errors: %d, warnings: %d"
                 % (summary["refunds"], summary["findings"],
                    summary["errors"], summary["warnings"]))
    lines.append("Total refunded: $%s" % summary["total_refunded"])
    if summary["errors"] == 0 and summary["warnings"] == 0:
        lines.append("All refunds clean.")
    return "\n".join(lines) + "\n"


def read_csv(path):
    """Read a refunds CSV export. Returns a list of row dicts."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("%s has no header row" % path)
        return list(reader)


def parse_args(argv):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit a WooCommerce refunds CSV export.")
    parser.add_argument("input", help="refunds CSV export file")
    parser.add_argument("--max-rate", type=float,
                        default=DEFAULT_MAX_RATE,
                        help="flag products above this share of all "
                        "refunds, in percent (default: 20.0)")
    parser.add_argument("--max-days", type=int,
                        default=DEFAULT_MAX_DAYS,
                        help="flag refunds more than this many days "
                        "after purchase (default: 30)")
    parser.add_argument("--high-value", type=Decimal,
                        default=DEFAULT_HIGH_VALUE,
                        help="full refunds at or above this order "
                        "total are flagged (default: 100)")
    parser.add_argument("--status", default=None,
                        help="only audit refunds with this status, "
                        "for example completed")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of text")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any error is found")
    parser.add_argument("--strict", action="store_true",
                        help="with --check, also exit 1 on warnings")
    parser.add_argument("--out", default=None,
                        help="write the report to a file")
    return parser.parse_args(argv)


def main(argv=None):
    """Entry point."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.max_rate < 0 or args.max_rate > 100:
        print("ERROR: --max-rate must be between 0 and 100, got %r"
              % args.max_rate, file=sys.stderr)
        return 2
    if args.max_days < 0:
        print("ERROR: --max-days must be 0 or more, got %r"
              % args.max_days, file=sys.stderr)
        return 2
    try:
        rows = read_csv(args.input)
    except OSError as exc:
        print("ERROR: cannot read %s: %s" % (args.input, exc),
              file=sys.stderr)
        return 2
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    findings, report = audit(
        rows, args.max_rate, args.max_days, args.high_value,
        status_filter=(args.status.strip().lower()
                       if args.status else None))
    summary = summarize(findings, report)
    if args.json:
        import json
        text = json.dumps(
            {"summary": summary, "products": report["products"],
             "variations": report["variations"],
             "clusters": report["clusters"],
             "findings": [f.as_dict() for f in findings]},
            indent=2)
    else:
        text = format_text(findings, report, summary)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            print("ERROR: cannot write %s: %s" % (args.out, exc),
                  file=sys.stderr)
            return 2
    else:
        sys.stdout.write(text)
    if args.check and (summary["errors"]
                       or (args.strict and summary["warnings"])):
        return 1
    return 0


def main_entry():
    """Console script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    main_entry()
