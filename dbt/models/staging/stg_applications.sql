-- One row per loan application.
select
    application_id,
    customer_id,
    decided_at,
    _run_id as loaded_by_run_id
from {{ source('raw', 'applications') }}
