"""Fixed public information topic taxonomy for incoming articles and archive migration."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TOPICS=tuple(x["name"] for x in json.loads((ROOT/"config/topic_taxonomy.json").read_text(encoding="utf-8"))["topics"])
ALIASES={
 "國內政策":"政策與貿易措施",
 "國際政策":"政策與貿易措施",
 "地緣政治":"國際情勢與能源",
 "上游原物料":"供應鏈與原物料",
 "物流供應鏈":"物流與航運",
 "台灣產業":"產業動態",
 "手工具業者":"產業動態",
 "金屬加工協作":"產業動態",
}
RULES=(
 ("匯率與出口競爭力",("匯率","新台幣","台幣","日圓","歐元","外匯","exchange rate","forex","currency")),
 ("物流與航運",("航運","運費","貨櫃","海運","港口","航線","shipping","freight","logistics")),
 ("政策與貿易措施",("關稅","反傾銷","出口管制","貿易限制","制裁","法規","tariff","antidumping","trade ban")),
 ("供應鏈與原物料",("鋼價","鋼材","鋼鐵","銅價","鋁價","原物料","原料成本","零件缺料","供應鏈","supply chain","steel prices","copper prices")),
 ("國際情勢與能源",("油價","石油","原油","能源","天然氣","戰爭","地緣","霍爾木茲","荷莫茲","crude oil","oil price","energy crisis","war")),
 ("進出口與訂單趨勢",("出口","外銷","進口","訂單","接單","出貨","export","import","orders")),
 ("技術發展與產業轉型",("智慧製造","自動化","數位轉型","技術研發","研發","創新製程","智能製造","automation","robotics technology")),
 ("市場需求與景氣",("需求","景氣","庫存","銷售","消費市場","sales","inventory","market demand")),
)
def canonical_topic(article):
    """One fixed topic per article; evidence is the original headline first."""
    title=(article.get("title") or "").casefold()
    for name,words in RULES:
        if any(word.casefold() in title for word in words):return name
    existing=ALIASES.get(article.get("topic"),article.get("topic"))
    if existing in TOPICS:return existing
    return "產業動態"

def normalize_article(article):
    article["topic"]=canonical_topic(article)
    # Avoid redundant industry/topic "tags" entirely: fixed region, sector,
    # topic are the only public pills. Never create new arbitrary labels.
    article["tags"]=[]
    bad=("版權所有","著作權所有","copyright","all rights reserved","隱私權")
    if article.get("title_zh","").strip().casefold().strip("。!！ " ) in bad:
        article.pop("title_zh",None)
        article.pop("translation_method",None)
    return article
