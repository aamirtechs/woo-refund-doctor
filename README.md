# woo-refund-doctor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/woo-refund-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/woo-refund-doctor/issues)

A zero-dependency Python CLI that audits a WooCommerce refunds CSV
export for the patterns that point at a product, listing, or
fulfilment problem: one product taking a large share of all
refunds, the same customer refunding again and again, refunds
that arrive long after the purchase, full refunds on high-value
orders, and refunds larger than the order total.

WooCommerce Analytics shows refund totals only, with no
product-level breakdown, and the product views come from paid
tools. The usual answer is manual spreadsheet work. This tool is
the offline audit: it reads the exported CSV, prints the refund
rate by product and variation, clusters refund reasons by keyword,
and flags every problem with a rule name and a severity. It never
touches your store.

## Install

Requires Python 3.10 or newer. No dependencies beyond the standard
library.

```bash
pip install woo-refund-doctor
```

Or run it straight from the source checkout:

```bash
python3 woo_refund_doctor.py examples/refunds.csv
```

## Input format

A CSV export with a header row. Columns used: `refund_id`,
`order_id`, `product`, `variation`, `customer_email`,
`order_date`, `refund_date`, `refund_amount`, `order_total`,
`reason`, `status`. Extra columns are ignored, so a full
WooCommerce export works as-is. Dates accept ISO form
(2026-10-05) and day-first form (05/10/2026). Money accepts a
leading `$` and thousands separators. A UTF-8 BOM header is
handled. Money is handled with Decimal throughout, so refund
totals are exact to the cent.

```csv
refund_id,order_id,product,variation,customer_email,order_date,refund_date,refund_amount,order_total,reason,status
R-1001,5001,Canvas Tote Bag,Natural,a@example.com,2026-10-01,2026-10-05,25.00,25.00,Changed my mind,completed
R-1002,5002,Leather Wallet,Brown,b@example.com,2026-09-15,2026-09-20,89.99,89.99,Defective stitching,completed
R-1003,5003,Silk Scarf,Red,c@example.com,2026-10-02,2026-10-03,45.00,60.00,Wrong item sent,completed
```

## What it checks

Errors, the ones that cost money or break the books:

* `refund-over-total`: refunded more than the order total.
* `full-refund-high-value`: full refund on an order at or above
  `--high-value` (default 100).
* `product-over-max-rate`: a product takes more than `--max-rate`
  percent of all refunds (default 20.0).
* `repeat-refunder`: the same customer has refunded 3 or more
  times.
* `refund-before-order`: refunded before the order date.
* `late-refund`: refunded more than 90 days after purchase.
* `duplicate-refund-id`: the same refund ID twice.
* `invalid-refund-amount`, `invalid-order-total`,
  `negative-refund-amount`, `negative-order-total`,
  `invalid-order-date`, `invalid-refund-date`: unparseable or
  impossible values.
* `missing-refund-id`, `missing-order-id`, `missing-product`:
  empty identifying fields.

Warnings, patterns worth investigating:

* `late-refund`: refunded more than `--max-days` after purchase
  (default 30), up to 90 days.
* `repeat-refunder`: the same customer has refunded twice.
* `reason-cluster`: one keyword accounts for more than 25 percent
  of refunds with a reason.
* `missing-reason`: no refund reason given.
* `missing-customer-email`: empty email, so repeat-refunder
  checks cannot see this refund.

The report also prints three tables after the findings: refund
rate by product (share of all refunds), refunds by variation
where a variation has 2 or more refunds, and refund reasons by
keyword (share of refunds with a reason). Reason keywords are
checked in order, so "Too small, wrong size" counts as
wrong-item: damaged, defective, wrong-item, size-fit, late,
quality, changed-mind, duplicate, other.

## Usage

```bash
python3 woo_refund_doctor.py examples/refunds.csv
```

Captured output:

```
ERROR [full-refund-high-value] R-1004: full refund of $120.00 on a high-value order
WARNING [late-refund] R-1004: refunded 75 days after purchase
ERROR [refund-over-total] R-1005: refunded $150.00 on an order totalling $120.00
ERROR [full-refund-high-value] R-1009: full refund of $120.00 on a high-value order
WARNING [missing-reason] R-1010: no refund reason given
ERROR [duplicate-refund-id] R-1001: refund_id duplicates order 5001
ERROR [full-refund-high-value] R-1013: full refund of $110.00 on a high-value order
ERROR [refund-before-order] R-1013: refunded on 2026-10-10, before the order date 2026-10-14
ERROR [invalid-refund-amount] R-1014: refund R-1014: refund_amount is not a money value: 'not-a-number'
ERROR [late-refund] R-1016: refunded 141 days after purchase
ERROR [product-over-max-rate] Wool Sweater: 4 of 16 refunds (25.0%) are for this product, above the 20.0% threshold
ERROR [repeat-refunder] a@example.com: this customer has refunded 3 times
WARNING [reason-cluster] defective: 4 of 15 refunds with a reason (26.7%) are about defective

Refund rate by product (share of all refunds):
  Wool Sweater             4 refunds    $300.00  25.0%
  Canvas Tote Bag          3 refunds     $75.00  18.8%
  Denim Jacket             3 refunds    $310.00  18.8%
  Leather Wallet           3 refunds    $219.98  18.8%
  Silk Scarf               3 refunds     $95.00  18.8%

Refunds by variation (2 or more):
  Canvas Tote Bag / Natural          2 refunds     $50.00  12.5%
  Leather Wallet / Brown             2 refunds    $179.98  12.5%
  Wool Sweater / Large               2 refunds    $240.00  12.5%

Refund reasons by keyword (share of refunds with a reason):
  defective        4 refunds  26.7%
  changed-mind     3 refunds  20.0%
  damaged          3 refunds  20.0%
  wrong-item       3 refunds  20.0%
  duplicate        1 refund  6.7%
  late             1 refund  6.7%

Refunds: 16, findings: 13, errors: 10, warnings: 3
Total refunded: $999.98
```

The sample has 16 refunds and 13 findings. The story it tells:
Wool Sweater takes a quarter of all refunds, a@example.com has
refunded three times, defective is the dominant reason cluster,
and R-1005 was refunded $150.00 on a $120.00 order. The Denim
Jacket is the biggest money leak at $310.00 refunded even though
it is only 3 of 16 refunds.

Use it as a CI gate: `--check` exits 1 when any error is found,
and 0 otherwise. On the sample above it exits 1:

```bash
python3 woo_refund_doctor.py examples/refunds.csv --check
```

On `examples/clean.csv`, five clean partial refunds, it exits 0:

```
Refund rate by product (share of all refunds):
  Canvas Tote Bag          1 refund     $10.00  20.0%
  Denim Jacket             1 refund     $25.00  20.0%
  Leather Wallet           1 refund     $15.00  20.0%
  Silk Scarf               1 refund     $20.00  20.0%
  Wool Sweater             1 refund     $30.00  20.0%

Refund reasons by keyword (share of refunds with a reason):
  changed-mind     1 refund  20.0%
  damaged          1 refund  20.0%
  defective        1 refund  20.0%
  late             1 refund  20.0%
  wrong-item       1 refund  20.0%

Refunds: 5, findings: 0, errors: 0, warnings: 0
Total refunded: $100.00
All refunds clean.
```

With `--strict`, `--check` also fails on warnings: a file with a
single warning (one refund with no reason) exits 0 under
`--check` and 1 under `--check --strict`. `--json` emits the
summary, product and variation tables, reason clusters, and
findings as JSON, and `--out` writes the report to a file.
`--status completed` audits only completed refunds. Raising the
threshold changes the verdict: `--max-rate 30` on the sample
drops the Wool Sweater finding and leaves 12 findings, 9 errors
and 3 warnings.

## Options

| Flag | Meaning |
| --- | --- |
| `--max-rate` | Flag products above this share of all refunds, in percent (default: 20.0) |
| `--max-days` | Flag refunds more than this many days after purchase (default: 30) |
| `--high-value` | Full refunds at or above this order total are flagged (default: 100) |
| `--status` | Only audit refunds with this status, for example completed |
| `--json` | Emit JSON instead of text |
| `--check` | Exit 1 if any error is found |
| `--strict` | With --check, also exit 1 on warnings |
| `--out` | Write the report to a file |

## Edge cases

* A refund equal to the order total below `--high-value` is not
  flagged; only full refunds on high-value orders are errors.
* A product at exactly the `--max-rate` threshold is not flagged;
  the share must be strictly above it.
* A reason cluster at exactly 25 percent is not flagged; the
  share must be strictly above it.
* Product rates and reason clusters need at least 5 refunds (5
  refunds with a reason for clusters) before they count as a
  pattern; rates from fewer refunds are noise.
* A refund more than `--max-days` after purchase is a warning up
  to 90 days, and an error past 90 days.
* Rows with an invalid refund amount are excluded from the
  refunded money totals but still count in the product refund
  counts.
* A refund dated before its order date is an error and is not
  also checked for lateness.
* Duplicate refund IDs are detected on the refund ID alone; the
  finding names the order of the first row with that ID.
* A missing customer email is a warning, and that row is excluded
  from repeat-refunder counts.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

54 tests, all passing: every rule, error and warning severities,
Decimal money math, product and variation tables, reason
clustering, repeat refunders, threshold flags, summary counts,
JSON output shape, and `--check` and `--strict` exit codes.

## License

MIT. See [LICENSE](LICENSE).
