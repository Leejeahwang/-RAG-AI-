"""
gui/dashboardtest.py
====================
라즈베리파이 없이 dashboard.py 기능을 검증하기 위한 진입점.

가짜로 대체된 부분:
    - QA (RAG/LLM)      → FakeQA: 간단한 한국어 응답
    - TTS               → FakeTTS: 로그로만 표시
    - STT/마이크        → 비활성. 텍스트 입력 박스로 대체
    - CCTV 카메라       → 합성 BGR 프레임 (격자 + 시간 + 화재 시 빨간 박스)
    - YOLO 화재 탐지    → 40초 시나리오 순환 (안전 → 의심 → 화재)
    - GPIO/MQTT 알람    → 백엔드가 자동 print fallback

그대로 사용:
    - 센서 (simulate=True)
    - 위험도 fusion 계산
    - state.RUNTIME / Lock / fragment 갱신 / 알람 트리거 CAS

실행:
    streamlit run gui/dashboardtest.py
"""

from __future__ import annotations

import os
import queue
import random
import sys
import threading
import time
from typing import Any, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)

# 테스트 대시보드는 멀티존 관제 화면을 시뮬레이션 — state import 전에 설정
os.environ["MQTT_MODE"] = "1"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import streamlit as st  # noqa: E402

from vision import cctv_service  # noqa: E402

from gui.state import RUNTIME, MQTT_MODE, FireSnapshot, SensorSnapshot, RiskSnapshot, STTMessage  # noqa: E402
from gui import workers as W, components as C  # noqa: E402

# 시뮬레이션 구역 목록
FAKE_ZONES = ["A구역", "B구역", "C구역"]


class FakeQA:
    _EMERGENCY = [
        "즉시 가장 가까운 비상구로 대피하세요. 엘리베이터 사용 금지. 젖은 수건으로 입과 코를 막으십시오.",
        "긴급! 모든 작업을 중지하고 비상 대피로를 따라 신속히 외부로 이동하십시오. 119에 즉시 신고하세요.",
        "위험 상황. 자세를 낮추고 연기를 피해 비상 출구로 대피하십시오. 화재구역에서 멀어지세요.",
    ]
    _QUERY = [
        "확인된 매뉴얼 기준, 평시 점검 절차를 따르시면 됩니다.",
        "현재 시스템은 정상 작동 중입니다. 추가 조치가 필요하지 않습니다.",
        "테스트 모드입니다. 실제 RAG 응답이 아닙니다.",
        "센서 모니터링 데이터 정상 범위. 30분 후 재점검을 권장합니다.",
    ]

    def invoke(self, prompt: str) -> dict:
        time.sleep(1.5)
        bank = self._EMERGENCY if any(k in prompt for k in ("위급", "재난", "긴급", "경고")) else self._QUERY
        return {"result": random.choice(bank)}


class FakeTTS:
    def speak(self, text: str, lang: str = "ko") -> None:
        RUNTIME.add_log(f"🔊 [FAKE-TTS] ({lang}) {text[:48]}...")

    def speak_async(self, text: str, lang: str = "ko") -> None:
        self.speak(text, lang)

    def stop(self) -> None:
        pass


# 시나리오 슬롯: 구역당 180초 (60s 상승 → 60s 화재 유지 → 60s 하강)
SCENARIO_RISE = 60.0
SCENARIO_HOLD = 60.0
SCENARIO_FALL = 60.0
SCENARIO_SLOT = SCENARIO_RISE + SCENARIO_HOLD + SCENARIO_FALL   # 180s


def _active_zone_in_cycle(elapsed: float) -> tuple:
    """현재 활성 구역과 그 구역 내 경과시간(초)을 반환."""
    total_cycle = SCENARIO_SLOT * len(FAKE_ZONES)
    t = elapsed % total_cycle
    idx = int(t // SCENARIO_SLOT)
    inner = t - idx * SCENARIO_SLOT
    return FAKE_ZONES[idx], inner


@st.cache_resource(show_spinner=False)
def _scenario_epoch() -> float:
    """모든 워커가 공유하는 시나리오 시작 기준 시각.
    Streamlit 리런/리로드에도 한 번만 결정되어, 워커가 중복으로 떠도 같은 phase를 계산한다.
    이걸로 sensor/fire 워커가 서로 다른 `start`를 써서 동일 zone에 서로 다른 phase 값을
    번갈아 쓰던 race(불 화면 깜빡임, A↔B 값 스왑)를 제거한다."""
    return time.time()


def fake_sensor_worker(stop_event: threading.Event) -> None:
    """순차 회전: A → B → C 차례대로 1분 상승 → 1분 하강 후 다음 구역."""
    from sensors import fusion
    RUNTIME.add_log(f"📊 [FAKE-SENSOR] 순차 회전 시작 (구역당 {int(SCENARIO_SLOT)}s)")
    BASE = {"temp": 24.0, "gas": 90.0, "smoke": 45.0}
    PEAK = {"temp": 72.0, "gas": 620.0, "smoke": 580.0}

    start = _scenario_epoch()
    last_active = None
    while not stop_event.is_set():
        now = time.time()
        elapsed = now - start
        active_zone, inner_t = _active_zone_in_cycle(elapsed)

        if active_zone != last_active:
            RUNTIME.add_log(f"🎬 [시나리오] '{active_zone}' 구역 시작")
            last_active = active_zone

        # 3단계: 상승 → 화재 유지(피크) → 하강
        if inner_t < SCENARIO_RISE:
            active_ratio = inner_t / SCENARIO_RISE
        elif inner_t < SCENARIO_RISE + SCENARIO_HOLD:
            active_ratio = 1.0   # 1분간 피크 유지
        else:
            active_ratio = max(
                0.0,
                1.0 - (inner_t - SCENARIO_RISE - SCENARIO_HOLD) / SCENARIO_FALL,
            )

        for zone in FAKE_ZONES:
            ratio = active_ratio if zone == active_zone else 0.0
            temp  = BASE["temp"]  + (PEAK["temp"]  - BASE["temp"])  * ratio + random.uniform(-0.3, 0.3)
            gas   = BASE["gas"]   + (PEAK["gas"]   - BASE["gas"])   * ratio + random.uniform(-3, 3)
            smoke = BASE["smoke"] + (PEAK["smoke"] - BASE["smoke"]) * ratio + random.uniform(-3, 3)
            snap = SensorSnapshot(
                smoke=max(0, int(smoke)), gas=max(0, int(gas)),
                temperature=round(temp, 1), humidity=round(50 + random.uniform(-2, 2), 1), ts=now,
            )
            RUNTIME.set_zone_sensors(zone, snap)
            t_data = {"temperature": temp, "humidity": snap.humidity}
            zone_fire = RUNTIME.get_zone_fire(zone)
            risk = fusion.calculate_risk_level(smoke, gas, t_data, zone_fire.detected)
            RUNTIME.set_zone_risk(zone, RiskSnapshot(
                level=int(risk["level"]), label=str(risk["label"]),
                details=str(risk["details"]), ts=now,
            ))
        stop_event.wait(1.0)
    RUNTIME.add_log("🛑 [FAKE-SENSOR] 종료")


def fake_camera_worker(stop_event: threading.Event) -> None:
    """현재 선택된 구역에 해당하는 합성 카메라 프레임 생성."""
    RUNTIME.add_log("📷 [FAKE-CAM] 합성 영상 스트리밍 시작")
    H, W = 480, 640
    prev_state = None  # (active_zone, fire.detected) 변화 추적
    while not stop_event.is_set():
        active = RUNTIME.get_active_zone() or "—"
        fire = RUNTIME.get_fire()
        cur_state = (active, fire.detected)
        if cur_state != prev_state:
            RUNTIME.add_log(
                f"📷 [DBG-CAM] 화면 변경: active='{active}' fire={fire.detected}"
            )
            prev_state = cur_state
        # 화재면 어둡고 붉은 톤, 안전이면 회색톤 (사인파 제거해 깜빡임 방지)
        if fire.detected:
            frame = np.full((H, W, 3), (30, 30, 90), dtype=np.uint8)
        else:
            frame = np.full((H, W, 3), (60, 65, 60), dtype=np.uint8)
        for x in range(0, W, 64):
            cv2.line(frame, (x, 0), (x, H), (90, 90, 90), 1)
        for y in range(0, H, 64):
            cv2.line(frame, (0, y), (W, y), (90, 90, 90), 1)
        cv2.putText(frame, f"FAKE CCTV [{active}]", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1)
        cv2.putText(frame, "TEST MODE - NO REAL CAMERA", (20, H - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        if fire.detected:
            cv2.rectangle(frame, (300, 200), (500, 360), (0, 0, 220), 4)
            cv2.putText(frame, "FIRE!", (320, 290),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 255), 4)
            cv2.putText(frame, f"conf {fire.confidence:.2f}", (320, 340),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cctv_service.latest_frame = frame
        RUNTIME.set_frame(frame)
        stop_event.wait(1.0)
    RUNTIME.add_log("🛑 [FAKE-CAM] 종료")


FAKE_STT_QUERIES = [
    "현재 상황 보고해 줘",
    "지금 어느 구역이 가장 위험해?",
    "A구역에서 화재가 나면 어디로 대피해야 해?",
    "비상 대피 절차 알려줘",
    "센서 값이 정상이야?",
    "B구역 가스 농도 위험해?",
]


def fake_stt_worker(stop_event: threading.Event) -> None:
    """가짜 STT — 마이크 토글이 켜지면 2초 뒤 임의의 질문을 STT 큐에 푸시하고 토글을 자동 OFF한다.

    실제 마이크 없이 단발성 음성 인식을 시뮬레이션한다. listen_once 패턴과 유사.
    """
    RUNTIME.add_log("🎙️ [FAKE-STT] 시뮬레이션 준비 (토글로 활성화)")
    was_on = False
    while not stop_event.is_set():
        on = RUNTIME.is_stt_enabled()
        if on and not was_on:
            RUNTIME.add_log("🎙️ [FAKE-STT] 마이크 켜짐 — 2초 후 가짜 음성 입력")
            stop_event.wait(2.0)
            if stop_event.is_set():
                break
            if RUNTIME.is_stt_enabled():
                text = random.choice(FAKE_STT_QUERIES)
                RUNTIME.add_log(f"🎤 [FAKE-STT] 인식: {text}")
                RUNTIME.push_stt(STTMessage(text=text, lang="ko", ts=time.time()))
                RUNTIME.set_stt_enabled(False)
        was_on = RUNTIME.is_stt_enabled()
        stop_event.wait(0.3)
    RUNTIME.add_log("🛑 [FAKE-STT] 종료")


def fake_fire_worker(stop_event: threading.Event) -> None:
    """순차 회전 시나리오 — 활성 구역에서만 화재 발생, 1분간 안정 유지.

    활성 구역 타임라인 (180s 슬롯):
      0~55s     : 안전 (sensors 상승 중)
      55~60s    : 연기 의심
      60~120s   : 화재 감지 — detected=True 60초간 깜빡임 없이 안정 유지
      120~180s  : 안전 복귀 (sensors 하강 중, 화면 정상 복귀)
    """
    RUNTIME.add_log("🔥 [FAKE-FIRE] 순차 회전 시나리오 시작 (구역당 180s)")
    FIRE_START = SCENARIO_RISE                          # 60s
    FIRE_END = SCENARIO_RISE + SCENARIO_HOLD            # 120s
    start = _scenario_epoch()
    last_phase = {z: "" for z in FAKE_ZONES}
    # 구역별 안정된 화재 conf (랜덤 깜빡임 방지를 위해 화재 진입 시 한 번만 결정)
    fire_conf_locked = {z: 0.0 for z in FAKE_ZONES}

    while not stop_event.is_set():
        now = time.time()
        elapsed = now - start
        active_zone, inner_t = _active_zone_in_cycle(elapsed)

        for zone in FAKE_ZONES:
            if zone == active_zone:
                if inner_t < FIRE_START - 5:           # 0~55s
                    detected = False
                    conf = round(0.05 + random.random() * 0.05, 2)
                    desc, phase = "안전", "safe"
                elif inner_t < FIRE_START:             # 55~60s
                    detected = False
                    conf = round(0.40 + random.random() * 0.15, 2)
                    desc, phase = "연기 의심", "suspect"
                elif inner_t < FIRE_END:               # 60~120s — 1분간 안정 유지
                    if last_phase[zone] != "fire":
                        fire_conf_locked[zone] = round(0.85 + random.random() * 0.10, 2)
                    detected = True
                    conf = fire_conf_locked[zone]
                    desc, phase = "화재 감지", "fire"
                else:                                  # 120~180s
                    detected = False
                    conf = round(0.10 + random.random() * 0.05, 2)
                    desc, phase = "안전화 진행", "cooldown"
            else:
                detected = False
                conf = round(0.03 + random.random() * 0.02, 2)
                desc, phase = "안전", "safe"

            if phase != last_phase[zone]:
                RUNTIME.add_log(f"🎬 [{zone}] {phase} 단계")
                last_phase[zone] = phase
            RUNTIME.set_zone_fire(zone, FireSnapshot(detected, conf, desc, now))
        stop_event.wait(0.5)
    RUNTIME.add_log("🛑 [FAKE-FIRE] 종료")


def _try_build_real_qa():
    """실제 RAG QA 체인 빌드 시도. 실패 시 None 반환.

    Ollama 서버 미실행 / 모델 미설치 / 벡터DB 없음 등 어떠한 사유로든
    실패하면 FakeQA로 폴백한다. 대시보드 자체는 항상 떠야 한다.
    """
    try:
        import requests
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        import config as _cfg
        r = requests.get(f"{ollama_host}/api/tags", timeout=2)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        wanted = _cfg.LLM_MODEL
        if not any(name == wanted or name.startswith(wanted + ":") or name.split(":")[0] == wanted.split(":")[0] for name in models):
            RUNTIME.add_log(f"⚠️ [REAL-QA] Ollama 모델 '{wanted}' 미설치 → FakeQA 폴백")
            RUNTIME.add_log(f"   설치: ollama pull {wanted}")
            return None

        from rag.loader import load_and_split
        from rag.retriever import build_vectorstore, get_retriever
        from rag.chain import build_qa_chain

        RUNTIME.add_log("📖 [REAL-QA] 매뉴얼 로딩...")
        chunks = load_and_split()
        if not chunks:
            RUNTIME.add_log("⚠️ [REAL-QA] 매뉴얼 청크 0개 → FakeQA 폴백")
            return None

        RUNTIME.add_log("🗂️ [REAL-QA] 벡터DB 로드...")
        db = build_vectorstore(chunks)
        retriever = get_retriever(db)

        RUNTIME.add_log("🤖 [REAL-QA] LLM 체인 구성...")
        qa = build_qa_chain(retriever)
        RUNTIME.add_log(f"✅ [REAL-QA] 실제 LLM 활성화 — model='{wanted}'")
        return qa
    except Exception as e:
        RUNTIME.add_log(f"⚠️ [REAL-QA] 빌드 실패: {e} → FakeQA 폴백")
        return None


@st.cache_resource(show_spinner="🧪 TEST 모드 부팅 중 (실제 LLM 시도)...")
def init_fake_engine():
    RUNTIME.add_log("=" * 40)
    RUNTIME.add_log("🧪 EDGE SAVER TEST 모드 기동 (라즈베리파이 없음)")
    RUNTIME.add_log("=" * 40)
    qa = _try_build_real_qa()
    if qa is None:
        RUNTIME.add_log("🤖 [QA] FakeQA 사용 (하드코딩 응답)")
        qa = FakeQA()
    return qa, FakeTTS()


_started = False
_llm_queue: Optional[queue.PriorityQueue] = None


def start_test_workers(qa: Any, tts_helper: Any) -> queue.PriorityQueue:
    global _started, _llm_queue
    if _started and _llm_queue is not None:
        return _llm_queue
    _llm_queue = queue.PriorityQueue(maxsize=8)
    stop_event = RUNTIME.stop_event()
    cctv_service.camera_running = True

    specs = [
        ("fake-cam", fake_camera_worker, (stop_event,)),
        ("fake-fire", fake_fire_worker, (stop_event,)),
        ("sensor", fake_sensor_worker, (stop_event,)),
        ("fake-stt", fake_stt_worker, (stop_event,)),
        ("alert_dispatcher", W.alert_dispatcher, (stop_event, _llm_queue)),
        ("llm", W.llm_worker, (stop_event, _llm_queue, qa, tts_helper)),
    ]
    for name, target, args in specs:
        threading.Thread(target=target, args=args, daemon=True, name=name).start()
    _started = True
    RUNTIME.add_log("✅ 모든 가짜 워커 시작")
    return _llm_queue


st.set_page_config(layout="wide", page_title="EDGE SAVER (TEST)", page_icon="🧪")

qa, tts_helper = init_fake_engine()
C.inject_css(theme=RUNTIME.get_theme())
llm_queue = start_test_workers(qa, tts_helper)


def _on_theme_toggle() -> None:
    cur = RUNTIME.get_theme()
    RUNTIME.set_theme("light" if cur == "dark" else "dark")
    st.rerun()


C.render_header(on_theme_toggle=_on_theme_toggle)
C.render_emergency_banner()
C.render_status_bar()

active_zone = RUNTIME.get_active_zone()

if active_zone is None:
    # 구역 목록 화면
    C.render_zone_overview()
else:
    # 선택된 구역 상세
    C.render_zone_nav(active_zone)

    col_left, col_right = st.columns([1.4, 1], gap="large")
    with col_left:
        C.render_camera_panel()

        mic_on = st.toggle(
            "🎙️ 음성 브리핑 (FAKE-STT)",
            value=RUNTIME.is_stt_enabled(),
            key="stt_toggle_widget",
            help="켜면 2초 뒤 가짜 음성 입력이 자동으로 들어갑니다.",
        )
        RUNTIME.set_stt_enabled(mic_on)

        with st.expander("⌨️ 텍스트 질의", expanded=False):
            q = st.text_input("질문 입력 후 버튼 클릭", key="fake_query_input")
            if st.button("AI 질의 전송", key="fake_query_send"):
                text = q.strip()
                if not text:
                    st.warning("질문을 입력해 주세요.")
                elif RUNTIME.is_generating():
                    st.warning("현재 AI가 다른 작업을 처리 중입니다.")
                else:
                    W.enqueue_query(llm_queue, text, "ko")
                    RUNTIME.add_log(f"⌨️ [TEST] 텍스트 질의: {text}")
                    st.success("질의 전송 완료. AI 응답을 기다리세요.")

    with col_right:
        C.render_sensor_mini()
        C.render_risk_gauge()
        C.render_log_panel()
        C.render_ai_panel(llm_queue)
