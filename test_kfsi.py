import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

chrome_options = Options()
# chrome_options.add_argument("--headless")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    url = "https://www.kfsi.or.kr/campaign/fireSafetyManualList.do"
    print(f"Connecting to {url}...")
    driver.get(url)
    time.sleep(5)
    
    # Try different selectors
    h5_tags = driver.find_elements(By.TAG_NAME, "h5")
    print(f"Found {len(h5_tags)} h5 tags.")
    for h5 in h5_tags:
        print(f"  Title: {h5.text}")
        
    # More flexible search
    elements = driver.find_elements(By.XPATH, "//*[contains(text(), '다운로드')]")
    print(f"Found {len(elements)} elements with '다운로드' text.")
    for el in elements:
        print(f"  Tag: {el.tag_name}, Class: {el.get_attribute('class')}")
        # print(f"  OuterHTML: {el.get_attribute('outerHTML')}")
        
    download_buttons = driver.find_elements(By.XPATH, "//a[contains(., '다운로드')] | //button[contains(., '다운로드')]")
    print(f"Found {len(download_buttons)} download buttons using refined XPath.")
    
    if download_buttons:
        print("Selector works!")
    else:
        print("Selector FAILED.")
        # Print page source to a file for analysis
        with open("kfsi_page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
            
finally:
    driver.quit()
