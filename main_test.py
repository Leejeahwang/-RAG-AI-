from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
import os
import sys

from voice.tts import TTSHelper
from voice.stt import _load_model, listen_once, _get_pyaudio_instance, _open_stream

# ... (기존 DB 삭제 및 로딩 로직 유지) ...
# (중략된 부분은 동일하게 유지)

# 임베딩 및 벡터 DB 초기화 (Ollama qwen2.5:1.5b 모델 사용)
embeddings = OllamaEmbeddings(model="qwen2.5:1.5b")
db = Chroma(persist_directory="./chroma_db", embedding_function=embeddings) # 기존 DB 로드

llm = Ollama(model="qwen2.5:1.5b")
tts = TTSHelper()   # TTS 엔진 초기화

print("🎙️ 음성 인식 엔진을 준비 중입니다...")
stt_model = _load_model()  # STT 모델 미리 로드하여 지연 시간 단축
pa = _get_pyaudio_instance()
stt_stream = _open_stream(pa)

# 1. 엣지 세이버의 정체성을 부여하는 프롬프트 템플릿
template = """너는 통신이 끊긴 재난 현장에서 생명을 구하는 '엣지 세이버(Edge Saver)' AI 비서야.
반드시 제공된 [매뉴얼 내용]만을 바탕으로, '한국어'로 침착하고 명확하게 대답해.
매뉴얼에 없는 내용이라면 절대로 지어내지 말고 "해당 상황에 대한 매뉴얼이 없습니다. 구조대를 기다리십시오."라고 대답해.

[매뉴얼 내용]: {context}

질문: {question}
답변:"""

prompt = PromptTemplate(template=template, input_variables=["context", "question"])

# 2. QA 체인 구성 (검색기 연결)
qa = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={"k": 4}),
    chain_type_kwargs={"prompt": prompt}
)

print("\n" + "="*60)
print("🚑 엣지 세이버(Edge Saver)가 가동되었습니다.")
print("   - 키보드로 직접 질문하거나,")
print("   - [엔터]를 치면 음성 인식을 시작합니다 (호출어: '세이버')")
print("   - 종료하려면 '종료' 또는 'exit' 입력")
print("="*60 + "\n")

while True:
    try:
        query = input("❓ 질문 (텍스트 입력 또는 '엔터'로 음성 모드): ").strip()
        
        # 음성 인식 모드 진입 트리거 (빈 엔터 또는 특정 키워드)
        if query == "" or query.lower() in ['v', 'voice', '음성', 'mic']:
            print("\n🎤 음성 인식 모드입니다. 바로 말씀해 주세요.")
            query = listen_once(model=stt_model, pa=pa, stream=stt_stream, use_wake_word=False)
            
            if not query:
                print("⚠️ 음성이 인식되지 않았습니다. 다시 시도해 주세요.")
                continue
            print(f"🎤 인식된 질문: {query}")

        if query in ['종료', 'exit', 'quit']:
            print("👋 안전을 기원합니다. 시스템을 종료합니다.")
            break
            
        print("🔍 답변 생성 중...")
        # AI 답변 생성
        result = qa.invoke(query)
        response_text = result['result']
        print(f"\n🤖 AI 답변: {response_text}\n")
        print("-" * 30)
        
        # TTS 음성 출력 시 STT 스트림 잠시 중지 (장치 충돌 방지)
        if stt_stream and stt_stream.is_active():
            stt_stream.stop_stream()
            
        tts.speak(response_text)
        
        if stt_stream and not stt_stream.is_active():
            stt_stream.start_stream()
        
    except KeyboardInterrupt:
        print("\n👋 시스템을 종료합니다.")
        break
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")
    finally:
        # 루프가 끝나기 전 스트림이 닫히지 않도록 주의 (필요시 추가)
        pass

# 프로그램 종료 시 오디오 자원 해제
stt_stream.stop_stream()
stt_stream.close()
pa.terminate()
