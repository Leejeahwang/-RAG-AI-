import json
import re
import os

def audit_data():
    data_dir = 'data'
    chunked_file = os.path.join(data_dir, 'chunked_manuals.json')
    
    if not os.path.exists(chunked_file):
        print(f"[오류] {chunked_file} 파일이 없습니다.")
        return

    with open(chunked_file, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    # AI의 자의적 판단이나 요약을 암시하는 위험 키워드들
    risk_keywords = [
        "죄송합니다", "혼재", "재구성", "요약", "손상", 
        "파악하기 어렵습니다", "생략", "추출된 키워드", 
        "제공된 원본", "핵심 정보만", "맥락에 맞게", 
        "구조화했습니다", "변형", "정리했습니다"
    ]
    
    suspicious_chunks = []
    
    print(f"[*] 총 {len(chunks)}개의 청크 조사 중...")
    
    for chunk in chunks:
        content = chunk.get('content', '')
        found_keywords = []
        
        for kw in risk_keywords:
            if kw in content:
                found_keywords.append(kw)
        
        if found_keywords:
            suspicious_chunks.append({
                "source": chunk.get('source'),
                "id": chunk.get('chunk_id'),
                "keywords": found_keywords,
                "preview": content[-200:] # 충분한 맥락 확인을 위해 길게 잡음
            })

    print(f"\n[!] 전수 조사 완료: 총 {len(suspicious_chunks)}개의 의심 청크가 발견되었습니다.\n")
    
    if suspicious_chunks:
        print("-" * 50)
        for i, sc in enumerate(suspicious_chunks, 1):
            try:
                print(f"[{i}] 출처: {sc['source']} (ID: {sc['id']})")
                print(f"    발견된 키워드: {sc['keywords']}")
                # 인코딩 오류 방지 처리
                safe_preview = sc['preview'].replace('\n', ' ').strip()
                print(f"    하단 내용 미리보기: ...{safe_preview[:150]}")
            except UnicodeEncodeError:
                print(f"[{i}] 출처: {sc['source']} (ID: {sc['id']}) [출력 중 인코딩 오류 발생]")
            print("-" * 50)
            
        # 결과를 별도 파일로 저장
        with open('data/audit_report.json', 'w', encoding='utf-8') as f:
            json.dump(suspicious_chunks, f, ensure_ascii=False, indent=4)
        print(f"\n[결과] 상세 리포트가 'data/audit_report.json'에 저장되었습니다.")
    else:
        print("[V] AI의 요약이나 변명이 포함된 청크가 발견되지 않았습니다. (안전)")

if __name__ == "__main__":
    audit_data()
