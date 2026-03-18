from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_classic.chains import RetrievalQA

print("1. 한국어 매뉴얼 불러오는 중...")
loader = TextLoader("mall_guide_ko.txt", encoding="utf-8") # 한글 깨짐 방지
docs = loader.load()

print("2. 텍스트 쪼개고 DB에 저장하는 중...")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
chunks = text_splitter.split_documents(docs)

# 모델 이름을 qwen2.5:1.5b 로 변경!
embeddings = OllamaEmbeddings(model="qwen2.5:1.5b")
db = Chroma.from_documents(chunks, embeddings, persist_directory="./chroma_db")

print("3. 한국어 AI 비서 준비 완료!\n")
llm = Ollama(model="qwen2.5:1.5b")
qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=db.as_retriever())

# 한국어로 질문 던지기
question = "2층 의류매장에서 불이 났어요! 어디로 대피해야 하나요?"
print(f"질문: {question}")

response = qa.invoke(question)
print(f"답변: {response['result']}")
