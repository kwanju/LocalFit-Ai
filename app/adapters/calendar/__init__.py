"""Google Calendar 도메인 어댑터 (ADR-022).

ADR-020 운동 히트맵(``app/api/calendar.py`` + ``app/core/calendar_metrics.py``)과는
**완전히 별개**의 gcal 네임스페이스다 — 히트맵은 로컬 DB 통계이고, 여기는 외부 Google
Calendar API + OAuth2 Desktop 이다(혼동 금지, phase-9 명세 ⚠️).

ADR-012 의존 규칙: adapters 는 ``app.core`` 를 import 하지 않는다(역참조 방지). 틈새
계산(순수 로직)은 ``app.core.calendar_gaps`` 에 있고, 그 둘을 묶는 오케스트레이션은
``app.pipecat_services.calendar_sync`` 가 담당한다.
"""
