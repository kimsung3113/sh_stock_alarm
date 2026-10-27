"""과거 데이터로 기법 검증. 스캔과 같은 기법 코드를 사용합니다."""
from datetime import timedelta

import pandas as pd

import config
from domain.indicators import add_indicators
from domain.performance import summarize
from domain.returns import forward_returns
from domain.strategy import evaluate
from infrastructure.market_data import get_ohlcv, get_universe, now_kst


def backtest_df(df: pd.DataFrame, horizons) -> list:
    df = add_indicators(df)
    rows = []
    for i in range(60, len(df) - 1):
        if not df["value_ma20"].iloc[i] >= config.MIN_AVG_TRADING_VALUE:
            continue
        hits = evaluate(df, i)
        if not hits:
            continue
        fwd = forward_returns(df, i, float(df["Close"].iloc[i]), horizons)
        for strat, _ in hits:
            for h, r in fwd.items():
                rows.append({"strategy_name": strat.name, "side": strat.side, "horizon": h,
                             "return_pct": r["return_pct"], "max_up_pct": r["max_up_pct"],
                             "max_down_pct": r["max_down_pct"]})
    return rows


def run_backtest(years: int = 3, sample: int = 200, codes=None, horizons=None) -> pd.DataFrame:
    horizons = horizons or config.HORIZONS
    universe = get_universe()
    if codes:
        universe = universe[universe["Code"].isin(codes)]
    elif sample and len(universe) > sample:
        universe = universe.sample(sample, random_state=42)
    start = (now_kst() - timedelta(days=365 * years + 120)).strftime("%Y-%m-%d")

    rows = []
    for n, r in enumerate(universe.itertuples(index=False), 1):
        try:
            df = get_ohlcv(r.Code, start)
        except Exception:
            continue
        if len(df) >= config.MIN_BARS:
            rows += backtest_df(df, horizons)
        if n % 25 == 0:
            print(f"  {n}/{len(universe)} 종목 완료")
    return summarize(pd.DataFrame(rows))
