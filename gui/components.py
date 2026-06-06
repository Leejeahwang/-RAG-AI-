"""
gui/components.py - CSS + 모든 UI fragment 한 파일.
"""

from __future__ import annotations

import time
import cv2
import pandas as pd
import streamlit as st
from gui.state import (
    RUNTIME, GAUGE_COLORS, CAM_WIDTH, ALERT_THRESHOLD, STALE_THRESHOLD,
    REFRESH_CAMERA, REFRESH_SENSORS, REFRESH_GAUGE, REFRESH_AI,
    REFRESH_TREND, REFRESH_LOG, REFRESH_STATUS,
    MQTT_MODE,
    escape_html, detect_lang,
)
from gui import workers as W


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
"""


def inject_css(theme: str = "dark") -> None:
    attr = "light" if theme == "light" else "dark"
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
    st.html(
        f"<style>html,body{{margin:0;padding:0;}}</style>"
        f"<script>window.parent.document.documentElement.setAttribute('data-theme','{attr}');</script>"
    )


def _is_stale(ts: float) -> bool:
    return ts > 0 and (time.time() - ts) > STALE_THRESHOLD


def _gauge_color(level: int) -> str:
    idx = max(0, min(level, len(GAUGE_COLORS) - 1))
    return GAUGE_COLORS[idx]


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
    risk = RUNTIME.get_risk()
    if risk.level >= ALERT_THRESHOLD:
        chip_cls, chip_label = "es-arm-chip danger", "EMERGENCY"
    elif risk.level >= 2:
        chip_cls, chip_label = "es-arm-chip warn", "ALERT"
    else:
        chip_cls, chip_label = "es-arm-chip", "SYSTEM ARMED"
    st.markdown(
        f'<span class="{chip_cls}"><span class="es-dot"></span> {chip_label}</span>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Header
# ════════════════════════════════════════════════════════════

def render_header(on_theme_toggle) -> None:
    c_brand, c_spacer, c_clock, c_chip, c_btn = st.columns([2, 6, 1.8, 1.5, 0.5])
    with c_brand:
        # MQTT 모드일 때 현재 보고 있는 구역 표시
        if MQTT_MODE:
            active = RUNTIME.get_active_zone()
            sub_label = f"관제 모드 · {escape_html(active)}" if active else "관제 모드 · 구역 목록"
        else:
            sub_label = "Factory Fire Monitoring"
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
#  KPI row
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_SENSORS)
def render_kpi_row() -> None:
    s = RUNTIME.get_sensors()
    r = RUNTIME.get_risk()
    if s is None:
        temp, gas_v, smoke_v = "--", "--", "--"
        t_cls = g_cls = sm_cls = "es-kpi"
    else:
        temp, gas_v, smoke_v = f"{s.temperature:.1f}", f"{s.gas}", f"{s.smoke}"
        t_cls = "es-kpi danger" if s.temperature >= 60 else ("es-kpi active" if s.temperature >= 28 else "es-kpi")
        g_cls = "es-kpi danger" if s.gas >= 500 else ("es-kpi active" if s.gas >= 400 else "es-kpi")
        sm_cls = "es-kpi danger" if s.smoke >= 500 else ("es-kpi active" if s.smoke >= 300 else "es-kpi")

    risk_cls = "es-kpi danger" if r.level >= ALERT_THRESHOLD else (
        "es-kpi active" if r.level >= 2 else "es-kpi")
    risk_color = _gauge_color(r.level)

    st.markdown(
        f"""
        <div class="es-kpi-row">
            <div class="{t_cls}">
                <div class="es-kpi-label">🌡 온도</div>
                <div class="es-kpi-value">{temp}<span class="es-kpi-unit">°C</span></div>
                <div class="es-kpi-meta">임계 28°C / 60°C</div>
            </div>
            <div class="{g_cls}">
                <div class="es-kpi-label">💨 가스</div>
                <div class="es-kpi-value">{gas_v}<span class="es-kpi-unit">ppm</span></div>
                <div class="es-kpi-meta">임계 400 / 500</div>
            </div>
            <div class="{sm_cls}">
                <div class="es-kpi-label">🌫 연기</div>
                <div class="es-kpi-value">{smoke_v}<span class="es-kpi-unit">%</span></div>
                <div class="es-kpi-meta">임계 300 / 500</div>
            </div>
            <div class="{risk_cls}">
                <div class="es-kpi-label">🚨 위험도</div>
                <div class="es-kpi-value" style="color:{risk_color};">LV {r.level}</div>
                <div class="es-kpi-meta">{escape_html(r.label)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Sensor mini row (3 compact cards, for right-column use)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_SENSORS)
def render_sensor_mini() -> None:
    s = RUNTIME.get_sensors()
    if s is None:
        temp, gas_v, smoke_v = "--", "--", "--"
        t_cls = g_cls = sm_cls = "es-kpi-sm"
    else:
        temp = f"{s.temperature:.1f}"
        gas_v = f"{s.gas}"
        smoke_v = f"{s.smoke}"
        t_cls = "es-kpi-sm danger" if s.temperature >= 60 else ("es-kpi-sm active" if s.temperature >= 28 else "es-kpi-sm")
        g_cls = "es-kpi-sm danger" if s.gas >= 500 else ("es-kpi-sm active" if s.gas >= 400 else "es-kpi-sm")
        sm_cls = "es-kpi-sm danger" if s.smoke >= 500 else ("es-kpi-sm active" if s.smoke >= 300 else "es-kpi-sm")
    st.markdown(
        f"""
        <div class="es-sensor-row">
            <div class="{t_cls}">
                <div class="es-kpi-label">🌡 온도</div>
                <div class="es-kpi-value" style="font-size:18px;margin-top:4px;">{temp}<span class="es-kpi-unit" style="font-size:11px;">°C</span></div>
            </div>
            <div class="{g_cls}">
                <div class="es-kpi-label">💨 가스</div>
                <div class="es-kpi-value" style="font-size:18px;margin-top:4px;">{gas_v}<span class="es-kpi-unit" style="font-size:11px;">ppm</span></div>
            </div>
            <div class="{sm_cls}">
                <div class="es-kpi-label">🌫 연기</div>
                <div class="es-kpi-value" style="font-size:18px;margin-top:4px;">{smoke_v}<span class="es-kpi-unit" style="font-size:11px;">%</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Camera panel
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_CAMERA)
def render_camera_panel() -> None:
    fire = RUNTIME.get_fire()
    frame = RUNTIME.get_frame_copy()

    # MQTT 모드 + 프레임 없음 → 원격 안내 (실제 관제 PC는 Pi 카메라 미수신)
    if frame is None and MQTT_MODE:
        conf_cls = "es-conf alert" if fire.detected else "es-conf"
        st.markdown(
            f"""
            <div style="border:1px dashed var(--border);border-radius:10px;
                        padding:40px;text-align:center;background:var(--card);">
                <div style="font-size:48px;">📡</div>
                <div style="color:var(--muted);margin-top:8px;">
                    원격 구역 — 라즈베리파이가 화재 탐지 결과를 전송 중
                </div>
                <div style="margin-top:14px;">
                    <span class='{conf_cls}'>FIRE CONFIDENCE: {fire.confidence:.2f}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if fire.detected:
            st.error(f"🚨 [화재 탐지됨] {escape_html(fire.description)}")
        return

    if frame is None:
        st.info("카메라 스트리밍 연결 대기 중...")
    else:
        try:
            st.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), width='stretch')
        except Exception as e:
            st.error("카메라 영상 표시 오류")
            RUNTIME.add_log(f"❌ [카메라] 변환 오류: {e}")
        conf_cls = "es-conf alert" if fire.detected else "es-conf"
        st.markdown(
            f"<span class='{conf_cls}'>FIRE CONFIDENCE: {fire.confidence:.2f}</span> "
            f"<span class='es-conf'>{escape_html(fire.description)}</span>",
            unsafe_allow_html=True,
        )
        if fire.detected:
            st.error(f"🚨 [화재 탐지됨] {escape_html(fire.description)}")
        if _is_stale(fire.ts):
            st.markdown("<div class='es-stale'>⚠ 화재 감지 신호 지연</div>",
                        unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
#  Risk gauge
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_GAUGE)
def render_risk_gauge() -> None:
    r = RUNTIME.get_risk()
    color = _gauge_color(r.level)
    width_pct = min(r.level, 5) * 20
    st.markdown(
        f"""
        <div class='es-panel' style='padding:12px 16px; margin-bottom:10px;'>
            <div class='es-panel-title' style='margin-bottom:8px;'>🚨 위험도 게이지</div>
            <div class='es-gauge-track' style='height:16px;'>
                <div class='es-gauge-fill' style='width:{width_pct}%;
                    background-color:{color};
                    box-shadow:0 0 14px {color}88;'></div>
            </div>
            <div class='es-gauge-label' style='margin-top:6px;'>
                <div class='es-gauge-level' style='color:{color}; font-size:22px;'>LV {r.level}</div>
                <div class='es-gauge-text'>{escape_html(r.label)} · {escape_html(r.details)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Trend (시계열 라인 차트)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_TREND)
def render_trend_panel() -> None:
    st.markdown(
        "<div class='es-panel'><div class='es-panel-title'>📈 추세 (최근 2분)</div>",
        unsafe_allow_html=True,
    )
    snaps = RUNTIME.snapshot_trend()
    if not snaps:
        st.caption("데이터 수집 중...")
    else:
        df = pd.DataFrame({
            "온도(°C)": [s.temperature for s in snaps],
            "가스/10": [s.gas / 10.0 for s in snaps],
            "연기/10": [s.smoke / 10.0 for s in snaps],
        })
        st.line_chart(df, height=180, width='stretch')
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
#  AI panel (알람 트리거 + STT 큐 소비도 여기서)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_AI)
def render_ai_panel(llm_queue) -> None:
    # 1) 알람 트리거 — MQTT 모드는 alert_dispatcher가 모든 구역 일괄 처리하므로 스킵
    if not MQTT_MODE:
        r = RUNTIME.get_risk()
        if r.level >= ALERT_THRESHOLD:
            if RUNTIME.try_claim_alert():
                sensors = RUNTIME.get_sensors()
                RUNTIME.add_log(f"🚨 위급상황 감지 LV{r.level} — RAG 지침 생성 시작")
                W.enqueue_emergency(llm_queue, r, sensors, RUNTIME.get_zone())
        else:
            RUNTIME.reset_alert()

    # 2) STT 큐 소비 → LLM 큐로 라우팅
    while True:
        msg = RUNTIME.pop_stt()
        if msg is None:
            break
        if RUNTIME.is_generating():
            RUNTIME.add_log("⚠️ AI가 다른 작업 중 — 음성 질의 대기")
            break
        W.enqueue_query(llm_queue, msg.text, msg.lang)

    # 2-1) STT 드롭 알림
    if RUNTIME.pop_stt_dropped():
        st.warning("음성이 처리되지 않았습니다.")

    # 3) 표시
    if RUNTIME.is_generating():
        cls = "es-ai-card generating"
        text = "⚠️ AI가 상황을 분석하여 지침을 생성 중입니다... ⏳"
    else:
        cls = "es-ai-card"
        ans = RUNTIME.get_last_answer()
        text = ans if ans else "안전 상태 유지 중입니다. (지침 대기 중)"

    st.markdown(
        f"<div class='es-panel'><div class='es-panel-title'>🤖 AI 지침</div>"
        f"<div class='{cls}'>{escape_html(text)}</div></div>",
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
#  Status bar (LIVE/SENSORS/AI READY)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=REFRESH_STATUS)
def render_status_bar() -> None:
    s = RUNTIME.get_sensors()
    sensors_ok = s is not None and not _is_stale(s.ts)
    ai_busy = RUNTIME.is_generating()

    def chip(ok: bool, label: str, fail_cls: str = "danger") -> str:
        cls = "es-arm-chip" if ok else f"es-arm-chip {fail_cls}"
        return f"<span class='{cls}'><span class='es-dot'></span> {label}</span>"

    if MQTT_MODE:
        zones_count = len(RUNTIME.get_all_zones())
        chips = (
            chip(zones_count > 0, f'MQTT · {zones_count}구역', 'warn')
            + chip(sensors_ok, 'SENSORS', 'danger')
            + chip(not ai_busy, 'AI READY' if not ai_busy else 'AI BUSY', 'warn')
        )
    else:
        cam_ok = RUNTIME.get_frame_copy() is not None
        chips = (
            chip(cam_ok, 'CAM LIVE', 'danger')
            + chip(sensors_ok, 'SENSORS', 'danger')
            + chip(not ai_busy, 'AI READY' if not ai_busy else 'AI BUSY', 'warn')
        )

    st.markdown(
        f"""
        <div style='display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px;'>
            {chips}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  Emergency banner (MQTT 관제 모드 — 모든 구역 감시)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=1.0)
def render_emergency_banner() -> None:
    """임계치 넘은 구역이 있으면 상단에 빨간 배너 + 이동 버튼."""
    if not MQTT_MODE:
        return
    danger = []
    for zone in RUNTIME.get_all_zones():
        r = RUNTIME.get_zone_risk(zone)
        if r.level >= ALERT_THRESHOLD:
            danger.append((zone, r))
    if not danger:
        return

    active = RUNTIME.get_active_zone()
    for zone, r in danger:
        with st.container():
            st.markdown('<span class="es-emerg-marker"></span>', unsafe_allow_html=True)
            c_msg, c_btn = st.columns([6, 1.2])
            with c_msg:
                st.markdown(
                    f"<div style='color:white;font-weight:700;font-size:16px;padding:2px 0;'>"
                    f"🚨 위급상황 감지 — <b>{escape_html(zone)}</b>"
                    f" · LV{r.level} {escape_html(r.label)}"
                    f"<span style='opacity:0.85;font-weight:500;margin-left:8px;'>"
                    f"({escape_html(r.details)})</span></div>",
                    unsafe_allow_html=True,
                )
            with c_btn:
                if active == zone:
                    st.markdown(
                        "<div style='color:#fca5a5;font-weight:600;text-align:center;"
                        "padding:8px 0;'>현재 보는 중</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    if st.button(f"→ {zone}", key=f"emerg_jump_{zone}"):
                        st.session_state["_zone_jump"] = zone
                        st.rerun()


# ════════════════════════════════════════════════════════════
#  구역 네비게이션 바 (목록 복귀 + 구역 전환 드롭다운)
# ════════════════════════════════════════════════════════════

def render_zone_nav(active_zone: str) -> None:
    """상세화면 상단 — 목록 복귀 버튼 + 구역 전환 드롭다운."""
    zones = sorted(RUNTIME.get_all_zones().keys())
    if active_zone not in zones:
        zones = [active_zone] + [z for z in zones if z != active_zone]

    c_back, c_sel, c_spacer = st.columns([1.2, 2, 6])
    with c_back:
        if st.button("← 구역 목록", key="zone_nav_back"):
            RUNTIME.set_active_zone(None)
            st.rerun(scope="app")
    with c_sel:
        try:
            idx = zones.index(active_zone)
        except ValueError:
            idx = 0
        picked = st.selectbox(
            "구역 선택", zones, index=idx, key="zone_nav_select", label_visibility="collapsed",
        )
        if picked != active_zone:
            RUNTIME.set_active_zone(picked)
            st.rerun(scope="app")


# ════════════════════════════════════════════════════════════
#  구역 목록 (MQTT 관제 모드)
# ════════════════════════════════════════════════════════════

@st.fragment(run_every=2.0)
def render_zone_overview() -> None:
    """연결된 모든 라즈베리파이 구역 카드 목록."""
    zones = RUNTIME.get_all_zones()

    if not zones:
        st.info("📡 라즈베리파이 연결 대기 중... (Pi에서 rpi_publisher.py 실행 확인)")
        return

    st.markdown("### 연결된 구역")
    cols = st.columns(min(len(zones), 3))

    for idx, (zone, snap) in enumerate(zones.items()):
        fire = RUNTIME.get_zone_fire(zone)
        risk = RUNTIME.get_zone_risk(zone)
        last_seen = RUNTIME.get_zone_last_seen(zone)
        age = time.time() - last_seen
        online = age < STALE_THRESHOLD

        status_color = "#ef4444" if risk.level >= ALERT_THRESHOLD else (
            "#f97316" if risk.level >= 2 else "#22c55e"
        )
        status_icon = "🔴" if not online else ("🚨" if risk.level >= ALERT_THRESHOLD else "🟢")
        fire_badge = " 🔥 화재감지!" if fire.detected else ""

        with cols[idx % 3]:
            st.markdown(
                f"""
                <span class="es-zone-card-marker"></span>
                <div class="es-zone-card-wrap">
                <div style="border:1px solid {status_color};border-radius:10px;
                            padding:16px;background:var(--card);
                            transition:border-color .2s ease,box-shadow .2s ease;">
                    <div style="font-size:15px;font-weight:700;color:var(--text);">
                        {status_icon} {escape_html(zone)}{escape_html(fire_badge)}
                    </div>
                    <div style="font-size:12px;color:var(--muted);margin:6px 0;">
                        {'온라인' if online else '⚠️ 신호 없음'}
                        &nbsp;|&nbsp; LV {risk.level} {escape_html(risk.label)}
                    </div>
                    <div style="font-size:13px;color:var(--text);">
                        🌡 {snap.temperature:.1f}°C &nbsp;
                        💨 {snap.gas} ppm &nbsp;
                        🌫 {snap.smoke}
                    </div>
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(" ", key=f"zone_card_{zone}", use_container_width=True):
                RUNTIME.set_active_zone(zone)
                st.rerun(scope="app")


# ════════════════════════════════════════════════════════════
#  Shutdown modal
# ════════════════════════════════════════════════════════════

@st.dialog("⚠️ 시스템 전원 종료")
def render_shutdown_modal(on_confirm) -> None:
    st.write("감시 시스템을 완전히 종료하시겠습니까?")
    c1, c2 = st.columns(2)
    if c1.button("예 (YES)", type="primary", width='stretch', key="sd_yes"):
        on_confirm()
        st.rerun()
    if c2.button("아니요 (NO)", width='stretch', key="sd_no"):
        st.rerun()
