"""
QA 체인 & 프롬프트 모듈 (승훈님 담당)
"""

import logging
from typing import List, Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
import config

# 시스템 로그 기록을 위한 설정
logger = logging.getLogger(__name__)

class EdgeEmergencyGuider:
    """
    센서 데이터 및 상황 보고를 받아 매뉴얼 기반의 즉각적인 지침을 생성하는 클래스입니다.
    5대 강령을 준수하며, 상황의 흐름(History)을 기억하여 지능적인 판단을 내립니다.
    """
    def __init__(self, retriever):
        # 1. 모델 설정: config.py에서 설정한 LLM 모델 이름을 가져옴
        self.model_name = getattr(config, "LLM_MODEL", "qwen2.5:1.5b")
        
        # 2. AI 엔진 설정: 
        # temperature=0: 창의성보다는 정확한 팩트 전달에 집중
        # streaming=True: 답변이 생성되는 대로 실시간으로 출력하여 체감 속도 향상
        self.llm = ChatOllama(model=self.model_name, temperature=0, streaming=True)
        
        # 3. 리트리버: 앞서 구축한 벡터 DB 검색기 연결
        self.retriever = retriever
        
        # 4. 메모리 보관소: 구역별/세션별 상황 맥락(Context)을 저장하는 딕셔너리
        self.history_store = {}

    def _get_session_history(self, session_id: str):
        """특정 구역이나 사용자의 대화 흐름(기억)을 관리하는 함수"""
        if session_id not in self.history_store:
            # 해당 세션의 기록이 없으면 새 메모장을 생성
            self.history_store[session_id] = ChatMessageHistory()
        return self.history_store[session_id]

    def _create_action_prompt(self):

        system_instructions = (
            "너는 건물 내 화재 감시 및 대응을 전담하는 AI 시스템 '엣지 세이버(Edge Saver)'다.\n\n"
            "※ 상황 발생 시 5대 행동 강령 (절대 준수):\n"
            "1. 센서와 카메라가 감지한 상황에 대해 매뉴얼을 검색하여 지체 없이 정확한 대응 지침을 제공하라.\n"
            "2. 해당 구역의 위험물질, 소화기 종류, 대피 경로 등을 포함한 구체적인 안내를 하라.\n"
            "3. 반드시 한국어로 답변하되, 서론(예: '알겠습니다') 없이 즉시 명령조로 지시하라.\n"
            "4. 매뉴얼에 없는 내용은 추측하지 말고 '해당 정보가 매뉴얼에 없습니다'라고 정직하게 말하라.\n"
            "5. 모든 판단의 최우선 순위는 언제나 '인명 안전'에 둔다.\n\n"
            "------- [참고 매뉴얼] -------\n"
            "{context}" # 리트리버가 찾아온 매뉴얼 조각들이 삽입되는 자리
        )

        return ChatPromptTemplate.from_messages([
            ("system", system_instructions), # 법과 원칙(System)
            MessagesPlaceholder(variable_name="chat_history"), # 과거 상황 기록(Memory)
            ("user", "🚨 [재난 상황 보고]: {input}"), # 외부 보고(User/Sensor Input)
        ])

    def build_guider(self):
        """최신 LCEL(LangChain Expression Language) 표준 기반으로 시스템 조립"""
        prompt = self._create_action_prompt()
        
        # 1. 문서 결합 체인: 찾은 매뉴얼과 프롬프트를 합쳐서 AI에게 전달
        combine_docs_chain = create_stuff_documents_chain(self.llm, prompt)
        
        # 2. RAG 체인: 검색기와 문서 결합 체인을 하나로 연결
        rag_chain = create_retrieval_chain(self.retriever, combine_docs_chain)

        # 3. 메모리 체인: 위 모든 과정에 '대화 기억 기능'을 입혀 최종 완성
        return RunnableWithMessageHistory(
            rag_chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

    def generate_guideline(self, situation: str, session_id: str = "emergency_unit_1"):
        """실제 상황 보고를 받아 최종 지침을 출력하는 메인 함수"""
        guider = self.build_guider()
        try:
            # 로그에 현재 접수된 상황 기록
            logger.info(f"🚨 [Session: {session_id}] 상황 접수: {situation}")
            
            # AI 실행 (세션 ID를 통해 해당 구역의 과거 기록을 자동으로 연동)
            response = guider.invoke(
                {"input": situation},
                config={"configurable": {"session_id": session_id}}
            )

            # 불필요한 메타데이터를 제외한 순수 답변(지침)만 반환
            return response["answer"]

        except Exception as e:
            # 에러 발생 시 시스템 중단 없이 안전 메시지 송출 (5번 원칙 준수)
            logger.error(f"❌ 지침 생성 실패: {e}")
            return "시스템 장애 발생. 즉시 매뉴얼에 따라 대피하고 수동으로 119에 신고하십시오."
