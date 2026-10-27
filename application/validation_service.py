"""기법 검증 (이벤트 스터디). 스캔과 같은 기법 코드를 사용합니다.

backtest_service.py와 다른 점
- 진입: 신호 다음 날 시가 (점상한가로 살 수 없는 날은 '미체결'로 따로 셈)
- 청산: 진입일 포함 h거래일째 종가, 왕복 비용(config.COST_ROUNDTRIP_PCT) 차감
- 비교 기준: 같은 날·같은 시장에서 거래대금 조건을 통과한 전 종목의 같은 규칙 수익률 평균
  (= 아무 종목이나 샀을 때) 과 지수(KS11/KQ11) 수익률
- 코스피·코스닥, 연도별로 나눠 보고, 같은 날 신호끼리의 상관을 피하려고 월별 평균으로 t값 계산
- 상장폐지 종목 포함. 보유 중 폐지되면 마지막 거래일 종가로 청산
"""
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import config
from domain.indicators import add_indicators
from domain.returns import forward_table
from domain.strategy import STRATEGIES, evaluate
from infrastructure.market_data import get_ohlcv, get_ohlcv_cached, get_validation_universe

INDEX_CODE = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}


def _index_forward(horizons) -> dict:
    """시장별 지수의 같은 규칙 수익률 (비용 없음)."""
    res = {}
    for mkt, code in INDEX_CODE.items():
        idx = get_ohlcv(code, config.VALIDATE_START, drop_unclosed=True)
        f = forward_table(idx, horizons, 0.0, False)
        res[mkt] = f[[f"ret_{h}" for h in horizons]]
    return res


def _process_code(args):
    code, name, market, delisted, start, strat_ids, horizons, refresh = args
    try:
        df = get_ohlcv_cached(code, start, refresh=refresh, static=delisted)
    except Exception:
        return None, None
    if len(df) < config.MIN_BARS:
        return None, None
    df = add_indicators(df)
    fwd = forward_table(df, horizons, config.COST_ROUNDTRIP_PCT, delisted)
    eligible = ((df["value_ma20"] >= config.MIN_AVG_TRADING_VALUE) & df["ma60"].notna()).to_numpy().copy()
    eligible[-1] = False  # 다음 날 진입가가 없는 마지막 봉

    ret_cols = [f"ret_{h}" for h in horizons]
    base = fwd.loc[eligible, ret_cols].astype("float32")
    base["market"] = market

    strategies = [s for s in STRATEGIES if s.id in strat_ids]
    lo = df["Low"].to_numpy(float)
    hi = df["High"].to_numpy(float)
    events = []
    for i in np.flatnonzero(eligible):
        for strat, reason in evaluate(df, i, strategies):
            e = {"date": df.index[i], "code": code, "name": name, "market": market,
                 "delisted": delisted, "strategy_id": strat.id, "strategy": strat.name,
                 "reason": reason, "close": float(df["Close"].iloc[i]),
                 "entry": fwd["entry"].iloc[i], "locked": bool(fwd["locked"].iloc[i])}
            for h in horizons:
                e[f"ret_{h}"] = fwd[f"ret_{h}"].iloc[i]
                win = slice(i + 1, min(i + h, len(df) - 1) + 1)
                if not np.isnan(e["entry"]) and win.start < len(df):
                    e[f"mae_{h}"] = (lo[win].min() / e["entry"] - 1) * 100  # 보유 중 최대 하락
                    e[f"mfe_{h}"] = (hi[win].max() / e["entry"] - 1) * 100  # 보유 중 최대 상승
            events.append(e)
    return base, events


def collect(strat_ids, start=None, horizons=None, limit=None, refresh=False, workers=None):
    """전 종목(상장폐지 포함)에서 신호 이벤트와 비교 기준을 모읍니다."""
    start = start or config.VALIDATE_START
    horizons = horizons or config.VALIDATE_HORIZONS
    universe = get_validation_universe(start)
    if limit:
        universe = universe.sample(limit, random_state=42)
    print(f"검증 대상 {len(universe)}종목 (상장폐지 {int(universe['Delisted'].sum())}종목 포함), {start}~")

    jobs = [(r.Code, r.Name, r.Market, bool(r.Delisted), start, set(strat_ids), horizons, refresh)
            for r in universe.itertuples(index=False)]
    bases, events = [], []
    with ProcessPoolExecutor(workers or config.MAX_WORKERS) as ex:
        for n, (b, ev) in enumerate(ex.map(_process_code, jobs, chunksize=4), 1):
            if b is not None:
                bases.append(b)
                events += ev
            if n % 250 == 0:
                print(f"  {n}/{len(jobs)} 종목 완료")

    ret_cols = [f"ret_{h}" for h in horizons]
    base = (pd.concat(bases).rename_axis("date").reset_index()
              .groupby(["date", "market"])[ret_cols].mean())
    ev = pd.DataFrame(events)
    if ev.empty:
        return ev, horizons

    # 초과수익 = 신호 종목 순수익률 - 같은 날·같은 시장 전 종목 평균 (둘 다 비용 차감이므로 비용 상쇄)
    b = base.reindex(pd.MultiIndex.from_frame(ev[["date", "market"]])).to_numpy()
    idx = _index_forward(horizons)
    for k, h in enumerate(horizons):
        ev[f"exu_{h}"] = ev[f"ret_{h}"] - b[:, k]
        ix = np.array([idx[m][f"ret_{h}"].get(d, np.nan) for d, m in zip(ev["date"], ev["market"])])
        ev[f"exi_{h}"] = ev[f"ret_{h}"] + config.COST_ROUNDTRIP_PCT - ix  # 지수 대비 (비용 제외 비교)
    return ev.sort_values(["strategy_id", "date", "code"]).reset_index(drop=True), horizons


def _tstat_monthly(s: pd.Series, dates: pd.Series) -> float:
    m = s.groupby(dates.dt.to_period("M")).mean().dropna()
    if len(m) < 3 or m.std() == 0:
        return np.nan
    return m.mean() / (m.std(ddof=1) / np.sqrt(len(m)))


def _verdict(r) -> str:
    ok = [r["건수"] >= config.PASS_MIN_SIGNALS, r["평균순수익"] > 0, r["초과수익"] > 0,
          r["t값"] >= config.PASS_MIN_TSTAT, r["플러스연도비율"] >= config.PASS_MIN_YEARS_POSITIVE]
    if all(ok):
        return "PASS"
    if r["초과수익"] > 0 and r["t값"] >= 1:
        return "WEAK"
    return "FAIL"


def summarize(ev: pd.DataFrame, horizons) -> pd.DataFrame:
    rows = []
    for (sid, sname), g0 in ev.groupby(["strategy_id", "strategy"]):
        for mkt in ["KOSPI", "KOSDAQ", "전체"]:
            g = g0 if mkt == "전체" else g0[g0["market"] == mkt]
            filled = g[g["entry"].notna()]
            for h in horizons:
                x = filled.dropna(subset=[f"ret_{h}", f"exu_{h}"])
                if x.empty:
                    continue
                yearly = x.groupby(x["date"].dt.year)[f"exu_{h}"].mean()
                r = {"기법": sname, "시장": mkt, "기간(일)": h, "건수": len(x),
                     "미체결": int(g["locked"].sum()),
                     "승률": (x[f"ret_{h}"] > 0).mean() * 100,
                     "평균순수익": x[f"ret_{h}"].mean(), "중앙값": x[f"ret_{h}"].median(),
                     "초과수익": x[f"exu_{h}"].mean(), "지수대비": x[f"exi_{h}"].mean(),
                     "t값": _tstat_monthly(x[f"exu_{h}"], x["date"]),
                     "플러스연도비율": (yearly > 0).mean(),
                     "평균최대하락": x[f"mae_{h}"].mean()}
                r["판정"] = _verdict(r)
                rows.append(r)
    return pd.DataFrame(rows).round(2)


def yearly(ev: pd.DataFrame, h: int) -> pd.DataFrame:
    x = ev[ev["entry"].notna()].dropna(subset=[f"exu_{h}"])
    t = (x.groupby(["strategy", "market", x["date"].dt.year])
          .agg(건수=(f"ret_{h}", "size"), 평균순수익=(f"ret_{h}", "mean"),
               초과수익=(f"exu_{h}", "mean"), 승률=(f"ret_{h}", lambda s: (s > 0).mean() * 100)))
    return t.round(2).reset_index().rename(columns={"strategy": "기법", "market": "시장", "date": "연도"})


def inspect(ev: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """눈으로 확인할 표본 (차트에서 해당 날짜를 찾아 조건이 맞는지 확인용)."""
    cols = ["date", "code", "name", "market", "strategy", "reason", "close", "entry", "ret_5", "exu_5"]
    return ev.sample(min(n, len(ev)), random_state=1)[[c for c in cols if c in ev]].sort_values("date")


def run_validation(strat_ids, start=None, limit=None, refresh=False, n_inspect=10):
    ev, horizons = collect(strat_ids, start, limit=limit, refresh=refresh)
    if ev.empty:
        print("신호 없음")
        return ev, pd.DataFrame()
    summary = summarize(ev, horizons)
    tag = f"{'_'.join(strat_ids)}_{start or config.VALIDATE_START}" + (f"_limit{limit}" if limit else "")  # 표본 실행이 전체 결과를 덮어쓰지 않게
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    ev.to_csv(f"{config.RESULTS_DIR}/{tag}_events.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(f"{config.RESULTS_DIR}/{tag}_summary.csv", index=False, encoding="utf-8-sig")

    print(f"\n[표본 {n_inspect}건]")
    print(inspect(ev, n_inspect).to_string(index=False))
    print("\n[요약] 순수익=비용 차감, 초과수익=같은 날 같은 시장 전 종목 평균 대비, t값=월별 평균 기준")
    print(summary.to_string(index=False))
    for h in (5, 20):
        if h in horizons:
            y = yearly(ev, h)
            y.to_csv(f"{config.RESULTS_DIR}/{tag}_yearly_{h}d.csv", index=False, encoding="utf-8-sig")
            print(f"\n[연도별, {h}일 보유]")
            print(y.to_string(index=False))
    print(f"\n→ {config.RESULTS_DIR}/{tag}_*.csv 저장")
    return ev, summary
