"""
QA 체인 & 프롬프트 모듈 (승훈님 담당)
"""

from langchain_classic.chains import RetrievalQA
from langchain_community.llms import Ollama
import config


SYSTEM_PROMPT = """너는 소방 AI '엣지 세이버'다.
사용자의 질문에 대해 오직 아래 제공된 [매뉴얼]의 내용만을 사용하여 답변하라.
매뉴얼은 '[파일명의 내용]' 형태로 제공된다. 사용자가 특정 구역(예: A구역, B구역)을 질문하면, 반드시 일치하는 구역의 파일 내용만 참조하여 답변하라. 다른 구역의 정보를 섞지 마라.
매뉴얼에 없는 내용은 절대 상상으로 지어내지 마라(환각 금지).
묻는 말에만 짧고 명확하게 대답하라.

[매뉴얼]
{context}

[질문]
{question}

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
