# Feature changelog

Every feature definition is written here before it's built, and every change gets a new version.
A change needs a pull request, passing tests, and an entry below showing what changed and why.

## income_regularity v1 (2026-10-27)

**Question it answers:** does this applicant have a steady, predictable income?

**Data allowed:** only incoming money (credits) the lender could see at decision time
(`available_at <= decided_at`), from the 6 months before the decision.

**Definition:** for each source of incoming money:
- at least 3 payments
- median gap between payments of 25 to 35 days
- every payment within 20% of that source's median amount

The main income source is the one with the most payments (ties broken by largest total).
An application with no qualifying source still gets a row, with `is_regular_income = false`.

**Known limitation:** generator v1 only creates salaried customers, so every real application
is currently regular. The "not regular" logic is proven with a dbt unit test using hand-made
rows until generator v2 adds gig income.

**Thresholds are starting assumptions** and will be revisited once there's data to test them against.
