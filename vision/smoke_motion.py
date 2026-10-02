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
    is_static_photo: bool = False           # 정지 영상/사진 오탐 여부
    mean_magnitude: float = 0.0             # 평균 움직임 강도 (픽셀 단위)
    moving_pixel_ratio: float = 0.0         # ROI 내 움직이는 픽셀 비율 (0.0 ~ 1.0)
    upward_ratio: float = 0.0               # 전체 움직임 중 위쪽(-Y) 방향 비율 (0.0 ~ 1.0)
    consecutive_upward_count: int = 0       # 연속 상방 이동 감지 횟수
    status: str = "INITIALIZING"            # 상태 문자열
    flow_vectors: Optional[np.ndarray] = None  # 시각화용 다운샘플링된 flow (u, v)
    roi_coords: Tuple[int, int, int, int] = (0, 0, 0, 0) # (x1, y1, x2, y2)


class SmokeMotionAnalyzer:
    """
    OpenCV Farneback Dense Optical Flow 기반 연기 동역학 분석기
    """
    def __init__(
        self,
        min_motion_mag: float = 0.4,       # 노이즈를 거르는 최소 픽셀 이동 임계값
        static_motion_ratio: float = 0.04, # 이 비율 이하로 움직이면 정지 사진(Static)으로 판정
        upward_ratio_threshold: float = 0.50, # 상방 이동 픽셀 비율 기준 (50% 이상 위로 이동)
        required_consecutive_frames: int = 3, # 진짜 연기로 확정하기 위한 연속 프레임 수
        history_len: int = 10              # 최근 프레임 기록 윈도우 크기
    ):
        self.min_motion_mag = min_motion_mag
        self.static_motion_ratio = static_motion_ratio
        self.upward_ratio_threshold = upward_ratio_threshold
        self.required_consecutive_frames = required_consecutive_frames
        
        # 이전 프레임 그레이스케일 저장용
        self.prev_gray: Optional[np.ndarray] = None
        
        # 박스별 시간축 추적 버퍼 (box_id 또는 단일 타겟용 카운터)
        self.consecutive_upward_frames = 0
        self.recent_results: deque = deque(maxlen=history_len)

    def reset(self):
        """내부 상태 초기화"""
        self.prev_gray = None
        self.consecutive_upward_frames = 0
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
        scale_x = 1.0
        scale_y = 1.0
        if box_w > target_size or box_h > target_size:
            scale = target_size / max(box_w, box_h)
            new_w = max(10, int(box_w * scale))
            new_h = max(10, int(box_h * scale))
            prev_roi_scaled = cv2.resize(prev_roi, (new_w, new_h))
            curr_roi_scaled = cv2.resize(curr_roi, (new_w, new_h))
            scale_x = new_w / box_w
            scale_y = new_h / box_h
        else:
            prev_roi_scaled = prev_roi
            curr_roi_scaled = curr_roi

        # 3. Dense Optical Flow 계산 (Farneback 알고리즘)
        # 파라미터는 노이즈 제거와 고속 연산에 최적화
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
        v = flow[..., 1] # 세로 방향 변위 (dy) : 주의! 이미지 좌표계에서는 위쪽이 -dy 임

        mag, _ = cv2.cartToPolar(u, v)

        # 4. 정지 영상(사진) 판별 (Static Check)
        total_pixels = mag.size
        moving_mask = mag > self.min_motion_mag
        moving_pixels = np.sum(moving_mask)
        moving_ratio = float(moving_pixels) / float(total_pixels + 1e-6)
        mean_mag = float(np.mean(mag))

        result.mean_magnitude = round(mean_mag, 2)
        result.moving_pixel_ratio = round(moving_ratio, 2)

        # 움직이는 픽셀 비율이 기준치 미만이면 정지된 사진으로 간주!
        if moving_ratio < self.static_motion_ratio:
            self.consecutive_upward_frames = max(0, self.consecutive_upward_frames - 1)
            result.is_static_photo = True
            result.is_real_smoke = False
            result.status = "STATIC_PHOTO_BLOCKED" # 사진 오탐 차단!
            result.consecutive_upward_count = self.consecutive_upward_frames
            self.prev_gray = curr_gray.copy()
            return result

        # 5. 연기 상방 확산(Upward Diffusion) 방향성 판정
        # 실제 연기는 대류 상승과 함께 난류 와류(Vortex/Eddy)가 동반되므로,
        # 전체 움직이는 픽셀 중 위쪽(v < -0.15) 성분이 우세한지 검사합니다.
        moving_v = v[moving_mask]
        upward_mask = moving_v < -0.15 # 위쪽 방향 drift
        upward_count = np.sum(upward_mask)
        upward_ratio = float(upward_count) / float(moving_pixels + 1e-6)
        result.upward_ratio = round(upward_ratio, 2)

        # 6. 시간축 안정성 검증 (슬라이딩 윈도우 기반)
        is_frame_upward = (upward_ratio >= self.upward_ratio_threshold)
        self.recent_results.append(is_frame_upward)
        
        # 최근 윈도우 내 상방 프레임 개수 집계
        upward_window_count = sum(1 for x in self.recent_results if x)
        
        if is_frame_upward:
            self.consecutive_upward_frames += 1
        else:
            self.consecutive_upward_frames = max(0, self.consecutive_upward_frames - 1)

        result.consecutive_upward_count = self.consecutive_upward_frames

        # 기준 프레임 이상(연속 3프레임 또는 최근 5프레임 중 3프레임 이상) 상방 대류 감지 시 확정!
        if self.consecutive_upward_frames >= self.required_consecutive_frames or (len(self.recent_results) >= 4 and upward_window_count >= 3):
            result.is_real_smoke = True
            result.is_static_photo = False
            result.status = "REAL_SMOKE_RISING" # 실제 연기 상방 확산 확인!
        else:
            result.is_real_smoke = False
            result.is_static_photo = False
            result.status = "EVALUATING_MOTION" # 판별 진행 중

        # 시각화용 다운샘플링 flow 저장
        result.flow_vectors = flow

        # 다음 프레임 비교를 위해 갱신
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
            color = (0, 0, 255) # 빨간색 (진짜 연기 경보)
            status_text = f"🔥 [REAL SMOKE] Rising Plume (Up:{int(result.upward_ratio*100)}% | Cnt:{result.consecutive_upward_count})"
        elif result.status == "STATIC_PHOTO_BLOCKED":
            color = (255, 128, 0) # 주황/하늘색 (사진 오탐 차단)
            status_text = f"🛡️ [PHOTO BLOCKED] Static Image (Motion:{int(result.moving_pixel_ratio*100)}%)"
        elif result.status == "EVALUATING_MOTION":
            color = (0, 255, 255) # 노란색 (분석 중)
            status_text = f"⏳ [ANALYZING] Upward:{int(result.upward_ratio*100)}% ({result.consecutive_upward_count}/{3})"
        else:
            color = (180, 180, 180)
            status_text = f"[{result.status}]"

        # 1. 바운딩 박스 그리기
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)

        # 2. 상단 상태 텍스트 바
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness = 2
        (tw, th), _ = cv2.getTextSize(status_text, font, font_scale, thickness)
        
        # 텍스트 배경 박스
        cv2.rectangle(output, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
        # 텍스트 출력 (흰색/검은색)
        text_color = (0, 0, 0) if result.status == "EVALUATING_MOTION" else (255, 255, 255)
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
                        # 원본 프레임 좌표로 매핑
                        start_pt = (int(x1 + c * sx), int(y1 + r * sy))
                        # 움직임 벡터 강조(스케일 x2.5)
                        end_pt = (int(start_pt[0] + dx * 2.5), int(start_pt[1] + dy * 2.5))
                        
                        # 위쪽 움직임(-dy)은 청록색/녹색, 그 외는 옅은 회색
                        arrow_color = (0, 255, 128) if dy < -0.2 else (180, 180, 180)
                        cv2.arrowedLine(output, start_pt, end_pt, arrow_color, 1, tipLength=0.3)

        return output
