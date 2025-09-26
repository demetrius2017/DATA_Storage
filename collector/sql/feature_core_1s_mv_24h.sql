-- ===============================================
-- 📦 FEATURE: CORE 1s ровная сетка (24h window)
-- ===============================================
-- Материализованный вид с ровной 1‑секундной сеткой по всем символам
-- Окно: [now()-24h .. now())
-- Политика LOCF: переносим только state‑поля (mid, spread),
-- счётчики/объёмы не переносим (0/NULL на пустых секундах)

CREATE SCHEMA IF NOT EXISTS feature;

-- Создаём MV (если уже есть — пересоздайте вручную при необходимости)
CREATE MATERIALIZED VIEW IF NOT EXISTS feature.core_1s_24h AS
WITH bounds AS (
  SELECT date_trunc('second', now() - interval '24 hours') AS t_from,
         date_trunc('second', now()) AS t_to
), syms AS (
  SELECT DISTINCT b.symbol_id
  FROM marketdata.bt_1s b
  WHERE b.ts_second >= (SELECT t_from FROM bounds) AND b.ts_second < (SELECT t_to FROM bounds)
), grid AS (
  SELECT s.symbol_id, gs.ts_second
  FROM syms s
  CROSS JOIN generate_series((SELECT t_from FROM bounds), (SELECT t_to FROM bounds), interval '1 second') AS gs(ts_second)
), joined AS (
  SELECT 
    g.symbol_id,
    g.ts_second,
    b.mid_close,
    b.spread_mean,
    b.update_count,
    t.trade_count,
    t.vol_sum,
    t.vwap
  FROM grid g
  LEFT JOIN marketdata.bt_1s b
    ON b.symbol_id = g.symbol_id AND b.ts_second = g.ts_second
  LEFT JOIN marketdata.trade_1s t
    ON t.symbol_id = g.symbol_id AND t.ts_second = g.ts_second
), sweep AS (
  SELECT 
    j.*,
    MAX(CASE WHEN j.mid_close IS NOT NULL THEN j.ts_second END)
      OVER (PARTITION BY j.symbol_id ORDER BY j.ts_second
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS last_bt_ts
  FROM joined j
)
SELECT 
  s.symbol_id,
  s.ts_second,
  b2.mid_close AS mid_ffill,
  b2.spread_mean AS spread_ffill,
  COALESCE(s.trade_count, 0) AS trade_count,
  COALESCE(s.vol_sum, 0) AS volume_sum,
  CASE WHEN COALESCE(s.trade_count, 0) = 0 THEN NULL ELSE s.vwap END AS vwap,
  COALESCE(s.update_count, 0) AS update_count
FROM sweep s
LEFT JOIN marketdata.bt_1s b2
  ON b2.symbol_id = s.symbol_id AND b2.ts_second = s.last_bt_ts
WITH NO DATA;

-- Индекс для быстрых выборок и REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS uq_core_1s_24h_symbol_time
  ON feature.core_1s_24h (symbol_id, ts_second);

-- Примечание: для регулярного обновления используйте
-- REFRESH MATERIALIZED VIEW CONCURRENTLY feature.core_1s_24h;
-- с расписанием минимум раз в минуту.
