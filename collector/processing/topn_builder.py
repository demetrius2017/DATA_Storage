"""
TopN Builder: реконструкция топ-5 уровней стакана из depth_events.

Поддерживает Binance Futures спецификацию: инициализация через REST snapshot (depth?limit=1000),
далее последовательное применение deltas (U/u/pu). На каждом событии формирует снимок топ-5
с базовыми микроструктурными фичами для записи в marketdata.orderbook_topN.

Ограничения MVP:
- ofi_1s не рассчитывается в онлайне (оставляем NULL или моментный OFI при необходимости);
- wall_* рассчитываются по топ-5 как простая метрика размера/дистанции.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import aiohttp


@dataclass
class BookState:
    last_update_id: Optional[int] = None
    bids: Dict[float, float] = field(default_factory=dict)  # price -> qty
    asks: Dict[float, float] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TopNBuilder:
    def __init__(self, rest_base_url: str = "https://fapi.binance.com"):
        self.rest_base_url = rest_base_url.rstrip('/')
        self._states: Dict[str, BookState] = {}

    def _get_state(self, symbol: str) -> BookState:
        if symbol not in self._states:
            self._states[symbol] = BookState()
        return self._states[symbol]

    async def _fetch_snapshot(self, symbol: str) -> Tuple[int, Dict[float, float], Dict[float, float]]:
        url = f"{self.rest_base_url}/fapi/v1/depth?symbol={symbol}&limit=1000"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json()
        last_id = int(data["lastUpdateId"])  # тип int
        bids = {float(p): float(q) for p, q in data.get("bids", [])}
        asks = {float(p): float(q) for p, q in data.get("asks", [])}
        return last_id, bids, asks

    def _apply_deltas(self, state: BookState, bids: List[List[str]], asks: List[List[str]]):
        # bid deltas
        for p_str, q_str in bids or []:
            p = float(p_str); q = float(q_str)
            if q == 0.0:
                state.bids.pop(p, None)
            else:
                state.bids[p] = q
        # ask deltas
        for p_str, q_str in asks or []:
            p = float(p_str); q = float(q_str)
            if q == 0.0:
                state.asks.pop(p, None)
            else:
                state.asks[p] = q

    def _top_levels(self, state: BookState, n: int = 5) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        bids_sorted = sorted(((p, q) for p, q in state.bids.items() if q > 0), key=lambda x: x[0], reverse=True)
        asks_sorted = sorted(((p, q) for p, q in state.asks.items() if q > 0), key=lambda x: x[0])
        return bids_sorted[:n], asks_sorted[:n]

    @staticmethod
    def _features_from_levels(bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]) -> Dict[str, Optional[float]]:
        if not bids or not asks:
            return {
                "microprice": None,
                "i1": None,
                "i5": None,
                "wall_size_bid": None,
                "wall_size_ask": None,
                "wall_dist_bid_bps": None,
                "wall_dist_ask_bps": None,
            }
        b1p, b1q = bids[0]
        a1p, a1q = asks[0]
        denom = (b1q + a1q) if (b1q + a1q) > 0 else 1.0
        microprice = (b1p * a1q + a1p * b1q) / denom
        i1 = (b1q - a1q) / denom
        # i5 по суммам топ-5
        sb = sum(q for _, q in bids)
        sa = sum(q for _, q in asks)
        denom5 = (sb + sa) if (sb + sa) > 0 else 1.0
        i5 = (sb - sa) / denom5
        mid = (a1p + b1p) / 2.0
        wall_size_bid = max((q for _, q in bids), default=0.0)
        wall_size_ask = max((q for _, q in asks), default=0.0)
        # расстояние до уровня с максимальным объёмом на стороне
        wb_price = next((p for p, q in bids if q == wall_size_bid), b1p)
        wa_price = next((p for p, q in asks if q == wall_size_ask), a1p)
        wall_dist_bid_bps = abs(wb_price - mid) / mid * 10000 if mid > 0 else None
        wall_dist_ask_bps = abs(wa_price - mid) / mid * 10000 if mid > 0 else None
        return {
            "microprice": microprice,
            "i1": i1,
            "i5": i5,
            "wall_size_bid": wall_size_bid,
            "wall_size_ask": wall_size_ask,
            "wall_dist_bid_bps": wall_dist_bid_bps,
            "wall_dist_ask_bps": wall_dist_ask_bps,
        }

    async def process_event(self, symbol: str, event: Dict, symbol_id: int) -> Optional[Dict]:
        """
        Обработать одно depthUpdate событие и вернуть запись для orderbook_topN
        либо None, если ещё не инициализировано или разрыв последовательности.
        """
        state = self._get_state(symbol)
        async with state.lock:
            # Требуем обязательные поля, иначе пропускаем событие
            if 'U' not in event or 'u' not in event or 'E' not in event:
                return None
            U = int(event.get('U') or 0)
            u = int(event.get('u') or 0)
            bids = event.get('b') or []
            asks = event.get('a') or []

            # Инициализация снапшотом при первом событии или если потеряли связь
            if state.last_update_id is None:
                # Буфер не ведём — простая логика: тянем снапшот и ждём события u >= last_id
                last_id, bids0, asks0 = await self._fetch_snapshot(symbol)
                state.last_update_id = last_id
                state.bids = bids0
                state.asks = asks0
                # Если текущее событие полностью до снапшота — игнорим
                if u < last_id:
                    return None
                # Применять начнём только если пересекается: U <= last_id+1 <= u
                if not (U <= last_id + 1 <= u):
                    # ждём следующее событие
                    return None

            # Проверка на разрыв последовательности
            last_id = int(state.last_update_id or 0)
            if U > last_id + 1:
                # Пропущены события — переинициализация снапшотом
                last_id, bids0, asks0 = await self._fetch_snapshot(symbol)
                state.last_update_id = last_id
                state.bids = bids0
                state.asks = asks0
                if not (U <= last_id + 1 <= u):
                    return None

            # Применяем дельты и продвигаем last_update_id
            self._apply_deltas(state, bids, asks)
            state.last_update_id = u

            # Собираем топ-5 и фичи
            b5, a5 = self._top_levels(state, n=5)
            feats = self._features_from_levels(b5, a5)

            # Временная метка биржи
            ts_exchange_ms = int(event.get('E') or 0)

            # Формируем запись для вставки в orderbook_topN
            rec: Dict[str, Optional[float] | int] = {
                'ts_exchange': ts_exchange_ms,
                'symbol_id': symbol_id,
                # bids
                'b1_price': b5[0][0] if len(b5) > 0 else None,
                'b1_qty': b5[0][1] if len(b5) > 0 else None,
                'b2_price': b5[1][0] if len(b5) > 1 else None,
                'b2_qty': b5[1][1] if len(b5) > 1 else None,
                'b3_price': b5[2][0] if len(b5) > 2 else None,
                'b3_qty': b5[2][1] if len(b5) > 2 else None,
                'b4_price': b5[3][0] if len(b5) > 3 else None,
                'b4_qty': b5[3][1] if len(b5) > 3 else None,
                'b5_price': b5[4][0] if len(b5) > 4 else None,
                'b5_qty': b5[4][1] if len(b5) > 4 else None,
                # asks
                'a1_price': a5[0][0] if len(a5) > 0 else None,
                'a1_qty': a5[0][1] if len(a5) > 0 else None,
                'a2_price': a5[1][0] if len(a5) > 1 else None,
                'a2_qty': a5[1][1] if len(a5) > 1 else None,
                'a3_price': a5[2][0] if len(a5) > 2 else None,
                'a3_qty': a5[2][1] if len(a5) > 2 else None,
                'a4_price': a5[3][0] if len(a5) > 3 else None,
                'a4_qty': a5[3][1] if len(a5) > 3 else None,
                'a5_price': a5[4][0] if len(a5) > 4 else None,
                'a5_qty': a5[4][1] if len(a5) > 4 else None,
                # features
                'microprice': feats['microprice'],
                'i1': feats['i1'],
                'i5': feats['i5'],
                'wall_size_bid': feats['wall_size_bid'],
                'wall_size_ask': feats['wall_size_ask'],
                'wall_dist_bid_bps': feats['wall_dist_bid_bps'],
                'wall_dist_ask_bps': feats['wall_dist_ask_bps'],
                'ofi_1s': None,
            }

            return rec
