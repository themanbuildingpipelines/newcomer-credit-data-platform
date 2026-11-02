-- One row per transaction, cleaned and given a direction.
select
    transaction_id,
    customer_id,
    amount,
    abs(amount)                                   as amount_abs,
    case when amount > 0 then 'credit'
         when amount < 0 then 'debit'
         else 'zero' end                          as direction,
    upper(currency)                               as currency,
    upper(trim(counterparty))                     as counterparty,
    description,
    event_at,
    booked_at,
    available_at,
    _run_id                                       as loaded_by_run_id
from {{ source('raw', 'bank_transactions') }}
