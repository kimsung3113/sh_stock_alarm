"""저장된 신호의 이후 수익률 추적."""
from collections import defaultdict

import numpy as np
import pandas as pd

import config
from domain.returns import forward_returns
from infrastructure import signal_repository as db
from infrastructure.market_data import get_ohlcv


def run_tracking(horizons=None) -> int:
    horizons = horizons or config.HORIZONS
    conn = db.connect()
    by_code = defaultdict(list)
    for s in db.pending_signals(conn, horizons):
        by_code[s["code"]].append(s)

    filled = 0
    for code, sigs in by_code.items():
        start = min(s["signal_date"] for s in sigs)
        try:
            df = get_ohlcv(code, start)
        except Exception as e:
            print(f"{code} 데이터 오류: {e}")
            continue
        dates = df.index.normalize()
        for s in sigs:
            pos = np.where(dates == pd.Timestamp(s["signal_date"]))[0]
            if not len(pos):
                continue
            for h, r in forward_returns(df, int(pos[0]), s["price"], horizons).items():
                db.insert_return(conn, s["id"], h, r)
                filled += 1
        conn.commit()
    conn.close()
    print(f"수익률 갱신: {filled}건")
    return filled
