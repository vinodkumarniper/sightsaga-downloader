"""Fetch openly licensed photos, source-page screenshots and the VO for the SightSaga Tawang Decode reel.

Runs on GitHub Actions. Writes everything into ./downloads with manifest.jsonl (source, author, licence).
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("downloads")
OUT.mkdir(exist_ok=True)
MANIFEST = OUT / "manifest.jsonl"
UA = "SightSagaResearchBot/1.0 (https://github.com/vinodkumarniper/sightsaga-downloader)"


def log(rec):
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(rec)


def get(url, binary=False, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def slug(s, n=50):
    return re.sub(r"[^A-Za-z0-9]+", "_", s)[:n].strip("_")


COMMONS_QUERIES = [
    ("dl_portrait", "14th Dalai Lama portrait", 8),
    ("dl_recent", "Dalai Lama 2019 Dharamshala", 4),
    ("tw_monastery", "Tawang Monastery", 10),
    ("tw_town", "Tawang Arunachal Pradesh landscape", 4),
    ("dl_1959", "Dalai Lama 1959 India", 6),
    ("dl_young", "14th Dalai Lama 1950s", 4),
    ("panchen", "Gedhun Choekyi Nyima", 4),
    ("golden_urn", "Golden Urn Qing reincarnation", 3),
    ("tsangyang", "Tsangyang Gyatso 6th Dalai Lama", 3),
    ("urgelling", "Urgelling Monastery Tawang", 3),
]


def commons():
    api = "https://commons.wikimedia.org/w/api.php"
    for tag, q, n in COMMONS_QUERIES:
        params = {"action": "query", "format": "json", "generator": "search",
                  "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": "6", "gsrlimit": str(n),
                  "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": "1600"}
        try:
            data = json.loads(get(api + "?" + urllib.parse.urlencode(params)))
        except Exception as e:  # noqa: BLE001
            log({"kind": "commons", "tag": tag, "status": "FAIL", "error": str(e)})
            continue
        pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        for i, p in enumerate(pages):
            ii = (p.get("imageinfo") or [{}])[0]
            url = ii.get("thumburl") or ii.get("url")
            if not url:
                continue
            md = ii.get("extmetadata", {})
            ext = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".jpg"
            name = f"commons_{tag}_{i:02d}_{slug(p['title'][5:], 40)}{ext}"
            try:
                (OUT / name).write_bytes(get(url, binary=True))
                log({"kind": "commons", "file": name, "title": p["title"], "page": ii.get("descriptionurl"),
                     "license": md.get("LicenseShortName", {}).get("value"),
                     "artist": re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", ""))[:200],
                     "date": md.get("DateTimeOriginal", {}).get("value", "")[:40],
                     "desc": re.sub("<[^>]+>", "", md.get("ImageDescription", {}).get("value", ""))[:300]})
            except Exception as e:  # noqa: BLE001
                log({"kind": "commons", "file": name, "status": "FAIL", "error": str(e)})


WIKI_PAGES = ["Gedhun_Choekyi_Nyima", "14th_Dalai_Lama", "Tawang_Monastery", "Tsangyang_Gyatso",
              "Gyaincain_Norbu", "1959_Tibetan_uprising", "Tawang"]


def wiki_lead_images():
    api = "https://en.wikipedia.org/w/api.php"
    for t in WIKI_PAGES:
        params = {"action": "query", "format": "json", "titles": t, "prop": "pageimages",
                  "piprop": "original|name"}
        try:
            data = json.loads(get(api + "?" + urllib.parse.urlencode(params)))
            for p in data["query"]["pages"].values():
                src = p.get("original", {}).get("source")
                if not src:
                    log({"kind": "wiki", "page": t, "status": "NO_IMAGE"})
                    continue
                name = f"wiki_{slug(t, 40)}{Path(urllib.parse.urlparse(src).path).suffix.lower()}"
                (OUT / name).write_bytes(get(src, binary=True))
                log({"kind": "wiki", "file": name, "page": f"https://en.wikipedia.org/wiki/{t}",
                     "src": src, "pageimage": p.get("pageimage")})
        except Exception as e:  # noqa: BLE001
            log({"kind": "wiki", "page": t, "status": "FAIL", "error": str(e)})


DOCS = [
    ("doc_tibetanreview_27names", "https://www.tibetanreview.net/china-claims-its-zangnan-not-arunachal-pradesh-slams-indias-release-of-standard-names-for-27-locations/"),
    ("doc_arunachaltimes_apr2026", "https://arunachaltimes.in/index.php/2026/04/13/india-rejects-chinas-renaming-places-in-arunachal/"),
    ("doc_indiatodayne_nullvoid", "https://www.indiatodayne.in/arunachal-pradesh/story/china-rejects-indias-naming-of-27-arunachal-places-calls-move-illegal-null-and-void-1436119-2026-08-11"),
    ("doc_newsonair_mea_2025", "https://www.newsonair.gov.in/india-rejects-chinas-renaming-of-arunachal-pradesh-locations-calls-it-absurd-unacceptable"),
    ("doc_ict_statement_2025", "https://savetibet.org/14th-dalai-lama-lays-out-the-future-of-his-institution-in-new-statement-clarifying-succession-direction/"),
    ("doc_rfa_freeworld", "https://www.rfa.org/english/tibet/2025/03/12/china-tibet-dalai-lama-succession/"),
    ("doc_mfa_apr14_2026", "https://www.mfa.gov.cn/eng/xw/fyrbt/lxjzh/202604/t20260414_11891740.html"),
    ("doc_eaf_succession", "https://eastasiaforum.org/2026/09/12/why-china-cannot-choose-the-next-dalai-lama/"),
]


def screenshots():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 900, "height": 1600}, device_scale_factor=2,
                            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
        for name, url in DOCS:
            pg = ctx.new_page()
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(4000)
                for sel in ["button:has-text('Accept')", "button:has-text('I agree')", "button:has-text('Agree')",
                            "button:has-text('Got it')", "button:has-text('Close')"]:
                    try:
                        pg.click(sel, timeout=1500)
                    except Exception:  # noqa: BLE001
                        pass
                pg.screenshot(path=str(OUT / f"{name}_top.png"))
                pg.screenshot(path=str(OUT / f"{name}_full.jpg"), full_page=True, type="jpeg", quality=80)
                (OUT / f"{name}.txt").write_text(pg.inner_text("body")[:20000], encoding="utf-8")
                log({"kind": "screenshot", "file": name, "url": url, "status": "OK"})
            except Exception as e:  # noqa: BLE001
                log({"kind": "screenshot", "file": name, "url": url, "status": "FAIL", "error": str(e)[:300]})
            finally:
                pg.close()
        b.close()


def vo():
    for line in Path("batches/tawang-vo-20261025.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, url = line.split("|", 1)
        try:
            (OUT / name).write_bytes(get(url, binary=True))
            log({"kind": "vo", "file": name, "status": "OK"})
        except Exception as e:  # noqa: BLE001
            log({"kind": "vo", "file": name, "status": "FAIL", "error": str(e)[:200]})


if __name__ == "__main__":
    steps = sys.argv[1:] or ["vo", "commons", "wiki", "screenshots"]
    for s in steps:
        try:
            {"vo": vo, "commons": commons, "wiki": wiki_lead_images, "screenshots": screenshots}[s]()
        except Exception as e:  # noqa: BLE001
            log({"kind": "step", "step": s, "status": "FAIL", "error": str(e)[:300]})
