"""시세 데이터 수집 (FinanceDataReader 사용)."""
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import pandas as pd

import config

KST = ZoneInfo("Asia/Seoul")
MARKET_CLOSED_AFTER = time(15, 40)  # 이 시각 이후면 당일 봉이 마감된 것으로 간주


def now_kst() -> datetime:
    return datetime.now(KST)


def get_universe() -> pd.DataFrame:
    """코스피·코스닥 보통주 중 시총 기준을 넘는 종목 목록 (Code, Name, Market)."""
    try:
        df = fdr.StockListing("KRX")
    except Exception:
        df = pd.concat([fdr.StockListing("KOSPI"), fdr.StockListing("KOSDAQ")], ignore_index=True)

    df = df[df["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])].copy()
    df["Market"] = df["Market"].replace({"KOSDAQ GLOBAL": "KOSDAQ"})
    df = df[df["Code"].astype(str).str.endswith("0")]            # 우선주 제외
    df = df[~df["Name"].str.contains("스팩|SPAC", na=False)]     # 스팩 제외
    if "Marcap" in df.columns:
        df = df[df["Marcap"] >= config.MIN_MARKET_CAP]
    return df[["Code", "Name", "Market"]].reset_index(drop=True)


def get_ohlcv(code: str, start: str, drop_unclosed: bool = True) -> pd.DataFrame:
    """일봉 OHLCV. 장중에 실행되면 아직 마감되지 않은 당일 봉은 제거합니다
    (미완성 봉으로 신호를 판정하면 백테스트와 실전 결과가 어긋납니다)."""
    df = fdr.DataReader(code, start)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df = drop_halted(df)
    if df.empty:
        return df
    if drop_unclosed:
        now = now_kst()
        if df.index[-1].date() == now.date() and now.time() < MARKET_CLOSED_AFTER:
            df = df.iloc[:-1]
    return df


def drop_halted(df: pd.DataFrame) -> pd.DataFrame:
    """거래정지일은 시가·고가·저가가 0으로 들어오므로 제거합니다
    (남겨두면 이동평균이 왜곡되고 기간 중 최대 하락률이 -100%로 계산됩니다)."""
    return df[(df["Open"] > 0) & (df["Low"] > 0) & (df["Volume"] > 0)]


def get_validation_universe(start: str) -> pd.DataFrame:
    """검증용 종목 목록 (Code, Name, Market, Delisted).
    생존 편향을 줄이기 위해 start 이후 상장폐지된 보통주도 포함하고,
    시총 필터는 현재 시점 값이라 미래 정보가 되므로 적용하지 않습니다
    (대신 신호 시점의 20일 평균 거래대금으로 거릅니다).
    시장 구분은 현재(또는 폐지 직전) 기준이라 이전상장 종목은 과거와 다를 수 있습니다."""
    live = fdr.StockListing("KRX")
    live = live[live["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])].copy()
    live["Market"] = live["Market"].replace({"KOSDAQ GLOBAL": "KOSDAQ"})
    live["Delisted"] = False

    dl = fdr.StockListing("KRX-DELISTING")
    dl["DelistingDate"] = pd.to_datetime(dl["DelistingDate"])
    dl = dl[(dl["DelistingDate"] >= start) & dl["Market"].isin(["KOSPI", "KOSDAQ"])
            & (dl["SecuGroup"] == "주권") & (dl["Kind"] == "보통주")]
    dl = dl[~dl["Reason"].str.contains("스팩", na=False)]
    dl = dl.rename(columns={"Symbol": "Code"}).assign(Delisted=True)

    df = pd.concat([live[["Code", "Name", "Market", "Delisted"]],
                    dl[["Code", "Name", "Market", "Delisted"]]], ignore_index=True)
    df = df[df["Code"].astype(str).str.endswith("0")]
    df = df[~df["Name"].str.contains("스팩|SPAC", na=False)]
    return df.drop_duplicates("Code", keep="first").reset_index(drop=True)


def get_ohlcv_cached(code: str, start: str, refresh: bool = False, static: bool = False) -> pd.DataFrame:
    """검증용 일봉. cache/ohlcv에 저장해 두고 오늘 받은 파일이면 재사용합니다.
    static=True(상장폐지 종목)면 시세가 더 바뀌지 않으므로 날짜와 관계없이 재사용합니다."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"{code}_{start}.pkl")
    if not refresh and os.path.exists(path):
        if static or datetime.fromtimestamp(os.path.getmtime(path), KST).date() == now_kst().date():
            return pd.read_pickle(path)
    df = get_ohlcv(code, start)
    df.to_pickle(path)
    return df


def is_trading_day() -> bool:
    """오늘 코스피 지수 봉이 있으면 거래일로 판단 (공휴일 스킵용)."""
    today = now_kst().strftime("%Y-%m-%d")
    try:
        idx = fdr.DataReader("KS11", today)
        return not idx.empty
    except Exception:
        return now_kst().weekday() < 5
