"""인터넷 없이 가짜 시세로 전체 흐름(스캔→저장→알림→추적→통계)을 점검합니다.
실행: python -m tests.test_offline
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import config
config.DB_PATH = os.path.join(config.BASE_DIR, "test_signals.db")
config.MIN_AVG_TRADING_VALUE = 0

from application import backtest_service as backtest  # noqa: E402
from application import report_service as report  # noqa: E402
from application import scan_service as scanner  # noqa: E402
from application import tracking_service as tracker  # noqa: E402
from infrastructure import telegram as notifier  # noqa: E402


def fake_ohlcv(code, start=None, drop_unclosed=True, n=400):
    rng = np.random.default_rng(int(code))
    ret = rng.normal(0.0005, 0.025, n)
    close = 10000 * np.exp(np.cumsum(ret))
    open_ = close * (1 + rng.normal(0, 0.01, n))
    high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.01, n)))
    low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.01, n)))
    vol = rng.lognormal(13, 0.6, n).astype(int)
    idx = pd.bdate_range(end="2026-10-23", periods=n)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx)
    return df.iloc[:-25] if drop_unclosed == "scan" else df


def run():
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    codes = [f"{i:05d}0" for i in range(1, 61)]
    uni = pd.DataFrame({"Code": codes, "Name": [f"테스트{i}" for i in range(60)], "Market": "KOSPI"})

    # 1) 25일 전 시점으로 스캔 (나중에 수익률을 채울 수 있게)
    scanner.get_universe = lambda: uni
    scanner.get_ohlcv = lambda c, s: fake_ohlcv(c, drop_unclosed="scan")
    new = scanner.run_scan(notify=False)
    assert new, "신호가 하나도 없음"
    print("샘플 알림:\n" + notifier.format_signal(new[0]))

    # 2) 중복 방지 확인
    again = scanner.run_scan(notify=False)
    assert again == [], "중복 신호가 저장됨"

    # 3) 수익률 추적
    tracker.get_ohlcv = lambda c, s: fake_ohlcv(c)
    filled = tracker.run_tracking()
    assert filled == len(new) * 3, (filled, len(new))

    # 4) 통계
    print(report.live_stats().to_string(index=False))

    # 5) 백테스트
    backtest.get_universe = lambda: uni
    backtest.get_ohlcv = lambda c, s: fake_ohlcv(c)
    bt = backtest.run_backtest(sample=20)
    print(bt.head(6).to_string(index=False))
    os.remove(config.DB_PATH)
    print("\n모든 오프라인 테스트 통과")


if __name__ == "__main__":
    run()
