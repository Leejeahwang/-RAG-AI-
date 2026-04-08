import json
import os
import olefile
import zlib
import re
import fitz

def extract_raw_hwp(file_path):
    try:
        f = olefile.OleFileIO(file_path)
        dirs = f.listdir()
        full_text = []
        for section in dirs:
            if section[0].startswith('BodyText/Section'):
                data = f.open_stream(section).read()
                try: data = zlib.decompress(data, -15)
                except: pass
                try:
                    decoded = data.decode('utf-16le', errors='ignore')
                    cleaned = re.sub(r'[\x00-\x1f]', ' ', decoded)
                    full_text.append(cleaned)
                except: pass
        f.close()
        return "\n".join(full_text)
    except: return ""

def extract_raw_pdf(file_path):
    try:
        doc = fitz.open(file_path)
        return "".join([page.get_text() for page in doc])
    except: return ""

def main():
    json_path = "data/parsed_manuals.json"
    raw_dir = "data/raw_documents"
    
    with open(json_path, "r", encoding="utf-8") as f:
        parsed_data = json.load(f)
    
    print(f"{'Source File':<50} | {'Raw Chars':<10} | {'Cleaned Chars':<10} | {'Ratio':<6}")
    print("-" * 85)
    
    for item in parsed_data:
        source = item["source"]
        raw_path = os.path.join(raw_dir, source)
        
        raw_text = ""
        if source.endswith(".hwp"):
            raw_text = extract_raw_hwp(raw_path)
        elif source.endswith(".pdf"):
            raw_text = extract_raw_pdf(raw_path)
        
        raw_len = len(raw_text)
        clean_len = len(item["content"])
        ratio = (clean_len / raw_len * 100) if raw_len > 0 else 0
        
        print(f"{source[:48]:<50} | {raw_len:<10} | {clean_len:<10} | {ratio:>5.1f}%")

if __name__ == "__main__":
    main()
