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
from topic_taxonomy import normalize_article
import requests

ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/"data/news.json"
TEXTS=ROOT/".article_texts.json"
INSIGHTS=ROOT/"data/insights.json"
KEY=os.environ.get("GROQ_API_KEY","").strip()
MODEL=os.environ.get("GROQ_MODEL","openai/gpt-oss-20b")
LIMIT=int(os.environ.get("AI_DAILY_LIMIT","48"))
API="https://api.groq.com/openai/v1/chat/completions"

SYSTEM="""你是臺灣製造業產業情報分析員。只能使用使用者提供的可追溯媒體資料作答；輸入可能是已驗證新聞正文，也可能只是媒體官方 RSS／公開新聞列表的簡介，兩者不得混淆。
輸出合法JSON，鍵必須是 summary, observation, sector, confidence。
summary: 繁體中文約120至250字，保留重要公司名稱、金額、日期、產銷數字與條件，不得杜撰。
observation: 繁體中文約80至170字，說明對臺灣製造業、上下游、訂單、成本、市場的具體關聯與後續追蹤點，將推論明確標示為「可能」「應追蹤」；若原文不足以支持特定影響，明確指出尚未有證據。
sector: 從「總體情勢」「機械與金屬加工」「自行車」「汽配」「手工具」「無人載具及機器人」擇一主要分類。
confidence: 高/中/低，按原文清晰度判斷。
嚴禁將合作備忘錄視為已下單；嚴禁憑標題推算營收或訂單。不可照抄原文大段內容。若只有簡介，只能摘要簡介明確提到的事實；不得聲稱已閱讀全文，不能推論簡介沒有記載的訂單、產能、成本、影響或因果。觀察重點須說明可追蹤的面向與資料限制，必要時直接說證據不足。
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
    # Full text is preferred, but the former 350-character AI threshold
    # was an implementation choice, not a user requirement. A verified
    # publisher-provided RSS/listing excerpt can support a *limited* brief.
    evidence={}
    for identifier,body in texts.items():
        if identifier in byid and identifier not in done and body.strip():
            evidence[identifier]=(body,"publisher_body")
    for article in doc["items"]:
        identifier=article["id"]
        if identifier in done or identifier in evidence:continue
        kind=article.get("publisher_excerpt_source")
        excerpt=(article.get("publisher_excerpt") or "").strip()
        url=article.get("source_url") or article.get("url") or ""
        if (kind in ("official_rss","publisher_news_listing") and
                url.startswith("https://") and "news.google.com" not in url and
                len(excerpt)>=65):
            evidence[identifier]=(excerpt,"publisher_excerpt")
    eligible=[(identifier,body,kind) for identifier,(body,kind) in evidence.items()]
    eligible.sort(key=lambda item:(byid[item[0]].get("region")!="台灣",
        -(datetime.fromisoformat(byid[item[0]].get("published_at") or byid[item[0]]["discovered_at"]).timestamp())))
    print("AI evidence:",sum(kind=="publisher_body" for _,_,kind in eligible),"publisher bodies,",
          sum(kind=="publisher_excerpt" for _,_,kind in eligible),"publisher excerpts")
    made=0
    failures=0
    for identifier,body,kind in eligible[:LIMIT]:
        article=byid[identifier]
        label=("已讀取的公開新聞正文" if kind=="publisher_body" else
               "媒體官方 RSS 或新聞列表公開簡介，非新聞全文")
        prompt=("新聞標題："+(article.get("title_zh") or article.get("title") or "")+
                "\n媒體："+article.get("source","")+
                "\n資料類型："+label+
                "\n原始來源網址："+(article.get("source_url") or article.get("url") or "")+
                "\n提供的來源內容：\n"+body[:11500]+
                ("\n重要：僅依公開簡介寫有限摘要與後續追蹤，不能杜撰正文細節。" if kind=="publisher_excerpt" else ""))
        req={"model":MODEL,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"temperature":0.1,"reasoning_effort":"low","max_completion_tokens":2200,"response_format":{"type":"json_object"}}
        try:
            resp=requests.post(API,headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},json=req,timeout=70)
            if resp.status_code in (401,403):
                print("AI authentication denied; check GROQ_API_KEY");break
            if resp.status_code in (429,402):
                print("AI quota/rate limit reached:",resp.status_code,"no paid calls enabled");break
            if resp.status_code == 400:
                # Preserve the provider's error type/code. A generic "Bad
                # Request" hides whether it is JSON validation, unsupported
                # settings, context size or another request-specific issue.
                # Never print the API key, request payload or article body.
                try:
                    err=resp.json().get("error",{})
                    if not isinstance(err,dict): err={"message":str(err)}
                    print("AI HTTP 400 diagnosis:",identifier,
                          "type:",str(err.get("type","unknown"))[:100],
                          "code:",str(err.get("code","unknown"))[:100],
                          "message:",str(err.get("message","unknown"))[:420])
                except (ValueError,KeyError,TypeError):
                    print("AI HTTP 400 diagnosis:",identifier,
                          "provider returned no readable error object")
                failures+=1
                continue
            resp.raise_for_status()
            answer=resp.json()["choices"][0]["message"]["content"]
            obj=json.loads(answer)
            summary=str(obj.get("summary","")).strip()
            observation=str(obj.get("observation","")).strip()
            sector=str(obj.get("sector","")).strip()
            if not(45<=len(summary)<=850 and 30<=len(observation)<=650):
                print("AI insufficient output; article",identifier);failures+=1;continue
            if sector not in ("總體情勢","機械與金屬加工","自行車","汽配","手工具","無人載具及機器人"):
                sector=article.get("industries",["總體情勢"])[0]
            if kind=="publisher_excerpt":
                summary="【媒體公開簡介整理，非全文摘要】"+summary
            record={"article_ids":[identifier],"title":article.get("title_zh") or article.get("title"),
                    "summary":summary,"observation":observation,"observation_type":"觀察重點",
                    "method":"groq_llm_from_publisher_body" if kind=="publisher_body" else "groq_llm_from_publisher_excerpt",
                    "evidence_type":kind,"model":MODEL,
                    "generated_at":datetime.now(timezone.utc).isoformat(),
                    "source_url":article.get("source_url") or article.get("url"),
                    "confidence":obj.get("confidence","未評估")}
            records["items"].append(record)
            article["ai_summary_status"]="generated_unreviewed"
            if sector!="總體情勢" and article.get("industries")==["總體情勢"]:
                article["industries"]=[sector]
            elif sector not in article.get("industries",[]):
                article.setdefault("industries",[]).append(sector)
            made+=1
            print("AI analyzed:",identifier,article.get("source"),sector,kind)
        except (requests.RequestException,ValueError,KeyError,TypeError) as e:
            failures+=1
            print("AI generation failed:",identifier,str(e)[:180])
        time.sleep(15)  # conservative pacing for rate-limited free models
    records["updated_at"]=datetime.now(timezone.utc).isoformat()
    INSIGHTS.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for x in doc["items"]: normalize_article(x)
    NEWS.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("AI summary finished:",made,"articles; failed:",failures,"eligible:",len(eligible))

if __name__=="__main__": main()
