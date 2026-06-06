import cv2
import os
import time
from vision.fire_detector import model, CONFIDENCE_THRESHOLD

def debug_vision_system():
    print("=====================================================")
    print("🔍 엣지 세이버 - 비전 감지 긴급 진단 스크립트 시작")
    print("=====================================================")
    
    if model is None:
        print("❌ [에러] YOLOv8 화재 모델이 로드되지 않았습니다. 모델 파일을 확인하세요.")
        return
        
    print(f"📌 현재 활성화된 모델: {model.ckpt_path if hasattr(model, 'ckpt_path') else 'Unknown'}")
    print(f"📌 감지 임계값(Confidence Threshold): {CONFIDENCE_THRESHOLD * 100:.1f}%")
    
    # 1. 카메라 장치 연결 시도
    print("\n[1단계] 카메라 연결 상태를 진단합니다...")
    # GStreamer 우선 시도
    gst_pipeline = "libcamerasrc ! video/x-raw, width=640, height=480, format=RGB ! videoconvert ! appsink drop=true"
    cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
    
    if not cap.isOpened():
        print("ℹ️ GStreamer 시도 실패. V4L2 드라이버로 폴백 시도합니다.")
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        if cap.isOpened():
            # [Broken pipe 방지] 라즈베리파이 V4L2 compat layer는 set 해상도 변경 시 통신선이 터지므로 속성 설정 없이 오픈
            pass
            
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
        
    if not cap.isOpened():
        print("❌ [에러] 라즈베리파이에 연결된 물리 카메라 장치를 열 수 없습니다.")
        print("💡 팁: 케이블 접촉 상태나 'rpicam-hello --list-cameras' 결과를 재점검하십시오.")
        return
        
    print("✅ 카메라 연결 성공!")
    
    # 2. 테스트 캡처 및 저장
    print("\n[2단계] 테스트 샷을 촬영하여 디스크에 저장합니다...")
    time.sleep(2.0) # 카메라 밝기 조절 대기
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        print("❌ [에러] 카메라 렌즈로부터 프레임(이미지) 데이터를 가져오지 못했습니다.")
        return
        
    test_img_path = "debug_capture.jpg"
    cv2.imwrite(test_img_path, frame)
    print(f"✅ 사진 촬영 완료 및 저장 완료 -> [ {test_img_path} ]")
    print("💡 팁: 이 이미지를 열어서 현재 초점이 뿌옇게 나갔는지, 불꽃이 선명하게 보이는지 확인해 보십시오.")
    
    # 3. YOLOv8 생 분석 (silence 해제 상태로 실행하여 라이브러리 디버그 로그 출력)
    print("\n[3단계] YOLOv8 모델 분석을 라이브러리 로그 생출력 모드로 실행합니다...")
    print("-----------------------------------------------------")
    
    # verbose=True로 설정하여 YOLOv8이 무엇을 감지하고 있는지 실시간 분석 텍스트 출력
    results = model.predict(source=test_img_path, conf=CONFIDENCE_THRESHOLD, save=True, verbose=True)
    
    print("-----------------------------------------------------")
    if len(results) == 0:
        print("ℹ️ 모델 분석 결과 빈 값이 리턴되었습니다.")
        return
        
    result = results[0]
    boxes = result.boxes
    
    if len(boxes) == 0:
        print("ℹ️ 감지된 객체(불꽃/연기)가 없습니다. (안전 상태)")
        print("💡 분석 팁: 만약 불을 비추었는데도 감지가 안 된다면,")
        print("   YOLOv8이 캡처한 이미지(debug_capture.jpg)에서 물체 초점이 아예 나갔을 확률이 높습니다.")
    else:
        print(f"🔥 감지 성공! 총 {len(boxes)}개의 위험 요소 발견:")
        names = result.names
        for idx, box in enumerate(boxes):
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = names[cls_id].upper()
            print(f"   - [{idx+1}] 종류: {cls_name} | AI 확신도: {conf*100:.1f}%")
            
        # 바운딩 박스가 쳐진 결과 이미지도 확인 가능 (runs/detect/predict/ 디렉토리)
        print("\n🎉 박스가 그려진 최종 분석본 이미지가 runs/detect/predict/ 디렉토리 내에 저장되었습니다.")

if __name__ == "__main__":
    debug_vision_system()
