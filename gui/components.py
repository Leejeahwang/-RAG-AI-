"""
gui/components.py - CSS + 모든 UI fragment 한 파일.

표시 전용: 모든 값은 RUNTIME 에 들어온 Pi 의 MQTT 수신값이다.
여기서 위험도를 다시 계산하거나 경보를 울리지 않는다.
"""

from __future__ import annotations

import time
from typing import Optional

import streamlit as st

from gui.protocol import LEVEL_LABELS, MAX_LEVEL, provider_label
from gui.state import (
    RUNTIME, ZoneView, GAUGE_COLORS, ALERT_THRESHOLD,
    REFRESH_CAMERA, REFRESH_SENSORS, REFRESH_GAUGE, REFRESH_AI,
    REFRESH_TREND, REFRESH_LOG, REFRESH_STATUS,
    escape_html,
)
from gui import workers as W

try:
    import config
    _THRESHOLDS = dict(config.SENSOR_THRESHOLDS)
except Exception:  # 관제 PC 에서 config 를 못 읽어도 화면은 뜬다
    _THRESHOLDS = {"smoke_mq2": 300, "gas_mq135": 400, "temperature_high": 60}

# 이 비율 이상이면 주황(주의) 테두리
_NEAR_RATIO = 0.8

# vision/fire_detector.py · smoke_motion.py 의 status 값 → 화면 문구
VISION_STATUS_LABELS = {
    "SAFE": "정상",
    "WARMING_UP": "움직임 분석 준비",
    "INITIALIZING": "움직임 분석 준비",
    "BOX_TOO_SMALL": "감지 영역 작음",
    "EVALUATING_FIRE_MOTION": "불꽃 움직임 분석 중",
    "EVALUATING_SMOKE_MOTION": "연기 움직임 분석 중",
    "REAL_FIRE_FLICKERING": "실제 불꽃 확인",
    "REAL_SMOKE_RISING": "연기 상승 확인",
    "STATIC_PHOTO_BLOCKED": "정지 사진 차단",
    "HANDHELD_PHOTO_BLOCKED": "손에 든 사진 차단",
    "CAMERA_OFFLINE": "카메라 오프라인",
    "MODEL_NOT_INITIALIZED": "모델 미준비",
    "ANALYSIS_ERROR": "분석 오류",
    "MOTION_ERROR": "움직임 분석 오류",
    "INVALID_INPUT": "입력 오류",
    "NO_RESULT": "결과 없음",
}


_CSS = """
:root, :root[data-theme="dark"] {
    --bg:#0b0f17; --card:#131a26; --card-2:#1b2433; --border:#232b3a;
    --text:#e4e8ef; --text-soft:#b6bfcc; --muted:#7a8699;
    --accent:#22c55e; --accent-soft:#22c55e22;
    --warn:#f59e0b; --warn-soft:#f59e0b22;
    --danger:#ef4444; --danger-soft:#ef444422;
    --radius:12px; --radius-sm:8px;
    --shadow:0 4px 16px rgba(0,0,0,.35);
    --shadow-strong:0 8px 28px rgba(0,0,0,.5);
}
:root[data-theme="light"] {
    --bg:#f5f7fb; --card:#ffffff; --card-2:#f1f5f9; --border:#e2e8f0;
    --text:#0f172a; --text-soft:#334155; --muted:#64748b;
    --accent:#16a34a; --accent-soft:#16a34a22;
    --warn:#d97706; --warn-soft:#d9770622;
    --danger:#dc2626; --danger-soft:#dc262622;
    --shadow:0 4px 14px rgba(15,23,42,.08);
    --shadow-strong:0 10px 24px rgba(15,23,42,.12);
}
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
html, body, [class*="css"], .stApp {
    font-family:'Pretendard','Noto Sans KR','Malgun Gothic',sans-serif !important;
    background-color:var(--bg) !important; color:var(--text) !important;
}
.block-container { padding:0.1rem 2% 1rem !important; max-width:1680px !important; }
header[data-testid="stHeader"], [data-testid="stAppDeployButton"],
[data-testid="stToolbar"] { display:none !important; }
section[data-testid="stMain"] { padding-top:0 !important; }
section[data-testid="stMain"] > div:first-child { padding-top:0 !important; }
[data-testid="stMainBlockContainer"] { padding-top:0.1rem !important; }
hr { border-color:var(--border) !important; margin:12px 0 !important; }

.es-header { display:flex; align-items:center; justify-content:space-between;
    padding:22px 28px;
    background:linear-gradient(135deg, var(--card) 0%, var(--card-2) 100%);
    border:1px solid var(--border); border-radius:var(--radius);
    box-shadow:var(--shadow); margin-bottom:14px; }
.es-brand { display:flex; align-items:baseline; gap:14px; }
.es-brand-title { font-size:26px; font-weight:800; letter-spacing:1px; color:var(--text); }
.es-brand-sub { color:var(--muted); font-size:13px; font-weight:600;
    text-transform:uppercase; letter-spacing:2px; }
.es-clock { font-family:'JetBrains Mono','Consolas',monospace;
    color:var(--text-soft); font-size:14px; font-weight:600; }
.es-arm-chip { display:inline-flex; align-items:center; gap:8px;
    padding:6px 14px; background:var(--accent-soft); color:var(--accent);
    border:1px solid var(--accent); border-radius:999px;
    font-size:12px; font-weight:700; letter-spacing:1px; }
.es-arm-chip.danger { background:var(--danger-soft); color:var(--danger); border-color:var(--danger); }
.es-arm-chip.warn { background:var(--warn-soft); color:var(--warn); border-color:var(--warn); }
.es-dot { width:8px; height:8px; border-radius:50%; background:currentColor;
    box-shadow:0 0 8px currentColor; animation:es-pulse 1.6s ease-in-out infinite; }
@keyframes es-pulse { 0%,100% { opacity:1; transform:scale(1); }
    50% { opacity:.5; transform:scale(.85); } }

.es-kpi-row { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:14px; }
.es-kpi { background:var(--card); border:1px solid var(--border);
    border-radius:var(--radius); padding:16px 18px; box-shadow:var(--shadow);
    transition:border-color .25s ease, box-shadow .25s ease; }
.es-kpi.active { border-color:var(--warn);
    box-shadow:0 0 0 1px var(--warn), var(--shadow-strong); }
.es-kpi.danger { border-color:var(--danger);
    box-shadow:0 0 0 1px var(--danger), var(--shadow-strong); }
.es-kpi-label { color:var(--muted); font-size:12px; font-weight:700;
    letter-spacing:1px; text-transform:uppercase; }
.es-kpi-value { color:var(--text); font-size:28px; font-weight:800;
    line-height:1.1; margin-top:6px; }
.es-kpi-unit { color:var(--text-soft); font-size:14px; font-weight:600; margin-left:4px; }
.es-kpi-meta { color:var(--muted); font-size:11px; margin-top:8px; }

.es-sensor-row { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:10px; }
.es-kpi-sm { background:var(--card); border:1px solid var(--border);
    border-radius:var(--radius-sm); padding:14px 12px 16px; box-shadow:var(--shadow);
    transition:border-color .25s ease; }
.es-kpi-sm.active { border-color:var(--warn); }
.es-kpi-sm.danger { border-color:var(--danger);
    box-shadow:0 0 0 1px var(--danger), var(--shadow); }

.es-panel { background:var(--card); border:1px solid var(--border);
    border-radius:var(--radius); padding:16px; box-shadow:var(--shadow);
    margin-bottom:14px; }
.es-panel-title { color:var(--text); font-size:13px; font-weight:800;
    letter-spacing:1px; text-transform:uppercase; margin-bottom:12px;
    display:flex; align-items:center; gap:8px; }
.es-panel-title .accent { color:var(--accent); }

.es-gauge-track { width:100%; height:16px; border-radius:999px;
    background:var(--card-2); overflow:hidden; border:1px solid var(--border); }
.es-gauge-fill { height:100%; border-radius:999px;
    transition:width .6s cubic-bezier(.4,0,.2,1), background-color .3s ease; }
.es-gauge-label { display:flex; justify-content:space-between;
    align-items:baseline; margin-top:6px; }
.es-gauge-level { font-size:20px; font-weight:800; line-height:1; }
.es-gauge-text { font-size:12px; color:var(--muted); font-weight:600;
    letter-spacing:1px; text-transform:uppercase; }

.es-ai-card { background:var(--card-2); border:1px solid var(--border);
    border-radius:var(--radius-sm); padding:14px 16px; color:var(--text);
    font-size:14px; line-height:1.7; min-height:130px;
    white-space:pre-wrap; word-break:break-word; }
.es-ai-card.generating { border-color:var(--warn);
    animation:es-pulse-soft 1.8s ease-in-out infinite; }
@keyframes es-pulse-soft { 0%,100% { box-shadow:0 0 0 0 var(--warn-soft); }
    50% { box-shadow:0 0 0 6px var(--warn-soft); } }

[data-testid="stHorizontalBlock"]:has(.es-hdr-marker) {
    position:relative !important;
    background:linear-gradient(135deg, var(--card) 0%, var(--card-2) 100%) !important;
    border:3px solid var(--muted) !important; border-radius:var(--radius) !important;
    box-shadow:var(--shadow) !important; padding:0 20px !important;
    margin-bottom:8px !important; align-items:center !important;
    height:64px !important; overflow:visible !important; }
[data-testid="stHorizontalBlock"]:has(.es-hdr-marker) [data-testid="stColumn"] {
    position:static !important;
    display:flex !important; align-items:center !important; padding:0 !important; }
[data-testid="stHorizontalBlock"]:has(.es-hdr-marker) [data-testid="stColumn"] > div,
[data-testid="stHorizontalBlock"]:has(.es-hdr-marker) [data-testid="stColumn"] > div > div {
    position:static !important;
    display:flex !important; align-items:center !important; width:100%; padding:0 !important; }
[data-testid="stHorizontalBlock"]:has(.es-hdr-marker) button {
    background:transparent !important; border:1px solid var(--muted) !important;
    color:var(--text) !important; padding:2px 8px !important; font-size:13px !important;
    min-height:0 !important; line-height:1.2 !important; }
.es-hdr-marker {
    position:absolute !important; left:50% !important; top:50% !important;
    transform:translate(-50%, -50%) !important;
    width:max-content !important; max-width:none !important;
    white-space:nowrap !important;
    z-index:2; pointer-events:none; }
.es-hdr-marker .es-brand-title,
.es-hdr-marker .es-brand-sub { white-space:nowrap !important; }
.es-log { background:var(--card-2); border:1px solid var(--border);
    border-radius:var(--radius-sm); padding:12px 14px; color:var(--text-soft);
    font-family:'JetBrains Mono','Consolas',monospace;
    font-size:12px; line-height:1.6; height:200px; overflow-y:auto;
    white-space:pre-wrap; }
.es-log::-webkit-scrollbar { width:6px; }
.es-log::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }

.es-live { display:inline-flex; align-items:center; gap:6px;
    background:var(--danger); color:white; padding:3px 12px;
    border-radius:6px; font-size:11px; font-weight:800; letter-spacing:1px; }
.es-live .es-dot { background:white; }

.es-conf { display:inline-block; background:var(--card-2);
    border:1px solid var(--border); border-radius:6px; padding:3px 10px;
    color:var(--muted); font-size:11px; font-weight:700;
    font-family:'JetBrains Mono',monospace; }
.es-conf.alert { color:var(--danger); border-color:var(--danger);
    background:var(--danger-soft); }
.es-stale { color:var(--warn); font-size:11px; font-weight:700; margin-top:6px; }

div[data-testid="stButton"] button { background:var(--card-2); color:var(--text);
    border:1px solid var(--border); border-radius:var(--radius-sm);
    font-weight:700; transition:all .2s ease; }
div[data-testid="stButton"] button:hover { border-color:var(--accent); color:var(--accent); }
[data-testid="stImage"] img { border-radius:var(--radius-sm); }

/* 마커는 DOM에만 존재, 시각적으로 안 보이게 */
.es-zone-card-marker, .es-emerg-marker {
    display:block; width:0; height:0; overflow:hidden;
    position:absolute; opacity:0; pointer-events:none; }

/* Task1: 구역 카드 — column의 stVerticalBlock 내부에서 button을 카드 위에 깔기 */
[data-testid="stVerticalBlock"]:has(> div:first-child .es-zone-card-marker) {
    position:relative !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-zone-card-marker) > div:nth-child(2) {
    position:absolute !important;
    top:0 !important; right:0 !important; bottom:0 !important; left:0 !important;
    margin:0 !important; padding:0 !important; z-index:10 !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-zone-card-marker) > div:nth-child(2) [data-testid="stButton"],
[data-testid="stVerticalBlock"]:has(> div:first-child .es-zone-card-marker) > div:nth-child(2) [data-testid="stButton"] > div {
    width:100% !important; height:100% !important; margin:0 !important; padding:0 !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-zone-card-marker) > div:nth-child(2) button {
    width:100% !important; height:100% !important; min-height:0 !important;
    background:transparent !important; border:none !important; box-shadow:none !important;
    cursor:pointer !important; opacity:0 !important; padding:0 !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-zone-card-marker):hover .es-zone-card-wrap > div {
    border-color:var(--accent) !important;
    box-shadow:0 0 0 2px var(--accent), var(--shadow-strong) !important;
    transition:all .2s ease; }

/* Task3: 위급상황 배너 — st.container의 stVerticalBlock 전체를 빨간 배경 박스로 */
[data-testid="stVerticalBlock"]:has(> div:first-child .es-emerg-marker) {
    background:linear-gradient(90deg,#dc2626,#b91c1c) !important;
    border-radius:10px !important; padding:2px 8px !important;
    margin-bottom:8px !important;
    box-shadow:0 0 18px rgba(220,38,38,0.55) !important;
    animation:edgepulse 1.2s infinite !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-emerg-marker) [data-testid="stHorizontalBlock"] {
    background:transparent !important; border:none !important;
    box-shadow:none !important; height:auto !important;
    padding:0 !important; margin:0 !important; align-items:center !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-emerg-marker) [data-testid="stColumn"] {
    padding:0 !important; background:transparent !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-emerg-marker) button {
    background:rgba(0,0,0,0.35) !important; border:1px solid rgba(255,255,255,0.6) !important;
    color:white !important; font-weight:700 !important; }
[data-testid="stVerticalBlock"]:has(> div:first-child .es-emerg-marker) button:hover {
    background:rgba(0,0,0,0.55) !important; border-color:white !important; color:white !important; }
@keyframes edgepulse {
    0%,100% { box-shadow:0 0 0 0 rgba(220,38,38,0.7); }
    50% { box-shadow:0 0 0 14px rgba(220,38,38,0); } }

/* 상태 배지 (DEMO, 카메라 오프라인, 조기 감지, 사진 오탐 차단 등) */
.es-badge { display:inline-block; padding:2px 10px; margin:2px 4px 2px 0;
    border-radius:6px; border:1px solid var(--border); background:var(--card-2);
    color:var(--text-soft); font-size:11px; font-weight:800; letter-spacing:.5px; }
.es-badge.ok { color:var(--accent); border-color:var(--accent); background:var(--accent-soft); }
.es-badge.warn { color:var(--warn); border-color:var(--warn); background:var(--warn-soft); }
.es-badge.danger { color:var(--danger); border-color:var(--danger); background:var(--danger-soft); }
.es-badge.info { color:#38bdf8; border-color:#38bdf8; background:#38bdf822; }
.es-cam-empty { border:1px dashed var(--border); border-radius:10px; padding:48px 16px;
    text-align:center; background:var(--card); color:var(--muted); margin-bottom:8px; }
.es-cam-empty .es-cam-icon { font-size:44px; }
.es-gauge-ticks { display:flex; justify-content:space-between; margin-top:4px;
    color:var(--muted); font-size:10px; font-family:'JetBrains Mono',monospace; }
.es-ai-meta { color:var(--muted); font-size:11px; margin-top:8px; }
.es-ai-sub { color:var(--muted); font-size:11px; font-weight:800; letter-spacing:1px;
    margin:12px 0 6px; }
"""


def inject_css(theme: str = "dark") -> None:
    attr = "light" if theme == "light" else "dark"
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
    st.html(
        f"<style>html,body{{margin:0;padding:0;}}</style>"
        f"<script>window.parent.document.documentElement.setAttribute('data-theme','{attr}');</script>"
    )


# ════════════════════════════════════════════════════════════
#  공용 헬퍼
# ════════════════════════════════════════════════════════════

def active_zone() -> Optional[str]:
    """브라우저 탭별로 보고 있는 구역 (None = 구역 목록)."""
    return st.session_state.get("active_zone")


def set_active_zone(zone: Optional[str]) -> None:
    st.session_state["active_zone"] = zone


def zone_label(zone: str) -> str:
    return f"{zone}구역"


def _gauge_color(level: int) -> str:
    idx = max(0, min(level, len(GAUGE_COLORS) - 1))
    return GAUGE_COLORS[idx]


def _badge(text: str, cls: str = "") -> str:
    return f"<span class='es-badge {cls}'>{escape_html(text)}</span>"


def _chip(ok: bool, label: str, fail_cls: str = "danger") -> str:
    cls = "es-arm-chip" if ok else f"es-arm-chip {fail_cls}"
    return f"<span class='{cls}'><span class='es-dot'></span> {escape_html(label)}</span>"


def _level_cls(value: float, threshold: float, base: str) -> str:
    """fusion.py 와 같은 기준: threshold 초과면 위험, 80% 이상이면 주의."""
    if value > threshold:
        return f"{base} danger"
    if value >= threshold * _NEAR_RATIO:
        return f"{base} active"
    return base


def _ago(ts: float) -> str:
    if ts <= 0:
        return "-"
    sec = max(0, int(time.time() - ts))
    return f"{sec}초 전" if sec < 120 else f"{sec // 60}분 전"


def _vision_label(status: str) -> str:
    return VISION_STATUS_LABELS.get(status, status or "-")


def _offline_box(icon: str, title: str, sub: str = "") -> str:
    sub_html = f"<div style='font-size:12px;margin-top:6px;'>{escape_html(sub)}</div>" if sub else ""
    return (f"<div class='es-cam-empty'><div class='es-cam-icon'>{icon}</div>"
            f"<div style='margin-top:8px;font-weight:700;'>{escape_html(title)}</div>{sub_html}</div>")


# ════════════════════════════════════════════════════════════
#  Header
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=1.0)
def _clock_fragment() -> None:
    st.markdown(
        f'<div style="text-align:right;">'
        f'<span class="es-clock">{time.strftime("%Y-%m-%d  %H:%M:%S")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


@st.fragment(run_every=REFRESH_STATUS)
def _armed_status_fragment() -> None:
    zones = [v for v in RUNTIME.all_zones() if v.connected]
    broker_ok, _, _ = RUNTIME.get_broker()
    level = max((v.level for v in zones), default=0)
    alarm = any(v.status is not None and v.status.alarm for v in zones)
    if level >= ALERT_THRESHOLD or alarm:
        chip_cls, chip_label = "es-arm-chip danger", "EMERGENCY"
    elif level >= 2:
        chip_cls, chip_label = "es-arm-chip warn", "ALERT"
    elif not broker_ok:
        chip_cls, chip_label = "es-arm-chip warn", "NO LINK"
    else:
        chip_cls, chip_label = "es-arm-chip", "MONITORING"
    st.markdown(
        f'<span class="{chip_cls}"><span class="es-dot"></span> {chip_label}</span>',
        unsafe_allow_html=True,
    )


def render_header(on_theme_toggle, zone: Optional[str]) -> None:
    c_brand, c_spacer, c_clock, c_chip, c_btn = st.columns([2, 6, 1.8, 1.5, 0.5])
    with c_brand:
        sub_label = f"원격 관제 · {escape_html(zone_label(zone))}" if zone else "원격 관제 · 구역 목록"
        st.markdown(
            f'<div class="es-hdr-marker" style="display:inline-flex;align-items:center;gap:14px;">'
            f'<span class="es-brand-title">EDGE SAVER</span>'
            f'<span class="es-brand-sub">{sub_label}</span></div>',
            unsafe_allow_html=True,
        )
    with c_clock:
        _clock_fragment()
    with c_chip:
        _armed_status_fragment()
    with c_btn:
        cur = RUNTIME.get_theme()
        icon = "☀️" if cur == "dark" else "🌙"
        if st.button(icon, help="다크/라이트 모드", key="btn_theme"):
            on_theme_toggle()


# ════════════════════════════════════════════════════════════
#  Status bar (MQTT / PI / CAM / 센서 모드 / AI)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_STATUS)
def render_status_bar(zone: Optional[str]) -> None:
    broker_ok, broker_err, target = RUNTIME.get_broker()
    chips = _chip(broker_ok, f"MQTT {target}" if broker_ok else f"MQTT {broker_err or '끊김'}")

    if zone:
        v = RUNTIME.get_zone(zone)
        connected = v is not None and v.connected
        chips += _chip(connected, "PI ONLINE" if connected else "PI 신호 없음")
        if connected and v.status is not None:
            if v.status.vision.camera_offline:
                chips += _chip(False, "CAM OFFLINE")
            else:
                chips += _chip(v.frame_live, "CAM LIVE" if v.frame_live else "영상 수신 없음", "warn")
            if v.status.sensor_mode == "demo":
                chips += _chip(False, "DEMO · 가상 센서", "warn")
            else:
                chips += _chip(True, "실센서")
    else:
        n = sum(1 for v in RUNTIME.all_zones() if v.connected)
        chips += _chip(n > 0, f"{n}개 구역 연결", "warn")

    if RUNTIME.is_qa_ready():
        busy = RUNTIME.is_generating()
        chips += _chip(not busy, "AI BUSY" if busy else "AI READY", "warn")
    else:
        chips += _chip(False, "관제 AI 꺼짐", "warn")

    st.markdown(
        f"<div style='display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px;'>{chips}</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Sensor mini row (원시값 표시)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_SENSORS)
def render_sensor_mini(zone: str) -> None:
    v = RUNTIME.get_zone(zone)
    s = v.status if v is not None and v.connected else None
    t_lim = _THRESHOLDS["temperature_high"]
    g_lim = _THRESHOLDS["gas_mq135"]
    sm_lim = _THRESHOLDS["smoke_mq2"]
    if s is None:
        temp = hum = gas_v = smoke_v = "--"
        t_cls = g_cls = sm_cls = "es-kpi-sm"
    else:
        sn = s.sensors
        temp, hum, gas_v, smoke_v = f"{sn.temperature:.1f}", f"{sn.humidity:.0f}", f"{sn.gas}", f"{sn.smoke}"
        t_cls = _level_cls(sn.temperature, t_lim, "es-kpi-sm")
        g_cls = _level_cls(sn.gas, g_lim, "es-kpi-sm")
        sm_cls = _level_cls(sn.smoke, sm_lim, "es-kpi-sm")

    value = "font-size:18px;margin-top:4px;"
    unit = "font-size:11px;"
    meta = "margin-top:4px;"
    demo = ""
    if s is not None and s.sensor_mode == "demo":
        demo = _badge("DEMO · 가상 센서값", "warn")
    st.markdown(
        f"""
        <div>{demo}</div>
        <div class="es-sensor-row">
            <div class="{t_cls}">
                <div class="es-kpi-label">🌡 온도</div>
                <div class="es-kpi-value" style="{value}">{temp}<span class="es-kpi-unit" style="{unit}">°C</span></div>
                <div class="es-kpi-meta" style="{meta}">습도 {hum}% · 임계 {t_lim}°C</div>
            </div>
            <div class="{g_cls}">
                <div class="es-kpi-label">💨 가스 MQ-135</div>
                <div class="es-kpi-value" style="{value}">{gas_v}<span class="es-kpi-unit" style="{unit}">/1023</span></div>
                <div class="es-kpi-meta" style="{meta}">ADC 원시값 · 임계 {g_lim}</div>
            </div>
            <div class="{sm_cls}">
                <div class="es-kpi-label">🌫 연기 MQ-2</div>
                <div class="es-kpi-value" style="{value}">{smoke_v}<span class="es-kpi-unit" style="{unit}">/1023</span></div>
                <div class="es-kpi-meta" style="{meta}">ADC 원시값 · 임계 {sm_lim}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Camera panel (Pi 가 보낸 JPEG)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_CAMERA)
def render_camera_panel(zone: str) -> None:
    v = RUNTIME.get_zone(zone)
    if v is None or not v.connected:
        last = _ago(v.last_seen) if v is not None else "-"
        st.markdown(_offline_box("📡", "Pi 신호 없음", f"마지막 수신: {last}"), unsafe_allow_html=True)
        return

    vision = v.status.vision
    if vision.camera_offline:
        st.markdown(_offline_box("📷", "카메라 오프라인", "Pi 가 카메라 프레임을 받지 못하고 있습니다"),
                    unsafe_allow_html=True)
    elif v.frame_live:
        try:
            st.image(v.frame, width="stretch")
        except Exception as e:
            st.error("카메라 영상 표시 오류")
            RUNTIME.add_log(f"❌ [카메라] 표시 오류: {e}")
    else:
        sub = f"마지막 영상: {_ago(v.frame_rx)}" if v.frame_rx else "Pi 의 EDGE_FRAME_FPS 설정을 확인하세요"
        st.markdown(_offline_box("🎞️", "영상 수신 없음", sub), unsafe_allow_html=True)

    # 비전 판정 배지: 사진 차단은 실제 판정 상태일 때만
    badges = [_badge(f"비전: {_vision_label(vision.status)}", "danger" if vision.fire_detected else "")]
    if vision.confidence > 0:
        badges.append(_badge(f"확신도 {vision.confidence:.2f}", "danger" if vision.fire_detected else ""))
    if vision.photo_blocked:
        badges.append(_badge(f"🛡️ 사진 오탐 차단 · {_vision_label(vision.status)}", "info"))
    if v.status.risk.early or vision.real_smoke:
        badges.append(_badge("⏱ 조기 감지", "warn"))
    st.markdown(f"<div>{''.join(badges)}</div>", unsafe_allow_html=True)
    if vision.fire_detected and vision.description:
        st.error(f"🚨 {vision.description}")


# ════════════════════════════════════════════════════════════
#  Risk gauge (LV 0~5)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_GAUGE)
def render_risk_gauge(zone: str) -> None:
    v = RUNTIME.get_zone(zone)
    connected = v is not None and v.connected
    level = v.level if connected else 0
    risk = v.status.risk if connected else None
    color = _gauge_color(level) if connected else "var(--muted)"
    width_pct = level * 100 // MAX_LEVEL
    label = LEVEL_LABELS[level] if connected else "신호 없음"
    details = risk.details if risk else ""

    badges = ""
    if connected and v.status.alarm:
        since = f" · {_ago(v.alarm_since)} 시작" if v.alarm_since else ""
        badges += _badge(f"🚨 Pi 경보·대피 방송 중{since}", "danger")
    if risk and risk.early:
        badges += _badge("⏱ 조기 감지", "warn")
    if risk and risk.fused_level != level:
        badges += _badge(f"현재 계산값 LV{risk.fused_level} (경보 유지 중)")
    ticks = "".join(f"<span>{i}</span>" for i in range(MAX_LEVEL + 1))

    st.markdown(
        f"""
        <div class='es-panel' style='padding:12px 16px; margin-bottom:10px;'>
            <div class='es-panel-title' style='margin-bottom:8px;'>🚨 위험도 게이지 (LV 0~{MAX_LEVEL})</div>
            <div class='es-gauge-track' style='height:16px;'>
                <div class='es-gauge-fill' style='width:{width_pct}%;
                    background-color:{color};
                    box-shadow:0 0 14px {color}88;'></div>
            </div>
            <div class='es-gauge-ticks'>{ticks}</div>
            <div class='es-gauge-label' style='margin-top:6px;'>
                <div class='es-gauge-level' style='color:{color}; font-size:22px;'>LV {level} / {MAX_LEVEL}</div>
                <div class='es-gauge-text'>{escape_html(label)}</div>
            </div>
            <div style='color:var(--text-soft);font-size:12px;margin-top:6px;'>{escape_html(details)}</div>
            <div style='margin-top:6px;'>{badges}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Trend (시계열 라인 차트, 원시값)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_TREND)
def render_trend_panel(zone: str) -> None:
    import pandas as pd

    st.markdown(
        "<div class='es-panel'><div class='es-panel-title'>📈 추세 (최근 2분)</div>",
        unsafe_allow_html=True,
    )
    points = RUNTIME.get_trend(zone)
    if not points:
        st.caption("데이터 수집 중...")
    else:
        df = pd.DataFrame({
            "온도(°C)": [p.sensors.temperature for p in points],
            "가스 ADC/10": [p.sensors.gas / 10.0 for p in points],
            "연기 ADC/10": [p.sensors.smoke / 10.0 for p in points],
        })
        st.line_chart(df, height=180, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
#  AI panel (Pi 비상 지침 + 관제사 질의 답변, STT 큐 소비)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_AI)
def render_ai_panel(zone: str, llm_queue) -> None:
    # 1) STT 큐 소비 → 관제사 질의 큐
    if RUNTIME.is_qa_ready():
        while True:
            if RUNTIME.is_generating():
                break
            msg = RUNTIME.pop_stt()
            if msg is None:
                break
            W.enqueue_query(llm_queue, msg.text, msg.lang)
    if RUNTIME.pop_stt_dropped():
        st.warning("음성이 처리되지 않았습니다.")

    # 2) 현장(Pi) 비상 지침
    v = RUNTIME.get_zone(zone)
    status = v.status if v is not None and v.connected else None
    if status is not None and status.ai.text:
        ai = status.ai
        cls = "es-ai-card"
        text = ai.text
        meta = f"생성: {provider_label(ai.provider)}"
        if ai.fallback_reason:
            meta += f" · 전환 이유: {ai.fallback_reason}"
        if ai.ts:
            meta += f" · {time.strftime('%H:%M:%S', time.localtime(ai.ts))}"
    elif status is not None and status.alarm:
        cls, text, meta = "es-ai-card generating", "Pi 가 비상 지침을 생성 중입니다... ⏳", ""
    elif status is not None:
        cls, text, meta = "es-ai-card", "안전 상태 유지 중입니다. (현장 경보 없음)", ""
    else:
        cls, text, meta = "es-ai-card", "Pi 신호 없음 — 현장 지침을 받을 수 없습니다.", ""

    # 3) 관제사 질의 답변 (관제 PC 자체 RAG)
    if RUNTIME.is_generating():
        q_html = "<div class='es-ai-card generating' style='min-height:0;'>답변 생성 중... ⏳</div>"
    else:
        answer, provider, at = RUNTIME.get_last_answer()
        if answer:
            q_meta = f"생성: {provider_label(provider)} · {time.strftime('%H:%M:%S', time.localtime(at))}"
            q_html = (f"<div class='es-ai-card' style='min-height:0;'>{escape_html(answer)}</div>"
                      f"<div class='es-ai-meta'>{escape_html(q_meta)}</div>")
        else:
            q_html = "<div class='es-ai-meta'>아래 입력창이나 음성으로 매뉴얼 질문을 할 수 있습니다.</div>"

    meta_html = f"<div class='es-ai-meta'>{escape_html(meta)}</div>" if meta else ""
    st.markdown(
        f"<div class='es-panel'><div class='es-panel-title'>🤖 현장 AI 지침</div>"
        f"<div class='{cls}'>{escape_html(text)}</div>{meta_html}"
        f"<div class='es-ai-sub'>관제사 질의 답변</div>{q_html}</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Log panel
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_LOG)
def render_log_panel() -> None:
    logs = RUNTIME.snapshot_logs()
    body = "\n".join(escape_html(line) for line in reversed(logs))
    st.markdown(
        f"<div class='es-panel'><div class='es-panel-title'>📟 Tactical Feed</div>"
        f"<div class='es-log'>{body}</div></div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Emergency banner (모든 구역 감시)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=1.0)
def render_emergency_banner() -> None:
    """경보 중이거나 LV4 이상인 구역이 있으면 상단에 빨간 배너 + 이동 버튼."""
    danger = [
        v for v in RUNTIME.all_zones()
        if v.connected and (v.level >= ALERT_THRESHOLD or v.status.alarm)
    ]
    if not danger:
        return

    current = active_zone()
    for v in danger:
        r = v.status.risk
        with st.container():
            st.markdown('<span class="es-emerg-marker"></span>', unsafe_allow_html=True)
            c_msg, c_btn = st.columns([6, 1.2])
            with c_msg:
                st.markdown(
                    f"<div style='color:white;font-weight:700;font-size:16px;padding:2px 0;'>"
                    f"🚨 위급상황 — <b>{escape_html(zone_label(v.zone))}</b>"
                    f" · LV{r.level} {escape_html(r.label)}"
                    f"<span style='opacity:0.85;font-weight:500;margin-left:8px;'>"
                    f"({escape_html(r.details)})</span></div>",
                    unsafe_allow_html=True,
                )
            with c_btn:
                if current == v.zone:
                    st.markdown(
                        "<div style='color:#fca5a5;font-weight:600;text-align:center;"
                        "padding:8px 0;'>현재 보는 중</div>",
                        unsafe_allow_html=True,
                    )
                elif st.button(f"→ {zone_label(v.zone)}", key=f"emerg_jump_{v.zone}"):
                    set_active_zone(v.zone)
                    st.rerun(scope="app")


# ════════════════════════════════════════════════════════════
#  구역 네비게이션 바 (목록 복귀 + 구역 전환 드롭다운)
# ════════════════════════════════════════════════════════════

def render_zone_nav(current: str) -> None:
    zones = RUNTIME.zone_ids()
    if current not in zones:
        zones = [current] + zones

    c_back, c_sel, _ = st.columns([1.2, 2, 6])
    with c_back:
        if st.button("← 구역 목록", key="zone_nav_back"):
            set_active_zone(None)
            st.rerun()
    with c_sel:
        picked = st.selectbox(
            "구역 선택", zones, index=zones.index(current), key="zone_nav_select",
            format_func=zone_label, label_visibility="collapsed",
        )
        if picked != current:
            set_active_zone(picked)
            st.rerun()


# ════════════════════════════════════════════════════════════
#  구역 목록
# ════════════════════════════════════════════════════════════

def _zone_card(v: ZoneView) -> str:
    s = v.status if v.connected else None
    if not v.connected:
        color, icon, state = "var(--muted)", "🔴", f"⚠️ 신호 없음 · 마지막 {_ago(v.last_seen)}"
    else:
        color = "#ef4444" if (v.level >= ALERT_THRESHOLD or s.alarm) else (
            "#f97316" if v.level >= 2 else "#22c55e")
        icon = "🚨" if (v.level >= ALERT_THRESHOLD or s.alarm) else "🟢"
        state = f"온라인 | LV {v.level} {LEVEL_LABELS[v.level]}"

    badges = ""
    if s is not None:
        if s.vision.fire_detected:
            badges += _badge("🔥 화재 감지", "danger")
        if s.risk.early:
            badges += _badge("⏱ 조기 감지", "warn")
        if s.vision.camera_offline:
            badges += _badge("📷 카메라 오프라인", "danger")
        if s.sensor_mode == "demo":
            badges += _badge("DEMO", "warn")
        sn = s.sensors
        values = (f"🌡 {sn.temperature:.1f}°C &nbsp; 💨 가스 {sn.gas} &nbsp; 🌫 연기 {sn.smoke}"
                  f" <span style='color:var(--muted);font-size:11px;'>(ADC)</span>")
    else:
        values = "🌡 -- &nbsp; 💨 -- &nbsp; 🌫 --"

    return f"""
        <span class="es-zone-card-marker"></span>
        <div class="es-zone-card-wrap">
        <div style="border:1px solid {color};border-radius:10px;
                    padding:16px;background:var(--card);
                    transition:border-color .2s ease,box-shadow .2s ease;">
            <div style="font-size:15px;font-weight:700;color:var(--text);">
                {icon} {escape_html(zone_label(v.zone))}
            </div>
            <div style="font-size:12px;color:var(--muted);margin:6px 0;">{escape_html(state)}</div>
            <div style="font-size:13px;color:var(--text);">{values}</div>
            <div style="margin-top:6px;">{badges}</div>
        </div>
        </div>
    """


@st.fragment(run_every=2.0)
def render_zone_overview() -> None:
    """연결된 모든 라즈베리파이 구역 카드 목록."""
    zones = RUNTIME.all_zones()
    if not zones:
        broker_ok, err, target = RUNTIME.get_broker()
        if broker_ok:
            st.info(f"📡 브로커 {target} 연결됨 — Pi 데이터 대기 중... "
                    "(Pi 에서 main.py 실행, 또는 PC 테스트: python -m gui.fake_edge)")
        else:
            st.warning(f"📡 MQTT 브로커 {target} 에 연결되지 않았습니다 ({err}). "
                       ".env 의 MQTT_BROKER_HOST 와 Pi 의 mosquitto 실행을 확인하세요.")
        return

    st.markdown("### 연결된 구역")
    cols = st.columns(min(len(zones), 3))
    for idx, v in enumerate(zones):
        with cols[idx % 3]:
            st.markdown(_zone_card(v), unsafe_allow_html=True)
            if st.button(" ", key=f"zone_card_{v.zone}", width="stretch"):
                set_active_zone(v.zone)
                st.rerun(scope="app")


# ════════════════════════════════════════════════════════════
#  Shutdown modal
# ════════════════════════════════════════════════════════════

@st.dialog("⚠️ 대시보드 종료")
def render_shutdown_modal(on_confirm) -> None:
    st.write("관제 대시보드를 종료하시겠습니까? (Pi 의 감시·경보는 계속 동작합니다)")
    c1, c2 = st.columns(2)
    if c1.button("예 (YES)", type="primary", width='stretch', key="sd_yes"):
        on_confirm()
        st.rerun()
    if c2.button("아니요 (NO)", width='stretch', key="sd_no"):
        st.rerun()
