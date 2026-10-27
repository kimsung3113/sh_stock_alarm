"""기법별 성과 통계."""
import numpy as np
import pandas as pd


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """매수 신호는 상승이 성공, 매도 신호는 하락(=피한 손실)이 성공으로 봅니다."""
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["edge"] = np.where(df["side"] == "BUY", df["return_pct"], -df["return_pct"])
    out = (df.groupby(["strategy_name", "side", "horizon"])
             .agg(건수=("edge", "size"),
                  승률=("edge", lambda x: (x > 0).mean() * 100),
                  평균성과=("edge", "mean"),
                  중앙값=("edge", "median"),
                  평균최대상승=("max_up_pct", "mean"),
                  평균최대하락=("max_down_pct", "mean"))
             .round(2).reset_index())
    return out.rename(columns={"strategy_name": "기법", "side": "구분", "horizon": "기간(일)"})
