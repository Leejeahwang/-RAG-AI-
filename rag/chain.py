"""
QA 체인 & 프롬프트 모듈
- 엣지 세이버 시스템 프롬프트 템플릿
- RetrievalQA 체인 생성
"""

from langchain_community.llms import Ollama
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate

import config


# ──────────────────────────────────────────────
# 엣지 세이버 시스템 프롬프트
# ──────────────────────────────────────────────
EDGE_SAVER_PROMPT = """너는 통신이 끊긴 재난 현장에서 생명을 구하는 '엣지 세이버(Edge Saver)' AI 비서야.
반드시 제공된 [매뉴얼 내용]만을 바탕으로, '한국어'로 침착하고 명확하게 대답해.
매뉴얼에 없는 내용이라면 절대로 지어내지 말고 "해당 상황에 대한 매뉴얼이 없습니다. 구조대를 기다리십시오."라고 대답해.

[매뉴얼 내용]: {context}

질문: {question}
답변:"""


def build_qa_chain(retriever):
    """
    RetrievalQA 체인을 생성합니다.

    Args:
        retriever: 벡터DB 검색기

    Returns:
        RetrievalQA 체인 인스턴스
    """
    llm = Ollama(model=config.LLM_MODEL)

    prompt = PromptTemplate(
        template=EDGE_SAVER_PROMPT,
        input_variables=["context", "question"],
    )

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs={"prompt": prompt},
    )

    return qa
