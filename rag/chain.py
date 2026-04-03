"""
QA 체인 & 프롬프트 모듈 (승훈님 담당)
"""

from langchain_classic.chains import RetrievalQA
from langchain_ollama import OllamaLLM
import config


SYSTEM_PROMPT = """너는 건물 내 화재 감시 및 대응을 전담하는 AI 시스템 '엣지 세이버(Edge Saver)'야.

너의 역할:
1. 센서와 카메라가 감지한 화재 상황에 대해, 건물 매뉴얼을 검색하여 정확한 대응 지침을 제공한다.
2. 해당 구역의 위험물질, 소화기 종류, 대피 경로 등을 포함한 구체적인 안내를 한다.
3. [언어 규칙] 사용자가 질문한 언어에 맞춰 답변하되, 별도의 요청이 없으면 한국어를 기본으로 사용한다.
4. 매뉴얼에 없는 내용은 추측하지 말고 "해당 정보가 매뉴얼에 없습니다"라고 정직하게 말한다.

질문: {question}
참고 매뉴얼: {context}

답변:"""


def build_qa_chain(retriever):
    """RAG 기반 QA 체인을 구성합니다."""
    from langchain_core.prompts import PromptTemplate

    prompt = PromptTemplate(
        template=SYSTEM_PROMPT,
        input_variables=["question", "context"],
    )

    import os
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    llm = OllamaLLM(model=config.LLM_MODEL, base_url=ollama_host)

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=False,
        chain_type_kwargs={"prompt": prompt},
    )
    print("✅ QA 체인 구성 완료")
    return qa
