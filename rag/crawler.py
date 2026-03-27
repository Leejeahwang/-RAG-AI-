import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# 1. 디렉토리 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
# 데이터는 data/ 디렉토리에 저장, 스크립트는 rag/에 유지
project_root = os.path.dirname(current_dir)
download_dir = os.path.join(project_root, "data", "raw_documents")

if not os.path.exists(download_dir):
    os.makedirs(download_dir)

# 2. 브라우저 설정
chrome_options = Options()
# chrome_options.add_argument("--headless")
prefs = {
    "profile.default_content_settings.popups": 0,
    "profile.default_content_setting_values.automatic_downloads": 1,
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
}
chrome_options.add_experimental_option("prefs", prefs)

print("[정보] 크롤러 시작 중...")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 10)

try:
    # 3. 포털 접속
    target_url = "https://safekorea.go.kr/idsiSFK/neo/sfk/cs/csc/bbs_conf.jsp?bbs_no=9&emgPage=Y&menuSeq=593"
    driver.get(target_url)
    time.sleep(3)

    print("[정보] 포털 접속 완료. 데이터 수집을 시작합니다.")
    
    # 4. 페이지네이션 처리
    time.sleep(2)
    try: max_page = int(driver.find_element(By.ID, "maxPage").text)
    except: max_page = 21
    print(f"[정보] 감지된 총 페이지 수: {max_page}")
    
    for current_page_num in range(1, max_page + 1):
        print(f"\n[페이지] {current_page_num} / {max_page}")
        time.sleep(2)
        
        try: driver.switch_to.alert.accept()
        except: pass
        
        try:
            if len(driver.find_elements(By.ID, "minPage")) == 0:
                driver.get(target_url)
                time.sleep(3)
                
            now_num = driver.find_element(By.ID, "minPage").text
            if str(now_num) != str(current_page_num):
                driver.execute_script(f"document.getElementById('bbs_page').value = '{current_page_num}'; onGoToPageBtnClick();")
                time.sleep(3)
        except:
            pass
            
        articles = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        
        for i in range(len(articles)):
            try:
                try: driver.switch_to.alert.accept()
                except: pass
                
                try:
                    if len(driver.find_elements(By.ID, "minPage")) == 0:
                        print("  [복구] 빈 페이지 감지. 게시판에 다시 접속합니다.")
                        driver.get(target_url)
                        time.sleep(3)
                        
                    now_num = driver.find_element(By.ID, "minPage").text
                    if str(now_num) != str(current_page_num):
                        driver.execute_script(f"document.getElementById('bbs_page').value = '{current_page_num}'; onGoToPageBtnClick();")
                        time.sleep(3)
                except:
                    pass
                        
                current_articles = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                row = current_articles[i]
                
                try:
                    title_link = row.find_element(By.CSS_SELECTOR, "td.title a, td.subj a, td:nth-child(2) a")
                except:
                    continue
                    
                article_title = title_link.text
                print(f"  [게시글] {article_title}")
                
                driver.execute_script("arguments[0].click();", title_link)
                time.sleep(2)
                
                # 첨부파일 다운로드
                download_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'fn_download') or contains(@href, 'download') or contains(text(), 'hwp') or contains(text(), 'pdf')]")
                
                if download_links:
                    import re, unicodedata
                    for link in download_links:
                        original_text = link.text.strip().replace('\xa0', ' ')
                        original_text = unicodedata.normalize('NFC', original_text)
                        clean_filename = re.sub(r'[\\/*?:"<>|]', '_', original_text)
                        
                        link_text_lower = clean_filename.lower()
                        if '.hwp' in link_text_lower or '.pdf' in link_text_lower or '.docx' in link_text_lower:
                            file_path = os.path.join(download_dir, clean_filename)
                            if os.path.exists(file_path):
                                print(f"    [건너뜀] 이미 존재함: {clean_filename}")
                                continue
                                
                            print(f"    [파일] 다운로드 중: {clean_filename}")
                            driver.execute_script("arguments[0].click();", link)
                            time.sleep(1.5)
                else:
                    print("    [알림] 첨부파일이 없습니다.")
                
                try:
                    list_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '목록') or contains(@title, '목록')] | //img[contains(@alt, '목록')]/parent::a | //button[contains(text(), '목록') or contains(@title, '목록')]")))
                    driver.execute_script("arguments[0].click();", list_btn)
                except:
                    driver.back()
                time.sleep(2)
                
            except Exception as e:
                print(f"  [오류] 게시글 처리 실패. 건너뜁니다.")
                try:
                    driver.switch_to.alert.accept()
                    time.sleep(2)
                except:
                    pass
                    
                try: 
                    if len(driver.find_elements(By.ID, "minPage")) == 0:
                        driver.get(target_url)
                        time.sleep(3)
                except: pass

        print(f"[정보] {current_page_num} 페이지 완료.")

except Exception as e:
    print(f"[치명적 오류] 프로세스 실패: {e}")

finally:
    print("\n[정보] 수집 종료. 다운로드를 마무리합니다.")
    time.sleep(10) 
    driver.quit()
    print("[정보] 종료되었습니다.")
