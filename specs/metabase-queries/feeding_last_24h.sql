SELECT
  ts AT TIME ZONE 'UTC'                                AS ts_utc,
  type,                                                -- 'feeding'
  notes,
  tags,
  (metadata ->> 'volume_ml')::int       AS volume_ml,
  (metadata ->> 'duration_min')::int    AS duration_min,
  (metadata ->> 'side')                 AS side
FROM events
WHERE type = 'feeding'
  AND ts >= NOW() - INTERVAL '24 hours'
ORDER BY ts DESC;
