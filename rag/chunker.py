import json
import os
import sys
import re
import requests
import config

# UTF-8 출력 보장
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class ManualChunker:
    """
    마크다운 구조와 AI 시맨틱 분석을 결합한 스마트 청킹 클래스.
    """
    def __init__(self, chunk_size=800, overlap=150, model=config.LLM_MODEL):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.model = model

    def generate_ai_title(self, text, filename):
        if not text: return filename
        prompt = f"아래 텍스트를 분석하여 문서의 핵심 주제를 10자 이내의 명사형으로 출력하세요.\n파일명: {filename}\n내용: {text[:1000]}\n결과(제목만):"
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=60
            )
            ai_title = response.json().get("response", "").strip()
            return re.sub(r'["\'#\.\(\)]', '', ai_title) if ai_title else filename
        except: return filename

    def get_semantic_splits(self, text):
        if len(text) < 400: return text
        prompt = f"아래 텍스트에서 주제나 카테고리가 바뀌는 지점에 '[SPLIT]' 마커만 삽입하세요. 원본 텍스트의 글자나 기호는 절대 수정하거나 삭제하지 마세요.\n원본 텍스트:\n{text}"
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=90
            )
            content = response.json().get("response", "").strip()
            # [안전 장치] 혹시나 AI가 변조한 LaTeX 기호 제거 (원본 텍스트 보존 우선)
            # 마커를 제외하고 원본과 너무 다르면 원본을 반환
            if "[SPLIT]" not in content: return text
            
            # AI가 임의로 추가한 수식 기호 제거
            content = content.replace('$', '').replace('\\text{', '').replace('}', '')
            return content
        except: return text

    def chunk_document(self, content, source_name):
        """단일 문서를 청크 리스트로 분할합니다."""
        
        # 1. AI 타이틀 생성
        print(f"  [AI 분석] {source_name} 주제 파악 중...")
        doc_topic = self.generate_ai_title(content, source_name)
        title = f"{os.path.splitext(source_name)[0]} ({doc_topic})"
        
        # 2. 구조 + 시맨틱 청킹
        sections = re.split(r'(^#{1,4} .+)', content, flags=re.MULTILINE)
        pre_chunks = []
        current_breadcrumbs = [title]
        current_content = ""
        
        for part in sections:
            if not part.strip(): continue
            if part.startswith('#'):
                level = len(re.match(r'^(#+)', part).group())
                header_text = part.lstrip('#').strip()
                if current_content.strip():
                    pre_chunks.append({"breadcrumb": " > ".join(current_breadcrumbs), "text": current_content.strip()})
                current_breadcrumbs = current_breadcrumbs[:level]
                while len(current_breadcrumbs) < level: current_breadcrumbs.append("...")
                current_breadcrumbs.append(header_text)
                current_content = part + "\n"
            else:
                current_content += part
        
        if current_content.strip():
            pre_chunks.append({"breadcrumb": " > ".join(current_breadcrumbs), "text": current_content.strip()})

        final_chunks = []
        for item in pre_chunks:
            # 시맨틱 분할
            body = item["text"]
            if len(body) > self.chunk_size * 0.8:
                try:
                    semantic_text = self.get_semantic_splits(body)
                except Exception as e:
                    print(f"  [AI 분석 경고] 시맨틱 분리 에러 발생 ({e}). 폴백 청커를 사용합니다.")
                    semantic_text = body
                
                if "[SPLIT]" in semantic_text:
                    sub_parts = semantic_text.split("[SPLIT]")
                else:
                    # AI 분할 실패 혹은 마커 누락 시 폴백 슬라이딩 윈도우 적용
                    sub_parts = self.fallback_split(body, chunk_size=self.chunk_size, overlap=self.overlap)
            else: 
                sub_parts = [body]

            for p in sub_parts:
                p = p.strip()
                if not p or len(p) < 60: continue
                
                # 가치 필터링
                if not self.is_useful_chunk(p): continue
                
                # 최종 메타데이터 결합
                final_chunks.append({
                    "chunk_id": len(final_chunks) + 1,
                    "source": source_name,
                    "title": title,
                    "content": f"### [위치: {item['breadcrumb']}]\n\n{p}"
                })
        return final_chunks

    def fallback_split(self, text, chunk_size=800, overlap=150):
        """
        AI 청킹 실패 혹은 마커 미삽입 시 작동하는 폴백 슬라이딩 윈도우 기능.
        문단 및 문장 경계를 존중하며 안정적인 크기로 텍스트를 나눕니다.
        """
        paragraphs = text.split('\n')
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para: continue
            
            # 크기 한도를 넘는 경우 분할 결정
            if len(current_chunk) + len(para) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # overlap 크기 보정 후 다음 청크 준비
                if len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + "\n" + para
                else:
                    current_chunk = para
            else:
                if current_chunk:
                    current_chunk += "\n" + para
                else:
                    current_chunk = para
                    
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        # 최종 보정: 크기가 과도하게 큰 청크가 남아있으면 강제 분할
        final_splits = []
        for chunk in chunks:
            if len(chunk) > chunk_size * 1.2:
                start = 0
                while start < len(chunk):
                    end = start + chunk_size
                    final_splits.append(chunk[start:end])
                    start += (chunk_size - overlap)
            else:
                final_splits.append(chunk)
        return final_splits

    @staticmethod
    def is_useful_chunk(text):
        if len(text.strip()) < 60: return False
        noise_keywords = ['발행처', '발행일', '발행인', '저작권', '무단 전재', '전화번호', '팩스번호']
        if sum(1 for kw in noise_keywords if kw in text) >= 2: return False
        return True

    def chunk_all(self, document_list):
        """문서 리스트를 받아 전체 청크를 반환합니다."""
        all_chunks = []
        for doc in document_list:
            res = self.chunk_document(doc["content"], doc["source"])
            all_chunks.extend(res)
        return all_chunks

if __name__ == "__main__":
    chunker = ManualChunker()
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_file = os.path.join(project_root, "data", "parsed_manuals.json")
    
    with open(input_file, "r", encoding="utf-8") as f:
        documents = json.load(f)
    
    final_chunks = chunker.chunk_all(documents)
    save_path = os.path.join(project_root, "data", "chunked_manuals.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(final_chunks, f, ensure_ascii=False, indent=4)
    print(f"\n[완료] {len(final_chunks)}개 청크 저장됨.")