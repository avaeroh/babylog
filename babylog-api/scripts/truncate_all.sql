\set ON_ERROR_STOP on
WITH ddl AS (
  SELECT CASE
           WHEN COUNT(*) = 0 THEN NULL
           ELSE 'TRUNCATE TABLE '
                || string_agg(format('%I.%I', schemaname, tablename), ', ')
                || ' RESTART IDENTITY CASCADE;'
         END AS sql
  FROM pg_tables
  WHERE schemaname = 'public'
)
SELECT sql FROM ddl WHERE sql IS NOT NULL;
\gexec
