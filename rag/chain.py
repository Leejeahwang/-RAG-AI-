"""
QA 체인 & 프롬프트 모듈 (승훈님 담당)
"""

from langchain_classic.chains import RetrievalQA
from langchain_community.llms import Ollama
import config


SYSTEM_PROMPT = """너는 '엣지 세이버'다.
반드시 아래 [매뉴얼]에 적힌 한국어 문장을 토씨 하나 틀리지 말고 "그대로 복사(Copy & Paste)"해서 답변해.
너 스스로 문장을 만들어내지 마. 번역 투로 말하지 마.

[매뉴얼]
{context}

[질문]
{question}

복붙 답변:"""


def build_qa_chain(retriever):
    """RAG 기반 QA 체인을 구성합니다."""
    from langchain_core.prompts import PromptTemplate

    prompt = PromptTemplate(
        template=SYSTEM_PROMPT,
        input_variables=["question", "context"],
    )

    import os
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    llm = Ollama(model=config.LLM_MODEL, base_url=ollama_host)

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=False,
        chain_type_kwargs={"prompt": prompt},
    )
    print("✅ QA 체인 구성 완료")
    return qa
