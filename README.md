# Newcomer Credit Data Platform

Picture this...

A nurse moves from Nairobi to Manchester. She has a steady salary, pays her rent on time, and sends money home every month. A UK lender still sees almost nothing, because her credit history stayed behind when she left.

This project builds the system a lender would need to see her clearly. It gathers her everyday financial records. These includes her salary coming in, her bills going out, the money she sends home. It turns them into a fair picture of what she can afford. And it makes sure that picture is built only from what the lender could have known on the day they made their decision.

<img width="1536" height="1024" alt="c39826e8-3df9-44d1-bef3-500bf63c3c70" src="https://github.com/user-attachments/assets/ce2d613b-9e10-4890-9efe-901ae5e5cf14" />


> [!IMPORTANT]
> **This is a data engineering portfolio project**. It is not a credit-risk model, and nothing here should be used to approve, decline, price or rank a real customer.

## Contents

- [Read this repo in five minutes](#read-this-repo-in-five-minutes)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Why I had to Synthesise the Data](#why-I-had-to-Synthesize-the-Data)
- [How the tables fit together](#how-the-tables-fit-together)
- [Feature definitions](#feature-definitions)
- [Point-in-time correctness](#point-in-time-correctness)
- [Test evidence](#test-evidence)
- [Design Decisions I Made](#design-decisions-I-made)
- [What doesn't work yet](#what-doesnt-work-yet)
- [Repository layout](#repository-layout)
- [Responsible use](#responsible-use)
- [Why I built this](#why-i-built-this)
  
---

## Read this Repo in Under Five Minutes

If you only have a few minutes, look at these three things in order.
 
1. **[`tests/temporal/test_point_in_time.py`](tests/temporal/)** shows that a transaction arriving after a decision can never change that decision's features. This is the hardest problem in the project.
2. **[`docs/defect_log.md`](docs/defect_log.md)** records every defect I deliberately planted, the test that caught it, and the fix.
3. **[`docs/feature_validation.md`](docs/feature_validation.md)** shows whether customers the features rated as affordable actually repaid more often.

---

## Quick Start

You need Python 3.12, PostgreSQL 17 running locally and `make`. It runs comfortably on a 16GB laptop.
 
```bash
git clone https://github.com/<your-username>/newcomer-credit-platform
cd newcomer-credit-platform
cp .env.example .env      # add your local Postgres connection details
 
make setup    # create a virtual environment and install dependencies
make seed     # generate the synthetic population (same output every run)
make run      # ingestion, dbt models and quality checks via Dagster
make serve    # start the feature API on localhost:8000
make test     # run pytest and dbt tests
```
Then try it:
 
```bash
curl localhost:8000/features/application/APP-000042
```

## How it Works

<img width="1672" height="941" alt="74d142f5-33ea-43c5-a48f-7dd64e51a6c5" src="https://github.com/user-attachments/assets/d0334f39-1172-42a7-afd6-4cbd031ccf6d" />

Raw data is never overwritten. Every derived table can be traced back to its source records through dbt docs and the Dagster asset graph.

**Stack**: Python, PostgreSQL, dbt Core, Dagster, FastAPI, pytest and GitHub Actions.

## Why I had to Synthesize the Customer Data

Real lending data is private, and that's how it should be. So the core of this project runs on a synthetic population that I generate, with one important twist.
 
Every synthetic customer is created first, before any of their data. The generator decides when they arrived and how they earn. It decides what they pay in rent and whether they send money home. Then it gives each person a hidden **true affordability** score that never appears in any table the pipeline can see.
 
Everything else is generated from that profile. Transactions, remittances, loan applications and repayments all flow from who the customer is. On top of that, the generator plants problems on purpose. Some records arrive late. Some are duplicated. Some transfers fail or get reversed. Merchant names come through messy.
 
This gives the pipeline something real to prove. If the features work, customers they rate as affordable should repay more often. If future data leaks into past decisions, the results come out suspiciously perfect, and that becomes its own alarm.
 
**What this proves, and what it doesn't.** It proves the pipeline can recover a real signal from messy, late and conflicting data. It says nothing about how actual newcomers manage money, because repayment behaviour comes from my generator's assumptions. That limit is deliberate and stated, not hidden.
 
A separate public credit dataset sits alongside the synthetic world as a real-data module. It never joins to the synthetic customers. Its job is to show the pipeline handling data nobody designed.
 
| | |
|---|---|
| Customers | `TBD` |
| Transactions | `TBD` |
| Deterministic across runs | Verified in CI: `TBD` |
 
---

## How the Tables Fit Together 

Everything hangs off one key: `customer_id`. That's what makes the synthetic world joinable from the first transaction to the final repayment.
 
```mermaid
erDiagram
    customers ||--o{ bank_transactions : "customer_id"
    customers ||--o{ remittances : "customer_id"
    customers ||--o{ applications : "customer_id"
    remittances ||--o{ processor_events : "remittance_id"
    applications ||--o{ repayments : "application_id"
    applications ||--|| feature_snapshots : "application_id"
    fx_rates }o..o{ remittances : "as-of date"
```
 
Two tables are deliberately kept away from features. `repayments` holds outcomes that happen after a decision, so it only joins later, to check whether the features worked. `generator_truth` holds the hidden affordability scores and is used only to grade the pipeline.
 
---
## Feature definitions

Every feature has a written definition and a version number. Changing a definition takes a pull request, passing tests, and an entry in [`features/CHANGELOG.md`](features/CHANGELOG.md) showing the old and new values side by side.
 
| Feature | Definition (v1) |
|---|---|
| **Income regularity** | Credits from the same source arriving every 25 to 35 days, at least three times in six months, with amounts within 20% of the median. Reports how often income arrives and how much it varies. |
| **Recurring obligations** | Payments to the same recipient at least three times in six months on a regular rhythm. Each one is tagged with a category and a confidence score. |
| **Estimated disposable income** | Average monthly eligible income minus average monthly recurring obligations over the lookback window. |
| **Remittance summary** | How often someone sends money, how much, what it costs, and how often it fails. Descriptive only. Sending money home is never treated as proof of anything. |
 
These thresholds are starting assumptions. I expect to revise them, and every revision is logged.
 
---

## Point-in-time Correctness

This is the part of the project I care about most.
 
When a lender decides on an application, they can only use what they knew at that moment. A pipeline that quietly uses later data produces features that look brilliant in testing and fail in real life.
 
Every transaction here carries three timestamps:
 
- **Event time:** when the transaction happened
- **Booking time:** when the bank recorded it
- **Ingestion time:** when this pipeline received it
A feature for an application decided on 1 June can only use records the pipeline had received by that moment. A payment that happened in May but arrived on 15 June does not count.
 
The platform answers two questions separately.
 
**What did we know at decision time?** Features are frozen at the moment of decision into an append-only table. They never change afterwards.
 
**What do we know now?** Features can be recomputed for any date using everything available today.
 
The gap between the two shows how much late data would have changed a decision. Exchange rates follow the same rule: a remittance only ever uses a rate that was published before it.
 
---

## Test Evidence

A green checkmark proves nothing on its own. Every result below comes from a test that checks a specific value or catches a specific planted defect.
 
| Area | What the test proves | Result |
|---|---|---|
| Generator | Same seed gives identical data. Planted defect rates match the config. No transaction happens before a customer arrives. | `TBD` |
| Ingestion | Malformed records are caught. Loading the same file twice creates no duplicates. | `TBD` |
| Schema changes | A renamed source column is detected and fails loudly. | `TBD` |
| Calculations | dbt tests pass, and hand-worked cases match. £2,000 income minus £700 obligations gives £1,300. | `TBD` |
| Incremental models | An incremental build matches a full rebuild, even after late records arrive. | `TBD` |
| Reconciliation | Every planted mismatch between the ledger and the processor is either reconciled or logged. Nothing disappears silently. | `TBD` |
| Point-in-time | A record received after a decision never changes that decision's features. Frozen snapshots never change. | `TBD` |
| Feature validity | Repayment rates rise across feature bands. A result that's too perfect triggers the leakage alarm. | `TBD` |
| Orchestration | A failed ingestion step is visible, and nothing downstream pretends to be fresh. Reruns recover cleanly. | `TBD` |
| API | Valid, unknown and invalid IDs return the right responses. Latency measured on stated hardware. | `TBD` |
| Categorisation | Rules versus an LLM, compared on a hand-labelled set the rules never saw. | `TBD` |
| Reproducibility | A fresh machine following this README gets the same results. CI runs on every push. | `TBD` |
 
The strongest evidence lives in [`docs/defect_log.md`](docs/defect_log.md). For each planted defect, it shows the test failing, the fix, and the test passing.
 
---

## Design Decisions I Made

A few choices that shaped the project, and why I made them.
 
**PostgreSQL instead of Snowflake.** It's free, runs locally and keeps the project reproducible for anyone. dbt keeps the SQL portable, so moving to a cloud warehouse later is a configuration change, not a rewrite.
 
**Frozen snapshots instead of recomputing features.** Recomputing is simpler, but it can't answer "what did we know at the time?" Lenders need that answer for audits and disputes, so the platform stores both.
 
**One synthetic world instead of several datasets.** An earlier version of this plan stitched together sources that described different people. Nothing could join, so nothing could be validated. One linked population fixed that.
 
**A hand-written test set for categorisation.** If I generated test descriptions from the same templates as the training data, any rule-based approach would score near perfectly and the comparison would mean nothing.
 
---

## What Doesn't Work Yet

This section is honest by design. If something is broken, skipped or simplified, it goes here.
 
- `TBD: list real gaps, skipped tests and shortcuts as the build progresses`
- The validation loop is partly circular. Features and outcomes both come from the same hidden score, so this shows the pipeline preserves a planted signal through messy data. Nothing more.
- Public credit datasets carry historical, geographic and population biases.
---

## Responsible use
 
This is not a credit-risk model. Synthetic outcomes reflect my generator's assumptions, not real behaviour. The only identities in the system are synthetic, and identifiers are masked in every demonstration. Analysts and the API use separate database roles, so sensitive fields stay restricted.
 
Nationality, immigration status and remittance habits are never used as features or as stand-ins for whether someone will repay. Any real lending use would need legal review, privacy and security controls, model validation, fairness testing, explainability and human oversight.
 
---
 
## Why I built this
 
I studied actuarial science, so I spent years learning how lenders and insurers think about risk. Now I'm moving into data engineering, and I wanted my first serious project to sit right where those two worlds meet.
 
The problem also isn't abstract to me. Plenty of people I know have moved abroad with solid financial lives and arrived as strangers to the local credit system. This project is my attempt to understand, from the data side, what it would take to see them clearly.
 
I'm documenting the build as I go. You can follow along at [jimmyokoth.com](https://jimmyokoth.com).
 
---

**Jimmy Okoth** · Nairobi, Kenya · [LinkedIn](https://linkedin.com/in/jimthedataguy) · [GitHub](https://github.com/themanbuildingpipelines)
