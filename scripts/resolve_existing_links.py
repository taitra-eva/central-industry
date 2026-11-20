"""Resolve original publisher links for EXISTING news, without Groq or news discovery.

The Bing URL is used *only* inside an authenticated server-side collection
run. Published links are direct publisher URLs and must pass same-host and
article-title validation. No URL guessing, Google News redirect, or paywall bypass.
"""
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin, parse_qs, unquote
import requests
from bs4 import BeautifulSoup
import feedparser

from read_articles import ROOT, DB, google_link, story_title, title_matches

MAX=int(os.environ.get("DIRECT_LINK_MAX","55"))
DELAY=float(os.environ.get("DIRECT_LINK_DELAY","1.2"))
AGENT={"User-Agent":"Mozilla/5.0 (compatible; CentralIndustryLinks/1.0)", "Accept-Language":"zh-TW,zh;q=0.9,en;q=0.8"}
HOSTS={
 "經濟日報":["money.udn.com"],
 "聯合新聞網":["udn.com"],
 "工商時報":["ctee.com.tw","chinatimes.com"],
 "中央社 CNA":["cna.com.tw"],
 "TechNews 科技新報":["technews.tw"],
 "MoneyDJ":["moneydj.com"],
 "CTIMES":["ctimes.com.tw"],
 "輪彥國際有限公司":["wheelgiant.com.tw"],
 "Robotics & Automation News":["roboticsandautomationnews.com"],
 "Unmanned Systems Technology":["unmannedsystemstechnology.com"],
 "The Robot Report":["therobotreport.com"],
 "Bike Europe":["bike-eu.com"],
 "Bicycle Retailer & Industry News":["bicycleretailer.com"],
 "ETMM":["etmm-online.com"],
 "taiwandrones.org":["taiwandrones.org"],
}
def host_allowed(url,hosts):
    p=urlparse(url)
    h=(p.hostname or "").lower()
    return p.scheme=="https" and bool(h) and any(h==x or h.endswith("."+x) for x in hosts)
def clean_candidate(url):
    # Bing HTML may wrap the publisher URL in a click-tracking URL;
    # never publish intermediary links or manufacture a URL.
    if not url.startswith("http"):return ""
    p=urlparse(url)
    host=(p.hostname or "").lower()
    if host in ("bing.com","www.bing.com"):
        for key in ("url","u"):
            for candidate in parse_qs(p.query).get(key,[]):
                if candidate.startswith("https://"):return candidate
        return ""
    return url
def bing_results(title,hosts,client):
    headline=story_title(title)
    if len(headline)<10:return []
    # Domain + normalized headline. Avoid exact 50-character title queries
    # as publishers frequently revise punctuation and headline suffixes.
    core=re.sub(r"\s+"," ",headline).strip()
    fragments=[core[:48]]
    if len(core)>30:fragments.append(core[:26])
    seen=set()
    # At most two Bing searches per article, not a fragments×domains
    # Cartesian product that could trigger provider throttling.
    query_pairs=list(dict.fromkeys([(fragments[0],hosts[0]),(fragments[-1],hosts[-1])]))
    for fragment,domain in query_pairs:
            query="site:"+domain+" "+fragment
            try:
                r=client.get("https://www.bing.com/search",params={"q":query,"format":"rss"},headers=AGENT,timeout=15)
                r.raise_for_status()
                rss=feedparser.parse(r.content)
                entries=[(x.get("link",""),x.get("title","")) for x in rss.entries[:12]]
                if not entries:
                    r=client.get("https://www.bing.com/search",params={"q":query},headers=AGENT,timeout=15)
                    r.raise_for_status()
                    soup=BeautifulSoup(r.content,"html.parser")
                    entries=[(a.get("href",""),a.get_text(" ",strip=True)) for a in soup.select("li.b_algo h2 a[href]")[:12]]
                for url,name in entries:
                    url=clean_candidate(url)
                    if url in seen or not host_allowed(url,hosts):continue
                    if not title_matches(title,name,minimum=.58):continue
                    seen.add(url)
                    yield url
            except requests.RequestException as ex:
                print("LINK_BING_ERROR",domain,str(ex)[:110])
            time.sleep(DELAY)
def verify_article(url,title,hosts,client):
    if not host_allowed(url,hosts):return None
    try:
        r=client.get(url,headers=AGENT,timeout=14,allow_redirects=True)
        if r.status_code!=200 or not host_allowed(r.url,hosts):return None
        if "text/html" not in r.headers.get("Content-Type","").lower():return None
        soup=BeautifulSoup(r.content[:2_500_000],"html.parser")
        candidates=[]
        if soup.title:candidates.append(soup.title.get_text(" ",strip=True))
        for key,value in (("property","og:title"),("name","twitter:title")):
            tag=soup.find("meta",attrs={key:value})
            if tag and tag.get("content"):candidates.append(tag["content"])
        for el in soup.select("h1")[:2]:candidates.append(el.get_text(" ",strip=True))
        if not any(title_matches(title,x,minimum=.71) for x in candidates):return None
        return r.url
    except requests.RequestException:return None
def main():
    doc=json.loads(DB.read_text(encoding="utf-8"))
    rows=doc.get("items",[])
    selected=[]
    for x in rows:
        src=x.get("source_url") or x.get("url") or ""
        if src and not google_link(src):continue
        hosts=HOSTS.get(x.get("source"))
        if not hosts:continue
        if len(story_title(x.get("title","")))<10:continue
        selected.append(x)
    # First correct direct links for articles with summaries; then other news.
    summarized=set()
    insights=ROOT/"data/insights.json"
    if insights.exists():
        d=json.loads(insights.read_text(encoding="utf-8"))
        summarized={a for item in d.get("items",[]) for a in item.get("article_ids",[])}
    selected.sort(key=lambda x:(x.get("id") not in summarized,
            -(datetime.fromisoformat(x.get("published_at") or x.get("discovered_at")).timestamp())))
    stats=Counter()
    with requests.Session() as client:
        for item in selected[:MAX]:
            hosts=HOSTS[item["source"]]
            matched=None
            for url in bing_results(item.get("title",""),hosts,client):
                matched=verify_article(url,item.get("title",""),hosts,client)
                if matched:break
            if matched:
                item["source_url"]=matched
                item["original_url_status"]="publisher_title_verified"
                item["original_url_checked_at"]=datetime.now(timezone.utc).isoformat()
                stats["resolved"]+=1
                print("DIRECT_LINK_RESOLVED",item["id"],item["source"],matched)
            else:
                stats["unresolved"]+=1
                print("DIRECT_LINK_NOT_FOUND",item["id"],item["source"])
    doc["direct_link_diagnostics"]={"checked":min(len(selected),MAX),
       "resolved":stats["resolved"],"unresolved":stats["unresolved"],
       "remaining_candidates":max(0,len(selected)-MAX),
       "checked_at":datetime.now(timezone.utc).isoformat()}
    DB.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("DIRECT_LINK_DIAGNOSTICS",json.dumps(doc["direct_link_diagnostics"],ensure_ascii=False))
if __name__=="__main__":main()
