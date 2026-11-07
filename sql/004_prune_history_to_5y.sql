-- Free-tier survival: prune prices older than 5 years.
--
-- Supabase free tier caps at ~500 MB (soft) / ~683 MB (hard). At 5.29M rows
-- across 10 years the prices table alone was 657 MB and the project was at
-- the hard ceiling, blocking any new writes.
--
-- Pruning to 5 years removes ~45% of rows. The DELETE itself doesn't shrink
-- the physical file (dead tuples stay until VACUUM FULL, which needs
-- temporary double space we don't have), but future daily inserts reuse the
-- freed pages instead of extending the file. Net effect: growth stops.
--
-- When the project is upgraded to Pro (or migrated to a fresh project with
-- REAL columns), run VACUUM FULL prices to actually reclaim disk.
--
-- Idempotent: re-running is a no-op if no rows match.

DELETE FROM prices
WHERE trade_date < CURRENT_DATE - INTERVAL '5 years';

-- Standard VACUUM marks dead tuples as reusable without full rewrite. Safe
-- at ceiling. Doesn't affect pg_database_size() but prevents further growth.
VACUUM prices;
