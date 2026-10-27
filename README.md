# 국내 주식 신호 알림 봇 (일봉 스윙)

장 마감 후 코스피·코스닥 전 종목을 스캔해 기법 조건을 만족한 종목을 텔레그램으로 알리고,
알림과 같은 시점에 신호 스냅샷을 DB에 저장한 뒤 1·5·20거래일 후 수익률을 자동으로 추적합니다.

## 1. 설치

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. 텔레그램 봇 연결

1. 텔레그램에서 `@BotFather` 검색 → `/newbot` → 받은 토큰을 `.env`의 `TELEGRAM_TOKEN`에 입력
2. 만든 봇에게 아무 메시지나 보낸 뒤 브라우저에서
   `https://api.telegram.org/bot<토큰>/getUpdates` 접속 → `"chat":{"id": ...}` 값을 `TELEGRAM_CHAT_ID`에 입력
3. `python main.py test-telegram` 으로 확인

## 3. 사용법

| 명령 | 설명 |
|---|---|
| `python main.py backtest --years 3 --sample 200` | 과거 데이터로 기법별 승률·평균 수익률 확인 (먼저 해볼 것) |
| `python main.py validate BRK20` | 기법 검증: 다음 날 시가 진입·비용 차감·코스피/코스닥·연도별·전 종목 평균 대비 (상장폐지 포함) |
| `python main.py scan` | 지금 스캔 1회 (15:40 이후 실행 권장) |
| `python main.py track` | 저장된 신호의 수익률 갱신 |
| `python main.py report --send` | 실전 신호 성과 통계 (텔레그램 전송) |
| `python main.py schedule` | 평일 15:50 스캔·추적, 금요일 16:30 주간 리포트 자동 실행 |

## 4. 구조 (DDD 계층)

```
main.py                         진입점 (interfaces.cli 호출)
config.py                       설정 (필터 기준, 추적 기간, 스케줄, 경로)

domain/                         순수 규칙 - 외부 I/O 없음
  indicators.py                 지표 계산 (이동평균, RSI, 볼린저, 거래량 비율)
  strategy.py                   기법 정의 + 판정  ← 기법은 여기서 추가·수정
  returns.py                    신호 이후 수익률 계산 규칙 (종가 기준 / 다음 날 시가 진입)
  performance.py                기법별 승률·평균 성과 집계

application/                    유스케이스 - domain과 infrastructure를 엮음
  scan_service.py               전 종목 스캔 → DB 저장 → 알림
  tracking_service.py           저장된 신호의 수익률 추적
  report_service.py             실전 신호 성과 조회
  backtest_service.py           같은 기법 코드로 과거 검증
  validation_service.py         기법 검증 (이벤트 스터디, 상장폐지 포함)

infrastructure/                 외부 시스템 어댑터
  market_data.py                시세 수집 (FinanceDataReader), 캐시, 휴장일 판단
  signal_repository.py          SQLite (signals, signal_returns 테이블)
  telegram.py                   텔레그램 전송·메시지 포맷

interfaces/
  cli.py                        명령줄 (scan, track, report, backtest, validate, schedule)

tests/                          오프라인·조건 대조 테스트
cache/, results/                검증 캐시·결과 (git 제외)
```

의존 방향: `interfaces → application → domain`, `application → infrastructure`. `domain`은 다른 계층을 참조하지 않습니다.

## 5. 기본 탑재 기법

매수: 골든크로스+거래량 2배, 20일 신고가 돌파+거래량 2.5배, RSI 과매도(30) 반등, 볼린저 하단 반등
매도: 데드크로스, RSI 과매수(70) 이탈

새 기법 추가는 `domain/strategy.py`에 `(df, i)`를 받아 근거 문자열(또는 None)을 반환하는 함수를 만들고
`STRATEGIES` 목록에 한 줄 추가하면 됩니다. 스캔·백테스트·통계에 자동 반영됩니다.

## 6. 알아둘 점

- 수익률 기준가는 신호 봉의 종가입니다. 실제로는 다음 날 시가에 진입하게 되므로 결과와 차이가 생깁니다.
- 수수료·세금(매도 시 약 0.18~0.2%)과 슬리피지는 반영되지 않았습니다.
- 신호 수가 30~50건 이상 쌓이기 전의 승률은 우연일 가능성이 큽니다.
- 백테스트는 현재 상장 종목만 대상이라 상장폐지 종목이 빠지는 생존 편향이 있습니다.
- 이 코드는 검증 도구이며 투자 수익을 보장하지 않습니다.
- 신호를 타인에게 유료로 제공하려면 자본시장법상 유사투자자문업 신고 대상인지 확인하세요.

## 7. 테스트

```bash
python -m tests.test_offline      # 오프라인 (가짜 데이터)
python -m tests.test_conditions   # 수익률 규칙 + 기법 조건을 독립 구현과 대조 (시세 다운로드)
```

검증 통과 기준(`config.py`의 PASS_*): 신호 100건 이상, 비용 차감 평균수익 > 0, 전 종목 평균 대비 초과수익 > 0,
월별 t값 2 이상, 초과수익 플러스 연도 60% 이상. 모두 만족하면 PASS, 초과수익 > 0이고 t값 1 이상이면 WEAK.
