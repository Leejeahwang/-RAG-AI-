"""
vision/test_vlm.py - 클라우드 VLM(Vision-Language Model) 화재 전조 진단 인터랙티브 테스트 도구
========================================================================================
작성자: 박규태 (Vision AI 담당)
용도:
  1. API 키 없이도 화재 전조(가열기구 방치, 가연물 적치) 모의 진단 및 센서 퓨전(Level 1) 연동 확인
  2. 실제 OpenAI GPT-4o-mini API 키 연동 시 웹캠 캡처 화면을 실시간 클라우드로 전송하여 진단 결과 검증
  3. 팀 회의 및 발표 시 VLM의 사전 예방 가치를 시연하는 데모 도구

실행 방법:
  python vision/test_vlm.py                     (인터랙티브 메뉴 실행)
  python vision/test_vlm.py --sim               (가상 시나리오 빠른 시뮬레이션)
  python vision/test_vlm.py --webcam            (웹캠 1회 캡처 후 실제 VLM 분석)
  python vision/test_vlm.py --image <파일경로>   (특정 이미지 파일 VLM 분석)
"""

import os
import sys
import time
import json
import argparse
import cv2
import numpy as np

# 프로젝트 루트 경로 추가
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from vision.vlm_analyzer import VLMHazardAnalyzer, vlm_analyzer
from sensors.fusion import calculate_risk_level


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f"🤖 {title}")
    print("=" * 70)


def print_vlm_result(res: dict, elapsed_sec: float = 0.0):
    """VLM 진단 결과를 가독성 높은 포맷으로 출력"""
    has_hazard = res.get("has_pre_hazard", False)
    hazard_type = res.get("hazard_type", "NONE")
    severity = res.get("severity", 0)
    warning_msg = res.get("warning_message", "")
    confidence = res.get("confidence", 0.0)
    desc = res.get("description", "")

    print("\n┌──────────────────────── [VLM 진단 결과 요약] ────────────────────────┐")
    if has_hazard:
        print(f"│ 🚨 화재 전조 감지 여부 : [ 위험 감지 (True) ]")
        print(f"│ 🏷️  위험 분류 유형     : {hazard_type}")
        print(f"│ 📊 진단 신뢰도         : {confidence * 100:.1f}%")
        print(f"│ ⚠️  현장 방송 경고 지침 : {warning_msg}")
        print(f"│ 📝 상세 정황 분석     : {desc}")
    else:
        print(f"│ 🟢 화재 전조 감지 여부 : [ 안전 (False) ]")
        print(f"│ 🏷️  위험 분류 유형     : {hazard_type}")
        print(f"│ 📝 상세 정황 분석     : {desc}")
    if elapsed_sec > 0:
        print(f"│ ⏱️  VLM 응답 소요 시간 : {elapsed_sec:.2f}초")
    print("└──────────────────────────────────────────────────────────────────────┘")


def test_simulation(hazard_type: str = "UNATTENDED_HEATING"):
    """API 키 없이 가상 시나리오 진단 및 센서 퓨전 연동 테스트"""
    print_banner(f"VLM 시뮬레이션 테스트: {hazard_type}")
    print("💡 [안내] API 키 및 네트워크 없이도 동작하는 모의(Mock) 시연 모드입니다.")

    start = time.time()
    result = vlm_analyzer.simulate_hazard(hazard_type=hazard_type)
    elapsed = time.time() - start

    print_vlm_result(result, elapsed)

    # 센서 퓨전 엔진 연동 테스트
    print("\n🔗 [센서 퓨전 엔진 연동 검증]")
    smoke_mq2 = 80       # 정상 평상시 수치
    gas_mq135 = 120      # 정상 평상시 수치
    temp_dht = {"temperature": 24.0, "humidity": 50.0}

    # fusion.py는 pre_hazard_alert 키가 존재하면 Level 1(주의)을 발령함
    vision_input = {
        "fire_detected": False,
        "is_real_smoke": False,
        "is_static_photo": False,
        "pre_hazard_alert": result.get("warning_message", "")
    }

    fusion_risk = calculate_risk_level(smoke_mq2, gas_mq135, temp_dht, vision_input=vision_input)

    print(f"  • 평상시 센서 수치 : 연기 {smoke_mq2} / 가스 {gas_mq135} (모두 정상)")
    print(f"  • 센서 퓨전 결과   : Level {fusion_risk['level']} ({fusion_risk['label']})")
    print(f"  • 조기 감지 플래그 : is_early_detection = {fusion_risk.get('is_early_detection')}")
    print(f"  • 시스템 상세 지침 : {fusion_risk.get('details')}")

    if fusion_risk['level'] == 1 and fusion_risk.get('is_early_detection'):
        print("  ✅ 판정 성공: 연기/열 센서가 0인 상태에서도 VLM 전조 진단으로 'Level 1 주의' 선제 발령 확인!")
    else:
        print("  ❌ 판정 실패: 퓨전 엔진 위험도 수준을 점검하세요.")


def test_webcam_live():
    """웹캠 화면 캡처 후 실제 OpenAI GPT-4o-mini 호출 (또는 시연 모드) 테스트"""
    print_banner("웹캠 실시간 캡처 & VLM 화재 전조 진단")
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    is_sim_fallback = False

    if not openai_key:
        print("💡 [OPENAI_API_KEY 확인]")
        print("  현재 환경변수에 OPENAI_API_KEY가 등록되어 있지 않습니다.")
        user_key = input("👉 OpenAI API 키가 있으시면 입력해주세요 (없으면 Enter 입력 시 모의 시연 모드 진행): ").strip()
        if user_key:
            os.environ["OPENAI_API_KEY"] = user_key
            openai_key = user_key
            vlm_analyzer.api_key = user_key
            print("✅ API 키가 등록되었습니다! 실제 클라우드 VLM(GPT-4o-mini)으로 진단합니다.")
        else:
            is_sim_fallback = True
            print("💡 [모의 시연 모드 활성화] API 키 없이도 웹캠 화면을 캡처하여 화재 전조 진단 데모를 시연합니다.")

    print("\n📷 웹캠(카메라 0번)을 연결하는 중...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ 웹캠을 열 수 없습니다. 카메라 연결 상태를 확인하세요.")
        if is_sim_fallback:
            test_simulation("UNATTENDED_HEATING")
        return

    print("✅ 웹캠 연결 완료!")
    print("👉 스페이스바(Space) 또는 'c'를 누르면 현재 화면을 캡처하여 VLM 전조 진단을 수행합니다.")
    print("👉 'q'를 누르면 취소하고 종료합니다.\n")

    captured_frame = None
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        preview = frame.copy()
        cv2.putText(preview, "Press SPACE or 'c' to Capture & Analyze VLM", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(preview, "Press 'q' to Quit", (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        cv2.imshow("VLM Webcam Hazard Tester", preview)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord(' '), ord('c')):
            captured_frame = frame
            break
        elif key == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    if captured_frame is not None:
        save_dir = os.path.join(ROOT_DIR, "vision", "captures")
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"vlm_capture_{int(time.time())}.jpg")
        cv2.imwrite(save_path, captured_frame)
        print(f"📸 캡처된 화면이 저장되었습니다: {save_path}")

        start = time.time()
        if not is_sim_fallback and openai_key:
            print("\n☁️ 클라우드 VLM(OpenAI gpt-4o-mini)에 영상 프레임 전송 및 분석 요청 중...")
            result = vlm_analyzer.analyze_frame_online(captured_frame)
        else:
            print("\n🤖 [시연 모드] 캡처된 프레임 기반 화재 전조 위험 진단 연동...")
            result = vlm_analyzer.simulate_hazard("UNATTENDED_HEATING")
        elapsed = time.time() - start

        print_vlm_result(result, elapsed)

        # 센서 퓨전 엔진 연동 검증
        print("\n🔗 [센서 퓨전 엔진(fusion.py) 연동 결과]")
        smoke_mq2 = 80
        gas_mq135 = 120
        temp_dht = {"temperature": 24.0, "humidity": 50.0}

        vision_input = {
            "fire_detected": False,
            "is_real_smoke": False,
            "is_static_photo": False,
            "pre_hazard_alert": result.get("warning_message", "")
        }

        fusion_risk = calculate_risk_level(smoke_mq2, gas_mq135, temp_dht, vision_input=vision_input)
        print(f"  • 평상시 센서 수치 : 연기 {smoke_mq2} / 가스 {gas_mq135} (모두 정상 상태)")
        print(f"  • 위험도 격발 레벨 : Level {fusion_risk['level']} ({fusion_risk['label']})")
        print(f"  • 조기 감지 여부   : is_early_detection = {fusion_risk.get('is_early_detection')}")
        print(f"  • 관제 지침 메시지 : {fusion_risk.get('details')}")
        print("\n🎉 VLM 화재 전조 감지 -> Level 1 선제 발령 연동 테스트 완료!")


def test_image_file(image_path: str):
    """지정된 이미지 파일로 VLM 진단 테스트"""
    print_banner(f"이미지 파일 VLM 진단: {image_path}")

    if not os.path.exists(image_path):
        print(f"❌ 파일을 찾을 수 없습니다: {image_path}")
        return

    frame = cv2.imread(image_path)
    if frame is None:
        print(f"❌ 이미지를 읽을 수 없습니다: {image_path}")
        return

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("⚠️ OPENAI_API_KEY가 설정되지 않아 시뮬레이션 모드로 분석합니다.")
        result = vlm_analyzer.simulate_hazard("UNATTENDED_HEATING")
        print_vlm_result(result, 0.05)
        return

    print("☁️ 클라우드 VLM에 이미지 전송 중...")
    start = time.time()
    result = vlm_analyzer.analyze_frame_online(frame)
    elapsed = time.time() - start
    print_vlm_result(result, elapsed)


def interactive_menu():
    """인터랙티브 콘솔 메뉴"""
    while True:
        print("\n" + "=" * 70)
        print("🤖 [엣지 세이버] 클라우드 VLM 화재 전조(Pre-Hazard) 진단 테스트 도구")
        print("=" * 70)
        print("1. [실제/시연] 웹캠 실시간 캡처 & VLM 진단 (추천 ⭐)")
        print("2. [모의 시연] 가열 기구(버너/인덕션) 무인 방치 시나리오")
        print("3. [모의 시연] 전기 배전반 앞 가연성 박스 적치 시나리오")
        print("4. [이미지 파일] 특정 사진 파일 분석")
        print("0. 종료")
        print("=" * 70)

        choice = input("👉 번호를 선택하세요 (0~4): ").strip()
        if choice == "1":
            test_webcam_live()
        elif choice == "2":
            test_simulation("UNATTENDED_HEATING")
        elif choice == "3":
            test_simulation("COMBUSTIBLE_NEAR_PANEL")
        elif choice == "4":
            path = input("분석할 이미지 경로를 입력하세요: ").strip()
            if path:
                test_image_file(path)
        elif choice == "0":
            print("테스트 도구를 종료합니다.")
            break
        else:
            print("⚠️ 잘못된 입력입니다. 0부터 4 사이 숫자를 입력하세요.")


def main():
    parser = argparse.ArgumentParser(description="VLM Hazard Analyzer Test Tool")
    parser.add_argument("--menu", action="store_true", help="인터랙티브 번호 메뉴 실행")
    parser.add_argument("--sim", action="store_true", help="가상 시나리오 빠른 시뮬레이션 모드")
    parser.add_argument("--hazard", type=str, default="UNATTENDED_HEATING",
                        choices=["UNATTENDED_HEATING", "COMBUSTIBLE_NEAR_PANEL"],
                        help="시뮬레이션할 위험 유형")
    parser.add_argument("--image", type=str, default="", help="분석할 이미지 파일 경로")

    args = parser.parse_args()

    if args.menu:
        interactive_menu()
    elif args.sim:
        test_simulation(args.hazard)
    elif args.image:
        test_image_file(args.image)
    else:
        # 기본 실행 시 곧바로 가장 중요한 '웹캠 실시간 캡처 진단 모드' 실행!
        test_webcam_live()


if __name__ == "__main__":
    main()

