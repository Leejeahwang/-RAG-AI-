import json
import os
import re

def clean_file(file_path):
    if not os.path.exists(file_path):
        return False
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # AI 메타 발언 패턴 (서론, 결론, 자기소개 등 - 매우 공격적으로 탐색)
    # 문장 단위가 아니라 키워드 조합이 발견되는 '문단' 전체를 타겟팅
    patterns = [
        # 제공하신/제공된 원본 데이터 계열 (심각하게 손상, 파편화 등)
        r"(?:제공해?주신|제공된|제공하신)\s+(?:원본\s+)?데이터는.*?(?:재구성|복원|정제)했습니다\.?",
        r"(?:제공해?주신|제공된|제공하신)\s+(?:원본\s+)?데이터는.*?(?:파편화|인코딩|오류).*?(?:어렵습니다|어려움이 있습니다)\.?",
        r"(?:제공해?주신|제공된|제공하신)\s+(?:원본\s+)?데이터는.*?(?:심각하게\s+)?(?:손상|파손)되어.*?(?:재구성|정제)했습니다\.?",
        
        # 전문가/RAG 최적화 계열
        r"(?:문서\s+)?정제\s+(?:및|및\s+RAG).*?전문가로서.*?(?:재구성|정제)했습니다\.?",
        r"RAG\s+시스템(?:에|이|용으로).*?최적화(?:된|하여).*?결과(?:물)?입니다\.?",
        r"안전\s+매뉴얼의\s+특성과.*?분석하여.*?재구성하였습니다\.?",
        # 4. AI의 변명 및 재구성 문구 (전수 조사 기반 추가)
        r"(제공|제시)해주신 (데이터|원본|텍스트).*?혼재되어.*?상태입니다\.?",
        r"(제공|제시)된 원본 데이터는 (심각하게 )?손상되어.*?파악하기 어렵습니다\.?",
        r"안전 매뉴얼의 맥락.*?구조화(하여 재구성)?했습니다\.?",
        r"원본 파일명.*?맥락을 기반으로.*?구조화한 것입니다\.?",
        r"구체적인 수치나 대응 절차는 원본 매뉴얼을.*?확인하시기 바랍니다\.?",
        r"원본 데이터에서 추출될 수 있었을 것으로 추정되는.*?재구성하여 제시합니다\.?",
        r"내용의 정확성을 확보하기 위해 전문적인 정제 작업을 진행했습니다\.?",
        r"데이터의 대부분이 무작위 문자열과 오류로 구성되어 있어.*?복원하는 것이 불가능합니다\.?",
        r"RAG 시스템이 (가장 )?효율적으로.*?구조화(하고 정규화)?한 결과입니다\.?",
        r"본 데이터는.*?재구성한 것입니다\.?",
        r"다음은 안전 매뉴얼의 내용을.*?재구성했습니다\.?",
        r"(\*|#|\s)*?제공해주신 데이터는.*?합니다\.?",
        
        # 서론/결론 상투어
        r"다음은\s+(?:안전\s+)?매뉴얼의\s+내용을.*?정제한\s+결과입니다\.?",
        r"추출된\s+핵심\s+의학\s+정보와.*?재구성했습니다\.?",
        r"이\s+구조화된\s+데이터는.*?최적화되어\s+있습니다\.?",
        r"본\s+섹션은.*?안내합니다\.?",
        
        # 기호 및 불필요한 레이블
        r"\[정제된\s+최종\s+마크다운\s+결과물\]",
        r"\[RAG\s+최적화\s+요약\]",
        r"\*{3,}\s*", # 별표 구분선
        r"-{3,}\s*", # 대시 구분선
        r"(?:\n|^)\s*하지만\s+안전\s+매뉴얼의\s+맥락과.*?재구성했습니다\.?"
    ]
    
    cleaned_count = 0
    for item in data:
        original = item["content"]
        new_content = original
        for p in patterns:
            new_content = re.sub(p, "", new_content, flags=re.DOTALL | re.MULTILINE)
        
        # 불필요한 공백 및 중복 줄바꿈 정리
        new_content = re.sub(r'\n{3,}', '\n\n', new_content).strip()
        
        if original != new_content:
            item["content"] = new_content
            cleaned_count += 1
            
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    print(f"  [{os.path.basename(file_path)}] {cleaned_count}개의 항목에서 AI 메타 발언 삭제 완료.")
    return True

def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    files = [
        os.path.join(project_root, "data", "parsed_manuals.json"),
        os.path.join(project_root, "data", "chunked_manuals.json")
    ]
    
    print("[정보] 데이터 내 AI 불필요 발언(Meta-talk) 청소 시작...")
    for f in files:
        clean_file(f)
    print("[정보] 청소 완료.")

if __name__ == "__main__":
    main()
