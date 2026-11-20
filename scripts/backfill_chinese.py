"""Backfill ONLY existing Chinese-language articles via verified Bing publisher links.

Never collects new stories. Never guesses original article URLs. Existing summaries
are preserved. Unreadable/blocked/mismatched publisher articles are skipped.
Save temporary full texts for Groq within this same GitHub Actions job.
"""
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
import feedparser
from read_articles import (
    ROOT, DB, TEMP, session, google_link, publisher_url,
    read_public_page, story_title, title_matches,
)

INSIGHTS=ROOT/"data/insights.json"
LIMIT=int(os.environ.get("ZH_BACKFILL_MAX","45"))
BING_DELAY=float(os.environ.get("ZH_BING_DELAY","1.5"))
# Original media identity is mandatory, to avoid a different event
# or unrelated syndicated coverage being mistaken for the user's article.
PUBLISHER_HOSTS={
    "經濟日報":("money.udn.com",),
    "聯合新聞網":("udn.com",),
    "工商時報":("ctee.com.tw","chinatimes.com"),
    "中央社 CNA":("cna.com.tw",),
    "TechNews 科技新報":("technews.tw",),
    "MoneyDJ":("moneydj.com",),
    "CTIMES":("ctimes.com.tw",),
    "輪彥國際有限公司":("wheelgiant.com.tw",),
    "taiwandrones.org":("taiwandrones.org",),
    "M&A Online":("maonline.jp",),
}
SKIP_TITLES=("所有消息|", "所有消息 |")

def is_chinese_news(row):
    if row.get("region")=="台灣":
        return True
    title=row.get("title","")
    return sum("\u4e00"<=ch<="\u9fff" for ch in title)>=6

def allowed_host(url,hosts):
    host=(urlparse(url).hostname or "").lower()
    return bool(host and any(host==h or host.endswith("."+h) for h in hosts))

def bing_candidates(title,source,hosts):
    """Bing RSS discovery with *same-publisher* and title checks, 2 queries max."""
    headline=story_title(title)
    if len(headline)<10:return []
    primary=hosts[0]
    # Exact title first; fallback to significant headline prefix + site filter.
    queries=[
        '"'+headline+'" site:'+primary,
        '"'+headline[:min(32,len(headline))]+'" site:'+primary,
    ]
    seen=set()
    output=[]
    for query in queries:
        try:
            res=session.get("https://www.bing.com/search",
                            params={"q":query,"format":"rss"},timeout=15)
            res.raise_for_status()
            feed=feedparser.parse(res.content)
            for entry in feed.entries[:12]:
                link=entry.get("link","")
                if not link.startswith("https://") or not allowed_host(link,hosts) or link in seen:
                    continue
                # RSS entry headline provides an independent preliminary check.
                if not title_matches(title,entry.get("title",""),minimum=.67):
                    continue
                seen.add(link)
                output.append(link)
                if len(output)>=3:return output
        except (requests.RequestException,ValueError) as exc:
            print("ZH_BING_SEARCH_FAILED",source,str(exc)[:160])
        time.sleep(BING_DELAY)
    return output

def main():
    doc=json.loads(DB.read_text(encoding="utf-8"))
    insights=json.loads(INSIGHTS.read_text(encoding="utf-8"))
    done={x for row in insights.get("items",[]) for x in row.get("article_ids",[]) if row.get("summary") and row.get("observation")}
    candidates=[
        row for row in doc.get("items",[])
        if is_chinese_news(row) and row.get("id") not in done and
           not any(bad in row.get("title","") for bad in SKIP_TITLES) and
           row.get("source") in PUBLISHER_HOSTS
    ]
    # Prefer actual industry news to general-market headlines, preserving
    # every original database item and never adding a new item.
    ranked=sorted(candidates,key=lambda row:(
        row.get("industries")==["總體情勢"],
        -(datetime.fromisoformat(row.get("published_at") or row["discovered_at"]).timestamp())
    ))
    texts={}
    counts=Counter()
    for row in ranked[:LIMIT]:
        source=row["source"]
        hosts=PUBLISHER_HOSTS[source]
        title=row.get("title","")
        urls=[]
        direct=row.get("source_url") or row.get("url") or ""
        if direct.startswith("https://") and not google_link(direct) and allowed_host(direct,hosts):
            urls.append(direct)
        else:
            decoded=publisher_url(row.get("url",""))
            if decoded and allowed_host(decoded,hosts):
                urls.append(decoded)
        if not urls:
            urls=bing_candidates(title,source,hosts)
        else:
            # Direct link must still be verified by page title. If it is
            # inaccessible, Bing has a chance to locate the original.
            urls+=bing_candidates(title,source,hosts)
        last_reason="publisher_article_not_found"
        for candidate in dict.fromkeys(urls):
            result=read_public_page(candidate,expected_title=title)
            # This exact page is revalidated after redirects.
            if result.get("access_status")=="readable" and allowed_host(result.get("source_url",""),hosts):
                body=result["body"].strip()
                if len(body)<120:
                    last_reason="body_too_short";continue
                row["source_url"]=result["source_url"]
                row["access_status"]="readable"
                row["read_checked_at"]=datetime.now(timezone.utc).isoformat()
                row["body_length"]=len(body)
                row["excerpt"]=body[:320].rsplit(" ",1)[0]
                row.pop("read_reason",None)
                texts[row["id"]]=body[:24000]
                counts["readable"]+=1
                print("ZH_BACKFILL_READABLE",row["id"],source,result["source_url"],len(body))
                break
            last_reason=result.get("read_reason") or result.get("access_status") or last_reason
        else:
            # Do not downgrade a previously readable item if it was not
            # successfully re-fetched during this backfill pass.
            if row.get("access_status")!="readable":
                row["read_reason"]="Bing backfill: "+str(last_reason)[:160]
                row["read_checked_at"]=datetime.now(timezone.utc).isoformat()
            counts["not_readable"]+=1
            print("ZH_BACKFILL_UNRESOLVED",row["id"],source,str(last_reason)[:100])
        time.sleep(.3)
    TEMP.write_text(json.dumps(texts,ensure_ascii=False),encoding="utf-8")
    doc["chinese_backfill_diagnostics"]={
        "attempted":min(LIMIT,len(ranked)),
        "readable":counts["readable"],
        "unresolved":counts["not_readable"],
        "eligible_existing":len(candidates),
        "updated_at":datetime.now(timezone.utc).isoformat(),
        "method":"Bing RSS title + official publisher hostname + article-page title + public body",
    }
    DB.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("ZH_BACKFILL_SUMMARY",json.dumps(doc["chinese_backfill_diagnostics"],ensure_ascii=False))
if __name__=="__main__":main()
