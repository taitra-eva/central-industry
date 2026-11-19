"""Remove only confirmed duplicate articles, never articles about a common topic.

Source-text similarity is necessary for cross-publisher merging; headline,
industry, keywords, the word 'oil', and dates are not enough. If a publisher
blocks reading, retain that article as an independent item.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/"data/news.json"
BODIES=ROOT/".article_texts.json"
INSIGHTS=ROOT/"data/insights.json"

def normalize(text):
    return re.sub(r"[^\w\u3400-\u9fff]+","",text.casefold())[:24000]

def source_url(row):
    address=row.get("source_url") or ""
    if not address:return ""
    s=urlsplit(address)
    if s.netloc.endswith("news.google.com"):return ""
    return urlunsplit((s.scheme,s.netloc.lower(),s.path.rstrip("/"),"",""))

def proven_duplicate(a,b,texts):
    ta=texts.get(a["id"],"");tb=texts.get(b["id"],"")
    if len(ta)<380 or len(tb)<380:
        return False
    # Re-reading the actual publisher content is a prerequisite; one broad
    # keyword or headline match must never be treated as an identical event.
    na=normalize(ta);nb=normalize(tb)
    if not na or not nb:return False
    if min(len(na),len(nb))/max(len(na),len(nb))<.88:return False
    # 9-character content shingles compare full factual text, not just topic.
    # Fast enough to run across daily batches without expensive O(n²) alignment.
    shingles=lambda x:set(x[i:i+9] for i in range(0,max(0,len(x)-8),4))
    sa=shingles(na[:8500]);sb=shingles(nb[:8500])
    if not sa or not sb:return False
    if len(sa&sb)/len(sa|sb)<.89:return False
    nums=lambda text:set(x for x in re.findall(r"\d+(?:[.,]\d+)?",text) if len(x)>=3)
    a_nums=nums(na);b_nums=nums(nb)
    if a_nums and b_nums and len(a_nums&b_nums)/min(len(a_nums),len(b_nums))<.85:
        return False
    return True


def headline_key(article):
    """Remove a trailing publisher suffix; preserve the factual headline."""
    title=(article.get("title") or "").strip()
    publisher=(article.get("source") or "").strip()
    # The suffix must be an actual publisher label, not part of the story.
    if publisher:
        escaped=re.escape(publisher)
        title=re.sub(r"\s+[-–|｜]\s*"+escaped+r"\s*$","",title,flags=re.I)
    title=re.sub(r"[\s\u3000]+"," ",title).casefold()
    title=re.sub(r"[^\w\u3400-\u9fff]+","",title)
    return title if len(title)>=22 else ""


def same_publication_window(a,b):
    """Exact syndication headlines within 48 hours; no broad topic merging."""
    try:
        ta=datetime.fromisoformat(a.get("published_at") or a["discovered_at"])
        tb=datetime.fromisoformat(b.get("published_at") or b["discovered_at"])
        return abs((ta-tb).total_seconds())<=48*3600
    except (KeyError,TypeError,ValueError):
        return False


def exact_title_duplicate(a,b):
    ka,kb=headline_key(a),headline_key(b)
    return bool(ka and kb and ka==kb and same_publication_window(a,b))


def keep_priority(article,insight_ids):
    """Prefer source-supported analysis, then direct publisher links."""
    direct=source_url(article)
    trusted=article.get("source","").casefold() in ("reuters","中央社 cna","經濟日報")
    return (
        article.get("id") in insight_ids,
        article.get("access_status")=="readable",
        bool(direct),
        trusted,
    )


def main():
    d=json.loads(NEWS.read_text(encoding="utf-8"))
    rows=d.get("items",[])
    texts=json.loads(BODIES.read_text(encoding="utf-8")) if BODIES.exists() else {}
    ins=json.loads(INSIGHTS.read_text(encoding="utf-8")) if INSIGHTS.exists() else {"items":[]}
    insight_ids={ident for record in ins.get("items",[]) for ident in record.get("article_ids",[])}
    # A strong exact-headline match is sufficient even if publisher bodies failed.
    # For different headlines, continue to require two verified full texts.
    chosen=[]
    removed={}
    exact_count=0
    body_count=0
    for item in sorted(rows,key=lambda x:keep_priority(x,insight_ids),reverse=True):
        prior=None
        by_title=False
        for existing in chosen:
            if exact_title_duplicate(item,existing):
                prior=existing
                by_title=True
                break
            if proven_duplicate(item,existing,texts):
                prior=existing
                break
        if prior:
            removed[item["id"]]=prior["id"]
            for sector in item.get("industries",[]):
                if sector not in prior.get("industries",[]):
                    prior.setdefault("industries",[]).append(sector)
            if by_title:
                exact_count+=1
                print("CONFIRMED SAME HEADLINE:",item["id"],"duplicate of",prior["id"])
            else:
                body_count+=1
                print("CONFIRMED SAME BODY:",item["id"],"duplicate of",prior["id"])
        else:
            chosen.append(item)
    if removed:
        d["items"]=chosen
        NEWS.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        # Analyses of removed source IDs must not be silently assigned to a
        # different publisher; retain only analyses of surviving sources.
        if INSIGHTS.exists():
            for entry in ins.get("items",[]):
                entry["article_ids"]=[x for x in entry.get("article_ids",[]) if x not in removed]
            ins["items"]=[x for x in ins["items"] if x.get("article_ids")]
            INSIGHTS.write_text(json.dumps(ins,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Duplicate removal: exact publisher-suffixed headlines",exact_count,
          "; full body confirmed",body_count,"; total",len(removed),"/",len(rows))
if __name__=="__main__":main()
