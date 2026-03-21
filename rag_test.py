from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
import os

# 기존 DB가 있다면 충돌 방지를 위해 삭제 (데이터 업데이트 반영)
if os.path.exists("./chroma_db"):
    import shutil
    shutil.rmtree("./chroma_db")

print("📦 엣지 세이버 매뉴얼 데이터를 분석 중입니다...")
loader = TextLoader("edge_saver_manual.txt", encoding="utf-8")
docs = loader.load()

text_splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=30)
chunks = text_splitter.split_documents(docs)

embeddings = OllamaEmbeddings(model="qwen2.5:1.5b")
db = Chroma.from_documents(chunks, embeddings, persist_directory="./chroma_db")

# 👇 아까 에러가 났던 원인! 여기서 llm(Qwen 모델)을 정의해 줍니다.
llm = Ollama(model="qwen2.5:1.5b")

# 1. 엣지 세이버의 정체성을 부여하는 아주 강력한 프롬프트
template = """너는 통신이 끊긴 재난 현장에서 생명을 구하는 '엣지 세이버(Edge Saver)' AI 비서야.
반드시 제공된 [매뉴얼 내용]만을 바탕으로, '한국어'로 침착하고 명확하게 대답해.
매뉴얼에 없는 내용이라면 절대로 지어내지 말고 "해당 상황에 대한 매뉴얼이 없습니다. 구조대를 기다리십시오."라고 대답해.

[매뉴얼 내용]: {context}

질문: {question}
답변:"""

prompt = PromptTemplate(template=template, input_variables=["context", "question"])

# 2. QA 체인에 프롬프트(족쇄) 채우기
qa = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={"k": 4}),
    chain_type_kwargs={"prompt": prompt}
)

print("\n" + "="*50)
print("🚑 엣지 세이버(Edge Saver)가 실행되었습니다.")
print("   질문을 입력하세요. (종료하려면 '종료' 또는 'exit' 입력)")
print("="*50 + "\n")

while True:
    query = input("❓ 질문: ")
    
    if query.strip() in ['종료', 'exit', 'quit']:
        print("👋 안전을 기원합니다. 시스템을 종료합니다.")
        break
        
    if not query.strip():
        continue

    print("🔍 답변 생성 중...")
    try:
        result = qa.invoke(query)
        print(f"\n🤖 AI 답변: {result['result']}\n")
        print("-" * 30)
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")
