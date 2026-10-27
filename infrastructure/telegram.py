"""텔레그램 알림 (메시지 전송·포맷)."""
import html
import time

import requests

import config

API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 3900  # 텔레그램 한도 4096자보다 여유 있게


def send_message(text: str) -> bool:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[텔레그램 미설정 - 콘솔 출력]\n" + text)
        return False
    for _ in range(3):
        r = requests.post(API.format(token=config.TELEGRAM_TOKEN), data={
            "chat_id": config.TELEGRAM_CHAT_ID, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10)
        if r.status_code == 429:  # 전송 속도 제한
            time.sleep(r.json().get("parameters", {}).get("retry_after", 3))
            continue
        if not r.ok:
            print("텔레그램 오류:", r.text)
        return r.ok
    return False


def format_signal(s: dict) -> str:
    icon, label = ("🟢", "매수") if s["side"] == "BUY" else ("🔴", "매도")
    vs20 = (s["price"] / s["ma20"] - 1) * 100 if s.get("ma20") else 0
    return (
        f"{icon} <b>{label} | {html.escape(s['strategy_name'])}</b>\n"
        f"{html.escape(s['name'])} ({s['code']}) · {s['market']}\n"
        f"종가 {s['price']:,.0f}원 | 거래량 {s.get('vol_ratio') or 0:.1f}배\n"
        f"RSI {s.get('rsi') or 0:.1f} | 20일선 대비 {vs20:+.1f}%\n"
        f"근거: {html.escape(s['reason'])}\n"
        f"<i>기준일 {s['signal_date']} · #{s.get('id', '-')}</i>"
    )


def send_signals(signals: list):
    """신호를 매수→매도, 거래량 비율 높은 순으로 묶어 전송."""
    if not signals:
        send_message("📭 오늘은 조건을 만족한 신호가 없습니다.")
        return
    signals = sorted(signals, key=lambda s: (s["side"] != "BUY", -(s.get("vol_ratio") or 0)))
    buys = sum(s["side"] == "BUY" for s in signals)
    header = f"📊 <b>{signals[0]['signal_date']} 신호 {len(signals)}건</b> (매수 {buys} · 매도 {len(signals) - buys})"
    chunk = header
    for s in signals:
        block = "\n\n" + format_signal(s)
        if len(chunk) + len(block) > MAX_LEN:
            send_message(chunk)
            chunk = block.strip()
            time.sleep(1)
        else:
            chunk += block
    send_message(chunk)


def format_stats(stats, title: str = "기법별 성과") -> str:
    if stats.empty:
        return f"📈 <b>{title}</b>\n아직 집계할 데이터가 없습니다."
    lines = [f"📈 <b>{title}</b>", "<pre>"]
    for r in stats.itertuples(index=False):
        lines.append(f"{r[0][:10]:<10} {r[2]:>2}일 n={r[3]:<4} 승률 {r[4]:5.1f}% 평균 {r[5]:+.2f}%")
    lines.append("</pre>")
    lines.append("<i>매도 신호의 성과는 이후 하락폭(피한 손실) 기준</i>")
    return "\n".join(lines)
