"""매수·매도 기법 정의.

모든 기법은 (df, i)를 받아 i번째 봉까지의 정보만으로 판정합니다.
→ 스캔과 백테스트가 같은 코드를 쓰고, 미래 데이터가 섞이지 않습니다.
새 기법은 함수 하나를 만들고 STRATEGIES 목록에 추가하면 됩니다.
"""
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd


@dataclass
class Strategy:
    id: str
    name: str
    side: str  # "BUY" 또는 "SELL"
    check: Callable[[pd.DataFrame, int], Optional[str]]  # 조건 충족 시 근거 문자열 반환


def _cross_up(a_now, a_prev, b_now, b_prev):
    return a_prev <= b_prev and a_now > b_now


# ---------- 매수 기법 ----------
def golden_cross_volume(df, i):
    r, p = df.iloc[i], df.iloc[i - 1]
    if _cross_up(r.ma5, p.ma5, r.ma20, p.ma20) and r.vol_ratio >= 2 and r.Close > r.ma60:
        return f"5일선이 20일선 상향 돌파, 거래량 {r.vol_ratio:.1f}배, 60일선 위"
    return None


def breakout_20d(df, i):
    r = df.iloc[i]
    if r.Close > r.high20_prev and r.vol_ratio >= 2.5 and r.Close > r.Open:
        return f"20일 최고가({r.high20_prev:,.0f}) 돌파 양봉, 거래량 {r.vol_ratio:.1f}배"
    return None


def rsi_rebound(df, i):
    r, p = df.iloc[i], df.iloc[i - 1]
    if p.rsi < 30 <= r.rsi and r.Close > r.Open:
        return f"RSI 과매도 탈출 ({p.rsi:.1f} → {r.rsi:.1f}), 양봉"
    return None


def bollinger_rebound(df, i):
    r, p = df.iloc[i], df.iloc[i - 1]
    if p.Close < p.bb_lower and r.Close > r.bb_lower and r.vol_ratio >= 1.5:
        return f"볼린저 하단 이탈 후 재진입, 거래량 {r.vol_ratio:.1f}배"
    return None


# ---------- 매도 기법 ----------
def dead_cross(df, i):
    r, p = df.iloc[i], df.iloc[i - 1]
    if _cross_up(r.ma20, p.ma20, r.ma5, p.ma5):
        return "5일선이 20일선 하향 이탈 (데드크로스)"
    return None


def rsi_overbought_exit(df, i):
    r, p = df.iloc[i], df.iloc[i - 1]
    if p.rsi > 70 >= r.rsi:
        return f"RSI 과매수 이탈 ({p.rsi:.1f} → {r.rsi:.1f})"
    return None


STRATEGIES = [
    Strategy("GC_VOL", "골든크로스+거래량", "BUY", golden_cross_volume),
    Strategy("BRK20", "20일 신고가 돌파", "BUY", breakout_20d),
    Strategy("RSI_UP", "RSI 과매도 반등", "BUY", rsi_rebound),
    Strategy("BB_LOW", "볼린저 하단 반등", "BUY", bollinger_rebound),
    Strategy("DEAD", "데드크로스", "SELL", dead_cross),
    Strategy("RSI_DN", "RSI 과매수 이탈", "SELL", rsi_overbought_exit),
]


def evaluate(df: pd.DataFrame, i: int, strategies=None):
    """i번째 봉에서 충족된 (Strategy, 근거) 목록. strategies를 주면 그 기법만 판정합니다."""
    if i < 1 or df["Volume"].iloc[i] == 0:  # 거래정지 등 제외
        return []
    hits = []
    for s in strategies or STRATEGIES:
        try:
            reason = s.check(df, i)
        except Exception:
            reason = None
        if reason:
            hits.append((s, reason))
    return hits


def snapshot(df: pd.DataFrame, i: int) -> dict:
    """신호 시점의 가격·지표 값을 그대로 기록 (나중에 조건별 성과 분석용)."""
    r = df.iloc[i]
    f = lambda x: None if pd.isna(x) else round(float(x), 2)
    return {
        "signal_date": df.index[i].strftime("%Y-%m-%d"),
        "price": float(r.Close),
        "volume": int(r.Volume),
        "vol_ratio": f(r.vol_ratio),
        "rsi": f(r.rsi),
        "ma5": f(r.ma5),
        "ma20": f(r.ma20),
        "ma60": f(r.ma60),
    }
