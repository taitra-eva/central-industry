"""Remove only confirmed duplicate articles, never articles about a common topic.

Source-text similarity is necessary for cross-publisher merging; headline,
industry, keywords, the word 'oil', and dates are not enough. If a publisher
blocks reading, retain that article as an independent item.
"""
import json
import re
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

def main():
    if not BODIES.exists():
        print("Duplicate review skipped: original publisher bodies unavailable")
        return
    texts=json.loads(BODIES.read_text(encoding="utf-8"))
    if not texts:
        print("Duplicate review: no publisher texts available; no headlines merged")
        return
    d=json.loads(NEWS.read_text(encoding="utf-8"))
    rows=d.get("items",[])
    chosen=[]
    removed={}
    for item in rows:
        prior=None
        for existing in chosen:
            if proven_duplicate(item,existing,texts):
                prior=existing
                break
        if prior:
            removed[item["id"]]=prior["id"]
            print("CONFIRMED SAME BODY:",item["id"],"duplicate of",prior["id"])
        else:chosen.append(item)
    if removed:
        d["items"]=chosen
        NEWS.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        # Keep previous editorial analyses only if a surviving article backs
        # them. Never replace their source IDs with unverified alternatives.
        if INSIGHTS.exists():
            ins=json.loads(INSIGHTS.read_text(encoding="utf-8"))
            for entry in ins.get("items",[]):
                entry["article_ids"]=[x for x in entry.get("article_ids",[]) if x not in removed]
            ins["items"]=[x for x in ins["items"] if x.get("article_ids")]
            INSIGHTS.write_text(json.dumps(ins,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Content-confirmed duplicate removal:",len(removed),"/",len(rows))
if __name__=="__main__":main()
