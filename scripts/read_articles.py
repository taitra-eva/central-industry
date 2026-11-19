"""Read the publisher article when public access allows it.

This is a REAL network fetch of the source page, not an RSS-only shortcut.
Never bypass logins/paywalls. Keep extracted bodies in an untracked temporary
workspace file; publish only short excerpts and metadata to the website.
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timezone

import requests
import trafilatura

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/news.json"
TEMP = ROOT / ".article_texts.json"
UA = "Mozilla/5.0 (compatible; CentralIndustryNews/1.0; public article reader)"
session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
LIMIT = 90  # bounded daily network work; prioritize Taiwan and current news
MAX_BYTES = 2_500_000

def google_link(url):
    return urlparse(url).netloc.endswith("news.google.com")

def publisher_url(link):
    """Attempt actual Google News -> publisher resolution; no guessed URL."""
    if not google_link(link):
        return link
    parsed = urlparse(link)
    direct = parse_qs(parsed.query).get("url", [])
    if direct and direct[0].startswith("https://"):
        return direct[0]
    # Google News RSS encoded links need a resolver. Optional library is preferred,
    # but failure must be observable, not silently treated as publisher content.
    try:
        from googlenewsdecoder import new_decoderv1
        r = new_decoderv1(link, interval=0)
        if isinstance(r, dict) and r.get("status") and r.get("decoded_url", "").startswith("http"):
            return r["decoded_url"]
    except Exception as ex:
        print("Google News URL resolver failed:", str(ex)[:160])
    return None

def read_public_page(url):
    try:
        response = session.get(url, timeout=16, allow_redirects=True, stream=True)
        status = response.status_code
        if status in (401,403,451):
            return {"access_status":"blocked","read_reason":"HTTP "+str(status)}
        if status != 200:
            return {"access_status":"read_failed","read_reason":"HTTP "+str(status)}
        if google_link(response.url) or urlparse(response.url).netloc.endswith("accounts.google.com"):
            return {"access_status":"unresolved","read_reason":"Publisher URL did not resolve"}
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return {"access_status":"unsupported","read_reason":"Not an HTML article"}
        payload = response.raw.read(MAX_BYTES + 1, decode_content=True)
        if len(payload) > MAX_BYTES:
            return {"access_status":"unsupported","read_reason":"Document larger than permitted fetch size"}
        response.encoding = response.apparent_encoding or response.encoding
        html = payload.decode(response.encoding or "utf-8", errors="replace")
        text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
        if not text or len(text.strip()) < 250:
            return {"access_status":"insufficient_text","read_reason":"Page retrieved but substantial article body not extracted"}
        return {"access_status":"readable","source_url":response.url,"body":text.strip()}
    except requests.RequestException as ex:
        return {"access_status":"read_failed","read_reason":str(ex)[:160]}
    except Exception as ex:
        return {"access_status":"read_failed","read_reason":str(ex)[:160]}

def main():
    d=json.loads(DB.read_text(encoding="utf-8"))
    rows=d.get("items", [])
    # Re-check articles not previously read; prefer Taiwan and newer articles.
    candidates=[n for n in rows if n.get("access_status") != "readable"]
    candidates.sort(key=lambda x:(x.get("region") != "台灣", -(datetime.fromisoformat(x.get("published_at") or x["discovered_at"]).timestamp())))
    texts={}
    stats={}
    for item in candidates[:LIMIT]:
        resolved=publisher_url(item["url"])
        if not resolved:
            result={"access_status":"unresolved","read_reason":"Google News did not provide a usable publisher URL"}
        else:
            result=read_public_page(resolved)
        item["access_status"]=result["access_status"]
        item["read_checked_at"]=datetime.now(timezone.utc).isoformat()
        if result.get("source_url"):
            item["source_url"]=result["source_url"]
        if result.get("read_reason"):
            item["read_reason"]=result["read_reason"]
        if result.get("body"):
            body=result["body"]
            item["body_length"]=len(body)
            # This sample is for evidence checking, not a copy of the full article.
            item["excerpt"]=body[:320].rsplit(" ", 1)[0]
            texts[item["id"]]=body[:24000]  # temporary, never committed
        stats[result["access_status"]]=stats.get(result["access_status"],0)+1
        time.sleep(0.15)
    TEMP.write_text(json.dumps(texts,ensure_ascii=False),encoding="utf-8")
    DB.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Publisher article read results:",json.dumps(stats,ensure_ascii=False))
    print("Saved ephemeral article texts:",len(texts))

if __name__=="__main__":
    main()
