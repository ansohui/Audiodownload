# pixabay_sound_bulk_download.py
# - Pixabay sound-effects 일괄 다운로드
# - 제목이나 카테고리/태그 중 "fire" 들어간 것만 다운로드
# - 중복 방지: 파일명 뒤에 CDN 해시 일부 붙이기
# - en-US 고정, 자동 다운로드 허용 포함

import os, re, time, random, urllib.parse
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

print("🚀 스크립트 로딩됨")

# ===================== 설정 =====================
SEARCH_QUERY   = "fire alarm"
BASE_URL       = "https://pixabay.com/en/"
SEARCH_URL     = f"{BASE_URL}sound-effects/search/{SEARCH_QUERY.replace(' ', '-')}/"

HEADLESS       = False
PAGE_START     = 6
PAGE_END       = 10       # 원하는 페이지 범위
MAX_ITEMS      = 30000
DOWNLOAD_DIR   = str(Path.home() / "Downloads" / "pixabay_fire_alarm")

PIXABAY_EMAIL  = os.getenv("PIXABAY_EMAIL", "")
PIXABAY_PASS   = os.getenv("PIXABAY_PASS", "")

AUDIO_EXTS     = (".mp3", ".wav", ".flac", ".m4a", ".ogg")
# =================================================

def human_sleep(a=0.7, b=1.5): time.sleep(random.uniform(a, b))

def build_driver():
    o = Options()
    if HEADLESS: o.add_argument("--headless=new")
    o.add_argument("--lang=en-US")
    o.add_argument("--window-size=1400,1000")
    o.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True
    })
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=o)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow", "downloadPath": DOWNLOAD_DIR
        })
    except: pass
    return driver

def wait_downloads_done(timeout=60, baseline=None):
    start = time.time()
    folder = Path(DOWNLOAD_DIR)
    if baseline is None:
        baseline = {p.name for p in folder.glob("*")}
    while time.time() - start < timeout:
        cur = {p.name for p in folder.glob("*")}
        if not any(n.endswith(".crdownload") for n in cur):
            new_files = [n for n in cur - baseline if any(n.lower().endswith(ext) for ext in AUDIO_EXTS)]
            if new_files:
                return folder / new_files[0]
        time.sleep(1)
    return None

def safe_filename(name, ext, hash_hint=""):
    safe = re.sub(r'[\\/*?:"<>|]', "_", name).strip().replace(" ", "_")
    if hash_hint: safe += "_" + hash_hint
    return (safe[:120] + ext).lower()

def make_unique_path(path: Path):
    if not path.exists(): return path
    stem, ext = path.stem, path.suffix
    for i in range(1, 999):
        cand = path.with_name(f"{stem}({i}){ext}")
        if not cand.exists(): return cand
    return path.with_name(f"{stem}_{int(time.time())}{ext}")

def extract_title_and_category(html):
    # title
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html, re.I)
    title = m.group(1).strip() if m else "pixabay_audio"
    # category/tags
    cats = re.findall(r'/sound-effects/search/([^/]+)/', html, re.I)
    cats = [c.replace("-", " ").strip() for c in cats]
    cats = list(dict.fromkeys(cats))
    return title, ", ".join(cats)

def download_via_detail(driver, url):
    driver.get(url)
    WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
    html = driver.page_source
    title, category = extract_title_and_category(html)

    # 🔥 필터 조건: 제목이나 카테고리에 fire, bell, siren
    keywords = ["fire", "siren"]
    if not any(k in title.lower() or k in category.lower() for k in keywords):
        print(f"   ⏩ skip (title='{title}', category='{category}')")
        return False

    # CDN 오디오 URL 추출
    urls = re.findall(r'https://cdn\.pixabay\.com/download/audio/[^\s"\']+\.(?:mp3|wav|flac|m4a|ogg)', html, re.I)
    if not urls:
        print("   ⚠️ no audio url")
        return False
    file_url = urls[0]
    ext = Path(urllib.parse.urlparse(file_url).path).suffix.lower()

    hash_hint = ""
    m = re.search(r"audio_([a-f0-9]+)", file_url)
    if m: hash_hint = m.group(1)[:6]

    print(f"   → parsed: {file_url}")
    baseline = {p.name for p in Path(DOWNLOAD_DIR).glob('*')}
    driver.get(file_url)
    downloaded = wait_downloads_done(60, baseline)
    if downloaded:
        new_name = safe_filename(title, ext, hash_hint)
        new_path = make_unique_path(Path(DOWNLOAD_DIR) / new_name)
        try:
            downloaded.rename(new_path)
            print(f"  ✨ {downloaded.name} → {new_path.name}")
        except Exception as e:
            print("  ⚠️ rename 실패:", e)
        print("  ✅ 다운로드 완료")
        return True
    return False

def collect_detail_links(driver):
    html = driver.page_source
    rels = re.findall(r'"(/sound-effects/[a-z0-9\-]+-\d+/)"', html, re.I)
    abss = re.findall(r'https://pixabay\.com/sound-effects/[a-z0-9\-]+-\d+/', html, re.I)
    return list(dict.fromkeys([f"https://pixabay.com{p}" for p in rels] + abss))

def goto_page(driver, page):
    url = SEARCH_URL if page == 1 else f"{SEARCH_URL}?pagi={page}"
    driver.get(url)
    WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
    time.sleep(1.0)
    print("📄 current:", driver.current_url)

def main():
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    d = build_driver()
    try:
        print(f"▶ 실행 범위: PAGE_START={PAGE_START}, PAGE_END={PAGE_END}")
        downloaded = 0
        for p in range(PAGE_START, PAGE_END + 1):
            if downloaded >= MAX_ITEMS: break
            goto_page(d, p)
            details = collect_detail_links(d)
            for link in details:
                if downloaded >= MAX_ITEMS: break
                if download_via_detail(d, link):
                    downloaded += 1
                    human_sleep()
        print(f"\n총 {downloaded}개 다운로드 완료. 저장 폴더: {DOWNLOAD_DIR}")
    finally:
        d.quit()

if __name__ == "__main__":
    main()
