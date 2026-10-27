"""전역 설정. 민감한 값은 .env 파일에서 읽습니다."""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 텔레그램
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 저장소
DB_PATH = os.path.join(BASE_DIR, os.getenv("DB_PATH", "signals.db"))

# 종목 필터 (너무 작거나 거래가 적은 종목은 신호 품질이 떨어지므로 제외)
MIN_MARKET_CAP = 100_000_000_000        # 시가총액 1,000억 원 이상
MIN_AVG_TRADING_VALUE = 3_000_000_000   # 20일 평균 거래대금 30억 원 이상

# 데이터
HISTORY_DAYS = 400          # 스캔 시 불러올 과거 일수 (60일선 등 계산용 여유분 포함)
MIN_BARS = 80               # 최소 봉 개수
MAX_WORKERS = 8             # 동시 다운로드 스레드 수

# 성과 추적 기간 (거래일 기준)
HORIZONS = [1, 5, 20]

# 기법 검증 (application/validation_service.py)
VALIDATE_START = "2019-01-01"          # 코로나 급락·2021 강세·2022 약세·2025~ 강세를 모두 포함
VALIDATE_HORIZONS = [1, 5, 10, 20]     # 다음 날 시가 진입 후 보유 거래일 수 (진입일 포함)
# 왕복 비용(%): 수수료 0.015%×2 + 거래세 0.20%(2026년 기준, 코스피는 농특세 포함) + 슬리피지 0.05%×2
COST_ROUNDTRIP_PCT = 0.33
CACHE_DIR = os.path.join(BASE_DIR, "cache", "ohlcv")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# 통과 기준 (시장별·기간별로 판정)
PASS_MIN_SIGNALS = 100       # 신호 건수 하한
PASS_MIN_TSTAT = 2.0         # 월별 평균 초과수익의 t값 하한 (같은 날 신호끼리의 상관을 고려)
PASS_MIN_YEARS_POSITIVE = 0.6  # 초과수익이 플러스인 연도 비율 하한

# 스케줄 (한국 시간)
SCAN_HOUR, SCAN_MINUTE = 15, 50
WEEKLY_REPORT_DAY = "fri"
WEEKLY_REPORT_HOUR, WEEKLY_REPORT_MINUTE = 16, 30
