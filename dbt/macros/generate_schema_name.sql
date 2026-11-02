{#
  By default dbt glues the profile's schema onto every custom schema,
  so "+schema: marts" would become "staging_marts". This macro makes dbt
  use the schema names exactly as written: staging, intermediate, marts.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
