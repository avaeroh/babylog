WITH days AS (
  SELECT generate_series(
           (CURRENT_DATE - INTERVAL '13 days')::date,
           CURRENT_DATE::date,
           INTERVAL '1 day'
         )::date AS d
),
feeding_daily AS (
  SELECT date_trunc('day', ts AT TIME ZONE 'UTC')::date AS d, COUNT(*) AS feeding_count
  FROM events
  WHERE type = 'feeding'
    AND ts >= (CURRENT_DATE - INTERVAL '13 days')
  GROUP BY 1
),
nappy_daily AS (
  SELECT date_trunc('day', ts AT TIME ZONE 'UTC')::date AS d, COUNT(*) AS nappy_count
  FROM events
  WHERE type = 'nappy'
    AND ts >= (CURRENT_DATE - INTERVAL '13 days')
  GROUP BY 1
)
SELECT
  days.d AS day,
  COALESCE(feeding_daily.feeding_count, 0) AS feeding_count,
  COALESCE(nappy_daily.nappy_count, 0)     AS nappy_count
FROM days
LEFT JOIN feeding_daily ON feeding_daily.d = days.d
LEFT JOIN nappy_daily   ON nappy_daily.d   = days.d
ORDER BY day;
