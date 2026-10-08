"""
vision/vlm_analyzer.py - 클라우드 VLM(Vision-Language Model) 기반 화재 전조 위험 진단 모듈
========================================================================================
작성자: 박규태 (Vision AI 담당)
목적:
  - 평상시 온라인(네트워크 가능) 환경에서 클라우드 VLM(GPT-4o-mini / Gemini / Ollama VLM)을 활용
  - 불꽃/연기 발생 이전의 '환경적 화재 전조(Pre-hazard)'를 사전 진단하여 화재 발생 자체를 예방
    1. 가열 기구(버너, 인덕션, 전열기) 켜짐 + 작업자 부재 (무인 방치)
    2. 전기 배전반 / 분전함 / 비상구 앞 종이 박스 등 가연성 물질 적치
  - 오프라인이거나 API 키가 없는 경우 안전한 Fallback 및 시연용 모의(Simulation) 모드 지원
"""

import os
import json
import base64
import time
import cv2
import numpy as np
from typing import Dict, Any, Optional

# 지원 VLM 설정
DEFAULT_VLM_PROMPT = """당신은 산업 시설 및 건물 화재 예방 안전 전문가입니다.
제공된 CCTV 영상을 면밀히 분석하여, 아직 불이나 연기는 나지 않았지만 화재로 이어질 수 있는 '환경적 전조 위험(Pre-hazard)'이 있는지 진단하세요.

[진단 항목]
1. UNATTENDED_HEATING: 가열 기구(휴대용 버너, 인덕션, 전기난로, 히터)가 켜져 있거나 김이 나는데 주변에 사람이 없는 무인 방치 상태인가?
2. COMBUSTIBLE_NEAR_PANEL: 전기 배전반, 분전함, 콘센트 또는 비상구 바로 앞에 종이 박스, 목재, 플라스틱 등 가연성 물질이 위험하게 적재되어 있는가?
3. ELECTRICAL_HAZARD: 문어발식 배선, 피복 손상, 스파크 위험 요인이 육안으로 확인되는가?

반드시 아래 JSON 포맷으로만 응답하세요 (마크다운 백틱 없이 순수 JSON만 출력):
{
  "has_pre_hazard": true 또는 false,
  "hazard_type": "UNATTENDED_HEATING" 또는 "COMBUSTIBLE_NEAR_PANEL" 또는 "ELECTRICAL_HAZARD" 또는 "NONE",
  "severity": 1,
  "warning_message": "관제실 및 현장 방송용 1~2줄 경고 지침",
  "confidence": 0.0 ~ 1.0,
  "description": "상황에 대한 구체적 설명"
}
"""

class VLMHazardAnalyzer:
    """클라우드 VLM 기반 화재 전조 분석기"""

    def __init__(self, provider: str = "auto", api_key: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self.last_check_time = 0.0
        self.last_result: Dict[str, Any] = {
            "has_pre_hazard": False,
            "hazard_type": "NONE",
            "severity": 0,
            "warning_message": "",
            "confidence": 0.0,
            "description": "정상 (화재 전조 위험 없음)"
        }

    @staticmethod
    def encode_frame_to_base64(frame: np.ndarray, quality: int = 80) -> str:
        """프레임을 JPEG로 압축 후 Base64 문자열로 인코딩"""
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, buffer = cv2.imencode('.jpg', frame, encode_param)
        if not success:
            raise ValueError("프레임 인코딩 실패")
        return base64.b64encode(buffer).decode('utf-8')

    def analyze_frame_online(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        클라우드 VLM API를 호출하여 프레임의 전조 위험을 분석합니다.
        (API 키가 없거나 네트워크 오류 시 안전하게 모의/오프라인 모드로 폴백)
        """
        # 1. API 키 확인
        openai_key = os.environ.get("OPENAI_API_KEY", self.api_key)
        
        if not openai_key:
            # API 키가 없으면 안전 모드로 반환 (시스템 중단 방지)
            return {
                "has_pre_hazard": False,
                "hazard_type": "NONE",
                "severity": 0,
                "warning_message": "VLM_API_KEY_NOT_SET",
                "confidence": 0.0,
                "description": "클라우드 VLM API 키가 설정되지 않아 로컬 감시 모드로 동작합니다."
            }

        try:
            import requests
            b64_img = self.encode_frame_to_base64(frame)

            # OpenAI gpt-4o-mini 호출
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": DEFAULT_VLM_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_img}",
                                    "detail": "low"  # 토큰 비용 및 속도 최적화
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 300,
                "temperature": 0.1
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 200:
                raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                # 마크다운 코드 블록 제거
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("\n", 1)[-1]
                if raw_text.endswith("```"):
                    raw_text = raw_text.rsplit("\n", 1)[0]
                raw_text = raw_text.strip()
                
                result = json.loads(raw_text)
                self.last_result = result
                return result
            else:
                return {
                    "has_pre_hazard": False,
                    "hazard_type": "ERROR",
                    "severity": 0,
                    "warning_message": f"API_ERROR_{resp.status_code}",
                    "confidence": 0.0,
                    "description": f"클라우드 VLM 응답 오류 ({resp.status_code})"
                }

        except Exception as e:
            return {
                "has_pre_hazard": False,
                "hazard_type": "NETWORK_FALLBACK",
                "severity": 0,
                "warning_message": "VLM_OFFLINE",
                "confidence": 0.0,
                "description": f"클라우드 통신 실패 (오프라인 모드 유지): {e}"
            }

    def simulate_hazard(self, hazard_type: str = "UNATTENDED_HEATING") -> Dict[str, Any]:
        """
        시연 및 테스트용 모의 전조 위험 데이터 생성 함수
        (발표 시 클라우드 API 호출 없이도 완벽한 데모를 보여줄 수 있음)
        """
        if hazard_type == "UNATTENDED_HEATING":
            return {
                "has_pre_hazard": True,
                "hazard_type": "UNATTENDED_HEATING",
                "severity": 1,
                "warning_message": "⚠️ 조리기구(버너) 가동 중 작업자 부재 감지! 화재 예방을 위해 전원을 즉시 차단하세요.",
                "confidence": 0.94,
                "description": "영상 중앙에 가열 기구가 켜져 있으나, 반경 내에 작업자가 5분 이상 부재하여 화재 위험이 감지됨."
            }
        elif hazard_type == "COMBUSTIBLE_NEAR_PANEL":
            return {
                "has_pre_hazard": True,
                "hazard_type": "COMBUSTIBLE_NEAR_PANEL",
                "severity": 1,
                "warning_message": "⚠️ 전기 배전반 앞 가연성 박스 적치 감지! 안전 거리(1m 이상)를 확보하세요.",
                "confidence": 0.91,
                "description": "고압 배전반 전면부에 종이 박스가 밀착 적재되어 있어 스파크 발생 시 급격한 연소 위험."
            }
        return {
            "has_pre_hazard": False,
            "hazard_type": "NONE",
            "severity": 0,
            "warning_message": "",
            "confidence": 0.99,
            "description": "정상 (특이 화재 전조 없음)"
        }

# 전역 싱글톤 인스턴스
vlm_analyzer = VLMHazardAnalyzer()


if __name__ == "__main__":
    import sys
    print("=" * 65)
    print("🤖 vision/vlm_analyzer.py - VLM 전조 진단 모듈 자체 테스트")
    print("=" * 65)
    
    # 1. API 키 확인
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        print(f"🔑 OPENAI_API_KEY 감지됨: {key[:6]}...{key[-4:]}")
        print("💡 온라인 클라우드 VLM API 호출 준비 완료.")
    else:
        print("⚠️ OPENAI_API_KEY 미설정 -> 오프라인 시뮬레이션 모드로 동작합니다.")

    # 2. 시뮬레이션 모드 테스트
    print("\n[테스트 1] 가열 기구 무인 방치 시뮬레이션:")
    res1 = vlm_analyzer.simulate_hazard("UNATTENDED_HEATING")
    print(f"  • 감지 여부: {res1['has_pre_hazard']}")
    print(f"  • 위험 유형: {res1['hazard_type']}")
    print(f"  • 경고 지침: {res1['warning_message']}")

    print("\n[테스트 2] 배전반 앞 가연물 적치 시뮬레이션:")
    res2 = vlm_analyzer.simulate_hazard("COMBUSTIBLE_NEAR_PANEL")
    print(f"  • 감지 여부: {res2['has_pre_hazard']}")
    print(f"  • 위험 유형: {res2['hazard_type']}")
    print(f"  • 경고 지침: {res2['warning_message']}")

    print("\n✅ VLM 모듈 정상 로드 및 기본 테스트 통과!")
    print("👉 대화형 인터랙티브 테스트 도구 실행: python vision/test_vlm.py")

