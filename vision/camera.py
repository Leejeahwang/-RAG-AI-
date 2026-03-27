"""
카메라 캡처 모듈 (규태님 담당)

Phase 1 작업 내용:
- OpenCV로 웹캠/카메라 프레임 캡처
- 프레임 선택 전략 (키 입력: 'c' 또는 'Space')
- 이미지 전처리 (리사이즈, 압축)
- Vision → RAG 파이프라인 연결
"""

import cv2
import os
import datetime

# 캡처된 이미지를 저장할 기본 폴더 (vision/captures/)
DEFAULT_SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")

def capture_frame(save_dir=DEFAULT_SAVE_DIR):
    """
    카메라에서 실시간 프레임을 받아 화면에 띄웁니다.
    사용자가 캡처 버튼('c' 또는 스페이스바)을 누르면 프레임을 저장(리사이즈 포함)하고 경로를 반환합니다.

    Args:
        save_dir: 캡처된 이미지를 저장할 디렉토리 경로

    Returns:
        str: 저장된 이미지의 파일 경로 또는 캡처 취소 시 None
    """
    # 저장 디렉토리가 없으면 자동 생성
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"📁 캡처 폴더를 생성했습니다: {save_dir}")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ 카메라를 열 수 없습니다. 카메라가 연결되어 있는지 확인해 주세요.")
        return None

    print("\n" + "="*50)
    print("📷 [Vision AI] 카메라가 켜졌습니다.")
    print("   👉 캡처하려면 'c' 키 또는 '스페이스바'를 누르세요.")
    print("   👉 캡처하지 않고 취소하려면 'q'를 누르세요.")
    print(f"   📥 저장 위치: {save_dir}")
    print("="*50 + "\n")

    captured_file = None

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ 카메라 프레임을 읽어오는 데 실패했습니다.")
            break

        # 좌우 반전(옵션) 후 화면에 출력
        display_frame = cv2.flip(frame, 1)
        cv2.imshow("Edge Saver Camera - Press 'c' to capture", display_frame)

        key = cv2.waitKey(1) & 0xFF

        # 종료 (q)
        if key == ord('q'):
            print("🚫 캡처를 취소합니다.")
            break

        # 캡처 (c 또는 스페이스바)
        elif key == ord('c') or key == 32:
            print("📸 찰칵! 프레임을 캡처했습니다.")
            
            # 현재 시간을 파일명으로 사용 (예: capture_20260328_143000.jpg)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp}.jpg"
            output_path = os.path.join(save_dir, filename)

            # 원본 프레임 사용 (화면 출력만 반전시켰음)
            # LLM 처리 속도를 높이기 위해 최대 너비 640px로 리사이즈
            h, w = frame.shape[:2]
            target_w = 640
            target_h = int(h * (target_w / w))
            resized_frame = cv2.resize(frame, (target_w, target_h))

            cv2.imwrite(output_path, resized_frame)
            captured_file = output_path
            break

    cap.release()
    cv2.destroyAllWindows()

    return captured_file

if __name__ == "__main__":
    result = capture_frame()
    if result:
        print(f"✅ 캡처 성공! 저장 위치: {result}")
        
        # 캡처 직후 AI 모델 테스트 연동
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from fire_detector import detect_fire
        
        analysis = detect_fire(result)
        print("\n" + "="*50)
        print("🔥 [화재 감지 분석 결과]")
        print(f"- 화재 발견 여부: {analysis['fire_detected']}")
        print(f"- AI 신뢰도:      {analysis['confidence']}")
        print(f"- 상세 내역:      {analysis['description']}")
        print("="*50 + "\n")

