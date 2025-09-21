#!/usr/bin/env python3
"""
CLI-проверка полноты и свежести инжеста данных в PostgreSQL/Timescale.

Критерии по умолчанию (изменяемые флагами/ENV):
- Свежесть: MAX(ts_exchange) не старше N секунд для каждой таблицы.
- Объём: COUNT(*) за последнюю минуту >= минимального порога.

Выход:
- Код 0, если все проверки пройдены; 1 — если есть нарушения.
- Печатает JSON-отчёт (pass/fail + метрики и причины отказа).
"""

import os
import sys
import json
import asyncio
import argparse
from typing import Dict, Any

import asyncpg
import ssl
from urllib.parse import urlparse


def parse_args():
    p = argparse.ArgumentParser(description='Verify ingestion freshness and volume in PostgreSQL')
    p.add_argument('--database-url', default=os.getenv('DATABASE_URL'), help='PostgreSQL URL (env: DATABASE_URL)')
    p.add_argument('--freshness-seconds', type=int, default=int(os.getenv('VERIFY_FRESHNESS_SEC', '60')),
                   help='Максимально допустимый лаг свежести (секунды)')
    p.add_argument('--min-bt-per-minute', type=int, default=int(os.getenv('VERIFY_MIN_BT_1M', '10')),
                   help='Минимум записей book_ticker за 1 минуту')
    p.add_argument('--min-tr-per-minute', type=int, default=int(os.getenv('VERIFY_MIN_TR_1M', '10')),
                   help='Минимум записей trades за 1 минуту')
    p.add_argument('--min-de-per-minute', type=int, default=int(os.getenv('VERIFY_MIN_DE_1M', '10')),
                   help='Минимум записей depth_events за 1 минуту')
    p.add_argument('--depth-required', action='store_true',
                   help='Требовать наличие свежих depth_events (например, если ENABLE_DEPTH=true в проде)')
    return p.parse_args()


async def query_row(conn: asyncpg.Connection, sql: str) -> Any:
    return await conn.fetchval(sql)


async def verify_indexes(conn: asyncpg.Connection) -> Dict[str, Any]:
    """Проверка наличия уникальности для depth_events по (symbol_id, ts_exchange, final_update_id)."""
    res: Dict[str, Any] = {"ok": True, "details": []}
    sql_idx = """
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'marketdata'
          AND tablename = 'depth_events'
          AND indexname = 'uq_depth_events_symbol_time_final'
    """
    has_unique = await conn.fetchval(sql_idx)
    if not has_unique:
        res["ok"] = False
        res["details"].append("Unique index uq_depth_events_symbol_time_final отсутствует")
    return res


def _ssl_from_dsn(dsn: str) -> ssl.SSLContext | bool | None:
    """Create an SSL context for asyncpg based on sslmode in DSN query.

    asyncpg does not honor libpq sslmode from DSN, so we map common values.
    """
    try:
        parsed = urlparse(dsn)
        query = {}
        if parsed.query:
            for part in parsed.query.split('&'):
                if not part:
                    continue
                k, _, v = part.partition('=')
                query[k] = v
        sslmode = (query.get('sslmode') or os.getenv('DB_SSLMODE') or 'require').lower()
        if sslmode in ('disable', 'allow', 'prefer'):
            return False
        if sslmode in ('require', 'verify-none'):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        if sslmode in ('verify-full', 'verify-ca'):
            cafile = os.getenv('DB_SSLROOTCERT')
            if cafile and os.path.exists(cafile):
                ctx = ssl.create_default_context(cafile=cafile)
            else:
                ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            return ctx
        # Fallback to require semantics
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return None


async def main_async():
    args = parse_args()
    if not args.database_url:
        print(json.dumps({"ok": False, "error": "DATABASE_URL is required"}))
        return 1

    report: Dict[str, Any] = {"ok": True, "checks": {}}
    conn: asyncpg.Connection
    try:
        ssl_ctx = _ssl_from_dsn(args.database_url)
        conn = await asyncpg.connect(args.database_url, command_timeout=10, ssl=ssl_ctx)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"DB connect failed: {e}"}))
        return 1

    try:
        # Метрики
        metrics_sql = {
            'bt_last': "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(ts_exchange)))::int FROM marketdata.book_ticker",
            'tr_last': "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(ts_exchange)))::int FROM marketdata.trades",
            'de_last': "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(ts_exchange)))::int FROM marketdata.depth_events",
            'bt_1m': "SELECT COUNT(*) FROM marketdata.book_ticker WHERE ts_exchange >= NOW() - INTERVAL '1 minute'",
            'tr_1m': "SELECT COUNT(*) FROM marketdata.trades WHERE ts_exchange >= NOW() - INTERVAL '1 minute'",
            'de_1m': "SELECT COUNT(*) FROM marketdata.depth_events WHERE ts_exchange >= NOW() - INTERVAL '1 minute'",
        }

        # Сбор
        data = {}
        for k, sql in metrics_sql.items():
            try:
                data[k] = await query_row(conn, sql)
            except Exception as e:
                data[k] = None
                report["ok"] = False
                report.setdefault("errors", []).append(f"Query {k} failed: {e}")

        # Индексы depth_events
        idx = await verify_indexes(conn)
        report["checks"]["indexes"] = idx
        if not idx["ok"]:
            report["ok"] = False

        # Правила
        freshness = args.freshness_seconds
        # book_ticker
        bt_fresh_ok = (data.get('bt_last') is not None) and (data['bt_last'] <= freshness)
        bt_rate_ok = (data.get('bt_1m') or 0) >= args.min_bt_per_minute
        report["checks"]["book_ticker"] = {
            "fresh_seconds": data.get('bt_last'),
            "count_1m": data.get('bt_1m'),
            "fresh_ok": bool(bt_fresh_ok),
            "rate_ok": bool(bt_rate_ok)
        }
        if not (bt_fresh_ok and bt_rate_ok):
            report["ok"] = False

        # trades
        tr_fresh_ok = (data.get('tr_last') is not None) and (data['tr_last'] <= freshness)
        tr_rate_ok = (data.get('tr_1m') or 0) >= args.min_tr_per_minute
        report["checks"]["trades"] = {
            "fresh_seconds": data.get('tr_last'),
            "count_1m": data.get('tr_1m'),
            "fresh_ok": bool(tr_fresh_ok),
            "rate_ok": bool(tr_rate_ok)
        }
        if not (tr_fresh_ok and tr_rate_ok):
            report["ok"] = False

        # depth_events — по требованию
        if args.depth_required:
            de_fresh_ok = (data.get('de_last') is not None) and (data['de_last'] <= freshness)
            de_rate_ok = (data.get('de_1m') or 0) >= args.min_de_per_minute
            report["checks"]["depth_events"] = {
                "fresh_seconds": data.get('de_last'),
                "count_1m": data.get('de_1m'),
                "fresh_ok": bool(de_fresh_ok),
                "rate_ok": bool(de_rate_ok)
            }
            if not (de_fresh_ok and de_rate_ok):
                report["ok"] = False

        print(json.dumps(report))
        return 0 if report["ok"] else 1
    finally:
        await conn.close()


def main():
    try:
        exit_code = asyncio.run(main_async())
    except KeyboardInterrupt:
        exit_code = 130
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
