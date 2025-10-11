WITH last AS (
  SELECT MAX(ts) AS last_ts
  FROM events
  WHERE type = 'nappy'
)
SELECT
  last.last_ts,
  FLOOR(EXTRACT(EPOCH FROM (NOW() - last.last_ts)) / 60)::int AS minutes_ago,
  CASE
    WHEN last.last_ts IS NULL THEN 'no data'
    WHEN FLOOR(EXTRACT(EPOCH FROM (NOW() - last.last_ts)) / 60) < 60
      THEN CONCAT(FLOOR(EXTRACT(EPOCH FROM (NOW() - last.last_ts)) / 60)::int, 'm ago')
    ELSE CONCAT(
      FLOOR(EXTRACT(EPOCH FROM (NOW() - last.last_ts)) / 3600)::int, 'h ',
      (FLOOR(EXTRACT(EPOCH FROM (NOW() - last.last_ts)) / 60)::int % 60), 'm ago'
    )
  END AS latest_nappy
FROM last;
