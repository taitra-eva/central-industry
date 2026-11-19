"""Cap news at 8 articles per industry per ORIGINAL PUBLICATION day.

Rules:
* All six categories count; a cross-sector article consumes one slot in each.
* A 14-day backfill allocates each story to its original publication day, not the crawl day.
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
 "機械與金屬加工":("工具機","精密機械","木工機","機床","金屬加工","精密零件","鈑金","沖壓","鑄造","鍛造","CNC","機械訂單","上銀","永進","東台","程泰","machine tool","metal fabrication","machining","woodworking machinery"),
 "自行車":("自行車","電動自行車","電動輔助自行車","電動二輪車","電動三輪車","三輪車","電動機車","美利達","巨大集團","捷安特","Specialized","Giant Bicycles","e-bike","ebike","electric bicycle","electric bike","electric two-wheeler","electric motorcycle","electric tricycle","e-trike","tricycle","bicycle","bike","pedelec","cargo bike"),
 "汽配":("汽車零組件","汽配","汽車零配件","車用零件","車用零組件","AM零件","汽車售後","汽車零件","東陽","堤維西","昭輝","車載相機","汽車部品","automotive parts","aftermarket","auto parts"),
 "手工具":("手工具","五金工具","五金業","水五金","扳手","套筒","氣動工具","電動工具","園藝工具","園林工具","修枝剪","鏈鋸","電鑽","衝擊起子","釘槍","氣動扳手","汽修工具","汽車維修工具","特殊工具","專用工具","特工","automotive special tools","automotive specialty tools","special service tools","special tools","special tool","power tools","pneumatic tools","air tools","garden tools","gardening tools","outdoor power equipment","伯鑫工具","臺灣五金","Taiwan Tools Expo","TITE x IHT","hand tools","hardware tools"),
 "無人載具及機器人":("機器人","無人機","無人載具","人形機器人","無人船","robotics","humanoid","drone","unmanned"),
}
# Clearly non-industry pages should never fill the daily quota just because
# a broad Google News query returned them.
BAD_HEADLINE=(
 "的搜尋結果","搜尋結果 -","選舉","宮廟","力挺候選人",
 "胰臟癌","癌症治療","投資組合","股票推薦","stocks worth watching",
 "top 10 tool set brands","brand ranked","比較評測","開戶優惠",
 "cagr","股價預測","記者個人頁","作者專頁","員工介紹",
 "人才培育","招生","就業講座","copyright","版權所有",
)
def relevant_to_sector(article,sector,verified):
    title=((article.get("title") or "")+" "+(article.get("title_zh") or "")).casefold()
    if any(word.casefold() in title for word in BAD_HEADLINE):return False
    terms=SECTOR_TERMS.get(sector,())
    if any(term.casefold() in title for term in terms):
        return True
    # A verified source-backed editorial summary can independently establish
    # industry relevance, even if a headline only names the manufacturer.
    return article["id"] in verified

TRUSTED=("中央社","經濟日報","工商時報","MoneyDJ","輪彥","Bicycle Retailer","Bike Europe","MA 工具機","Modern Machine Shop","ITIS 每日新聞")
def date_key(article):
    stamp=article.get("published_at") or article.get("discovered_at") or ""
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
            sectors=list(dict.fromkeys(x for x in article.get("industries",[]) if x in SECTORS and relevant_to_sector(article,x,verified)))
            if not sectors:
                rejected["no_confirmed_sector_subject"]+=1
                continue
            article["industries"]=sectors
            available=[x for x in sectors if per_sector[x]<CAP]
            for x in sectors:
                if x not in available:rejected[x]+=1
            if not available:
                continue
            # Preserve the article once, and count each eligible sector separately.
            article["industries"]=available
            retained.append(article)
            for sector in available:per_sector[sector]+=1
        print("Daily selection",day,json.dumps(dict(per_sector),ensure_ascii=False))
    data["items"]=sorted(retained,key=timestamp,reverse=True)
    data["daily_category_cap"]=CAP
    data["daily_selection_limit_note"]="每個產業以原始發布日期計算，每日最多8則；最近14天新聞可補抓，舊日新聞在30日內保留"
    DB.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Daily cap selection:",len(articles),"->",len(retained),"; dropped:",dict(rejected))
if __name__=="__main__":main()
