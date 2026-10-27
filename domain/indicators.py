"""기술적 지표 계산. i번째 값은 i번째 봉까지의 정보만 사용합니다."""
import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c, v = df["Close"], df["Volume"]

    df["ma5"] = c.rolling(5).mean()
    df["ma20"] = c.rolling(20).mean()
    df["ma60"] = c.rolling(60).mean()

    # 거래량 비율: 오늘 거래량 / 직전 20일 평균 (오늘은 평균에서 제외)
    df["vol_ma20"] = v.rolling(20).mean().shift(1)
    df["vol_ratio"] = v / df["vol_ma20"]

    # RSI(14), Wilder 방식
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = (100 - 100 / (1 + rs)).fillna(100)

    # 볼린저 밴드(20, 2)
    std = c.rolling(20).std()
    df["bb_upper"] = df["ma20"] + 2 * std
    df["bb_lower"] = df["ma20"] - 2 * std

    # 직전 20일 최고가 (오늘 제외)
    df["high20_prev"] = df["High"].rolling(20).max().shift(1)

    # 20일 평균 거래대금 (유동성 필터용)
    df["value_ma20"] = (c * v).rolling(20).mean()
    return df
