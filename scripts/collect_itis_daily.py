"""Discover relevant news links from ITIS daily news (secondary discovery source).

Try the date-addressed daily archive, and only admit entries with direct HTTP
publisher links and explicit five-sector/policy keywords. ITIS itself is not a
license to republish the articles; the following read_articles.py step must still
verify publisher content and access.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from relevance import should_keep

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/news.json"
NOW = datetime.now(timezone.utc)
HEADERS = {"User-Agent":"Mozilla/5.0 (compatible; IndustryNewsIndexer/1.0)"}
BASES = [
    "https://www.itis.org.tw/ITIS_Publish/ITISNEWS_New_One.aspx?td={date}",
    "https://itisweb2.itis.org.tw/ITIS_Publish/ITISNews_New_One.asp?td={date}"
]
KEYWORDS = {
    "機械":("工具機","機械","金屬加工","CNC","機床","機電","精密製造"),
    "自行車":("自行車","單車","電動輔助自行車","美利達","巨大集團","捷安特","bike"),
    "汽配":("汽車零件","汽車零組件","汽配","車用零組件","售後市場","AM零件"),
    "手工具":("手工具","五金","水五金","衛浴五金","氣動工具","電動工具","扳手","套筒","扣件"),
    "無人載具及機器人":("無人機","無人載具","機器人","工業機器人","無人船","無人車"),
    "總體情勢":("關稅","貿易","經濟部","工業生產","原物料","鋼價","鋁價","銅價","石油","能源",
               "航運","物流","運費","戰爭","制裁","供應鏈","產業政策","貨幣","匯率")
}
BLOCKED_HOSTS = ("itis.org.tw","itisweb2.itis.org.tw","trade.gov.tw","trade.moea.gov.tw")
SKIP_TEXT = ("登入","會員","更多","首頁","列印","回上頁","最新活動","研討會","top")
MAX_NEW=75

def is_publisher_link(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http","https") or not parsed.netloc:
        return False
    return not any(parsed.netloc.lower().endswith(x) for x in BLOCKED_HOSTS)

def choose_categories(title):
    low=title.casefold()
    return [sector for sector,words in KEYWORDS.items() if any(w.casefold() in low for w in words)]

def get_day(day):
    value=day.strftime("%Y/%m/%d")
    for template in BASES:
        url=template.format(date=value)
        try:
            r=requests.get(url,headers=HEADERS,timeout=10)
            if r.status_code!=200:
                print("ITIS daily HTTP",r.status_code,value)
                continue
            r.encoding=r.apparent_encoding or r.encoding
            soup=BeautifulSoup(r.text,"html.parser")
            headline_links=[]
            for a in soup.select("a[href]"):
                title=" ".join(a.get_text(" ",strip=True).split())
                if not (9<=len(title)<=135) or any(skip in title for skip in SKIP_TEXT):
                    continue
                sectors=choose_categories(title)
                if not should_keep(title,'總體情勢' if '總體情勢' in sectors else None)[0]:
                    continue
                if not sectors:
                    continue
                direct=urljoin(r.url,a["href"])
                if not is_publisher_link(direct):
                    continue
                headline_links.append((title,direct,sectors))
            print("ITIS",value,"matching accessible direct links",len(headline_links))
            return headline_links
        except requests.RequestException as e:
            print("ITIS daily read failed",value,str(e)[:100])
    return []

def main():
    data=json.loads(DATA.read_text(encoding="utf8"))
    news={n["id"]:n for n in data.get("items",[]) if should_keep(n.get('title',''), '總體情勢' if '總體情勢' in n.get('industries',[]) else None)[0]}
    added=0
    successful_days=0
    # Attempt each day of the publication discovery window; ITIS can have gaps.
    for ago in range(14):
        day=(NOW+timedelta(hours=8)-timedelta(days=ago)).date()
        found=get_day(day)
        if found:successful_days+=1
        for title,url,sectors in found:
            norm=re.sub(r"\W+","",title.casefold())
            uid=hashlib.sha256(norm.encode("utf8")).hexdigest()[:20]
            if uid in news:
                for sector in sectors:
                    if sector not in news[uid].get("industries",[]):
                        news[uid].setdefault("industries",[]).append(sector)
                continue
            if added>=MAX_NEW:break
            stamp=datetime.combine(day,datetime.min.time(),tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).isoformat()
            news[uid]={"id":uid,"title":title,"url":url,"source":"ITIS 每日新聞所引述的原始媒體",
                       "published_at":stamp,"date_precision":"itis_index_date_not_original_pubdate",
                       "discovered_at":NOW.isoformat(),"industries":sectors,
                       "region":"台灣","topic":"產業動態","access_status":"not_verified",
                       "discovery_source":"ITIS 每日重點新聞"}
            added+=1
        if added>=MAX_NEW:break
        time.sleep(0.2)
    data["items"]=sorted(news.values(),key=lambda n:n.get("published_at") or n["discovered_at"],reverse=True)
    data["itis_discovery"]={"checked_at":NOW.isoformat(),"days_with_direct_links":successful_days,
                             "new_items":added}
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("ITIS daily discovery:",added,"new articles,",successful_days,"days with links")

if __name__=="__main__":
    main()
