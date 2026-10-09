"""Current vision integrated with feature/RAG and local voice I/O."""
import itertools
import logging
import os
import platform
import queue
import re
import threading
import time
from html import escape

if platform.system() == "Windows":
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import config
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from alerts.alarm import trigger_alarm, stop_siren
from alerts.notifier import send_alert
from rag.context import build_manual_context
from rag.layout import layout_for_question, layout_for_zone
from rag.native_retriever import rag_manager
from rag.provider import EMERGENCY_GUIDANCE, generate_guidance, mode_command_response
from sensors import fusion
from sensors.temperature import read_temperature
from sensors.gas import read_gas_level
from sensors.smoke import read_smoke_level
import vision_bridge
from vision_bridge import cctv_service, fire_detector
from voice.tts import TTSHelper

LOG = logging.getLogger(__name__)


class EdgeSaver:
    def __init__(self, session=None):
        self.session = session
        self._initialized = self._monitor_running = False
        self._stop = threading.Event()
        self._state_lock = threading.RLock()
        self._jobs = queue.PriorityQueue(maxsize=8)
        self._sequence = itertools.count()
        self._threads = []
        self._request_id = self._event_id = 0
        self._alarm_active = False
        self._cached_evac_guidance = ""
        self._alarm_hold_until = 0.0
        self._safe_since = None
        self._last_frame_id = -1
        self._last_analysis = {}
        self._tts = self._stt_model = self._pa = self._stt_stream = None
        self.current_level = 0
        self.current_risk_stats = "시스템 초기화 중"

    @property
    def tts(self):
        if self._tts is None:
            self._tts = TTSHelper()
        return self._tts

    def _start_thread(self, target, name):
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._threads.append(thread)
        thread.start()
        return thread

    def initialize(self):
        if self._initialized:
            return
        print(f"[시스템] {config.APP_NAME} | 센서 {config.SENSOR_MODE} | {config.ZONE_ID}구역")
        rag_manager.load_resources()
        if rag_manager.index is None or rag_manager.index_needs_refresh:
            from tools.rebuild_rag_index import main as rebuild_index
            rebuild_index()
            rag_manager.load_resources()
        _ = self.tts
        fire_detector.warmup()
        # STT is lazy: camera startup never waits for Whisper or a microphone.
        cctv_service.camera_running = True
        self._monitor_running = True
        for target, name in [(cctv_service.camera_worker_thread, "camera"),
                             (self._guidance_worker, "guidance"),
                             (self._monitor_sensors, "monitor"),
                             (self._run_evac_broadcast, "broadcast")]:
            self._start_thread(target, name)
        self._initialized = True

    def _get_bottom_toolbar(self):
        return HTML(f'<style bg="ansiblue" fg="white"> [EDGE SAVER] {escape(self.current_risk_stats)} </style>')

    def _speed(self):
        return (1.3 if self.current_level >= 5 else 1.2 if self.current_level >= 4 else 1.0) if config.TTS_SPEED_SCALING else 1.0

    def _discard_pending_jobs(self):
        while True:
            try:
                self._jobs.get_nowait()
                self._jobs.task_done()
            except queue.Empty:
                return

    def _trigger_rag_alert(self, prompt, sensor_info, zone_id, level=4):
        """Issue local first guidance immediately; queue further analysis."""
        with self._state_lock:
            if self._alarm_active or self._stop.is_set():
                return
            self._alarm_active = True
            self._event_id += 1
            self._request_id += 1
            self.current_level = level
            self._safe_since = None
            self._cached_evac_guidance = EMERGENCY_GUIDANCE
            self._discard_pending_jobs()
            self.tts.stop()
            trigger_alarm(level, sensor_info)
            send_alert(zone=zone_id, risk_level=level, sensor_details=sensor_info)
            print(f"\n[첫 비상 안내] {EMERGENCY_GUIDANCE}")
            self.tts.speak_async(EMERGENCY_GUIDANCE, lang="ko", speed=self._speed())
            stop_siren()
            self._jobs.put_nowait((0, next(self._sequence), {
                "emergency": True, "id": self._event_id, "question": prompt,
                "zone": zone_id, "lang": "ko", "level": level,
            }))

    def _clear_alarm(self):
        with self._state_lock:
            if not self._alarm_active:
                return
            self._alarm_active = False
            self._event_id += 1
            self._request_id += 1
            self._cached_evac_guidance = ""
            self._safe_since = None
            self._discard_pending_jobs()
            self.tts.stop()
            stop_siren(force=True)
            print("\n[시스템] 정상 복귀, 비상 방송 종료")

    def _process_query(self, query, lang="ko"):
        with self._state_lock:
            if self._alarm_active:
                print("[시스템] 비상 안내를 우선합니다. 정상 복귀 후 질문해 주세요.")
                return
            self._request_id += 1
            self._discard_pending_jobs()
            self.tts.stop()
            self._jobs.put_nowait((1, next(self._sequence), {
                "emergency": False, "id": self._request_id, "question": query, "lang": lang,
            }))
        print("[분석] 질문 접수. 감시를 계속하며 답변을 생성합니다.")

    def _job_valid(self, job):
        if self._stop.is_set():
            return False
        if job["emergency"]:
            return self._alarm_active and job["id"] == self._event_id
        return not self._alarm_active and job["id"] == self._request_id

    def _guidance_worker(self):
        # Serialize search/model access; first alarms do not wait for this worker.
        while not self._stop.is_set():
            try:
                _, _, job = self._jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                with self._state_lock:
                    if not self._job_valid(job):
                        continue
                started = time.perf_counter()
                docs = rag_manager.search(job["question"])
                manual = build_manual_context(docs)
                layout = layout_for_zone(job["zone"]) if job["emergency"] else layout_for_question(job["question"])
                searched = time.perf_counter()
                with self._state_lock:
                    if not self._job_valid(job):
                        continue
                result = generate_guidance(layout+manual, job["question"], emergency=job["emergency"],
                                           cloud_context=layout+manual if config.GEMINI_SEND_LAYOUT else manual)
                with self._state_lock:
                    if not self._job_valid(job):
                        continue
                    print(f"\n[AI: {result.provider}] {result.text}")
                    print(f"[시간] 검색 {searched-started:.2f}s / 답변 {time.perf_counter()-searched:.2f}s")
                    if job["emergency"]:
                        self._cached_evac_guidance = result.text
                        if result.text == EMERGENCY_GUIDANCE:
                            continue
                    self.tts.speak_async(result.text, lang=job["lang"], speed=self._speed())
            except Exception:
                LOG.exception("답변 생성 실패; 감시는 계속됩니다")
            finally:
                self._jobs.task_done()

    def _monitor_once(self):
        simulate = config.SENSOR_MODE == "demo"
        temp = read_temperature(simulate=simulate)
        gas = read_gas_level(simulate=simulate)
        smoke = read_smoke_level(simulate=simulate)
        frame, acquired, frame_id, offline = vision_bridge.frame_snapshot()
        now = time.monotonic()
        fresh = frame is not None and not offline and now-acquired <= config.FRAME_MAX_AGE
        if fresh:
            if frame_id != self._last_frame_id:
                self._last_frame_id = frame_id
                self._last_analysis = fire_detector.detect_fire(frame)
            analysis = self._last_analysis
        else:
            analysis = {"status": "CAMERA_OFFLINE", "fire_detected": False}
            self._last_analysis = {}
            self._last_frame_id = -1
        healthy = fresh and analysis.get("status") not in {
            "MODEL_NOT_INITIALIZED", "ANALYSIS_ERROR", "MOTION_ERROR", "INVALID_INPUT", "NO_RESULT"
        }
        clear_observation = healthy and analysis.get("status") in {
            "SAFE", "STATIC_PHOTO_BLOCKED", "HANDHELD_PHOTO_BLOCKED"
        }
        # Virtual sensor elevation is demo-only. Early smoke retains Level 2.
        if simulate and config.DEMO_VISION_ESCALATION and analysis.get("fire_detected") and not analysis.get("is_real_smoke"):
            temp["temperature"], smoke, gas = 75.0, 550, 600
        risk = fusion.calculate_risk_level(smoke, gas, temp, vision_input=analysis)
        with self._state_lock:
            self.current_level = max(risk["level"], self.current_level) if self._alarm_active else risk["level"]
            if risk["level"] >= 4:
                prompt = f"[공장 {config.ZONE_ID}구역] {risk['details']}. 대피 지침을 알려주세요."
                self._trigger_rag_alert(prompt, risk["details"], config.ZONE_ID, risk["level"])
                self._safe_since = None
            elif self._alarm_active and clear_observation and risk["level"] < 2 and now >= self._alarm_hold_until:
                if self._safe_since is None:
                    self._safe_since = now
                elif now-self._safe_since >= config.ALARM_RECOVERY_SECONDS and not self.tts.is_speaking():
                    self._clear_alarm()
                    self.current_level = risk["level"]
            else:
                self._safe_since = None
            label = config.RISK_LEVELS.get(self.current_level, "정상")
            self.current_risk_stats = (f"[{config.SENSOR_MODE}] T:{temp['temperature']}C G:{gas} S:{smoke} "
                                       f"CAM:{analysis.get('status', 'UNKNOWN')} | {label}")

    def _monitor_sensors(self):
        while not self._stop.is_set():
            try:
                self._monitor_once()
            except Exception:
                self.current_risk_stats = "SENSOR / VISION ERROR"
                LOG.exception("센서/비전 감시 오류")
            self._stop.wait(config.MONITOR_INTERVAL)

    def _run_evac_broadcast(self):
        last_play = time.monotonic()
        while not self._stop.wait(0.5):
            with self._state_lock:
                if self._alarm_active and time.monotonic()-last_play >= 25 and not self.tts.is_speaking():
                    self.tts.speak_async(self._cached_evac_guidance, lang="ko", speed=self._speed())
                    last_play = time.monotonic()
                elif not self._alarm_active:
                    last_play = time.monotonic()

    def _listen(self):
        if not config.STT_ENABLED:
            print("[STT] 비활성화. STT_ENABLED=true 설정 후 장치를 검증하세요.")
            return "", "ko"
        if self._alarm_active or not self.tts.wait_until_idle(timeout=10):
            print("[STT] 음성 안내가 끝난 후 다시 입력해 주세요.")
            return "", "ko"
        try:
            from voice.stt import _load_model, _get_pyaudio_instance, _open_stream, listen_once
            if self._stt_model is None:
                self._stt_model = _load_model()
            if self._stt_model is None:
                return "", "ko"
            if self._pa is None:
                self._pa = _get_pyaudio_instance()
            if self._pa is None:
                return "", "ko"
            if self._stt_stream is None:
                self._stt_stream = _open_stream(self._pa)
            if self._stt_stream is None:
                return "", "ko"
            event_id = self._event_id
            query, lang = listen_once(model=self._stt_model, pa=self._pa, stream=self._stt_stream, use_wake_word=False)
            if self._alarm_active or self._event_id != event_id:
                return "", "ko"
            return query, lang
        except Exception:
            LOG.exception("STT 실패; 텍스트 입력으로 계속 사용 가능합니다")
            return "", "ko"

    def run(self):
        self.initialize()
        if self.session is None and not config.SIMPLE_UI:
            self.session = PromptSession()
        print("질문 | v: 음성 | test fire: 데모 경보 | /ai auto|api|local | q: 종료")
        with patch_stdout():
            while not self._stop.is_set():
                try:
                    query = (self.session.prompt("질문: ", bottom_toolbar=self._get_bottom_toolbar, refresh_interval=0.5)
                             if self.session else input("질문: ")).strip()
                    if query.lower() in {"q", "exit", "quit"}:
                        break
                    mode_response = mode_command_response(query)
                    if mode_response is not None:
                        print(mode_response)
                        continue
                    if query.lower() in {"test fire", "fire test", "화재 테스트", "화재실험"}:
                        if config.SENSOR_MODE != "demo":
                            print("[시스템] test fire는 SENSOR_MODE=demo에서 사용하세요.")
                            continue
                        self._alarm_hold_until = time.monotonic()+config.DEMO_ALARM_HOLD_SECONDS
                        self._trigger_rag_alert(f"[공장 {config.ZONE_ID}구역] 화재 대피 방법", "데모 화재", config.ZONE_ID)
                        continue
                    if not query or query.lower() in {"v", "voice"}:
                        query, lang = self._listen()
                    else:
                        lang = "ko" if re.search("[가-힣]", query) else "en"
                    if query:
                        self._process_query(query, lang)
                except (KeyboardInterrupt, EOFError):
                    break

    def cleanup(self):
        with self._state_lock:
            self._stop.set()
            self._monitor_running = False
            self._event_id += 1
            self._request_id += 1
            self._discard_pending_jobs()
            cctv_service.camera_running = False
            stop_siren(force=True)
        for resource, method in [(self._stt_stream, "stop_stream"), (self._stt_stream, "close"), (self._pa, "terminate")]:
            if resource:
                try:
                    getattr(resource, method)()
                except Exception:
                    LOG.exception("오디오 입력 정리 실패")
        if self._tts:
            self._tts.close()
        for thread in self._threads:
            thread.join(timeout=1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = EdgeSaver()
    try:
        app.run()
    finally:
        app.cleanup()
