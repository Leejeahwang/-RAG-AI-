# 📓 Vision AI 개발 일지 (박규태)

이 문서는 엣지 세이버의 **Vision AI 모듈(`vision/camera.py` 등)**을 개발하면서 발생한 진행 상황, 문제점, 그리고 해결 방법을 매일 기록하는 용도입니다. 
(이 내용들이 쌓이면 주간 보고서 작성 시 그대로 복사해서 붙여넣을 수 있습니다.)

---

## 📅 2026-03-24

### 🚀 진행 내용
- `main` 환경 보호를 위해 나만의 독립적인 개발 공간(`dev_park` 브랜치) 개설
- 단일 스크립트(`rag_test.py`)로 짜여있던 코드를 협업이 가능하도록 전면 모듈화 (설정, RAG, Vision, Voice, GUI 등 폴더 분리)
- 내가 개발할 **Vision AI 모듈**(`vision/camera.py`)의 기본 구조(스켈레톤) 구성
- 가상 사진 입력을 통해 Vision AI 모조 분석 후 → RAG 서버 답변이 나오는 E2E 파이프라인(`test.py`) 자동화 및 정상 동작 확인

### 💥 발생한 문제 (Issue)
1. `test.py` 실행 타임에 패키지 누락(`ModuleNotFoundError: No module named 'langchain_community'`) 발생
2. Windows 환경 터미널에서 한국어와 특수문자(이모지)를 출력하다가 `cp949 UnicodeEncodeError` 앱 튕김 현상 발생
3. 지정한 AI 모델(`qwen2.5:1.5b`)이 로컬 환경에 없어 `ConnectionError / 404` 뱉음

### 💡 해결 및 배운 점 (Solution/TIL)
- `pip install langchain langchain-community langchain-core...` 등으로 필수 패키지들을 모두 설치 완료
- 스크립트 실행 전 Windows 환경 변수에 `$env:PYTHONIOENCODING="utf-8"`을 할당해주어 강제로 utf-8로 인코딩하도록 처리하여 에러 해결
- `ollama` CLI가 시스템 환경변수(PATH)에 잡혀있지 않았으나, 백그라운드 API를 직접 호출하여 모델(qwen2.5) 다운로드 해결

--- 

## 📅 [어제 날짜]
### 🚀 진행 내용
- ...

---
*(새로운 날이 시작될 때마다 위에 템플릿을 복사해서 맨 위에 계속 추가해 주세요!)*
