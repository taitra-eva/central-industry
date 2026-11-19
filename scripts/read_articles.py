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
LIMIT = 65  # daily attempt cap, distributed across Taiwan and overseas regions
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
        from googlenewsdecoder import gnewsdecoder
        r = gnewsdecoder(link, interval=0)
        if isinstance(r, dict) and r.get("status") and r.get("decoded_url", "").startswith("http"):
            return r["decoded_url"]
    except Exception as ex:
        print("Google News URL resolver failed:", str(ex)[:160])
    return None

def read_public_page(url):
    try:
        response = session.get(url, timeout=10, allow_redirects=True, stream=True)
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
        # Do not mistake a subscription prompt surrounded by recommendations
        # for a freely accessible full article. Do not bypass the paywall.
        if text:
            paywall_phrases=("此篇限「暢讀會員", "升級付費方案，即可暢讀",
                             "訂閱會員才能閱讀全文", "訂閱後可閱讀完整內容",
                             "subscribe to read the full article", "sign in to read the full article")
            if any(phrase.casefold() in text.casefold() for phrase in paywall_phrases):
                return {"access_status":"blocked","read_reason":"Article body is behind subscription/login"}
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
    # Balance original-article attempts across regions rather than letting a
    # large Taiwan queue consume the entire daily allowance. Already-readable
    # items with a saved excerpt need not be fetched again.
    quotas={"台灣":24,"歐洲":12,"北美":12,"亞洲":12,"其他":5}
    # Prefer new articles without AI summaries; retain explicit source URLs and retry
    # previously unreadable publisher pages after failed Google News resolution.
    existing_insights=ROOT/"data/insights.json"
    already_summarized=set()
    if existing_insights.exists():
        try:
            already_summarized={id for record in json.loads(existing_insights.read_text(encoding="utf-8")).get("items",[]) for id in record.get("article_ids",[])}
        except (ValueError,OSError):pass
    candidates=[n for n in rows if n["id"] not in already_summarized or (n.get("source_url") and n.get("access_status")!="readable")]
    candidates.sort(key=lambda x:(x.get("access_status")=="readable" and bool(x.get("summary_zh")),-(datetime.fromisoformat(x.get("published_at") or x["discovered_at"]).timestamp())))

    chosen=[]
    for region,quota in quotas.items():
        picked=[n for n in candidates if n.get("region")==region][:quota]
        chosen.extend(picked)
    chosen_ids={x["id"] for x in chosen}
    chosen.extend(n for n in candidates if n["id"] not in chosen_ids)
    candidates=chosen[:LIMIT]
    texts={}
    stats={}
    for item in candidates:
        resolved=item.get("source_url") or publisher_url(item["url"])
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
            item.pop("read_reason",None)
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
    print("Publisher reads by region:",json.dumps({r:sum(x.get("region")==r for x in candidates) for r in quotas},ensure_ascii=False))
    print("Saved ephemeral article texts:",len(texts))
    print("Original URL resolution:",sum(bool(x.get("source_url")) for x in rows),"of",len(rows),"articles")

if __name__=="__main__":
    main()
