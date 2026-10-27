"""실전 신호 성과 조회."""
import pandas as pd

from domain.performance import summarize
from infrastructure import signal_repository as db


def live_stats() -> pd.DataFrame:
    conn = db.connect()
    df = pd.read_sql(
        """SELECT s.strategy_name, s.side, r.horizon, r.return_pct, r.max_up_pct, r.max_down_pct
           FROM signal_returns r JOIN signals s ON s.id = r.signal_id""", conn)
    conn.close()
    return summarize(df)
