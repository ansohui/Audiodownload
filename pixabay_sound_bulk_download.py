# pixabay_sound_bulk_download_detail_only.py
# - 목록 무시, 상세페이지 전용
# - START_PAGE ~ END_PAGE 범위 지정 가능
# - HTML 파싱으로 CDN mp3/wav/flac URL 직접 추출 → 다운로드
# - 다운로드 후 제목 기반으로 파일명 변경

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

# =====================[ 설정 ]=====================
SEARCH_QUERY      = "fire alarm"
BASE_URL          = "https://pixabay.com/en/"
HEADLESS          = False
START_PAGE        = 1
END_PAGE          = 3                   # 원하는 범위 지정
MAX_ITEMS         = 50                  # 전체 다운로드 제한
DOWNLOAD_DIR      = str(Path.home() / "Downloads" / "pixabay_fire_alarm")
# ==================================================

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a", ".ogg")
SEARCH_URL = f"{BASE_URL}sound-effects/search/{SEARCH_QUERY.replace(' ', '-')}/"

def human_sleep(a=0.7, b=1.6): time.sleep(random.uniform(a, b))

def build_driver():
    o = Options()
    if HEADLESS:
        o.add_argument("--headless=new")
    o.add_argument("--lang=en-US")
    o.add_argument("--window-size=1400,1000")
    o.add_argument("--disable-gpu")
    o.add_argument("--no-sandbox")
    o.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
    })
    d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=o)
    try:
        d.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow","downloadPath": DOWNLOAD_DIR})
    except: pass
    return d

def wait_downloads_done(timeout=60):
    start = time.time()
    folder = Path(DOWNLOAD_DIR)
    baseline = {p.name for p in folder.glob("*")}
    while time.time() - start < timeout:
        cur = {p.name for p in folder.glob("*")}
        if not any(name.endswith(".crdownload") for name in cur):
            new_files = [name for name in cur - baseline if any(name.lower().endswith(ext) for ext in AUDIO_EXTS)]
            if new_files:
                path = folder / sorted(new_files, key=lambda n: (folder/n).stat().st_mtime)[-1]
                return path
        time.sleep(1)
    return None

def safe_title_to_filename(title, ext):
    title = title.strip() or "pixabay_audio"
    safe = re.sub(r'[\\/*?:"<>|]', "_", title)
    safe = re.sub(r"\s+", "_", safe)[:120]
    return safe + ext.lower()

def rename_download(downloaded_path, title, ext):
    if not downloaded_path: return
    folder = Path(DOWNLOAD_DIR)
    new_name = safe_title_to_filename(title, ext)
    new_path = folder / new_name
    if new_path.exists():
        stem, ext0 = new_path.stem, new_path.suffix
        i = 1
        while True:
            cand = folder / f"{stem}({i}){ext0}"
            if not cand.exists():
                new_path = cand; break
            i += 1
    try:
        downloaded_path.rename(new_path)
        print(f"  ✨ {downloaded_path.name} → {new_path.name}")
    except Exception as e:
        print("  ⚠️ rename 실패:", e)

def extract_urls(html):
    urls = re.findall(r"https://cdn\.pixabay\.com/download/audio/[^\s\"'<>]+?\.(?:mp3|wav|flac|m4a|ogg)", html, flags=re.I)
    urls += re.findall(r'"contentUrl"\s*:\s*"([^"]+)"', html, flags=re.I)
    urls += re.findall(r'"url"\s*:\s*"([^"]+)"', html, flags=re.I)
    seen, uniq = set(), []
    for u in urls:
        if u.startswith("http") and u not in seen:
            seen.add(u); uniq.append(u)
    return uniq

def extract_title(html):
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html, flags=re.I)
    if m: return m.group(1).strip()
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I|re.S)
    if m:
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        return re.sub(r"\s+", " ", text).strip()
    return "pixabay_audio"

def download_via_detail_page(d, url):
    d.get(url)
    WebDriverWait(d, 15).until(lambda d: d.execute_script("return document.readyState")=="complete")
    html = d.page_source
    title = extract_title(html)
    urls  = extract_urls(html)
    if not urls: return False
    file_url = urls[0]
    print("   → parsed:", file_url)
    d.get(file_url)
    downloaded = wait_downloads_done()
    if downloaded:
        ext = Path(file_url).suffix or downloaded.suffix
        rename_download(downloaded, title, ext)
        return True
    return False

def collect_detail_links_from_list(d):
    html = d.page_source
    rels = re.findall(r'"(/sound-effects/[a-z0-9\-]+-\d+/)"', html, flags=re.I)
    abss = re.findall(r'https://pixabay\.com/sound-effects/[a-z0-9\-]+-\d+/', html, flags=re.I)
    links = [f"https://pixabay.com{p}" for p in rels] + abss
    uniq = []
    for u in links:
        u = u if u.endswith("/") else u + "/"
        if "/sound-effects/search/" not in u and u not in uniq:
            uniq.append(u)
    return uniq

def main():
    print("▶ main() 시작")
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    d = build_driver()
    try:
        downloaded = 0
        for p in range(START_PAGE, END_PAGE+1):
            if downloaded >= MAX_ITEMS: break
            url = SEARCH_URL if p==1 else f"{SEARCH_URL}?pagi={p}"
            d.get(url)
            WebDriverWait(d, 20).until(lambda d: d.execute_script("return document.readyState")=="complete")
            time.sleep(1)
            details = collect_detail_links_from_list(d)
            print(f"🔎 page {p} links: {len(details)}")
            for detail in details:
                if downloaded >= MAX_ITEMS: break
                ok = download_via_detail_page(d, detail)
                if ok:
                    print("  ✅ 다운로드 완료")
                    downloaded += 1
                else:
                    print("  ⚠️ 실패")
                human_sleep()
        print(f"\n총 {downloaded}개 다운로드 완료. 저장 폴더: {DOWNLOAD_DIR}")
    finally:
        d.quit()

if __name__=="__main__":
    main()
