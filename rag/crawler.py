import os
import time
import re
import unicodedata
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# 1. 디렉토리 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
download_dir = os.path.join(project_root, "data", "raw_documents")

if not os.path.exists(download_dir):
    os.makedirs(download_dir)

def setup_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    prefs = {
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True  # PDF를 브라우저에서 열지 않고 바로 다운로드
    }
    chrome_options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def crawl_national_disaster_portal(driver):
    wait = WebDriverWait(driver, 10)
    target_url = "https://safekorea.go.kr/idsiSFK/neo/sfk/cs/csc/bbs_conf.jsp?bbs_no=9&emgPage=Y&menuSeq=593"
    
    print("[정보] 국민재난안전포털 접속 중...")
    driver.get(target_url)
    time.sleep(3)
    
    try:
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
            except: pass
                
            articles = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            
            for i in range(len(articles)):
                try:
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
                    except: pass
                            
                    current_articles = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                    row = current_articles[i]
                    
                    try:
                        title_link = row.find_element(By.CSS_SELECTOR, "td.title a, td.subj a, td:nth-child(2) a")
                    except: continue
                        
                    article_title = title_link.text
                    print(f"  [게시글] {article_title}")
                    
                    driver.execute_script("arguments[0].click();", title_link)
                    time.sleep(2)
                    
                    download_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'fn_download') or contains(@href, 'download') or contains(text(), 'hwp') or contains(text(), 'pdf') or contains(text(), 'hwp') or contains(text(), 'pdf')]")
                    
                    if download_links:
                        # 1. 문서별로 파일 확장자 우선순위 정리 (PDF > HWP/DOCX)
                        files_to_download = {} # {base_name: (best_ext, link_element, clean_filename)}
                        
                        for link in download_links:
                            original_text = link.text.strip().replace('\xa0', ' ')
                            original_text = unicodedata.normalize('NFC', original_text)
                            if not original_text: continue
                            
                            clean_filename = re.sub(r'[\\/*?Binary:"<>|]', '_', original_text)
                            link_text_lower = clean_filename.lower()
                            
                            # 확장자 분리
                            match = re.search(r'^(.*)\.(hwp|pdf|docx)$', link_text_lower)
                            if match:
                                base_name = match.group(1).strip()
                                ext = match.group(2)
                                
                                # 우선순위 결정 (pdf=2, others=1)
                                priority = 2 if ext == 'pdf' else 1
                                
                                if base_name not in files_to_download or priority > files_to_download[base_name][0]:
                                    files_to_download[base_name] = (priority, link, clean_filename)
                        
                        # 2. 결정된 최적의 파일들만 다운로드 실행
                        for base_name, (priority, link, clean_filename) in files_to_download.items():
                            file_path = os.path.join(download_dir, clean_filename)
                            if os.path.exists(file_path):
                                print(f"    [건너뜀] 이미 존재함: {clean_filename}")
                                continue
                                
                            print(f"    [파일] 다운로드 중: {clean_filename}")
                            driver.execute_script("arguments[0].click();", link)
                            time.sleep(2.0) # 다운로드 안정성을 위해 약간 대기
                    else:
                        print("    [알림] 첨부파일이 없습니다.")
                    
                    try:
                        list_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '목록') or contains(@title, '목록')] | //img[contains(@alt, '목록')]/parent::a | //button[contains(text(), '목록') or contains(@title, '목록')]")))
                        driver.execute_script("arguments[0].click();", list_btn)
                    except: driver.back()
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"  [오류] 게시글 처리 실패: {e}")
                    try:
                        driver.switch_to.alert.accept()
                        time.sleep(2)
                    except: pass
                    try: 
                        if len(driver.find_elements(By.ID, "minPage")) == 0:
                            driver.get(target_url)
                            time.sleep(3)
                    except: pass

    except Exception as e:
        print(f"[오류] 포털 크롤링 중 문제 발생: {e}")

def crawl_kfsi_portal(driver):
    target_url = "https://www.kfsi.or.kr/campaign/fireSafetyManualList.do"
    print("[정보] 한국소방안전원 접속 중...")
    driver.get(target_url)
    time.sleep(3)
    
    try:
        # h5 태그(제목)를 기준으로 매뉴얼 항목 찾기
        titles = driver.find_elements(By.TAG_NAME, "h5")
        print(f"[정보] 감지된 매뉴얼 수: {len(titles)}")
        
        for i in range(len(titles)):
            try:
                # element가 stale해지는 것을 방지하기 위해 매번 새로 찾음
                current_titles = driver.find_elements(By.TAG_NAME, "h5")
                if i >= len(current_titles): break
                
                title_el = current_titles[i]
                title = title_el.text.strip()
                if not title: continue
                
                print(f"  [매뉴얼] {title}")
                
                # 제목 요소에서 전체 아이템 컨테이너로 올라가서 버튼 탐색
                try:
                    # 'kfsi-manual-item' 클래스를 가진 조상 요소를 컨테이너로 설정
                    parent_container = title_el.find_element(By.XPATH, "./ancestor::div[contains(@class, 'kfsi-manual-item')]")
                    
                    # 컨테이너 내에서 '다운로드' 텍스트를 포함하거나 'btn-info' 클래스를 가진 요소 찾기
                    download_btn = parent_container.find_element(By.XPATH, ".//button[contains(@class, 'btn-info')] | .//a[contains(., '다운로드')] | .//button[contains(., '다운로드')]")
                    
                    driver.execute_script("arguments[0].click();", download_btn)
                    print(f"    [파일] 다운로드 실행됨")
                    time.sleep(2)
                except Exception as inner_e:
                    print(f"    [경고] '{title}'의 다운로드 버튼을 찾을 수 없습니다.")
                    
            except Exception as e:
                print(f"  [오류] 매뉴얼 처리 중 건너뜀: {e}")
                
    except Exception as e:
        print(f"[오류] 소방안전원 크롤링 중 문제 발생: {e}")

def main():
    print("="*50)
    print(" 소방안전 매뉴얼 데이터 수집기")
    print("="*50)
    print("1. 국민재난안전포털 (PDF, HWP 중심)")
    print("2. 한국소방안전원 (이미지/PDF 중심)")
    print("="*50)
    
    choice = input("수집할 포털 번호를 선택하세요 (1 또는 2): ").strip()
    
    driver = setup_driver()
    try:
        if choice == '1':
            crawl_national_disaster_portal(driver)
        elif choice == '2':
            crawl_kfsi_portal(driver)
        else:
            print("[오류] 잘못된 선택입니다. 프로그램을 종료합니다.")
    finally:
        print("\n[정보] 작업 완료. 10초 후 종료합니다.")
        time.sleep(10)
        driver.quit()

if __name__ == "__main__":
    main()
