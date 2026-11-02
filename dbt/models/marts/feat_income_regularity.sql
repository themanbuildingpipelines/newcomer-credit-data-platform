-- Income regularity, version 1. One row per application, always.
--
-- Definition (written down before the SQL, and versioned in features/CHANGELOG.md):
--   For each source of incoming money, in the 6 months before the decision,
--   using only money the lender could see at decision time:
--     - at least 3 payments
--     - median gap between payments of 25 to 35 days
--     - every payment within 20% of that source's median amount
--   The main income source is the one with the most payments (ties: largest total).
--   An application with no qualifying source still gets a row, marked not regular.

with gaps as (
    select * from {{ ref('int_income_gaps') }}
),

source_medians as (
    select
        application_id,
        counterparty,
        count(*)                                              as n_payments,
        sum(amount)                                           as total_amount,
        percentile_cont(0.5) within group (order by amount)   as median_amount,
        percentile_cont(0.5) within group (order by gap_days) as median_gap_days
    from gaps
    group by application_id, counterparty
),

source_stats as (
    select
        m.*,
        bool_and(abs(g.amount - m.median_amount) <= 0.20 * m.median_amount) as amounts_consistent,
        stddev_samp(g.amount) / nullif(avg(g.amount), 0)                    as amount_cv
    from source_medians m
    join gaps g
      on g.application_id = m.application_id
     and g.counterparty   = m.counterparty
    group by m.application_id, m.counterparty, m.n_payments, m.total_amount,
             m.median_amount, m.median_gap_days
),

main_source as (
    select *
    from (
        select
            *,
            row_number() over (
                partition by application_id
                order by n_payments desc, total_amount desc, counterparty
            ) as source_rank
        from source_stats
    ) ranked
    where source_rank = 1
),

applications as (
    select * from {{ ref('stg_applications') }}
)

select
    a.application_id,
    a.customer_id,
    a.decided_at,
    s.counterparty                                  as main_income_source,
    coalesce(s.n_payments, 0)                       as income_payments_6m,
    round(s.median_amount::numeric, 2)              as median_income_amount,
    s.median_gap_days,
    round(s.amount_cv::numeric, 4)                  as income_amount_cv,
    coalesce(
        s.n_payments >= 3
        and s.median_gap_days between 25 and 35
        and s.amounts_consistent,
        false
    )                                               as is_regular_income,
    'v1'                                            as feature_version
from applications a
left join main_source s
    on s.application_id = a.application_id
