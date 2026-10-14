"""Fetch clips (yt-dlp sections) and Commons images listed in a batch file; write a manifest that records
title, uploader/channel, upload date, licence and any error, so the result can be read from the branch."""
import json, os, subprocess, sys, time, urllib.parse, urllib.request

batch, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
manifest = []
UA = {"User-Agent": "SightSagaDownloader/1.0 (public-footage archiving; github.com/vinodkumarniper/sightsaga-downloader)"}

def yt(key, url, start, dur, subs_only=False):
    rec = {"key": key, "kind": "subs" if subs_only else "yt", "source": url}
    try:
        meta = subprocess.run(["yt-dlp", "-J", "--no-playlist", url], capture_output=True, text=True, timeout=180)
        if meta.returncode == 0:
            j = json.loads(meta.stdout)
            rec.update({k: j.get(k) for k in ("title", "uploader", "channel", "upload_date", "duration", "webpage_url")})
        else:
            rec["meta_error"] = meta.stderr.strip()[-600:]
        if subs_only:
            cmd = ["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*", "--sub-format", "vtt",
                   "-o", os.path.join(out, key + ".%(ext)s"), url]
        else:
            cmd = ["yt-dlp", "--no-playlist", "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/b",
                   "--merge-output-format", "mp4", "--download-sections", "*%s-%s" % (start, int(start) + int(dur)),
                   "-o", os.path.join(out, key + ".%(ext)s"), url]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        rec["ok"] = r.returncode == 0
        if r.returncode != 0: rec["error"] = r.stderr.strip()[-800:]
    except Exception as e:
        rec["ok"] = False; rec["error"] = repr(e)
    manifest.append(rec)

def get(url, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90)
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1: time.sleep(6 * (i + 1)); continue
            raise

def commons(key, query, n, ftype="bitmap"):
    time.sleep(2)
    api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrsearch": query + " filetype:" + ftype,
        "gsrnamespace": 6, "gsrlimit": int(n) * 3, "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1600})
    try:
        data = json.load(get(api))
        pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        got = 0
        for p in pages:
            if got >= int(n): break
            ii = (p.get("imageinfo") or [{}])[0]; md = ii.get("extmetadata", {})
            lic = md.get("LicenseShortName", {}).get("value", "")
            if not any(x in lic for x in ("CC", "Public domain", "PD")): continue
            src = (ii.get("thumburl") or ii.get("url")) if ftype == "bitmap" else ii.get("url")
            if ftype != "bitmap" and ii.get("size", 0) > 90_000_000: continue
            ext = os.path.splitext(urllib.parse.urlparse(src).path)[1] or ".jpg"
            fn = "%s_%d%s" % (key, got + 1, ext)
            time.sleep(1.5)
            with get(src) as r, open(os.path.join(out, fn), "wb") as f:
                f.write(r.read())
            manifest.append({"key": key, "kind": "commons", "file": fn, "title": p.get("title"), "license": lic,
                             "artist": md.get("Artist", {}).get("value", "")[:200], "date": md.get("DateTimeOriginal", {}).get("value", "")[:40],
                             "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(p.get("title", "").replace(" ", "_")), "ok": True})
            got += 1
        if got == 0: manifest.append({"key": key, "kind": "commons", "ok": False, "error": "no CC/PD results", "query": query})
    except Exception as e:
        manifest.append({"key": key, "kind": "commons", "ok": False, "error": repr(e), "query": query})

for line in open(batch, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"): continue
    kind, key, src, a, b = line.split("|")
    if kind == "yt": yt(key, src, a, b)
    elif kind == "subs": yt(key, src, 0, 0, subs_only=True)
    elif kind == "commons": commons(key, src, a, b if b not in ("", "0") else "bitmap")

json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=1, ensure_ascii=False)
print(json.dumps(manifest, indent=1)[:4000])
