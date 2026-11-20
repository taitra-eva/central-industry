"""Publisher HTML-list discovery. This is not a full-article scraper.

Each candidate must contain a direct same-publisher URL, a substantive
industry-relevant headline AND an explicit publication date within 14 days.
Undated cards, paywalls, site navigation and company PR feeds are ignored.
"""
import json, re, hashlib, calendar
from html import unescape
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from relevance import should_keep
from select_daily import relevant_to_sector
from industry_entities import entity_sectors
from topic_taxonomy import normalize_article

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"data/news.json"
CONFIG=ROOT/"config/direct_sources.json"
MONTHS={"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"nov":11,"dec":12}
DATE_RE=re.compile(r"(?<!\d)(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")
EU_DATE=re.compile(r"(?<!\d)(\d{1,2})\.\s*([A-Za-z]+)\s+(20\d{2})")
EN_DATE=re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})")
def publish_date(value):
    for regex,order in [(DATE_RE,0),(EU_DATE,1),(EN_DATE,2)]:
        match=regex.search(value or "")
        if not match:continue
        x=match.groups()
        try:
            if order==0:year,month,day=map(int,x)
            elif order==1:day,month,year=int(x[0]),MONTHS[x[1].casefold()],int(x[2])
            else:month,day,year=MONTHS[x[0].casefold()],int(x[1]),int(x[2])
            return datetime(year,month,day,tzinfo=timezone.utc)
        except (ValueError,KeyError):continue
    return None
def clean(value):
    return " ".join(unescape(re.sub(r"<[^>]*>"," ",value or "")).split())
def host_matches(url,allowed):
    host=(urlparse(url).hostname or "").lower()
    return any(host==name or host.endswith("."+name) for name in allowed)
def extract(source,html,now):
    soup=BeautifulSoup(html,"html.parser")
    records=[]
    seen=set()
    for a in soup.select("a[href]"):
        url=urljoin(source["url"],a.get("href",""))
        if not url.startswith("https://") or not host_matches(url,source["hosts"]):
            continue
        if not any(p in urlparse(url).path for p in source.get("url_patterns",["/"])):
            continue
        if url.rstrip("/")==source["url"].rstrip("/") or url in seen:
            continue
        title=clean(a.get_text(" ",strip=True))
        if not 15<=len(title)<=180:
            img=a.find("img")
            title=clean(img.get("alt","")) if img else ""
        if not 15<=len(title)<=180:
            continue
        # Date may appear on the article preview card, but never scan the
        # entire page: that could assign one date to unrelated links.
        stamp=None
        snippet=""
        node=a
        for _ in range(4):
            node=node.parent
            if not node or node.name in ("body","html","main"):break
            time=node.select_one("time[datetime]")
            dt=(time.get("datetime","") if time else "") or ""
            short=clean(node.get_text(" ",strip=True))[:700]
            stamp=publish_date(dt) or publish_date(short)
            if stamp:
                snippet=short
                break
        if not stamp or stamp<now-timedelta(days=14) or stamp>now+timedelta(days=1):
            continue
        if not should_keep(title,source["industry"])[0]:continue
        candidate={"id":"","title":title,"title_zh":"","source":source["name"]}
        if not relevant_to_sector(candidate,source["industry"],set()):continue
        snippet=snippet.replace(title,"",1).strip(" -–|.:")
        if len(snippet)<80 or len(snippet)>500:snippet=snippet[:500] if len(snippet)>=80 else ""
        records.append({"title":title,"link":url,"published_at":stamp.isoformat(),"snippet":snippet})
        seen.add(url)
        if len(records)>=35:break
    return records
def main():
    now=datetime.now(timezone.utc)
    doc=json.loads(DB.read_text(encoding="utf-8"))
    rows={x["id"]:x for x in doc.get("items",[])}
    sources=[x for x in json.loads(CONFIG.read_text(encoding="utf-8"))["sources"] if x.get("type")=="html"]
    diagnostics=[]
    for source in sources:
        stats={"source":source["name"],"url":source["url"],"type":"html","new":0}
        try:
            resp=requests.get(source["url"],headers={"User-Agent":"Mozilla/5.0 (compatible; CentralIndustryNews/1.0)"},timeout=15)
            resp.raise_for_status()
            entries=extract(source,resp.text,now)
            stats["dated_relevant_cards"]=len(entries)
            for entry in entries:
                norm=re.sub(r"\W+","",entry["title"].casefold())
                uid=hashlib.sha256(norm.encode()).hexdigest()[:20]
                sectors=[source["industry"]]+[x for x in entity_sectors(entry["title"]) if x!=source["industry"]]
                if uid in rows:
                    old=rows[uid]
                    if "news.google.com" in (old.get("source_url") or old.get("url") or ""):
                        old["source_url"]=entry["link"]
                        old["source"]=source["name"]
                    if entry["snippet"] and len(entry["snippet"])>len(old.get("publisher_excerpt","")):
                        old["publisher_excerpt"]=entry["snippet"]
                        old["publisher_excerpt_source"]="publisher_news_listing"
                    continue
                rows[uid]=normalize_article({"id":uid,"title":entry["title"],"url":entry["link"],"source_url":entry["link"],
                    "source":source["name"],"published_at":entry["published_at"],"discovered_at":now.isoformat(),
                    "industries":sectors,"region":source["region"],"priority":"international",
                    "topic":"產業動態","tags":[],"access_status":"not_verified","excerpt":"",
                    "publisher_excerpt":entry["snippet"],"publisher_excerpt_source":"publisher_news_listing" if entry["snippet"] else ""})
                stats["new"]+=1
        except (requests.RequestException,ValueError,KeyError) as exc:
            stats["error"]=str(exc)[:200]
        diagnostics.append(stats)
        print("DIRECT_HTML",json.dumps(stats,ensure_ascii=False))
    doc["items"]=sorted(rows.values(),key=lambda x:x.get("published_at") or x.get("discovered_at") or "",reverse=True)
    doc["direct_html_diagnostics"]=diagnostics
    DB.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
