-- One row per customer. Staging only cleans and renames: no business logic here.
select
    customer_id,
    arrival_date,
    lower(income_type) as income_type,
    _run_id            as loaded_by_run_id
from {{ source('raw', 'customers') }}
