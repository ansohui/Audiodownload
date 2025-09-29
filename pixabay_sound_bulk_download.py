# pixabay_sound_bulk_download.py
# - 목록의 Download 버튼( <a> / <button> )을 직접 처리해 빠르게 다운로드
# - 목록에서 실패하면 상세 페이지 HTML에서 CDN 오디오 URL을 파싱해 다운로드(폴백)
# - 다운로드 완료 후 상세/목록에서 얻은 "제목"으로 파일명 자동 변경
# - macOS/Windows 안전한 파일명 처리 + 중복 시 자동 번호 붙임
# - en-US 고정, 쿠키 동의 처리, 자동 다운로드 허용, CDP 다운로드 허용 포함

import os, re, time, random, urllib.parse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

print("🚀 스크립트 로딩됨")

# =====================[ 설정 ]=====================
SEARCH_QUERY      = "fire alarm"                          # 검색어
BASE_URL          = "https://pixabay.com/en/"             # en 고정(리다이렉트 회피)
HEADLESS          = False                                 # 창 숨기려면 True
MAX_PAGES         = 2                                     # 검색 페이지 수
MAX_ITEMS         = 20                                    # 최대 다운로드 시도 개수
DOWNLOAD_DIR      = str(Path.home() / "Downloads" / "pixabay_fire_alarm")
PIXABAY_EMAIL     = os.getenv("PIXABAY_EMAIL", "")        # (선택) 로그인
PIXABAY_PASS      = os.getenv("PIXABAY_PASS", "")

SEARCH_URL = f"{BASE_URL}sound-effects/search/{SEARCH_QUERY.replace(' ', '-')}/"
# ==================================================

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a", ".ogg")

def human_sleep(a=0.7, b=1.6):
    time.sleep(random.uniform(a, b))

def build_driver():
    o = Options()
    if HEADLESS:
        o.add_argument("--headless=new")
    o.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
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
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=o)
    # CDP 다운로드 허용
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": DOWNLOAD_DIR
        })
    except Exception:
        pass
    return driver

def accept_cookies_if_present(driver):
    try:
        wait = WebDriverWait(driver, 6)
        texts = ["Accept","I agree","Agree","Allow","Got it","허용","동의","수락","확인",
                 "Akceptovat","Aceptar","Accepter","Accetta","Akzeptieren"]
        for t in texts:
            try:
                btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, f"//button[contains(., '{t}')] | //a[contains(., '{t}')]")
                ))
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.3)
                return
            except:
                pass
    except:
        pass

def goto_page(driver, page):
    url = SEARCH_URL if page == 1 else f"{SEARCH_URL}?pagi={page}"
    driver.get(url)
    WebDriverWait(driver, 20).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    accept_cookies_if_present(driver)
    for _ in range(6):
        driver.execute_script("window.scrollBy(0, 1400);")
        time.sleep(0.4)
    print("📄 current:", driver.current_url)
    time.sleep(1.0)  # SPA 하이드레이션 여유

def newest_audio_file():
    """다운로드 폴더에서 가장 최근 완료된 오디오 파일 Path 반환 (없으면 None)"""
    folder = Path(DOWNLOAD_DIR)
    files = [p for p in folder.glob("*") if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in AUDIO_EXTS]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)

def wait_downloads_done(timeout=90):
    """다운로드 완료까지 기다리고, 새로 생성된 최신 오디오 파일 Path를 반환"""
    start = time.time()
    folder = Path(DOWNLOAD_DIR)
    baseline = {p.name for p in folder.glob("*")}
    last_print = set()
    while time.time() - start < timeout:
        cur = {p.name for p in folder.glob("*")}
        if cur != last_print:
            print("  📂 폴더 상태:", sorted(cur))
            last_print = cur
        # .crdownload가 없고, baseline에 없던 새 오디오 파일이 있으면 그걸 반환
        if not any(name.endswith(".crdownload") for name in cur):
            new_files = [name for name in cur - baseline if any(name.lower().endswith(ext) for ext in AUDIO_EXTS)]
            if new_files:
                path = folder / sorted(new_files, key=lambda n: (folder / n).stat().st_mtime)[-1]
                return path
        time.sleep(1)
    return None

def safe_title_to_filename(title: str, ext: str):
    """제목을 안전한 파일명으로 변환하고 길이 제한 적용"""
    title = title.strip()
    if not title:
        title = "pixabay_audio"
    # 위험 문자 제거
    safe = re.sub(r'[\\/*?:"<>|]', "_", title)
    safe = re.sub(r"\s+", " ", safe).strip()
    safe = safe.replace(" ", "_")
    # 너무 길면 자르기
    safe = safe[:120]
    # 확장자 정규화
    if not ext.startswith("."):
        ext = "." + ext
    return safe + ext.lower()

def make_unique_path(base_path: Path):
    """같은 이름이 있으면 (1), (2) ... 붙여 고유화"""
    if not base_path.exists():
        return base_path
    stem, ext = base_path.stem, base_path.suffix
    for i in range(1, 1000):
        cand = base_path.with_name(f"{stem} ({i}){ext}")
        if not cand.exists():
            return cand
    # 비상용
    return base_path.with_name(f"{stem}_{int(time.time())}{ext}")

def rename_last_download(new_title: str, prefer_ext: str | None, downloaded_path: Path | None):
    """
    방금 내려받은 파일을 제목 기반으로 리네임.
    - prefer_ext: 확장자 힌트 ('.mp3' 등). 없으면 실제 다운로드된 파일의 확장자를 사용.
    - downloaded_path: wait_downloads_done()이 반환한 Path. None이면 최신 파일로 추정.
    """
    folder = Path(DOWNLOAD_DIR)
    if downloaded_path is None or not downloaded_path.exists():
        downloaded_path = newest_audio_file()
        if downloaded_path is None:
            print("  ⚠️ 이름 변경 실패: 새 파일을 찾지 못함")
            return

    ext = prefer_ext.lower() if prefer_ext else downloaded_path.suffix.lower()
    # 제목이 너무 일반적이면 CDN 파일명에서 힌트 추출
    if not new_title or new_title.lower() in {"pixabay_audio", "audio"}:
        # 파일명에서 힌트
        hint = downloaded_path.stem.replace("audio_", "")
        if hint:
            new_title = f"pixabay_{hint}"

    new_name = safe_title_to_filename(new_title, ext)
    new_path = make_unique_path(folder / new_name)
    try:
        downloaded_path.rename(new_path)
        print(f"  ✨ 이름 변경: {downloaded_path.name} → {new_path.name}")
    except Exception as e:
        print("  ⚠️ 이름 변경 실패:", e)

def get_extension_from_url(url: str) -> str | None:
    path = urllib.parse.urlparse(url).path
    for ext in AUDIO_EXTS:
        if path.lower().endswith(ext):
            return ext
    return None

def login_if_needed(driver):
    if not (PIXABAY_EMAIL and PIXABAY_PASS): return
    driver.get(BASE_URL + "accounts/login/")
    wait = WebDriverWait(driver, 20)
    try:
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        pass_input  = driver.find_element(By.NAME, "password")
        email_input.clear(); email_input.send_keys(PIXABAY_EMAIL)
        pass_input.clear();  pass_input.send_keys(PIXABAY_PASS)
        pass_input.send_keys(Keys.ENTER)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href='/sounds/']")))
        print("✅ 로그인 성공(추정)")
    except Exception as e:
        print("⚠️ 로그인 실패(무시하고 진행).", e)

# ---------- 목록: a + button 모두 처리하여 다운로드 (+제목 추출) ----------
def collect_and_download_from_listing(driver, max_left):
    """
    목록 화면에서:
      - <a aria-label='Download' href='...mp3|wav|flac'>는 직접 GET → 제목 추출 후 리네임
      - <button aria-label='Download'> 클릭 → 메뉴에서 포맷 anchor href GET → 리네임
    제목은 같은 카드 내 제목 요소(h2/h3/aria-label 등)에서 추출 시도
    """
    wait = WebDriverWait(driver, 12)
    tried = 0

    # 모든 다운로드 트리거 수집 (a + button + 아이콘 케이스)
    triggers = driver.find_elements(
        By.XPATH,
        "//main//a[@aria-label='Download']"
        " | //main//button[@aria-label='Download']"
        " | //main//*[self::button or self::a][@aria-label='Download']"
        " | //main//button[.//svg[@title='Download'] or .//*[@title='Download']]"
    )
    print(f"🖱️ 목록 다운로드 트리거: {len(triggers)}개")

    for tr in triggers:
        if tried >= max_left:
            break
        try:
            # 카드 컨테이너 및 제목 추출
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tr)
            time.sleep(0.2)

            title_text = None
            try:
                card = tr.find_element(By.XPATH, "./ancestor::*[self::article or self::div][1]")
            except:
                card = None
            if card:
                for xp in [
                    ".//h2", ".//h3", ".//*[@itemprop='name']", ".//a[contains(@href,'/sound-effects/') and @title]"
                ]:
                    try:
                        el = card.find_element(By.XPATH, xp)
                        t = (el.get_attribute("title") or el.text or "").strip()
                        if t:
                            title_text = t
                            break
                    except:
                        continue
            if not title_text:
                title_text = "pixabay_audio"

            tag = (tr.tag_name or "").lower()
            # case 1: <a href="...ext">
            if tag == "a":
                href = tr.get_attribute("href") or ""
                if re.search(r"\.(mp3|wav|flac|m4a|ogg)(\?|$)", href, re.I):
                    print("   → direct GET:", href)
                    driver.get(href)
                    downloaded = wait_downloads_done(45)
                    if downloaded:
                        # 확장자 힌트
                        ext = get_extension_from_url(href) or downloaded.suffix
                        rename_last_download(title_text, ext, downloaded)
                        print("  ✅ (list/direct) 다운로드 완료")
                        tried += 1
                        human_sleep()
                        continue

            # case 2: 버튼 → 클릭 후 메뉴에서 href 추출
            try:
                ActionChains(driver).move_to_element(tr).pause(0.05).click().perform()
            except Exception:
                driver.execute_script("arguments[0].click();", tr)
            time.sleep(0.5)

            # 포맷 anchor 우선
            fmt_anchor = None
            for xp in [
                "//a[contains(@href,'.mp3') or contains(@href,'.wav') or contains(@href,'.flac') or contains(@href,'.m4a') or contains(@href,'.ogg')]",
                # 텍스트만 있는 경우
                "//a[contains(translate(., 'mp3wavflacm4aogg', 'MP3WAVFLACM4AOGG'), 'MP3') "
                " or contains(translate(., 'mp3wavflacm4aogg', 'MP3WAVFLACM4AOGG'), 'WAV') "
                " or contains(translate(., 'mp3wavflacm4aogg', 'MP3WAVFLACM4AOGG'), 'FLAC') "
                " or contains(translate(., 'mp3wavflacm4aogg', 'MP3WAVFLACM4AOGG'), 'M4A') "
                " or contains(translate(., 'mp3wavflacm4aogg', 'MP3WAVFLACM4AOGG'), 'OGG') ]",
            ]:
                try:
                    fmt_anchor = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
                    break
                except:
                    continue

            if fmt_anchor:
                href = fmt_anchor.get_attribute("href") or ""
                if href.startswith("http"):
                    print("   → menu GET:", href)
                    driver.get(href)
                    downloaded = wait_downloads_done(45)
                    if downloaded:
                        ext = get_extension_from_url(href) or downloaded.suffix
                        rename_last_download(title_text, ext, downloaded)
                        print("  ✅ (list/menu) 다운로드 완료")
                        tried += 1
                    else:
                        print("  ⚠️ (list/menu) 타임아웃")
                else:
                    # href가 없으면 진짜 버튼 항목을 클릭
                    clicked = False
                    for xp in [
                        "//button[contains(translate(., 'mp3', 'MP3'), 'MP3')]",
                        "//button[contains(translate(., 'wav', 'WAV'), 'WAV')]",
                        "//button[contains(translate(., 'flac', 'FLAC'), 'FLAC')]",
                        "//button[contains(translate(., 'm4a', 'M4A'), 'M4A')]",
                        "//button[contains(translate(., 'ogg', 'OGG'), 'OGG')]",
                        "//button[contains(., 'Original')]",
                    ]:
                        try:
                            el = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
                            driver.execute_script("arguments[0].click();", el)
                            clicked = True
                            break
                        except:
                            continue
                    downloaded = wait_downloads_done(45) if clicked else None
                    if downloaded:
                        rename_last_download(title_text, None, downloaded)
                        print("  ✅ (list/button) 다운로드 완료")
                        tried += 1
                    else:
                        print("  ⚠️ (list/button) 타임아웃")
            else:
                print("   … 포맷 항목을 못 찾음 (이 항목 스킵)")

            human_sleep()

        except Exception as e:
            print("  ⚠️ 목록 처리 에러, 스킵:", e)
            continue

    return tried

# ---------- 폴백: 상세 페이지 HTML에서 직접 파일 URL 파싱 (+제목 추출, 리네임) ----------
def download_via_detail_page(driver, detail_url):
    """
    버튼 누르지 않고 page_source에서 CDN 파일 URL(.mp3/.wav/.flac 등)을 추출해 GET,
    다운로드 후 상세페이지의 제목(h1/og:title)을 파일명으로 리네임
    """
    wait = WebDriverWait(driver, 15)

    def extract_urls(html: str):
        urls = re.findall(
            r"https://cdn\.pixabay\.com/download/audio/[^\s\"'<>]+?\.(?:mp3|wav|flac|m4a|ogg)",
            html, flags=re.I
        )
        # 구조화 데이터/메타
        urls += re.findall(r'"contentUrl"\s*:\s*"([^"]+\.(?:mp3|wav|flac|m4a|ogg))"', html, flags=re.I)
        urls += re.findall(r'"url"\s*:\s*"([^"]+\.(?:mp3|wav|flac|m4a|ogg))"', html, flags=re.I)
        urls = [u for u in urls if u.startswith("http")]
        # 중복 제거(순서 유지)
        seen, uniq = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u); uniq.append(u)
        return uniq

    def extract_title(html: str):
        # 우선 og:title
        m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, flags=re.I)
        if m:
            return m.group(1).strip()
        # 그다음 <h1>
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I|re.S)
        if m:
            # 태그 제거
            text = re.sub(r"<[^>]+>", " ", m.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text
        return "pixabay_audio"

    driver.get(detail_url)
    try:
        WebDriverWait(driver, 20).until(lambda d: d.execute_script("return document.readyState") == "complete")
    except:
        pass
    accept_cookies_if_present(driver)
    time.sleep(0.8)

    html = driver.page_source
    title = extract_title(html)
    urls  = extract_urls(html)

    if not urls:
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 1200);"); time.sleep(0.6)
            html = driver.page_source
            urls = extract_urls(html)
            if urls: break

    if urls:
        file_url = urls[0]
        print("   → parsed file url:", file_url)
        driver.get(file_url)
        downloaded = wait_downloads_done(60)
        if downloaded:
            ext = get_extension_from_url(file_url) or downloaded.suffix
            rename_last_download(title, ext, downloaded)
            return True

    # 마지막으로 Download 버튼 한번 눌러서 다시 파싱
    try:
        btn = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[@aria-label='Download'] | //button[normalize-space()='Download'] | //a[contains(.,'Download')]"
        )))
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(0.6)
        html = driver.page_source
        urls = extract_urls(html)
        if urls:
            file_url = urls[0]
            print("   → parsed file url (after button):", file_url)
            driver.get(file_url)
            downloaded = wait_downloads_done(60)
            if downloaded:
                ext = get_extension_from_url(file_url) or downloaded.suffix
                rename_last_download(title, ext, downloaded)
                return True
    except:
        pass

    print("   ⚠️ detail page parsing 실패")
    return False

# ---------- 목록 HTML에서 상세 링크 정규식 추출 (폴백용) ----------
def collect_detail_links_from_list(driver):
    html = driver.page_source
    rels = re.findall(r'"(/sound-effects/[a-z0-9\-]+-\d+/)"', html, flags=re.I)
    abss = re.findall(r'https://pixabay\.com/sound-effects/[a-z0-9\-]+-\d+/', html, flags=re.I)
    links = [f"https://pixabay.com{p}" for p in rels] + abss
    seen, uniq = set(), []
    for u in links:
        u = u if u.endswith("/") else u + "/"
        if "/sound-effects/search/" in u:
            continue
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq

def main():
    print("▶ main() 시작")
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    d = build_driver()
    try:
        if PIXABAY_EMAIL and PIXABAY_PASS:
            login_if_needed(d)

        downloaded = 0

        for p in range(1, MAX_PAGES + 1):
            if downloaded >= MAX_ITEMS: break

            goto_page(d, p)

            left = MAX_ITEMS - downloaded
            got = collect_and_download_from_listing(d, left)
            downloaded += got
            print(f"↳ 목록 페이지 {p}에서 {got}개 완료 (누적 {downloaded})")

            if downloaded >= MAX_ITEMS:
                break

            # 폴백: 상세페이지 파싱 방식
            details = collect_detail_links_from_list(d)
            print(f"🛟 fallback detail links: {len(details)}")
            for detail_url in details:
                if downloaded >= MAX_ITEMS: break
                ok = download_via_detail_page(d, detail_url)
                if ok:
                    print("  ✅ (fallback) 다운로드 완료")
                    downloaded += 1
                else:
                    print("  ⚠️ (fallback) 실패/타임아웃")
                human_sleep()

        print(f"\n총 {downloaded}개 다운로드 시도 완료.")
        print(f"저장 폴더: {DOWNLOAD_DIR}")

    finally:
        d.quit()

if __name__ == "__main__":
    main()
