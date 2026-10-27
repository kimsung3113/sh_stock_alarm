"""실행 진입점.

python main.py scan        # 지금 스캔 1회 (장 마감 후 실행 권장)
python main.py track       # 저장된 신호의 수익률 갱신
python main.py report      # 실전 신호 성과 통계 출력 (--send 로 텔레그램 전송)
python main.py backtest    # 과거 데이터 검증 (--years 3 --sample 200)
python main.py validate BRK20   # 기법 검증: 다음 날 시가 진입·비용·시장별·기준 대비 (application/validation_service.py)
python main.py schedule    # 평일 자동 실행 (스캔·추적 + 주간 리포트)
python main.py test-telegram
"""
import argparse
import os

import pandas as pd

import config
from application import report_service as report
from application.backtest_service import run_backtest
from application.scan_service import run_scan
from application.tracking_service import run_tracking
from infrastructure import telegram as notifier
from infrastructure.market_data import is_trading_day

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)


def daily_job():
    if not is_trading_day():
        print("휴장일 - 건너뜀")
        return
    run_scan()
    run_tracking()


def weekly_job():
    notifier.send_message(notifier.format_stats(report.live_stats(), "주간 기법별 성과"))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").add_argument("--no-notify", action="store_true")
    sub.add_parser("track")
    sub.add_parser("report").add_argument("--send", action="store_true")
    bt = sub.add_parser("backtest")
    bt.add_argument("--years", type=int, default=3)
    bt.add_argument("--sample", type=int, default=200)
    bt.add_argument("--codes", nargs="*")
    va = sub.add_parser("validate")
    va.add_argument("strategies", nargs="+", help="기법 id (예: BRK20)")
    va.add_argument("--start", default=config.VALIDATE_START)
    va.add_argument("--limit", type=int, help="빠른 확인용 종목 수 제한")
    va.add_argument("--refresh", action="store_true", help="캐시 무시하고 다시 받기")
    va.add_argument("--inspect", type=int, default=10, help="출력할 표본 신호 수")
    sub.add_parser("schedule")
    sub.add_parser("test-telegram")
    a = p.parse_args()

    if a.cmd == "scan":
        run_scan(notify=not a.no_notify)
    elif a.cmd == "track":
        run_tracking()
    elif a.cmd == "report":
        stats = report.live_stats()
        print(stats.to_string(index=False) if not stats.empty else "데이터 없음")
        if a.send:
            notifier.send_message(notifier.format_stats(stats))
    elif a.cmd == "backtest":
        stats = run_backtest(a.years, a.sample, a.codes)
        print(stats.to_string(index=False) if not stats.empty else "신호 없음")
        os.makedirs(config.RESULTS_DIR, exist_ok=True)
        path = os.path.join(config.RESULTS_DIR, "backtest_result.csv")
        stats.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"→ {path} 저장")
    elif a.cmd == "validate":
        from application.validation_service import run_validation
        run_validation(a.strategies, a.start, a.limit, a.refresh, a.inspect)
    elif a.cmd == "schedule":
        from apscheduler.schedulers.blocking import BlockingScheduler
        s = BlockingScheduler(timezone="Asia/Seoul")
        s.add_job(daily_job, "cron", day_of_week="mon-fri",
                  hour=config.SCAN_HOUR, minute=config.SCAN_MINUTE)
        s.add_job(weekly_job, "cron", day_of_week=config.WEEKLY_REPORT_DAY,
                  hour=config.WEEKLY_REPORT_HOUR, minute=config.WEEKLY_REPORT_MINUTE)
        print("스케줄러 시작 (Ctrl+C로 종료)")
        s.start()
    elif a.cmd == "test-telegram":
        ok = notifier.send_message("✅ 텔레그램 연결 테스트 성공")
        print("전송 성공" if ok else "전송 실패 - .env 설정을 확인하세요")

