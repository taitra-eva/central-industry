"""Discover articles from publisher-owned RSS feeds without Google News links.

Only the source-provided direct article URL is used. Failed feeds are logged
and never fabricated; pending HTML sites require validated parsers first.
"""
import hashlib
import json
import calendar
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
import feedparser
from relevance import should_keep
from industry_entities import entity_sectors
from topic_taxonomy import normalize_article
ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/"data/news.json"
SOURCES=ROOT/"config/direct_sources.json"
WINDOW=timedelta(days=14)
def main():
    now=datetime.now(timezone.utc)
    doc=json.loads(NEWS.read_text(encoding="utf-8"))
    rows={row["id"]:row for row in doc.get("items",[])}
    cfg=json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    total=0
    stats=[]
    for source in cfg:
        added=0
        try:
            response=requests.get(source["url"],timeout=15,headers={"User-Agent":"CentralIndustryNews/1.0","Accept":"application/rss+xml,application/xml,text/xml"})
            response.raise_for_status()
            feed=feedparser.parse(response.content)
            if not feed.entries:
                raise ValueError("feed contains no entries")
            for entry in feed.entries[:35]:
                title=re.sub(r"<[^>]+>"," ",entry.get("title","")).strip()
                link=entry.get("link","")
                host=(urlparse(link).hostname or "").lower()
                if not host.endswith("bike-eu.com") or not link.startswith("https://"):
                    continue
                if not should_keep(title,source["industry"])[0]:continue
                parsed=entry.get("published_parsed") or entry.get("updated_parsed")
                if not parsed:continue
                stamp=datetime.fromtimestamp(calendar.timegm(parsed),timezone.utc)
                if not now-WINDOW<=stamp<=now+timedelta(hours=3):continue
                uid=hashlib.sha256(re.sub(r"\W+","",title.casefold()).encode()).hexdigest()[:20]
                sectors=[source["industry"]]
                for sec in entity_sectors(title):
                    if sec not in sectors: sectors.append(sec)
                if uid in rows:
                    x=rows[uid]
                    for sec in sectors:
                        if sec not in x.get("industries",[]):x.setdefault("industries",[]).append(sec)
                    original=x.get("source_url") or x.get("url") or ""
                    if original.startswith("https://news.google.com/"):
                        x["source_url"]=link
                        x["source"]=source["name"]
                    continue
                item={"id":uid,"title":title,"url":link,"source_url":link,"source":source["name"],
                      "published_at":stamp.isoformat(),"discovered_at":now.isoformat(),
                      "industries":sectors,"tags":[],"priority":"international",
                      "region":source["region"],"language_hint":"en","topic":"產業動態",
                      "access_status":"not_verified","excerpt":""}
                rows[uid]=normalize_article(item)
                added+=1
            total+=added
            stats.append({"source":source["name"],"url":source["url"],"found":len(feed.entries),"new":added})
        except (requests.RequestException,ValueError) as exc:
            stats.append({"source":source["name"],"url":source["url"],"error":str(exc)[:140]})
    doc["items"]=sorted(rows.values(),key=lambda x:x.get("published_at") or x.get("discovered_at") or "",reverse=True)
    doc["direct_source_diagnostics"]=stats
    NEWS.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Direct publisher RSS added:",total,"from",len(cfg),"feeds")
    for row in stats: print("DIRECT_FEED",json.dumps(row,ensure_ascii=False))
if __name__=="__main__": main()
