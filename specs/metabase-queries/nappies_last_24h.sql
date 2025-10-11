SELECT
  ts AT TIME ZONE 'UTC' AS ts_utc,
  type,                 -- 'nappy'
  notes,
  tags,
  COALESCE(metadata->>'subtype', 'unknown') AS subtype
FROM events
WHERE type = 'nappy'
  AND ts >= NOW() - INTERVAL '24 hours'
ORDER BY ts DESC;
