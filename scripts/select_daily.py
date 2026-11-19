"""Cap new discoveries at 8 articles per industry per discovery day.

Rules:
* All six categories count; a cross-sector article consumes one slot in each.
* Existing 30-day archive uses the same cap per original discovery date.
* News is ranked by supported, specific subject and freshness, not RSS order.
* This is an editorial selection limit, NOT proof that 8 stories exist.
* Duplicates are handled separately only when source content supports it.
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"data/news.json"
INSIGHTS=ROOT/"data/insights.json"
CAP=8
SECTORS=("總體情勢","機械與金屬加工","自行車","汽配","手工具","無人載具及機器人")
SECTOR_TERMS={
 "總體情勢":("匯率","新台幣","關稅","反傾銷","出口管制","油價","石油","鋼價","運價","航運","原物料","貨櫃","war","tariff","exchange rate","oil price"),
 "機械與金屬加工":("工具機","精密機械","木工機","機床","金屬加工","鈑金","沖壓","鑄造","鍛造","CNC","machine tool","metal fabrication","machining","woodworking machinery"),
 "自行車":("自行車","電動自行車","電動輔助自行車","電動二輪車","電動三輪車","三輪車","電動機車","e-bike","ebike","electric bicycle","electric bike","electric two-wheeler","electric motorcycle","electric tricycle","e-trike","tricycle","bicycle","bike","pedelec","cargo bike"),
 "汽配":("汽車零組件","汽配","車用零件","AM零件","汽車售後","汽車零件","automotive parts","aftermarket","auto parts"),
 "手工具":("手工具","五金工具","水五金","扳手","套筒","氣動工具","電動工具","hand tools","hardware tools"),
 "無人載具及機器人":("機器人","無人機","無人載具","人形機器人","無人船","robotics","humanoid","drone","unmanned"),
}
TRUSTED=("中央社","經濟日報","工商時報","MoneyDJ","輪彥","Bicycle Retailer","Bike Europe","MA 工具機","Modern Machine Shop","ITIS 每日新聞")
def date_key(article):
    stamp=article.get("discovered_at") or article.get("published_at") or ""
    return stamp[:10] if len(stamp)>=10 else "undated"

def timestamp(article):
    try:return datetime.fromisoformat(article.get("published_at") or article.get("discovered_at")).timestamp()
    except (TypeError,ValueError):return 0

def score(article,verified):
    title=((article.get("title") or "")+" "+(article.get("title_zh") or "")).casefold()
    industries=[x for x in article.get("industries",[]) if x in SECTORS]
    specific=max((sum(1 for term in SECTOR_TERMS[x] if term.casefold() in title) for x in industries),default=0)
    publisher=article.get("source","")
    return (
      1 if article["id"] in verified else 0,
      1 if article.get("access_status")=="readable" and article.get("summary_zh") else 0,
      min(specific,4),
      1 if article.get("region")=="台灣" else 0,
      1 if any(name.casefold() in publisher.casefold() for name in TRUSTED) else 0,
      timestamp(article),
    )

def main():
    data=json.loads(DB.read_text(encoding="utf-8"))
    articles=data.get("items",[])
    verified=set()
    if INSIGHTS.exists():
        i=json.loads(INSIGHTS.read_text(encoding="utf-8"))
        verified={ident for entry in i.get("items",[]) if entry.get("summary") and entry.get("observation") for ident in entry.get("article_ids",[])}
    # Keep separate day buckets; never truncate 30 days to merely 8 articles.
    byday=defaultdict(list)
    for article in articles:byday[date_key(article)].append(article)
    retained=[]
    rejected=defaultdict(int)
    for day,bucket in sorted(byday.items()):
        per_sector=defaultdict(int)
        for article in sorted(bucket,key=lambda x:score(x,verified),reverse=True):
            sectors=list(dict.fromkeys(x for x in article.get("industries",[]) if x in SECTORS))
            if not sectors:
                rejected["no_valid_sector"]+=1
                continue
            if any(per_sector[x]>=CAP for x in sectors):
                for x in sectors:
                    if per_sector[x]>=CAP:rejected[x]+=1
                continue
            retained.append(article)
            for sector in sectors:per_sector[sector]+=1
        print("Daily selection",day,json.dumps(dict(per_sector),ensure_ascii=False))
    data["items"]=sorted(retained,key=timestamp,reverse=True)
    data["daily_category_cap"]=CAP
    data["daily_selection_limit_note"]="每個產業以首次收錄日期計算，每日最多8則；舊日新聞在30日內保留"
    DB.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Daily cap selection:",len(articles),"->",len(retained),"; dropped:",dict(rejected))
if __name__=="__main__":main()
