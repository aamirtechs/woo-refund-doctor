# Good first issues

Seeded issues for new contributors. File each one on GitHub with the
`good first issue` and `help wanted` labels.

## 1. Add a refunded-amount share column to the product table

Title: Show each product's share of refunded money, not just count

Description: The product table shows each product's share of refund
count. Add a second share column for refunded money, so a store
owner can see when a cheap, often-refunded product matters less
than an expensive, rarely-refunded one. Keep the count share
column as it is.

Difficulty: Easy

Acceptance criteria: the product table in text output shows both
shares; JSON product rows gain a money_share field; a test checks
both shares for the sample file; README documents the columns.

## 2. Add a per-customer refunded total

Title: Show the total refunded per repeat customer

Description: The repeat-refunder finding names the customer and the
refund count. Extend it to also state the total amount refunded to
that customer, so the owner can see at a glance how much a repeat
refunder has cost the store.

Difficulty: Easy

Acceptance criteria: the repeat-refunder message for the sample
file names a@example.com with 3 refunds and $170.00 refunded; a
test covers the message; README documents the rule.

## 3. Support a custom reason-keyword file

Title: Let stores define their own reason keywords

Description: Add an optional --keywords flag that takes a JSON
file mapping keyword names to word lists, replacing the built-in
reason clusters. Stores phrase reasons differently, so their own
buckets (for example "packaging" or "gift") should be usable
without editing the code.

Difficulty: Medium

Acceptance criteria: a custom keywords file clusters the sample
reasons under the new names; the built-in clusters still apply
without the flag; invalid JSON exits 2 with a clear error; a test
covers both cases; README documents the flag.

## 4. Add a monthly refund-rate trend

Title: Show refunds per month in the summary

Description: Add a small table after the reason clusters showing
refunds per month (by refund_date), with count and total refunded,
so a store owner can see whether refunds are rising or falling
over time.

Difficulty: Easy

Acceptance criteria: the table appears in text output with the
correct months for the sample file; JSON output gains a months
field; a test checks the rows; README documents the table.
