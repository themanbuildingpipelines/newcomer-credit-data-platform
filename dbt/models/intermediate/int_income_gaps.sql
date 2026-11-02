-- Days between consecutive payments from the same source, per application.
-- Dates are taken in UTC on purpose, so the answer never depends on
-- the time zone of whoever runs the query.

select
    *,
    (event_at at time zone 'UTC')::date
      - lag((event_at at time zone 'UTC')::date) over (
            partition by application_id, counterparty
            order by event_at
        ) as gap_days
from {{ ref('int_income_known_at_decision') }}