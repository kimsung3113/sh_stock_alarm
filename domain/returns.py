"""신호 이후 수익률 계산 규칙."""
import numpy as np
import pandas as pd


def forward_returns(df: pd.DataFrame, pos: int, base: float, horizons) -> dict:
    """pos번째 봉(신호 봉) 종가 기준, h거래일 뒤 수익률과 기간 중 최대 상승·하락률."""
    out = {}
    for h in horizons:
        t = pos + h
        if t >= len(df):
            continue
        win = df.iloc[pos + 1:t + 1]
        price = float(df["Close"].iloc[t])
        out[h] = {
            "target_date": df.index[t].strftime("%Y-%m-%d"),
            "price": price,
            "return_pct": round((price / base - 1) * 100, 3),
            "max_up_pct": round((win["High"].max() / base - 1) * 100, 3),
            "max_down_pct": round((win["Low"].min() / base - 1) * 100, 3),
        }
    return out


def forward_table(df: pd.DataFrame, horizons, cost: float, delisted: bool) -> pd.DataFrame:
    """모든 봉에 대해 '이 봉 종가에 신호 → 다음 봉 시가 진입 → h거래일째 종가 청산' 순수익률(%)."""
    o, hi, lo, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    n = len(df)
    entry = np.full(n, np.nan)
    entry[:-1] = o[1:]
    # 시가부터 상한가에 묶인 날(고가=저가, 전일 대비 +25% 이상)은 매수 불가
    locked = np.zeros(n, bool)
    locked[:-1] = (hi[1:] == lo[1:]) & (o[1:] >= c[:-1] * 1.25)
    entry[locked] = np.nan

    out = pd.DataFrame({"entry": entry, "locked": locked}, index=df.index)
    pos = np.arange(n)
    for h in horizons:
        t = pos + h
        if delisted:
            t = np.minimum(t, n - 1)  # 보유 중 상장폐지 → 마지막 거래일 종가
        valid = (t < n) & (pos + 1 < n)
        ex = np.full(n, np.nan)
        ex[valid] = c[t[valid]]
        out[f"ret_{h}"] = (ex / entry - 1) * 100 - cost
    return out
