import os
import json
import hashlib
import shutil
import time
from rag.parser import ManualParser
from rag.chunker import ManualChunker
from rag.native_retriever import rag_manager
import config

class RAGPipelineManager:
    """
    RAG 파이프라인 통합 매니저 (v35: Native FAISS 대응)
    문서 파싱, 청킹, FAISS 인덱싱 과정을 자동화하고 증분 업데이트를 관리합니다.
    """
    def __init__(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.raw_dir = os.path.join(self.project_root, "data", "raw_documents")
        self.backup_dir = os.path.join(self.project_root, "data", "backups")
        self.filtered_dir = os.path.join(self.project_root, "data", "filtered_documents")
        self.state_file = os.path.join(self.project_root, "data", "pipeline_state.json")
        self.parsed_file = os.path.join(self.project_root, "data", "parsed_manuals.json")
        self.chunked_file = os.path.join(self.project_root, "data", "chunked_manuals.json")
        
        # 폴더 생성
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.filtered_dir, exist_ok=True)
        
        self.parser = ManualParser()
        self.chunker = ManualChunker()

    def _calculate_hash(self, file_path):
        """파일의 MD5 해시값을 계산합니다."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"processed_files": {}, "last_sync": None}

    def _save_state(self, state):
        state["last_sync"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

    def _backup_data(self):
        """기존 파싱/청킹 데이터를 백업합니다."""
        for f in [self.parsed_file, self.chunked_file]:
            if os.path.exists(f):
                shutil.copy(f, f + ".bak")

    def sync(self, force=False):
        """증분 동기화를 수행합니다."""
        print("\n[Pipeline] FAISS 증분 동기화 시작 중...")
        state = self._load_state()
        processed_files = state["processed_files"]
        
        current_files = os.listdir(self.raw_dir)
        updated = False
        
        # 1. 변경된 파일 탐지
        to_process = []
        for filename in current_files:
            file_path = os.path.join(self.raw_dir, filename)
            if not os.path.isfile(file_path): continue
            
            file_hash = self._calculate_hash(file_path)
            if force or filename not in processed_files or processed_files[filename] != file_hash:
                to_process.append((filename, file_path, file_hash))
        
        if not to_process:
            print("[Pipeline] 변경 사항이 없습니다. 동기화를 건너뜁니다.")
            return False

        print(f"[Pipeline] {len(to_process)}개의 새로운 또는 변경된 파일 감지됨.")
        self._backup_data()
        
        # 2. 파싱 (기존 데이터 로드 후 업데이트)
        all_docs = []
        if os.path.exists(self.parsed_file):
            with open(self.parsed_file, "r", encoding="utf-8") as f:
                all_docs = json.load(f)
        
        # 기존 문서 중 삭제된 파일 제거
        all_docs = [d for d in all_docs if d["source"] in current_files]
        
        for filename, path, f_hash in to_process:
            # 기존 문서에 해당 파일이 있으면 제거 (교체 목적)
            all_docs = [d for d in all_docs if d["source"] != filename]
            
            parsed_res = self.parser.parse_file(path)
            if parsed_res:
                all_docs.append(parsed_res)
                processed_files[filename] = f_hash
                updated = True
            else:
                # 검역 탈락 또는 파싱 실패 시 파일 격리
                print(f"  [격리] '{filename}' 문서를 filtered_documents 폴더로 이동합니다.")
                dest_path = os.path.join(self.filtered_dir, filename)
                try:
                    if os.path.exists(dest_path):
                        dest_path = os.path.join(self.filtered_dir, f"{int(time.time())}_{filename}")
                    shutil.move(path, dest_path)
                except Exception as e:
                    print(f"  [오류] 파일 격리 중 에러: {e}")
        
        if updated:
            # 3. 데이터 저장 (중간 결과)
            with open(self.parsed_file, "w", encoding="utf-8") as f:
                json.dump(all_docs, f, ensure_ascii=False, indent=4)
            
            # 4. 청킹
            print("[Pipeline] 전체 문서 재청킹 시작...")
            chunks = self.chunker.chunk_all(all_docs)
            with open(self.chunked_file, "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=4)
            
            # 5. Native FAISS 인덱스 갱신
            print("[Pipeline] Native FAISS 인덱스 업데이트 중...")
            from rag.loader import load_and_split
            all_langchain_chunks = load_and_split() 
            
            # FAISS 인덱싱 실행
            rag_manager.load_resources()
            rag_manager.build_index(all_langchain_chunks)
            
            self._save_state(state)
            
            # 6. 미리보기 파일(preview_chunks.md) 갱신
            try:
                from rag.utils.generate_preview import generate_preview
                generate_preview()
            except Exception as e:
                print(f"[Pipeline] 미리보기 생성 중 오류: {e}")
                
            print("[Pipeline] 동기화 및 인덱싱 완료.")
            return True
            
        return False

    def reindex(self):
        """기존 청크 데이터를 활용하여 FAISS 인덱스만 다시 구축합니다."""
        print("\n[Pipeline] 기존 청크 데이터를 이용한 FAISS 재색인 시작...")
        
        print(f"[Pipeline] 데이터를 통합 로딩 중...")
        from rag.loader import load_and_split
        all_chunks = load_and_split()
        
        print(f"[Pipeline] {len(all_chunks)}개의 통합 청크 준비 완료.")
        
        # FAISS 인덱싱 실행
        rag_manager.load_resources()
        rag_manager.build_index(all_chunks)
        
        print("[Pipeline] 재색인이 완료되었습니다.")
        return True

if __name__ == "__main__":
    import sys
    manager = RAGPipelineManager()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--reindex":
        manager.reindex()
    else:
        manager.sync()
