import sys
import os
import time

# Ensure package paths are correct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import EdgeSaver
from sensors import fusion
import config

class MockTTSHelper:
    def warmup(self):
        print("    [Mock TTS] 예열 완료")
    def speak(self, text, lang='ko', speed=None):
        print(f"🔊 [Mock TTS 발화] (배속: {speed if speed else 1.0}) >> {text}")
    def speak_async(self, text, lang='ko', speed=None):
        self.speak(text, lang, speed)
    def stop(self):
        pass

class TestEdgeSaver(EdgeSaver):
    def __init__(self, mock_zone_char):
        # Bypassing the Win32 Console Screen Buffer headless error of prompt_toolkit
        self.main_llm = None
        self._initialized = False
        self._monitor_running = False
        self._monitor_thread = None
        self._tts = MockTTSHelper()  # Inject headless Mock TTS to bypass pyttsx3/SAPI5 COM deadlock
        self._stt_model = None
        self._pa = None
        self._stt_stream = None
        self.session = None  # Mock session for headless run
        self.current_risk_stats = "시스템 초기화 중..."
        self.current_level = 0
        self.mock_zone_char = mock_zone_char.upper()
        
    @property
    def tts(self):
        return self._tts
        
    def _trigger_rag_alert_with_zone(self, prompt, sensor_info, zone_name):
        print("\n" + "!" * 55)
        print(f"🚨 [긴급 개입] AI가 {zone_name} 현장 상황을 분석하여 대응 지시를 내립니다.")
        print("!" * 55)
        
        try:
            self.tts.stop()
            from rag.chain import call_ollama_native, SYSTEM_PROMPT
            from rag.native_retriever import rag_manager
            
            # FAISS 검색 수행
            source_docs = rag_manager.search(prompt)
            
            # 검색 문서 출력 (검증용)
            print(f"\n[RAG 검색 성공] 총 {len(source_docs)}개의 관련 문서를 탐색했습니다.")
            for doc in source_docs[:2]:
                print(f" - 출처: {doc.get('source')} (위치: {doc.get('title')})")
            
            zone_chunks = []
            general_chunks = []
            seen_sources = set()  # 소스 파일 중복 방지 필터
            
            for doc in source_docs:
                src = doc.get('source', '')
                if not src: continue
                if src in seen_sources: continue
                seen_sources.add(src)
                
                src_lower = src.lower()
                content = doc.get('page_content', '')
                
                # 메타데이터 헤더 삭제
                lines = content.split('\n')
                clean_lines = [l for l in lines if '[위치:' not in l and '[출처:' not in l and not l.strip().startswith(('###', '---'))]
                cleaned_content = "\n".join(clean_lines).strip()
                if not cleaned_content: continue
                
                if 'layout' in src_lower or 'zone_' in src_lower:
                    zone_chunks.append(cleaned_content)
                else:
                    general_chunks.append(cleaned_content)
                    
            zone_context_text = "\n\n".join(zone_chunks) if zone_chunks else "해당 구역의 고유 대피 정보가 매뉴얼에 없습니다."
            general_context_text = "\n\n".join(general_chunks) if general_chunks else "일반 소방 수칙 정보가 없습니다."
            
            formatted_prompt = SYSTEM_PROMPT.format(zone_context=zone_context_text, general_context=general_context_text, question=prompt)
            
            print("\n" + "#" * 55)
            print("[DEBUG - LLM에 전달된 최종 프롬프트]")
            print(formatted_prompt)
            print("#" * 55 + "\n")
            
            print("\n[AI 분석 대피 가이드 로딩 및 스트리밍 중...]")
            print("=" * 55)
            print("🔊 [AI 긴급 피난 안내]")
            print("-" * 55)
            
            ai_response = ""
            for token in call_ollama_native(formatted_prompt):
                print(token, end="", flush=True)
                ai_response += token
            print("\n" + "=" * 55 + "\n")
            
            from alerts.notifier import send_alert
            send_alert(zone=zone_name, risk_level=self.current_level, sensor_details=sensor_info, ai_guidance=ai_response)
            
            print("\n[TTS 음성 송출 중] (속도 가속 모드)...")
            speed = 1.0
            if self.current_level >= 5: speed = 1.3
            elif self.current_level >= 4: speed = 1.2
            self.tts.speak_async(f"비상 상황 발생! {ai_response}", lang='ko', speed=speed)
            
            # 음성 출력이 완료되거나 충분히 들릴 때까지 잠시 대기
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ 긴급 RAG 생성 오류: {e}")

    def run_mock_alert(self):
        # 1. Initialize RAG and TTS
        self.initialize()
        
        # 2. Determine Zone parameter
        zone_map = {
            'A': ("A구역 (화학물질 보관소 및 배터리 충전실)", 350, 150, 65, True), # smoke high, gas normal, temp high, cam True -> Level 5 (Disaster)
            'B': ("B구역 (기계조립실 및 일반 프레스 가공실)", 120, 450, 25, True), # smoke normal, gas high, temp normal, cam True -> Level 4 (Urgent)
            'C': ("C구역 (직원 휴게실 및 식당)", 150, 120, 70, True)             # smoke normal, gas normal, temp high, cam True -> Level 4 (Urgent)
        }
        
        zone_name, smoke, gas, temp, cam_fire = zone_map.get(self.mock_zone_char, zone_map['A'])
        temp_data = {"temperature": temp, "humidity": 45.0}
        
        # 3. Calculate Risk Level using Fusion
        risk = fusion.calculate_risk_level(smoke, gas, temp_data, cam_fire)
        level = risk['level']
        self.current_level = level
        
        print(f"\n[테스트 실행] 구역: {zone_name} | 위험 레벨: {level} ({risk['label']})")
        print(f"[센서 수치] 연기 MQ-2: {smoke} | 가스 MQ-135: {gas} | 온도 DHT22: {temp}°C | 카메라 불꽃: {cam_fire}")
        
        from alerts.alarm import trigger_alarm
        trigger_alarm(level, risk['details'])
        
        # 4. Generate query with zone context (Extremely simplified to prevent LLM parroting)
        prompt = f"🚨 긴급 상황: {zone_name} 화재 발생! 다른 행동 지침이나 인사말은 전부 배제하고, 반드시 {zone_name}의 '대피로' 문장을 가장 첫 문장에 최우선 출력할 것. 그 후 소화기 위치를 아주 짧게 한 줄 덧붙일 것."
        
        # 5. Trigger the warning flow
        self._trigger_rag_alert_with_zone(prompt, risk['details'], zone_name)

if __name__ == "__main__":
    print("=" * 55)
    print("🔥 엣지 세이버 - 구역별 4/5단계 긴급 대피 테스트 실행기 🔥")
    print("=" * 55)
    
    # Check command line argument
    import sys
    if len(sys.argv) > 1:
        choice = sys.argv[1].upper()
    else:
        print("테스트할 구역을 선택해 주세요:")
        print("  - A : A구역 (화학물질 보관소 및 배터리 충전실 - 5단계 재난)")
        print("  - B : B구역 (기계조립실 및 일반 프레스 가공실 - 4단계 긴급)")
        print("  - C : C구역 (직원 휴게실 및 식당 - 4단계 긴급)")
        choice = input("\n선택 (A/B/C) [기본값 A]: ").strip().upper()
        if not choice:
            choice = 'A'
            
    if choice not in ['A', 'B', 'C']:
        print(f"❌ 올바르지 않은 구역 선택 '{choice}' 입니다. A구역으로 자동 지정합니다.")
        choice = 'A'
        
    tester = TestEdgeSaver(mock_zone_char=choice)
    try:
        tester.run_mock_alert()
    finally:
        tester.cleanup()
