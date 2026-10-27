"""전 종목 스캔 → 신호 DB 저장 → 텔레그램 알림."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import config
from domain.indicators import add_indicators
from domain.strategy import evaluate, snapshot
from infrastructure import signal_repository as db
from infrastructure import telegram as notifier
from infrastructure.market_data import get_ohlcv, get_universe, now_kst


def scan_one(row, start: str) -> list:
    try:
        df = get_ohlcv(row.Code, start)
    except Exception:
        return []
    if len(df) < config.MIN_BARS:
        return []
    df = add_indicators(df)
    i = len(df) - 1
    if not df["value_ma20"].iloc[i] >= config.MIN_AVG_TRADING_VALUE:
        return []
    signals = []
    for strat, reason in evaluate(df, i):
        s = snapshot(df, i)
        s.update(code=row.Code, name=row.Name, market=row.Market, strategy_id=strat.id,
                 strategy_name=strat.name, side=strat.side, reason=reason)
        signals.append(s)
    return signals


def run_scan(notify: bool = True) -> list:
    universe = get_universe()
    start = (now_kst() - timedelta(days=config.HISTORY_DAYS)).strftime("%Y-%m-%d")
    print(f"스캔 대상 {len(universe)}종목")

    with ThreadPoolExecutor(config.MAX_WORKERS) as ex:
        results = ex.map(lambda r: scan_one(r, start), universe.itertuples(index=False))
        found = [s for lst in results for s in lst]

    conn = db.connect()
    new = []
    for s in found:
        sid = db.insert_signal(conn, s)  # 신호 저장과 알림이 같은 시점에 일어남
        if sid:
            s["id"] = sid
            new.append(s)
    conn.close()
    print(f"신규 신호 {len(new)}건 (중복 제외 전 {len(found)}건)")
    if notify:
        notifier.send_signals(new)
    return new
