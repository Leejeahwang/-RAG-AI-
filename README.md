# 🚑 로컬 RAG 기반 재난 대피 및 응급처치 AI 비서

> **프로젝트**
> 아두이노 센서와 라즈베리파이를 연동하여, 재난 상황(화재, 지진 등) 발생 시 사용자의 텍스트 및 음성 질문을 인식하고 오프라인 상태에서도 로컬 LLM을 통해 최적의 대피로와 응급처치 방법을 안내하는 시스템입니다.

---

## 🚀 프로젝트 소개

이 프로젝트는 인터넷 연결이 불안정한 재난 상황에서도 작동하는 **오프라인 AI 비서**의 프로토타입입니다. 백화점 매뉴얼과 공신력 있는 응급처치 가이드라인을 데이터베이스화하여, 사용자의 질문에 가장 정확하고 안전한 정보를 실시간으로 제공하는 것을 목표로 합니다.

**핵심 기능:**
- **Local RAG (검색 증강 생성):** 신뢰할 수 있는 매뉴얼 데이터에 기반한 답변 생성 (환각 현상 방지).
- **한국어 특화 로컬 LLM:** 작은 용량 대비 한국어 성능이 뛰어난 Qwen 2.5 (1.5B) 모델 활용.
- **다국어 및 고정 답변:** 연속 대화가 가능한 챗봇 모드 및 시스템 프롬프트를 통한 한국어 전용 답변 구현.

---

## 🛠️ 설치 및 실행 방법 (Windows 기준)

이 프로젝트를 윈도우 로컬 환경에서 구동하기 위한 단계별 가이드입니다. 

### **1. 필수 프로그램 설치**

먼저 컴퓨터에 아래 프로그램들이 설치되어 있어야 합니다.
1. **Python (3.11 이상 권장)**
2. **Miniconda** (가상환경 관리): [Miniconda 다운로드](https://docs.conda.io/en/latest/miniconda.html)
3. **Ollama** (로컬 LLM 구동 엔진): [Ollama 다운로드](https://ollama.com)

### **2. 프로젝트 로드 및 가상환경 세팅**

윈도우 검색창에서 **'Anaconda Prompt'**를 실행한 뒤, 아래 명령어들을 순서대로 입력하세요.

```cmd
# 프로젝트 폴더로 이동 (바탕화면에 폴더가 있는 경우)
cd Desktop\disaster-ai

# 1. 전용 가상환경 생성 (이름: disaster_env)
conda create -n disaster_env python=3.11 -y

# 2. 가상환경 활성화
conda activate disaster_env
# (프롬프트 맨 앞이 (disaster_env)로 바뀌었는지 확인하세요.)

# 3. 필수 파이썬 패키지 설치
pip install langchain langchain-community langchain-core chromadb pypdf ollama langchain-classic

### **3. 한국어 특화 AI 모델 다운로드 (Qwen 2.5 적용)
# AI 모델 다운로드
ollama pull qwen2.5:1.5b

### **4. 실행 및 대화
# 가상환경 (disaster_env)이 켜져있는 상태에서
python rag_test.py
```

---

## 📂 프로젝트 구조
```text
disaster-ai/
├── rag_test.py          # [핵심] 대화형 RAG 챗봇 실행 파이썬 스크립트
├── mall_guide_ko.txt    # AI 지식 데이터베이스 (백화점 대피로 & 응급처치 매뉴얼)
├── .gitignore           # 깃허브 업로드 제외 목록 (가상환경, 벡터DB 등)
└── README.md            # [현재 파일] 프로젝트 설명서
```

