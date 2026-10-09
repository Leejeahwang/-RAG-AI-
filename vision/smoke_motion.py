"""
vision/smoke_motion.py - 미세 연기 상방 확산(Optical Flow) 분석 및 사진 오탐 차단 모듈
========================================================================================
작성자: 박규태 (Vision AI 담당)
목적:
  1. 단순 2D 정지 사진(모니터/스마트폰에 띄운 불꽃/연기)을 '움직임 없음'으로 식별하여 오경보 차단
  2. 실제 훈소(Smoldering) 화재 시 피어오르는 미세 연기의 상방 대류(Upward Motion) 벡터를 포착하여 조기 경보
"""

import cv2
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any


@dataclass
class MotionAnalysisResult:
    """단일 바운딩 박스에 대한 모션 분석 결과"""
    is_real_smoke: bool = False             # 상방 확산이 확인된 진짜 연기 여부
    is_real_fire: bool = False              # 난류 플리커링이 확인된 진짜 불꽃 여부
    is_static_photo: bool = False           # 정지 영상/사진 오탐 여부
    is_rigid_motion: bool = False           # 손에 들고 흔드는 사진(강체 평행 이동) 오탐 여부
    mean_magnitude: float = 0.0             # 평균 움직임 강도 (픽셀 단위)
    moving_pixel_ratio: float = 0.0         # ROI 내 움직이는 픽셀 비율 (0.0 ~ 1.0)
    upward_ratio: float = 0.0               # 전체 움직임 중 위쪽(-Y) 방향 비율 (0.0 ~ 1.0)
    directional_coherence: float = 0.0      # 방향 일치도 R (0.0 ~ 1.0, 1.0에 가까우면 손으로 든 사진의 평행 이동)
    turbulence_score: float = 0.0           # 난류 분산 점수 (0.0 ~ 1.0, 1.0에 가까우면 실제 화재의 와류 플리커링)
    consecutive_count: int = 0              # 연속 조건 충족 프레임 수
    consecutive_upward_count: int = 0       # 하위 호환용 연속 상방 이동 횟수
    status: str = "INITIALIZING"            # 상태 문자열
    flow_vectors: Optional[np.ndarray] = None  # 시각화용 다운샘플링된 flow (u, v)
    roi_coords: Tuple[int, int, int, int] = (0, 0, 0, 0) # (x1, y1, x2, y2)


class SmokeMotionAnalyzer:
    """
    OpenCV Farneback Dense Optical Flow 기반 연기/불꽃 동역학 및 사진 오탐 차단 분석기
    - 강체 평행 이동(Rigid Motion) 필터: 손에 든 스마트폰/인쇄물 사진의 흔들림 완벽 차단
    - 유체 난류(Fluid Turbulence) 분석: 실제 불꽃의 사방 플리커링 및 연기 상방 대류 검증
    """
    def __init__(
        self,
        min_motion_mag: float = 0.4,       # 노이즈를 거르는 최소 픽셀 이동 임계값
        static_motion_ratio: float = 0.05, # 이 비율 이하로 움직이면 정지 사진(Static)으로 판정
        upward_ratio_threshold: float = 0.50, # 상방 이동 픽셀 비율 기준 (50% 이상 위로 이동)
        rigid_coherence_threshold: float = 0.78, # R 임계값: 이 이상이면 한 덩어리로 흔들리는 사진(Rigid)
        required_consecutive_frames: int = 3, # 진짜 연기/불꽃으로 확정하기 위한 연속 프레임 수
        history_len: int = 10              # 최근 프레임 기록 윈도우 크기
    ):
        self.min_motion_mag = min_motion_mag
        self.static_motion_ratio = static_motion_ratio
        self.upward_ratio_threshold = upward_ratio_threshold
        self.rigid_coherence_threshold = rigid_coherence_threshold
        self.required_consecutive_frames = required_consecutive_frames
        
        # 이전 프레임 그레이스케일 저장용
        self.prev_gray: Optional[np.ndarray] = None
        
        # 박스별 시간축 추적 버퍼
        self.consecutive_upward_frames = 0
        self.consecutive_fire_frames = 0
        self.recent_smoke_results: deque = deque(maxlen=history_len)
        self.recent_fire_results: deque = deque(maxlen=history_len)
        self.recent_results: deque = deque(maxlen=history_len)  # 하위 호환용

    def reset(self):
        """내부 상태 초기화"""
        self.prev_gray = None
        self.consecutive_upward_frames = 0
        self.consecutive_fire_frames = 0
        self.recent_smoke_results.clear()
        self.recent_fire_results.clear()
        self.recent_results.clear()

    def analyze(
        self,
        current_frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        class_name: str = "smoke"
    ) -> MotionAnalysisResult:
        """
        현재 프레임과 이전 프레임을 비교하여 지정된 bbox(x1, y1, x2, y2) 영역의 움직임을 분석합니다.

        Args:
            current_frame: 현재 BGR 또는 Gray 영상 프레임
            bbox: (x1, y1, x2, y2) 바운딩 박스 좌표
            class_name: 'smoke' 또는 'fire'

        Returns:
            MotionAnalysisResult 객체
        """
        result = MotionAnalysisResult(roi_coords=bbox)
        
        # 1. 그레이스케일 변환
        if len(current_frame.shape) == 3:
            curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        else:
            curr_gray = current_frame

        # 첫 프레임인 경우 이전 프레임만 저장하고 대기 상태 반환
        if self.prev_gray is None:
            self.prev_gray = curr_gray.copy()
            result.status = "WARMING_UP"
            return result

        h, w = curr_gray.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        # 좌표 유효 범위 클리핑
        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h))

        box_w = x2 - x1
        box_h = y2 - y1

        if box_w < 10 or box_h < 10:
            result.status = "BOX_TOO_SMALL"
            self.prev_gray = curr_gray.copy()
            return result

        # 2. ROI 영역 추출
        prev_roi = self.prev_gray[y1:y2, x1:x2]
        curr_roi = curr_gray[y1:y2, x1:x2]

        # 엣지 디바이스(라즈베리파이) CPU 연산 최적화를 위한 ROI 다운샘플링 (최대 120x120)
        target_size = 120
        if box_w > target_size or box_h > target_size:
            scale = target_size / max(box_w, box_h)
            new_w = max(10, int(box_w * scale))
            new_h = max(10, int(box_h * scale))
            prev_roi_scaled = cv2.resize(prev_roi, (new_w, new_h))
            curr_roi_scaled = cv2.resize(curr_roi, (new_w, new_h))
        else:
            prev_roi_scaled = prev_roi
            curr_roi_scaled = curr_roi

        # 3. Dense Optical Flow 계산 (Farneback 알고리즘)
        flow = cv2.calcOpticalFlowFarneback(
            prev_roi_scaled,
            curr_roi_scaled,
            None,
            pyr_scale=0.5,
            levels=2,
            winsize=13,
            iterations=2,
            poly_n=5,
            poly_sigma=1.1,
            flags=0
        )

        u = flow[..., 0] # 가로 방향 변위 (dx)
        v = flow[..., 1] # 세로 방향 변위 (dy) : 이미지 좌표계에서는 위쪽이 -dy 임

        mag, _ = cv2.cartToPolar(u, v)

        # 4. 정지 영상(완전 고정 사진) 판별 (Static Check)
        total_pixels = mag.size
        moving_mask = mag > self.min_motion_mag
        moving_pixels = int(np.sum(moving_mask))
        moving_ratio = float(moving_pixels) / float(total_pixels + 1e-6)
        mean_mag = float(np.mean(mag))

        result.mean_magnitude = round(mean_mag, 2)
        result.moving_pixel_ratio = round(moving_ratio, 2)
        result.flow_vectors = flow

        # 움직이는 픽셀 비율이 기준치 미만이면 완전 정지된 사진으로 간주!
        if moving_ratio < self.static_motion_ratio:
            self.consecutive_upward_frames = max(0, self.consecutive_upward_frames - 1)
            self.consecutive_fire_frames = max(0, self.consecutive_fire_frames - 1)
            result.is_static_photo = True
            result.is_real_smoke = False
            result.is_real_fire = False
            result.status = "STATIC_PHOTO_BLOCKED" # 사진 오탐 차단!
            result.consecutive_count = 0
            result.consecutive_upward_count = self.consecutive_upward_frames
            self.prev_gray = curr_gray.copy()
            return result

        # 5. 강체 평행 이동(손에 든 사진 흔들림) vs 유체 난류(실제 화재) 동역학 판별
        u_mov = u[moving_mask]
        v_mov = v[moving_mask]
        angles = np.arctan2(v_mov, u_mov)
        cos_mean = float(np.mean(np.cos(angles)))
        sin_mean = float(np.mean(np.sin(angles)))
        
        # Mean Resultant Length R (0.0: 완전 사방 난류 ~ 1.0: 모든 벡터가 한 방향으로 동일 이동)
        R = float(np.sqrt(cos_mean**2 + sin_mean**2))
        turbulence = max(0.0, 1.0 - R)
        result.directional_coherence = round(R, 2)
        result.turbulence_score = round(turbulence, 2)

        # 6. 클래스별 동역학 검증
        if "fire" in class_name.lower():
            # 🔥 [불꽃 사진 방어]:
            # 불꽃은 자체 연소 반응으로 사방으로 펄럭이는 유체 난류(Turbulence)를 동반함
            # 손에 든 스마트폰/인쇄물 사진은 손떨림/이동 시 내부 모든 픽셀이 같은 방향으로 이동 (R >= 0.78)
            if R >= self.rigid_coherence_threshold and moving_ratio < 0.85:
                self.consecutive_fire_frames = max(0, self.consecutive_fire_frames - 1)
                result.is_rigid_motion = True
                result.is_static_photo = True
                result.is_real_fire = False
                result.status = "HANDHELD_PHOTO_BLOCKED" # 손에 든 사진 움직임 차단!
                result.consecutive_count = 0
                self.prev_gray = curr_gray.copy()
                return result

            # 진짜 불꽃 판별:
            # - 사방으로 펄럭이는 플리커링 난류 (Turbulence >= 0.22, 즉 R < 0.78)
            # - 충분한 움직임 비율 (moving_ratio >= 0.06)
            is_frame_fire = (moving_ratio >= 0.06 and turbulence >= 0.22)
            self.recent_fire_results.append(is_frame_fire)

            if is_frame_fire:
                self.consecutive_fire_frames += 1
            else:
                self.consecutive_fire_frames = max(0, self.consecutive_fire_frames - 1)

            result.consecutive_count = self.consecutive_fire_frames

            # 불꽃 연속 프레임(3프레임 이상) 플리커링 유지 시 확정!
            if self.consecutive_fire_frames >= self.required_consecutive_frames:
                result.is_real_fire = True
                result.is_static_photo = False
                result.status = "REAL_FIRE_FLICKERING"
            else:
                result.is_real_fire = False
                result.is_static_photo = False
                result.status = "EVALUATING_FIRE_MOTION"

        else:
            # 💨 [연기 상방 확산 동역학]:
            # 연기는 위쪽(-Y)으로 피어오르는 상방 대류(Upward Diffusion)가 핵심
            upward_mask = v_mov < -0.15 # 위쪽 방향 drift
            upward_count = int(np.sum(upward_mask))
            upward_ratio = float(upward_count) / float(moving_pixels + 1e-6)
            result.upward_ratio = round(upward_ratio, 2)

            # 손에 든 연기 사진을 좌우나 아래로 흔드는 경우(R 높고 upward 부족) 차단
            if R >= 0.85 and upward_ratio < 0.35:
                self.consecutive_upward_frames = max(0, self.consecutive_upward_frames - 1)
                result.is_rigid_motion = True
                result.is_static_photo = True
                result.is_real_smoke = False
                result.status = "HANDHELD_PHOTO_BLOCKED"
                result.consecutive_count = 0
                result.consecutive_upward_count = self.consecutive_upward_frames
                self.prev_gray = curr_gray.copy()
                return result

            is_frame_upward = (upward_ratio >= self.upward_ratio_threshold)
            self.recent_smoke_results.append(is_frame_upward)
            self.recent_results.append(is_frame_upward) # 하위 호환

            if is_frame_upward:
                self.consecutive_upward_frames += 1
            else:
                self.consecutive_upward_frames = max(0, self.consecutive_upward_frames - 1)

            result.consecutive_count = self.consecutive_upward_frames
            result.consecutive_upward_count = self.consecutive_upward_frames

            # 연속 3프레임 이상 상방 대류 감지 시 확정
            if self.consecutive_upward_frames >= self.required_consecutive_frames:
                result.is_real_smoke = True
                result.is_static_photo = False
                result.status = "REAL_SMOKE_RISING"
            else:
                result.is_real_smoke = False
                result.is_static_photo = False
                result.status = "EVALUATING_SMOKE_MOTION"

        self.prev_gray = curr_gray.copy()
        return result

    @staticmethod
    def draw_motion_overlay(
        frame: np.ndarray,
        result: MotionAnalysisResult,
        step: int = 15
    ) -> np.ndarray:
        """
        화면에 바운딩 박스, 상태 텍스트, 그리고 옵티컬 플로우 움직임 화살표를 시각화합니다.
        """
        output = frame.copy()
        x1, y1, x2, y2 = result.roi_coords

        # 상태에 따른 색상 정의 (BGR)
        if result.status == "REAL_SMOKE_RISING":
            color = (0, 0, 255) # 빨간색
            status_text = f"🔥 [REAL SMOKE] Rising Plume (Up:{int(result.upward_ratio*100)}% | Cnt:{result.consecutive_count})"
        elif result.status == "REAL_FIRE_FLICKERING":
            color = (0, 0, 255) # 빨간색
            status_text = f"🔥 [REAL FIRE] Turbulent Flame (Turb:{int(result.turbulence_score*100)}% | Cnt:{result.consecutive_count})"
        elif result.status == "HANDHELD_PHOTO_BLOCKED":
            color = (255, 140, 0) # 주황색 (손에 든 사진 흔들림 차단)
            status_text = f"🛡️ [PHOTO BLOCKED] Handheld Shake (Rigid R:{int(result.directional_coherence*100)}%)"
        elif result.status == "STATIC_PHOTO_BLOCKED":
            color = (255, 140, 0) # 주황색 (완전 정지 사진 차단)
            status_text = f"🛡️ [PHOTO BLOCKED] Static Image (Motion:{int(result.moving_pixel_ratio*100)}%)"
        elif result.status == "EVALUATING_FIRE_MOTION":
            color = (0, 255, 255) # 노란색 (분석 중)
            status_text = f"⏳ [ANALYZING] Evaluating Flame Turbulence ({result.consecutive_count}/{3})"
        elif result.status == "EVALUATING_SMOKE_MOTION":
            color = (0, 255, 255) # 노란색 (분석 중)
            status_text = f"⏳ [ANALYZING] Upward:{int(result.upward_ratio*100)}% ({result.consecutive_count}/{3})"
        else:
            color = (180, 180, 180)
            status_text = f"[{result.status}]"

        # 1. 바운딩 박스 그리기
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)

        # 2. 상단 상태 텍스트 바
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.52
        thickness = 2
        (tw, th), _ = cv2.getTextSize(status_text, font, font_scale, thickness)
        
        cv2.rectangle(output, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
        text_color = (0, 0, 0) if "ANALYZING" in result.status else (255, 255, 255)
        cv2.putText(output, status_text, (x1 + 3, y1 - 4), font, font_scale, text_color, thickness - 1, cv2.LINE_AA)

        # 3. ROI 내부에 움직임 벡터 화살표 그리기
        if result.flow_vectors is not None:
            flow = result.flow_vectors
            fh, fw = flow.shape[:2]
            box_w = max(1, x2 - x1)
            box_h = max(1, y2 - y1)
            sx = box_w / fw
            sy = box_h / fh

            for r in range(0, fh, step):
                for c in range(0, fw, step):
                    dx = flow[r, c, 0]
                    dy = flow[r, c, 1]
                    mag = np.hypot(dx, dy)
                    
                    if mag > 0.4:
                        start_pt = (int(x1 + c * sx), int(y1 + r * sy))
                        end_pt = (int(start_pt[0] + dx * 2.5), int(start_pt[1] + dy * 2.5))
                        
                        if result.status == "HANDHELD_PHOTO_BLOCKED":
                            arrow_color = (255, 180, 50) # 균일 이동 화살표 (청회색)
                        elif dy < -0.2:
                            arrow_color = (0, 255, 128) # 상방 움직임
                        else:
                            arrow_color = (0, 180, 255) # 기타 플리커링
                        cv2.arrowedLine(output, start_pt, end_pt, arrow_color, 1, tipLength=0.3)

        return output
