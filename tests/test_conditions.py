"""기법이 '조건대로' 신호를 내는지 확인.

1) 수익률 계산 규칙 (오프라인): 다음 날 시가 진입, h일째 종가 청산, 비용, 점상한가 미체결, 상장폐지 청산
2) 기법 조건 대조 (온라인, 캐시 사용): domain/strategy.py와 별개로 원시 OHLCV에서 조건을 직접 다시 계산해
   두 결과의 신호 날짜가 정확히 같은지 비교합니다 (놓친 신호·잘못된 신호 모두 0이어야 통과).
   새 기법을 검증할 때는 REFERENCE에 같은 조건의 독립 구현을 추가합니다.

python -m tests.test_conditions
"""
import numpy as np
import pandas as pd

import config
from domain.indicators import add_indicators
from domain.returns import forward_table
from domain.strategy import STRATEGIES, evaluate
from infrastructure.market_data import get_ohlcv_cached


def test_forward_table():
    idx = pd.date_range("2024-01-01", periods=6, freq="B")
    df = pd.DataFrame({"Open":  [100, 110, 143, 150, 160, 170],
                       "High":  [105, 115, 143, 155, 165, 175],
                       "Low":   [95, 105, 143, 145, 155, 165],
                       "Close": [102, 112, 143, 152, 162, 172]}, index=idx)
    f = forward_table(df, [1, 3], cost=0.3, delisted=False)
    assert f["entry"].iloc[0] == 110                                  # 다음 날 시가 진입
    assert np.isclose(f["ret_1"].iloc[0], (112 / 110 - 1) * 100 - 0.3)  # 진입일 종가 청산
    assert np.isclose(f["ret_3"].iloc[0], (152 / 110 - 1) * 100 - 0.3)  # 진입일 포함 3일째 종가
    assert f["locked"].iloc[1] and np.isnan(f["entry"].iloc[1])       # 다음 날 점상한가 → 미체결
    assert np.isnan(f["ret_3"].iloc[3])                               # 데이터 부족 → 제외
    g = forward_table(df, [3], cost=0.0, delisted=True)
    assert np.isclose(g["ret_3"].iloc[3], (172 / 160 - 1) * 100)      # 폐지 종목 → 마지막 종가 청산
    assert np.isnan(g["ret_3"].iloc[5])                               # 마지막 봉은 진입 불가
    print("수익률 계산 규칙 OK")


def ref_brk20(raw: pd.DataFrame) -> set:
    """20일 신고가 돌파: 종가 > 직전 20일 고가 최댓값, 거래량 >= 직전 20일 평균의 2.5배, 양봉."""
    o, h, c, v = (raw[k].tolist() for k in ("Open", "High", "Close", "Volume"))
    hits = set()
    for i in range(20, len(raw)):
        prev_high = max(h[i - 20:i])
        vol_avg = sum(v[i - 20:i]) / 20
        if c[i] > prev_high and v[i] >= 2.5 * vol_avg and c[i] > o[i]:
            hits.add(raw.index[i])
    return hits


REFERENCE = {"BRK20": ref_brk20}
SAMPLE_CODES = ["005930", "000660", "035420", "086520", "247540", "196170",
                "028300", "293490", "042700", "012450", "058470", "214150"]


def test_reference(strategy_id: str, codes=SAMPLE_CODES):
    strat = next(s for s in STRATEGIES if s.id == strategy_id)
    ref = REFERENCE[strategy_id]
    total, examples = 0, []
    for code in codes:
        raw = get_ohlcv_cached(code, config.VALIDATE_START)
        df = add_indicators(raw)
        mine = {df.index[i] for i in range(1, len(df)) if evaluate(df, i, [strat])}
        theirs = ref(raw)
        missed, extra = theirs - mine, mine - theirs
        assert not missed and not extra, f"{code} 불일치: 놓침 {sorted(missed)[:3]} 잘못 {sorted(extra)[:3]}"
        total += len(mine)
        examples += [(code, d) for d in sorted(mine)[-1:]]
    print(f"{strategy_id} 조건 대조 OK: {len(codes)}종목, 신호 {total}건 모두 일치")
    print("  차트 확인용 최근 신호:", ", ".join(f"{c} {d:%Y-%m-%d}" for c, d in examples))


if __name__ == "__main__":
    test_forward_table()
    for sid in REFERENCE:
        test_reference(sid)
    print("\n모든 조건 테스트 통과")
