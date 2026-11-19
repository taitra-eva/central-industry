"""Entity-aware candidate discovery, without matching bare 'tools' or brands blindly."""
import json
import re
from pathlib import Path
from functools import lru_cache
DATA=Path(__file__).resolve().parents[1]/"config/industry_entities.json"
EVENTS=("訂單","接單","出貨","擴產","增產","產能","營收","獲利","財報","併購","收購","投資","設廠","關廠","裁員","出口","量產","新品","合作","市場","庫存","營運","供應鏈","sales","revenue","earnings","results","orders","backlog","production","manufacturing","manufacturer","manufactured","factory","plant","capacity","acquisition","investment","export","demand","launch","market","layoffs","restructuring","forecast","partnership","expansion","growth","shipment","tariff","業績","売上","受注","生産","工場","買収","輸出","新製品")
PRODUCT={
"總體情勢":("鋼價","油價","石油","原油","運費","關稅","匯率","鋼鐵","oil price","steel price"),
"機械與金屬加工":("工具機","機床","金屬加工","滾珠螺桿","線性滑軌","線軌","加工中心","CNC","machining","machine tool","metalworking","woodworking machinery"),
"自行車":("自行車","電動自行車","電動二輪車","電動三輪車","電動機車","單車","車架","變速器","bike","bicycle","e-bike","cycling","pedelec","tricycle"),
"汽配":("汽車零件","汽車零組件","汽配","車燈","車用","售後市場","aftermarket","automotive parts","auto parts","car parts","vehicle parts","headlamp"),
"手工具":("手工具","電動工具","氣動工具","汽修工具","汽車維修工具","特殊工具","套筒","扳手","園藝工具","power tool","hand tool","special tool","socket wrench","tool storage","cordless drill","outdoor power equipment","repair tool"),
"無人載具及機器人":("機器人","無人機","無人載具","無人船","機械手臂","協作機器人","drone","robot","unmanned","cobot","humanoid","UAV","UAS")}
@lru_cache(maxsize=1)
def entities():
    return json.loads(DATA.read_text(encoding="utf-8"))["sectors"]
def has(text,term):
    text=(text or "").casefold()
    term=term.casefold()
    if term.isascii() and term.replace(" ","").isalnum():
        return bool(re.search(r"(?<![a-z0-9])"+re.escape(term)+r"(?![a-z0-9])",text))
    return term in text
def entity_event(title,sector):
    entry=entities().get(sector,{})
    event=any(has(title,w) for w in EVENTS)
    product=any(has(title,w) for w in PRODUCT.get(sector,()))
    strong=any(has(title,w) for w in entry.get("strong",()))
    ambiguous=any(has(title,w) for w in entry.get("contextual",()))
    return bool((strong and (event or product)) or (ambiguous and product and event))
def entity_sectors(title):
    return [sector for sector in entities() if entity_event(title,sector)]
