"""Search Wikimedia Commons and download freely licensed images with licence metadata.
Usage: python scripts/commons_fetch.py batches/<file>.txt downloads/
Batch line: slug|search query|max_results
"""
import json, re, sys, time, urllib.parse, urllib.request, pathlib
API = "https://commons.wikimedia.org/w/api.php"
UA = "SightSagaAssetFetcher/1.0 (https://github.com/vinodkumarniper/sightsaga-downloader)"
OK = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? [1-4]\.0|cc by(-sa)? [1-4]\.0 .*|cc by(-sa)?-[1-4]\.0|godl.*|attribution|no restrictions)", re.I)
def get(params):
    params.update(format="json", formatversion="2")
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)
out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
manifest = []
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"): continue
    slug, q, n = line.split("|"); n = int(n)
    try:
        d = get(dict(action="query", generator="search", gsrsearch="filetype:bitmap " + q, gsrnamespace=6, gsrlimit=25,
                     prop="imageinfo", iiprop="url|size|extmetadata|mime", iiurlwidth=1600))
    except Exception as e:
        manifest.append(dict(slug=slug, query=q, error=str(e))); continue
    pages = sorted(d.get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
    got = 0
    for p in pages:
        if got >= n: break
        ii = (p.get("imageinfo") or [{}])[0]; md = ii.get("extmetadata", {})
        lic = re.sub("<[^>]+>", "", md.get("LicenseShortName", {}).get("value", "")).strip()
        if not OK.match(lic) or ii.get("width", 0) < 900: continue
        url = ii.get("thumburl") or ii.get("url")
        ext = ".png" if ii.get("mime") == "image/png" else ".jpg"
        name = f"{slug}_{got+1:02d}{ext}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r: (out / name).write_bytes(r.read())
        except Exception as e:
            manifest.append(dict(slug=slug, title=p["title"], error=str(e))); continue
        manifest.append(dict(file=name, slug=slug, query=q, title=p["title"], license=lic,
            artist=re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", "")).strip()[:200],
            credit=re.sub("<[^>]+>", "", md.get("Credit", {}).get("value", "")).strip()[:200],
            date=re.sub("<[^>]+>", "", md.get("DateTimeOriginal", {}).get("value", "")).strip()[:40],
            desc=re.sub("<[^>]+>", "", md.get("ImageDescription", {}).get("value", "")).strip()[:300],
            page=ii.get("descriptionurl"), w=ii.get("width"), h=ii.get("height")))
        got += 1; time.sleep(0.5)
(out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"{sum(1 for m in manifest if 'file' in m)} files")
