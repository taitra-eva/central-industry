"""Source-grounded AI analysis using an explicitly configured inference API.

Requires GROQ_API_KEY in GitHub Actions secrets. No free tier is guaranteed
forever; rate-limit / quota errors are reported and don't generate false text.
Original bodies remain untracked and are never committed.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/"data/news.json"
TEXTS=ROOT/".article_texts.json"
INSIGHTS=ROOT/"data/insights.json"
KEY=os.environ.get("GROQ_API_KEY","").strip()
MODEL=os.environ.get("GROQ_MODEL","openai/gpt-oss-20b")
LIMIT=int(os.environ.get("AI_DAILY_LIMIT","35"))
API="https://api.groq.com/openai/v1/chat/completions"

SYSTEM="""你是臺灣製造業產業情報分析員。只能使用使用者提供的原始新聞全文作答。
輸出合法JSON，鍵必須是 summary, observation, sector, confidence。
summary: 繁體中文約120至250字，保留重要公司名稱、金額、日期、產銷數字與條件，不得杜撰。
observation: 繁體中文約80至170字，說明對臺灣製造業、上下游、訂單、成本、市場的具體關聯與後續追蹤點，將推論明確標示為「可能」「應追蹤」；若原文不足以支持特定影響，明確指出尚未有證據。
sector: 從「總體情勢」「機械與金屬加工」「自行車」「汽配」「手工具」「無人載具及機器人」擇一主要分類。
confidence: 高/中/低，按原文清晰度判斷。
嚴禁將合作備忘錄視為已下單；嚴禁憑標題推算營收或訂單。不可照抄原文大段內容。沒有可靠正文就不要輸出分析。
"""

def main():
    if not TEXTS.exists():
        print("AI analysis: missing extracted source text; skipping")
        return
    texts=json.loads(TEXTS.read_text(encoding="utf-8"))
    if not KEY:
        print("AI analysis NOT ACTIVE: set GROQ_API_KEY in repository Actions secrets; no API calls made")
        return
    doc=json.loads(NEWS.read_text(encoding="utf-8"))
    records=json.loads(INSIGHTS.read_text(encoding="utf-8")) if INSIGHTS.exists() else {"items":[]}
    done={ident for entry in records["items"] for ident in entry.get("article_ids",[])}
    byid={x["id"]:x for x in doc["items"]}
    eligible=[(id,body) for id,body in texts.items() if id in byid and id not in done and len(body)>=350]
    eligible.sort(key=lambda pair:(byid[pair[0]].get("region")!="台灣",-(datetime.fromisoformat(byid[pair[0]].get("published_at") or byid[pair[0]]["discovered_at"]).timestamp())))
    made=0
    failures=0
    for identifier,body in eligible[:LIMIT]:
        article=byid[identifier]
        prompt=("新聞標題："+(article.get("title_zh") or article.get("title") or "")+"\n媒體："+article.get("source","")+"\n原始文章內容：\n"+body[:11500])
        req={"model":MODEL,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"temperature":0.1,"max_completion_tokens":1200,"response_format":{"type":"json_object"}}
        try:
            resp=requests.post(API,headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},json=req,timeout=70)
            if resp.status_code in (401,403):
                print("AI authentication denied; check GROQ_API_KEY");break
            if resp.status_code in (429,402):
                print("AI quota/rate limit reached:",resp.status_code,"no paid calls enabled");break
            resp.raise_for_status()
            answer=resp.json()["choices"][0]["message"]["content"]
            obj=json.loads(answer)
            summary=str(obj.get("summary","")).strip()
            observation=str(obj.get("observation","")).strip()
            sector=str(obj.get("sector","")).strip()
            if not(70<=len(summary)<=850 and 45<=len(observation)<=650):
                print("AI insufficient output; article",identifier);failures+=1;continue
            if sector not in ("總體情勢","機械與金屬加工","自行車","汽配","手工具","無人載具及機器人"):
                sector=article.get("industries",["總體情勢"])[0]
            record={"article_ids":[identifier],"title":article.get("title_zh") or article.get("title"),
                    "summary":summary,"observation":observation,"observation_type":"觀察重點",
                    "method":"groq_llm_from_publisher_body","model":MODEL,
                    "generated_at":datetime.now(timezone.utc).isoformat(),
                    "source_url":article.get("source_url") or article.get("url"),
                    "confidence":obj.get("confidence","未評估")}
            records["items"].append(record)
            article["ai_summary_status"]="generated_unreviewed"
            if sector not in article.get("industries",[]):
                article.setdefault("industries",[]).append(sector)
            made+=1
            print("AI analyzed:",identifier,article.get("source"),sector)
        except (requests.RequestException,ValueError,KeyError,TypeError) as e:
            failures+=1
            print("AI generation failed:",identifier,str(e)[:180])
        time.sleep(1.6)
    records["updated_at"]=datetime.now(timezone.utc).isoformat()
    INSIGHTS.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    NEWS.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("AI summary finished:",made,"articles; failed:",failures,"eligible:",len(eligible))

if __name__=="__main__": main()
