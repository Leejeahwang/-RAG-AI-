"""
vision/test_unit_verification.py
=================================
비전 조기 감지 & 센서 퓨전 핵심 알고리즘 통합 자동 검증 스크립트
작성자: Antigravity AI
"""

import sys
import os
import cv2
import numpy as np

# 프로젝트 루트를 sys.path에 추가
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from vision.smoke_motion import SmokeMotionAnalyzer
from sensors.fusion import calculate_risk_level
from vision.vlm_analyzer import VLMHazardAnalyzer
import vision.fire_detector as fire_detector


def print_header(title):
    print("\n" + "=" * 65)
    print(f"🧪 {title}")
    print("=" * 65)


def test_smoke_motion_analyzer():
    print_header("1. 연기 동역학 분석기 (SmokeMotionAnalyzer) 단위 테스트")
    analyzer = SmokeMotionAnalyzer(
        min_motion_mag=0.4,
        static_motion_ratio=0.04,
        upward_ratio_threshold=0.50,
        required_consecutive_frames=3
    )

    passed = 0
    total = 3

    # 1-A. 완전 정지 이미지 테스트 (스마트폰/인쇄 사진 시뮬레이션)
    # 200x200 크기의 고정된 체커보드/노이즈 이미지 생성
    base_frame = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.circle(base_frame, (100, 100), 40, (120, 120, 120), -1)
    bbox = (50, 50, 150, 150)

    # 첫 프레임: warm up
    analyzer.analyze(base_frame, bbox)
    # 동일 프레임 2번째 입력: 움직임 0
    res_static = analyzer.analyze(base_frame, bbox)
    
    print(f"[1-A] 정지 사진 입력 테스트:")
    print(f"      - moving_pixel_ratio: {res_static.moving_pixel_ratio}")
    print(f"      - status: {res_static.status}")
    print(f"      - is_static_photo: {res_static.is_static_photo}")
    if res_static.is_static_photo and res_static.status == "STATIC_PHOTO_BLOCKED":
        print("      ✅ 결과: 통과 (정지 사진 오탐 완벽 차단)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 1-B. 상방 대류(위쪽 이동) 연기 테스트
    analyzer.reset()
    frames_up = []
    for step in range(5):
        f = np.zeros((200, 200, 3), dtype=np.uint8)
        # 매 프레임마다 y 위치가 4픽셀씩 위(-Y)로 이동
        center_y = 130 - (step * 4)
        cv2.circle(f, (100, center_y), 30, (180, 180, 180), -1)
        frames_up.append(f)

    # 연속 입력
    last_res = None
    for i, f in enumerate(frames_up):
        last_res = analyzer.analyze(f, bbox, class_name="smoke")
    
    print(f"\n[1-B] 상방 확산 연기 연속 입력 테스트 (5프레임):")
    print(f"      - upward_ratio: {last_res.upward_ratio}")
    print(f"      - consecutive_upward_count: {last_res.consecutive_upward_count}")
    print(f"      - status: {last_res.status}")
    print(f"      - is_real_smoke: {last_res.is_real_smoke}")
    if last_res.is_real_smoke and last_res.status == "REAL_SMOKE_RISING":
        print("      ✅ 결과: 통과 (미세 연기 상방 확산 조기 감지 확정)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 1-C. 하방/수평 이동 테스트 (단순 흔들림/내려앉는 먼지)
    analyzer.reset()
    frames_down = []
    for step in range(5):
        f = np.zeros((200, 200, 3), dtype=np.uint8)
        # 매 프레임마다 y 위치가 4픽셀씩 아래(+Y)로 이동
        center_y = 70 + (step * 4)
        cv2.circle(f, (100, center_y), 30, (180, 180, 180), -1)
        frames_down.append(f)

    for f in frames_down:
        last_res = analyzer.analyze(f, bbox, class_name="smoke")

    print(f"\n[1-C] 하방 이동(먼지/낙하물) 입력 테스트:")
    print(f"      - upward_ratio: {last_res.upward_ratio}")
    print(f"      - is_real_smoke: {last_res.is_real_smoke}")
    if not last_res.is_real_smoke:
        print("      ✅ 결과: 통과 (비연기 움직임 오탐 방지 성공)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 1-D. 손에 든 불꽃 사진 흔들림 테스트 (Rigid Motion / Handheld Photo Shake)
    analyzer.reset()
    total = 5
    # 스마트폰 화면/인쇄 사진과 같이 텍스처를 지닌 객체가 통째로 우하단(+dx, +dy)으로 이동하는 시뮬레이션
    np.random.seed(123)
    texture = np.random.randint(60, 220, (60, 60, 3), dtype=np.uint8)
    f_rigid1 = np.zeros((200, 200, 3), dtype=np.uint8)
    f_rigid1[70:130, 70:130] = texture
    analyzer.analyze(f_rigid1, bbox, class_name="fire")

    f_rigid2 = np.zeros((200, 200, 3), dtype=np.uint8)
    f_rigid2[74:134, 74:134] = texture  # 우하단(+4, +4)으로 평행 이동
    res_rigid = analyzer.analyze(f_rigid2, bbox, class_name="fire")

    print(f"\n[1-D] 손에 든 사진 흔들림(강체 평행 이동) 입력 테스트:")
    print(f"      - directional_coherence (R): {res_rigid.directional_coherence}")
    print(f"      - turbulence_score: {res_rigid.turbulence_score}")
    print(f"      - status: {res_rigid.status}")
    print(f"      - is_rigid_motion: {res_rigid.is_rigid_motion}")
    print(f"      - is_real_fire: {res_rigid.is_real_fire}")
    if res_rigid.is_rigid_motion and res_rigid.status == "HANDHELD_PHOTO_BLOCKED" and not res_rigid.is_real_fire:
        print("      ✅ 결과: 통과 (손에 든 사진 흔들림 오탐 완벽 차단!)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 1-E. 실제 불꽃 난류 플리커링(Turbulent Flame) 테스트
    analyzer.reset()
    # 사방으로 불규칙하게 진동/팽창하는 플리커링 시뮬레이션
    np.random.seed(42)
    flame_base = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.circle(flame_base, (100, 100), 35, (0, 140, 255), -1)
    analyzer.analyze(flame_base, bbox, class_name="fire")

    res_fire = None
    for step in range(4):
        f_flame = flame_base.copy()
        # 불꽃 내부 픽셀들의 비정형 플리커링 노이즈
        noise = (np.random.randn(200, 200, 3) * 35).astype(np.int16)
        f_flame = np.clip(f_flame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        res_fire = analyzer.analyze(f_flame, bbox, class_name="fire")

    print(f"\n[1-E] 실제 불꽃 난류 플리커링(Turbulent Flame) 4프레임 연속 테스트:")
    print(f"      - directional_coherence (R): {res_fire.directional_coherence}")
    print(f"      - turbulence_score: {res_fire.turbulence_score}")
    print(f"      - consecutive_count: {res_fire.consecutive_count}")
    print(f"      - status: {res_fire.status}")
    print(f"      - is_real_fire: {res_fire.is_real_fire}")
    if res_fire.is_real_fire and res_fire.status == "REAL_FIRE_FLICKERING":
        print("      ✅ 결과: 통과 (실제 불꽃 난류 플리커링 정확 감지 확정!)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    print(f"\n>> 모션 분석기 검증 결과: {passed}/{total} 통과")
    return passed == total


def test_sensor_fusion():
    print_header("2. 센서 퓨전 엔진 (calculate_risk_level) 단위 테스트")

    # 기본 센서 정상값
    smoke_normal = 80
    gas_normal = 120
    temp_normal = {"temperature": 24.5, "humidity": 50.0}

    passed = 0
    total = 5

    # 2-A. 사진 오탐 차단 (센서 정상 + 사진 감지) -> Level 0 정상
    vision_static = {
        "fire_detected": False,
        "is_real_smoke": False,
        "is_static_photo": True,
        "description": "사진 오탐"
    }
    risk_a = calculate_risk_level(smoke_normal, gas_normal, temp_normal, vision_static)
    print(f"[2-A] 사진 오탐 차단 테스트:")
    print(f"      - Level: {risk_a['level']} ({risk_a['label']}) | Details: {risk_a['details']}")
    if risk_a['level'] == 0:
        print("      ✅ 결과: 통과 (Level 0 정상 유지, 오경보 원천 차단)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 2-B. 미세 훈소 연기 조기 감지 (센서 정상 0단계 + 비전 상방 연기) -> Level 2 경고, early=True
    vision_early = {
        "fire_detected": False,
        "is_real_smoke": True,
        "is_static_photo": False,
        "description": "미세 연기 상방 확산"
    }
    risk_b = calculate_risk_level(smoke_normal, gas_normal, temp_normal, vision_early)
    print(f"\n[2-B] 비전 미세 연기 조기 감지 테스트 (센서 수치 0일 때):")
    print(f"      - Level: {risk_b['level']} ({risk_b['label']}) | Early Detection: {risk_b['is_early_detection']}")
    print(f"      - Details: {risk_b['details']}")
    if risk_b['level'] == 2 and risk_b['is_early_detection']:
        print("      ✅ 결과: 통과 (천장 센서 미도달 상태에서 Level 2 선제 발령)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 2-C. 클라우드 VLM 전열기 방치 진단 -> Level 1 주의, early=True
    vision_vlm = {
        "fire_detected": False,
        "is_real_smoke": False,
        "is_static_photo": False,
        "pre_hazard_alert": "작업자 부재 중 이동식 전열기 고온 가열 포착"
    }
    risk_c = calculate_risk_level(smoke_normal, gas_normal, temp_normal, vision_vlm)
    print(f"\n[2-C] 클라우드 VLM 화재 전조 진단 테스트:")
    print(f"      - Level: {risk_c['level']} ({risk_c['label']}) | Early Detection: {risk_c['is_early_detection']}")
    print(f"      - Details: {risk_c['details']}")
    if risk_c['level'] == 1 and risk_c['is_early_detection']:
        print("      ✅ 결과: 통과 (사전 위험 Level 1 주의 정상 발령)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 2-D. 레거시 bool 호환성 테스트 (vision_input=True) -> Level 2
    risk_d = calculate_risk_level(smoke_normal, gas_normal, temp_normal, fire_detected_by_camera=True)
    print(f"\n[2-D] 기존 레거시 파라미터(bool) 호환성 테스트:")
    print(f"      - Level: {risk_d['level']} ({risk_d['label']})")
    if risk_d['level'] == 2:
        print("      ✅ 결과: 통과 (100% 하위 호환성 유지)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    # 2-E. 복합 상황 (조기 감지 연기 + 천장 연기 센서 1개 초과) -> Level 4 격상
    smoke_triggered = 350 # 임계값 300 초과
    risk_e = calculate_risk_level(smoke_triggered, gas_normal, temp_normal, vision_early)
    print(f"\n[2-E] 복합 훈소 화재 확정 테스트 (센서 1개 + 비전 조기 연기):")
    print(f"      - Level: {risk_e['level']} ({risk_e['label']}) | Details: {risk_e['details']}")
    if risk_e['level'] == 4:
        print("      ✅ 결과: 통과 (Level 4 화재 긴급 격상 정상 동작)")
        passed += 1
    else:
        print("      ❌ 결과: 실패")

    print(f"\n>> 센서 퓨전 엔진 검증 결과: {passed}/{total} 통과")
    return passed == total


def test_fire_detector_model():
    print_header("3. YOLO 화재/연기 모델 로드 및 추론 테스트")
    if fire_detector.model is None:
        print("❌ 모델이 로드되지 않았습니다.")
        return False

    print(f"✅ 모델 인스턴스 확인: {type(fire_detector.model)}")

    # 더미 블랙 이미지로 파이프라인 안전성 검증
    dummy_path = os.path.join(ROOT_DIR, "vision", "captures", "test_dummy.jpg")
    os.makedirs(os.path.dirname(dummy_path), exist_ok=True)
    dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
    cv2.imwrite(dummy_path, dummy_img)

    try:
        res = fire_detector.detect_fire(dummy_path)
        print("✅ detect_fire() 추론 정상 수행 완료:")
        print(f"   - fire_detected: {res.get('fire_detected')}")
        print(f"   - confidence: {res.get('confidence')}")
        print(f"   - description: {res.get('description')}")
        return True
    finally:
        if os.path.exists(dummy_path):
            os.remove(dummy_path)


def test_vlm_analyzer():
    print_header("4. VLM 전조 진단 모듈 (VLMHazardAnalyzer) 테스트")
    analyzer = VLMHazardAnalyzer()
    sim_result = analyzer.simulate_hazard(hazard_type="UNATTENDED_HEATING")
    print("✅ VLM 시뮬레이션 진단 결과:")
    print(f"   - has_pre_hazard: {sim_result['has_pre_hazard']}")
    print(f"   - hazard_type: {sim_result['hazard_type']}")
    print(f"   - warning_message: {sim_result['warning_message']}")
    return sim_result['has_pre_hazard'] and sim_result['hazard_type'] == "UNATTENDED_HEATING"


if __name__ == "__main__":
    t1 = test_smoke_motion_analyzer()
    t2 = test_sensor_fusion()
    t3 = test_fire_detector_model()
    t4 = test_vlm_analyzer()

    print("\n" + "=" * 65)
    if t1 and t2 and t3 and t4:
        print("🎉 모든 단위/통합 테스트 전원 통과! (ALL TESTS PASSED) 🎉")
    else:
        print("⚠️ 일부 테스트 실패 발생")
    print("=" * 65 + "\n")
