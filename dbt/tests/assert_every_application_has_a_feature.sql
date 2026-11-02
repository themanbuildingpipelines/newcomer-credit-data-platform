-- Every application must get exactly one feature row, even with no income at all.
-- Returns applications that are missing from the feature table.
select a.application_id
from {{ ref('stg_applications') }} a
left join {{ ref('feat_income_regularity') }} f
    on f.application_id = a.application_id
where f.application_id is null
