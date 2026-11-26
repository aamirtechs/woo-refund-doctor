# Changelog

## 1.0.0 - 2026-11-13

Initial release.

* Refund audit over a WooCommerce refunds CSV export: refund rate
  by product and by variation, products above a --max-rate
  threshold, repeat refunders, refunds long after purchase, full
  refunds on high-value orders, refunds over the order total, and
  refund reasons clustered by keyword.
* Data checks: duplicate refund IDs, refunds dated before the
  order date, invalid or negative amounts, invalid dates, and
  missing refund IDs, order IDs, products, customer emails, and
  reasons.
* Money handled with Decimal throughout, so refund totals are
  exact to the cent and never float-rounded.
* Findings carry a code, rule name, severity (error or warning),
  and message; errors and warnings are counted in the summary.
* Text and --json output, --out file output, --max-rate,
  --max-days, and --high-value thresholds, --status filter, and a
  --check CI gate that exits 1 on errors (and on warnings with
  --strict).
* Zero dependencies, Python 3.10 or newer.
