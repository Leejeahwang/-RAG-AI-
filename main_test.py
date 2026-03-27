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

# 기존 DB가 있다면 삭제하여 데이터 업데이트 반영 (필요시 비활성화)
if os.path.exists("./chroma_db"):
    import shutil
    shutil.rmtree("./chroma_db")

print("📦 재난 안전 매뉴얼 데이터를 분석 중입니다...")
# 매뉴얼 데이터 폴더 경로 (중앙 관리되는 data/raw_documents 사용)
data_dir = "data/raw_documents"
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
    print(f"⚠️ {data_dir} 폴더에 매뉴얼 파일(.txt)이 없습니다. 전처리(rag/crawler.py)를 먼저 수행하세요.")
    sys.exit(1)

# 폴더 내 모든 .txt 파일 로드
loader = DirectoryLoader(data_dir, glob="**/*.txt", loader_cls=TextLoader, loader_kwargs={"encoding": "utf-8"})
docs = loader.load()

if not docs:
    print(f"⚠️ {data_dir} 폴더에 로드할 수 있는 텍스트 문서가 없습니다.")
    sys.exit(1)

# 텍스트 분할 (청크 크기 200, 중첩 30)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=30)
chunks = text_splitter.split_documents(docs)

# 임베딩 및 벡터 DB 초기화 (Ollama qwen2.5:1.5b 모델 사용)
embeddings = OllamaEmbeddings(model="qwen2.5:1.5b")
db = Chroma.from_documents(chunks, embeddings, persist_directory="./chroma_db")

llm = Ollama(model="qwen2.5:1.5b")
tts = TTSHelper()  # TTS 엔진 초기화

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

print("\n" + "="*50)
print("🚑 엣지 세이버(Edge Saver)가 가동되었습니다.")
print("   질문을 입력하세요. (종료하려면 '종료' 또는 'exit' 입력)")
print("="*50 + "\n")

while True:
    try:
        query = input("❓ 질문: ").strip()
        
        if query in ['종료', 'exit', 'quit']:
            print("👋 안전을 기원합니다. 시스템을 종료합니다.")
            break
            
        if not query:
            continue

        print("🔍 답변 생성 중...")
        # AI 답변 생성
        result = qa.invoke(query)
        response_text = result['result']
        print(f"\n🤖 AI 답변: {response_text}\n")
        print("-" * 30)
        
        # TTS 음성 출력
        tts.speak(response_text)
        
    except KeyboardInterrupt:
        print("\n👋 시스템을 종료합니다.")
        break
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")
