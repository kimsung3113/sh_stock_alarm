"""신호 저장소 (SQLite). 신호 스냅샷과 이후 수익률을 기록합니다."""
import sqlite3
from datetime import datetime

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,          -- 알림을 보낸 실제 시각
    signal_date   TEXT NOT NULL,          -- 신호가 발생한 봉의 날짜
    code          TEXT NOT NULL,
    name          TEXT,
    market        TEXT,
    strategy_id   TEXT NOT NULL,
    strategy_name TEXT,
    side          TEXT NOT NULL,          -- BUY / SELL
    price         REAL NOT NULL,          -- 신호 봉 종가 (수익률 기준가)
    volume        INTEGER,
    vol_ratio     REAL,
    rsi           REAL,
    ma5           REAL,
    ma20          REAL,
    ma60          REAL,
    reason        TEXT,
    UNIQUE (signal_date, code, strategy_id)   -- 같은 신호 중복 저장·알림 방지
);
CREATE TABLE IF NOT EXISTS signal_returns (
    signal_id     INTEGER NOT NULL REFERENCES signals(id),
    horizon       INTEGER NOT NULL,       -- 거래일 수 (1, 5, 20 ...)
    target_date   TEXT NOT NULL,
    price         REAL NOT NULL,
    return_pct    REAL NOT NULL,          -- 기준가 대비 종가 변화율
    max_up_pct    REAL,                   -- 기간 중 최고가 기준 최대 상승률
    max_down_pct  REAL,                   -- 기간 중 최저가 기준 최대 하락률
    PRIMARY KEY (signal_id, horizon)
);
CREATE INDEX IF NOT EXISTS idx_signals_code ON signals(code);
"""

COLUMNS = ["signal_date", "code", "name", "market", "strategy_id", "strategy_name", "side",
           "price", "volume", "vol_ratio", "rsi", "ma5", "ma20", "ma60", "reason"]


def connect(path: str = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_signal(conn, s: dict):
    """새 신호면 id 반환, 이미 저장된 신호면 None."""
    cols = ["created_at"] + COLUMNS
    vals = [datetime.now().isoformat(timespec="seconds")] + [s.get(c) for c in COLUMNS]
    cur = conn.execute(
        f"INSERT OR IGNORE INTO signals ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


def pending_signals(conn, horizons):
    """아직 모든 추적 기간의 수익률이 채워지지 않은 신호."""
    return conn.execute(
        """SELECT s.* FROM signals s
           WHERE (SELECT COUNT(*) FROM signal_returns r WHERE r.signal_id = s.id) < ?
           ORDER BY s.code, s.signal_date""", (len(horizons),)).fetchall()


def insert_return(conn, signal_id: int, horizon: int, r: dict):
    conn.execute(
        """INSERT OR IGNORE INTO signal_returns
           (signal_id, horizon, target_date, price, return_pct, max_up_pct, max_down_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (signal_id, horizon, r["target_date"], r["price"], r["return_pct"],
         r["max_up_pct"], r["max_down_pct"]))
