🖥️ Edge Saver 통합 관제 대시보드 (Dashboard)
본 모듈은 Edge Saver 프로젝트의 프론트엔드이자 통합 제어 시스템으로, 라즈베리파이 5 환경에서 실시간 데이터 시각화 및 지능형 AI 대응을 총괄하는 지능형 관제 플랫폼입니다. 단순한 모니터링을 넘어, 센서 데이터와 비전 분석을 결합한 위험 판단 및 RAG(검색 증강 생성) 기반의 음성 가이드를 실시간으로 제공합니다.

📐 인터페이스 레이아웃 (Interface Layout)
사용자 편의성과 긴급 상황 시 정보 인지 속도를 극대화하기 위해 2.1:1 분할 레이아웃을 적용했습니다.

상단 헤더 (Header): 시스템 타이틀과 함께 오작동 방지 로직이 적용된 전원 종료(⏻) 버튼 배치.

좌측 메인 패널 (Main Monitor):

CCTV Stream: 실시간 영상 출력 및 YOLOv8 기반 화재 탐지 결과 시각화.

Voice Control: 음성 브리핑 활성화 토글 및 실시간 상태 표시.

Tactical Feed: 시스템의 가동 상태와 AI 판단 근거를 타임스탬프와 함께 출력하는 실시간 전술 로그.

우측 사이드바 (Data Intelligence):

Sensor Metrics: 온도(°C), 가스 농도, 연기 농도를 3열 메트릭으로 정밀 표시.

Risk Gauge: fusion.py 연산 결과(Level 1~5)를 위험도에 따라 색상이 변하는 수평형 프로그레스 바로 시각화.

AI Command Center: RAG 엔진이 생성한 대응 지침을 상시 노출하고 음성 답변을 텍스트로 병행 출력.

🚨 핵심 전술 로직 (Core Tactical Logic)
1. 비동기 멀티스레딩 아키텍처 (Parallel Processing)
관제 연속성을 보장하기 위해 병렬 처리 기술을 적용했습니다.

Background Workers: CCTV 영상 수집과 STT(음성 인식) 엔진을 각각 별도의 스레드로 운영하여, AI와 교신하는 중에도 감시 화면과 센서 데이터가 멈추지 않는 무중단 관제를 실현했습니다.

Queue-based Communication: 백그라운드에서 인식된 음성 데이터를 큐(Queue)를 통해 메인 루프에 전달하여 자원 충돌을 방지합니다.

2. 다국어 지능형 음성 인터페이스 (Multilingual AI)
언어 자동 판별: 정규표현식 기반의 언어 감지 로직을 통해 한국어, 일본어, 영어, 중국어를 실시간으로 구분하여 사용자 언어에 최적화된 답변을 제공합니다.


3. 선제적 대응 및 세이프 가드 (Proactive Safety)
Emergency Auto-Pilot: 위험 단계 LV.4 이상 또는 화재 감지 시, AI가 즉시 RAG 엔진을 가동하여 **비상 피난 방송(TTS)과 외부 알림(Notifier)**을 선제적으로 실행합니다.
