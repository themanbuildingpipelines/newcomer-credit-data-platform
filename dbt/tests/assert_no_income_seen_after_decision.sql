-- POINT-IN-TIME GUARD.
-- Returns every income event that the lender could NOT have seen at decision time.
-- dbt treats any returned row as a failure, so this must always return nothing.
select application_id, transaction_id, available_at, decided_at
from {{ ref('int_income_known_at_decision') }}
where available_at > decided_at
