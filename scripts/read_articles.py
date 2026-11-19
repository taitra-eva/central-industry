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

def clean_title(value):
    """Normalize the full title while tolerating site suffixes and punctuation."""
    import html
    value = html.unescape(value or "").casefold()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def story_title(value):
    # Google News often appends " - Publisher" to the original title.
    return re.sub(r"\s+[-–|｜]\s+[^-–|｜]{2,65}$", "", value or "").strip()


def title_matches(wanted, found, minimum=0.78):
    """Require high textual agreement, avoiding topic-only false positives."""
    from difflib import SequenceMatcher
    a, b = clean_title(story_title(wanted)), clean_title(story_title(found))
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) >= 28 and (a in b or b in a):
        return True
    return SequenceMatcher(None, a, b).ratio() >= minimum


def search_original_articles(title, source):
    """Find candidate direct links using free RSS searches, then verify page titles."""
    import feedparser
    headline = story_title(title)
    if len(headline) < 12:
        return []
    queries = ['"' + headline + '"']
    if source:
        queries.insert(0, '"' + headline + '" "' + source + '"')
    candidates = []
    seen = set()
    for query in queries:
        try:
            response = session.get("https://www.bing.com/search",
                                   params={"q":query, "format":"rss"}, timeout=12)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            for entry in feed.entries[:10]:
                url = entry.get("link","")
                host = (urlparse(url).hostname or "").lower()
                if (not url.startswith("https://") or not host or
                        google_link(url) or url in seen):
                    continue
                if not title_matches(title,entry.get("title","")):
                    continue
                seen.add(url)
                candidates.append(url)
                if len(candidates) >= 4:
                    return candidates
        except (requests.RequestException,ValueError) as exc:
            print("Free original-article search failed:",str(exc)[:140])
    return candidates


def read_public_page(url, expected_title=None):
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
        from charset_normalizer import from_bytes
        html = str(from_bytes(payload).best() or payload.decode("utf-8", errors="replace"))
        if expected_title:
            metadata = trafilatura.extract_metadata(html)
            page_title = metadata.title if metadata else ""
            if not title_matches(expected_title, page_title):
                return {"access_status":"unresolved",
                        "read_reason":"Search result page title differs from the original news headline"}
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
        if resolved:
            result=read_public_page(resolved)
        else:
            result={"access_status":"unresolved","read_reason":"Encoded Google News URL could not be decoded"}
        # If direct reading fails, try independent free publisher discovery.
        # Every candidate MUST pass a real page-title match and article-body check.
        if result["access_status"] != "readable" and google_link(item.get("url","")):
            for candidate in search_original_articles(item.get("title",""),item.get("source","")):
                trial=read_public_page(candidate,expected_title=item.get("title",""))
                if trial["access_status"]=="readable":
                    result=trial
                    break
        if result["access_status"]=="unresolved":
            result["read_reason"]="Google News decoding and verified free publisher search did not resolve the article"
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
