import olefile
import zlib
import re
import json
import os

def extract_raw_hwp(file_path):
    f = olefile.OleFileIO(file_path)
    dirs = f.listdir()
    full_text = []
    
    for section in dirs:
        if section[0].startswith('BodyText/Section'):
            data = f.open_stream(section).read()
            # zlib 압축 해제 (HWP 기본값)
            try:
                data = zlib.decompress(data, -15)
            except:
                pass
            
            # UTF-16LE 인코딩
            try:
                decoded = data.decode('utf-16le', errors='ignore')
                cleaned = re.sub(r'[\x00-\x1f]', ' ', decoded)
                full_text.append(cleaned)
            except:
                pass
    f.close()
    return "\n".join(full_text)

def main():
    root = "c:/Users/User/Desktop/projects/RAG"
    hwp_path = os.path.join(root, "data/raw_documents", "[자료] 119생활응급처치매뉴얼 및 핸드북.hwp")
    json_path = os.path.join(root, "data", "parsed_manuals.json")
    
    print("--- [연구] raw 데이터 vs 정제 데이터 비교 ---")
    
    # 1. RAW 추출
    raw_text = extract_raw_hwp(hwp_path)
    
    # 2. 정제 데이터 로드
    with open(json_path, "r", encoding="utf-8") as f:
        parsed_data = json.load(f)
    
    cleaned_entry = next((item for item in parsed_data if "119생활응급처치매뉴얼" in item["source"]), None)
    
    if not cleaned_entry:
        print("정제된 데이터를 찾을 수 없습니다.")
        return

    # 특정 키워드로 비교 (예: 난소 낭종)
    keyword = "난소 낭종"
    
    print(f"\n[키워드: '{keyword}' 기준 RAW 발췌]")
    raw_match = re.search(f".{{0,300}}{keyword}.{{0,500}}", raw_text, re.DOTALL)
    if raw_match:
        print(raw_match.group(0))
    else:
        print("RAW에서 키워드를 찾지 못함")
        
    print(f"\n[키워드: '{keyword}' 기준 정제 데이터 발췌]")
    cleaned_text = cleaned_entry["content"]
    cleaned_match = re.search(f".{{0,300}}{keyword}.{{0,500}}", cleaned_text, re.DOTALL)
    if cleaned_match:
        print(cleaned_match.group(0))
    else:
        print("정제 데이터에서 키워드를 찾지 못함")

if __name__ == "__main__":
    main()
