"""Build source-backed, non-generative industry briefs.

Groups same-topic reports using conservative, explicit labels; no paid AI/API
and no invented impact ratings. Stores only small source-based snippets,
article IDs and date metadata. A future generative model can replace the
source-passage previews with well-attributed, reviewed analysis.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data/news.json"
OUTPUT=ROOT/"data/brief.json"
SECTORS=["總體情勢","機械","自行車","汽配","手工具","無人載具及機器人"]

THEMES=[
 ("machine-apple","蘋果與機器人供應鏈",("蘋果","機器人"),"無人載具及機器人"),
 ("robot-eink","元太電子紙與機器人應用",("元太","機器人"),"無人載具及機器人"),
 ("robot-jialianyi","嘉聯益機器人專案",("嘉聯益","機器人"),"無人載具及機器人"),
 ("robot-robotready","台灣機器人通用化與產業政策",("機器人","指引"),"無人載具及機器人"),
 ("robot-aeon","研揚機器人運算平台",("研揚","機器人"),"無人載具及機器人"),
 ("tariff-steel-eu","歐盟對台灣冷軋鋼材課稅",("歐盟","冷軋"),"總體情勢"),
 ("oil-middle-east","中東情勢與國際原油市場",("oil","crude","brent","石油","原油","荷莫茲","hormuz"),"總體情勢"),
 ("taiwan-electric","台灣電網建設與用電",("台電","電網","電力"),"總體情勢"),
 ("taiwan-steel","台灣及亞洲鋼鐵市場",("鋼價","中鋼","鋼廠"),"總體情勢"),
 ("foxconn-auto","鴻海車用零組件布局",("鴻海","車載","sony","索尼"),"汽配"),
 ("industry-machinery","機電四雄營運與電網訂單",("機電四雄",),"機械"),
 ("bike-inventory","自行車市場庫存與採購",("自行車","庫存","bike inventory","bicycle"),"自行車"),
 ("handtools-market","台灣手工具與水五金市場",("手工具","水五金","五金工具"),"手工具"),
]

def event_key(item):
    title=((item.get("title_zh") or "")+" "+(item.get("title") or "")).casefold()
    # The oil topic intentionally groups coverage into one issue rather than
    # calling all reports duplicate. Individual articles remain accessible.
    for key,label,terms,industry in THEMES:
        if key=="oil-middle-east":
            if item.get("industries") and "總體情勢" in item["industries"] and any(t in title for t in terms):
                return key,label
        elif industry in item.get("industries",[]):
            if key.startswith(("machine-apple","robot-eink","robot-jialianyi","robot-robotready","robot-aeon","tariff-steel-eu","foxconn-auto")):
                if all(t in title for t in terms): return key,label
            elif any(t in title for t in terms):
                return key,label
    # Unique fallback: keep individual articles, rather than grouping on one
    # overly broad keyword and accidentally hiding a distinct development.
    return "article-"+item["id"],item.get("title_zh") or item.get("title") or "未命名事件"

def summary_preview(item, limit=175):
    summary=item.get("summary_zh","")
    if item.get("summary_status") not in ("verified","source_excerpt_translated") or not summary:
        return ""
    summary=re.sub(r"\s+"," ",summary).strip()
    # Avoid long literal republishing: display a concise excerpt, not full text.
    chunks=re.split(r"(?<=[。！？])",summary)
    result=""
    for chunk in chunks:
        if len(result)+len(chunk)>limit:break
        result+=chunk
        if len(result)>90: break
    if not result:
        result=summary[:min(limit,120)].rstrip("，、 ")
    return result

def timestamp(row):
    try:
        return datetime.fromisoformat(row.get("published_at") or row["discovered_at"]).timestamp()
    except Exception:
        return 0

def main():
    data=json.loads(DATA.read_text(encoding="utf-8"))
    records=data.get("items",[])
    groups=defaultdict(list)
    names={}
    for item in records:
        k,label=event_key(item)
        groups[k].append(item)
        names[k]=label
    events=[]
    for key,items in groups.items():
        items.sort(key=timestamp,reverse=True)
        reliable=[x for x in items if summary_preview(x)]
        if not reliable:
            continue
        lead=reliable[0]
        titles=[x.get("title_zh") or x.get("title") for x in items]
        sectors=[s for s in SECTORS if any(s in x.get("industries",[]) for x in items)]
        events.append({
            "id":key,
            "title":names[key] if len(items)>1 else (lead.get("title_zh") or lead.get("title")),
            "sector":sectors[0] if sectors else "總體情勢",
            "sectors":sectors,
            "preview":summary_preview(lead),
            "body_status":"publisher_excerpt_not_ai_summary" if lead.get("summary_status")!="verified" else "reviewed_summary",
            "article_ids":[x["id"] for x in items],
            "readable_sources":len(reliable),
            "source_count":len(items),
            "latest_at":items[0].get("published_at") or items[0].get("discovered_at"),
            "taiwan_focus":any(x.get("region")=="台灣" for x in items),
        })
    # Prioritize reports with Taiwan industry evidence; broad aggregates are not
    # necessarily more important than company-specific verified developments.
    # Neutral, auditable order. No company or issue receives a hard-coded bonus.
    # Taiwan relevance, distinct contributing sources and recency are the only sort factors.
    events.sort(key=lambda e:(not e["taiwan_focus"],-e["readable_sources"],-datetime.fromisoformat(e["latest_at"]).timestamp() if e["latest_at"] else 0))
    output={
       "generated_at":datetime.now(timezone.utc).isoformat(),
       "method":"rule_based_source_backed_grouping_no_generative_ai",
       "articles_total":len(records),
       "readable_total":sum(x.get("access_status")=="readable" for x in records),
       "sectors":[{"name":sector,"articles":sum(sector in x.get("industries",[]) for x in records),
                   "readable":sum(sector in x.get("industries",[]) and bool(summary_preview(x)) for x in records)}
                  for sector in SECTORS],
       "events":events,
    }
    OUTPUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Industry brief:",len(events),"sourced event groups;",len(records),"articles")

if __name__=="__main__":
    main()
