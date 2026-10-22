"""Fetch public-domain / openly licensed assets for the SightSaga F-16 wheat explainer.

Runs on GitHub Actions. Writes everything into ./downloads with a manifest.jsonl
recording source URL, title, author and licence for every file.
"""
import json
import re
import subprocess
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


def get(url, binary=False, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def slug(s, n=50):
    return re.sub(r"[^A-Za-z0-9]+", "_", s)[:n].strip("_")


# ---------- 1. Wikimedia Commons search ----------
COMMONS_QUERIES = [
    ("paf_f16", "Pakistan Air Force F-16", 10),
    ("paf_f16b", "PAF F-16 Fighting Falcon", 6),
    ("amarg", "Davis-Monthan AMARG aerial view aircraft storage", 8),
    ("amarg_f16", "AMARC F-16 storage Davis-Monthan", 6),
    ("dm_gate", "Davis-Monthan Air Force Base sign", 3),
    ("pressler", "Larry Pressler", 2),
    ("clinton_sharif", "Bill Clinton Nawaz Sharif", 4),
    ("sharif_1998", "Nawaz Sharif 1998", 3),
    ("wheat_harvest", "wheat harvest combine Kansas", 4),
    ("wheat_ship", "grain ship loading wheat port", 4),
    ("wheat_grain", "wheat grains closeup", 3),
    ("f16_factory", "F-16 production line Fort Worth", 4),
    ("rnzaf_f16", "New Zealand F-16 lease", 2),
    ("f16_takeoff", "F-16 takeoff afterburner", 4),
]


def commons():
    api = "https://commons.wikimedia.org/w/api.php"
    for tag, q, n in COMMONS_QUERIES:
        params = {
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": "6", "gsrlimit": str(n),
            "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": "1600",
        }
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


# ---------- 2. DoD photo pages (igphoto) ----------
DOD_PAGES = [
    "https://www.afcent.af.mil/News/Photos/igphoto/2000278236/",
    "https://www.afcent.af.mil/News/Photos/igphoto/2000278237/",
    "https://www.afcent.af.mil/News/Art/igphoto/2000278243/",
    "https://www.af.mil/News/Article-Display/Article/132471/pakistan-gets-two-upgraded-f-16s/",
]


def dod_photos():
    for page in DOD_PAGES:
        try:
            html = get(page)
        except Exception as e:  # noqa: BLE001
            log({"kind": "dod", "page": page, "status": "FAIL", "error": str(e)})
            continue
        urls = sorted(set(re.findall(r"https://media\.defense\.gov/[^\"'\s<>]+?\.(?:jpg|JPG|jpeg|png)", html)))
        title = re.search(r"<title>(.*?)</title>", html, re.S)
        for j, u in enumerate(urls[:4]):
            name = f"dod_{slug(page.split('/')[-2] or page.split('/')[-1], 30)}_{j}{Path(u).suffix.lower()}"
            try:
                (OUT / name).write_bytes(get(u, binary=True))
                log({"kind": "dod", "file": name, "page": page, "src": u,
                     "title": title.group(1).strip() if title else "", "license": "US Government work (public domain)"})
            except Exception as e:  # noqa: BLE001
                log({"kind": "dod", "page": page, "src": u, "status": "FAIL", "error": str(e)})


# ---------- 3. DVIDS video ----------
DVIDS_IDS = ["953392", "953035", "953493", "953494", "696338"]


def dvids():
    for vid in DVIDS_IDS:
        page = f"https://www.dvidshub.net/video/{vid}"
        outdir = OUT / f"dvids_{vid}"
        outdir.mkdir(exist_ok=True)
        ok = False
        try:
            r = subprocess.run(["yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--no-playlist",
                                "-o", str(outdir / "%(title).60s.%(ext)s"), "--write-info-json", page],
                               capture_output=True, text=True, timeout=900)
            ok = r.returncode == 0 and any(outdir.glob("*.mp4"))
            if not ok:
                print(r.stdout[-1500:], r.stderr[-1500:])
        except Exception as e:  # noqa: BLE001
            print("yt-dlp error", e)
        title = ""
        if not ok:
            try:
                html = get(page)
                t = re.search(r"<title>(.*?)</title>", html, re.S)
                title = t.group(1).strip() if t else ""
                mp4s = re.findall(r"https://[^\"'\s<>]+?\.mp4", html)
                mp4s = sorted(set(mp4s), key=lambda u: ("1080" not in u, "720" not in u))
                if mp4s:
                    (outdir / f"dvids_{vid}.mp4").write_bytes(get(mp4s[0], binary=True, timeout=600))
                    ok = True
            except Exception as e:  # noqa: BLE001
                print("html fallback error", e)
        log({"kind": "dvids", "id": vid, "page": page, "status": "OK" if ok else "FAIL", "title": title,
             "license": "US Government work (public domain); credit DVIDS"})


# ---------- 4. Document screenshots ----------
DOCS = [
    ("doc_wh_19981221", "https://clintonwhitehouse6.archives.gov/1998/12/1998-12-21-statement-by-the-press-secretary-on-pakistani-f-16s.html"),
    ("doc_wh_19981204", "https://clintonwhitehouse6.archives.gov/1998/12/1998-12-04-joint-statement-from-pakistan-and-the-united-states.html"),
    ("doc_aca_199811", "https://www.armscontrol.org/act/1998-11/us-repay-pakistan-undelivered-f-16s"),
    ("doc_fp_2011", "https://foreignpolicy.com/2011/02/03/the-u-s-pakistan-f-16-fiasco/"),
    ("doc_theprint_2019", "https://theprint.in/defence/days-after-trump-imran-meet-us-approves-deal-to-monitor-24x7-pakistans-f-16-fighter-jets/268749/"),
    ("doc_arabnews_2025", "https://www.arabnews.pk/pakistan/us-approves-sale-of-686-million-tech-upgrade-equipment-for-pakistans-f-16-fighter-jets-2625810"),
    ("doc_dawn_2026", "https://www.dawn.com/news/1996840"),
    ("doc_f16net_paf", "https://www.f-16.net/f-16_users_article14.html"),
    ("doc_crs_2013", "https://www.everycrsreport.com/files/20130307_7-5415_d1a10a2f60b12c9e8ae664d037bb9b595088dd5b.html"),
]


def screenshots():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        for dpr, w, h, suffix in [(2, 900, 1600, "")]:
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr,
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
                    pg.screenshot(path=str(OUT / f"{name}{suffix}_top.png"))
                    pg.screenshot(path=str(OUT / f"{name}{suffix}_full.jpg"), full_page=True, type="jpeg", quality=80)
                    (OUT / f"{name}.txt").write_text(pg.inner_text("body")[:20000], encoding="utf-8")
                    log({"kind": "screenshot", "file": name, "url": url, "status": "OK"})
                except Exception as e:  # noqa: BLE001
                    log({"kind": "screenshot", "file": name, "url": url, "status": "FAIL", "error": str(e)[:300]})
                finally:
                    pg.close()
        b.close()


if __name__ == "__main__":
    steps = sys.argv[1:] or ["commons", "dod", "dvids", "screenshots"]
    for s in steps:
        try:
            {"commons": commons, "dod": dod_photos, "dvids": dvids, "screenshots": screenshots}[s]()
        except Exception as e:  # noqa: BLE001
            log({"kind": s, "status": "STEP_FAIL", "error": str(e)[:500]})
