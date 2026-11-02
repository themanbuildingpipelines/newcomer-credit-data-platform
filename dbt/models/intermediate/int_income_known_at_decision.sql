-- For every loan application: the money that came IN to that customer which
-- the lender could actually see at the moment of decision, within the
-- six months before it.
--
-- The single most important line in the project is the first WHERE condition.
-- It uses available_at (when the lender could SEE the money), not event_at
-- (when it happened). A payment that happened before the decision but only
-- arrived after it must not count.

with applications as (
    select * from {{ ref('stg_applications') }}
),

credits as (
    select * from {{ ref('stg_bank_transactions') }}
    where direction = 'credit'
)

select
    a.application_id,
    a.customer_id,
    a.decided_at,
    c.transaction_id,
    c.counterparty,
    c.amount,
    c.event_at,
    c.available_at
from applications a
join credits c
    on c.customer_id = a.customer_id
where c.available_at <= a.decided_at                      -- point in time: no peeking
  and c.event_at     >= a.decided_at - interval '6 months' -- lookback window
