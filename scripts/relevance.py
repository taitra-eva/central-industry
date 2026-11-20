"""Conservative industry intelligence relevance filter for RSS and ITIS discovery.

Blocks personal notices, navigation/static pages and investment sales pitches.
Keeps industrial policies, manufacturing supply chains, global shipping/energy.
This is a first-pass rule filter, not semantic or editorial fact-checking.
"""
import re

ADMIN_EXCLUSIONS = (
    "公示送達", "送達本部", "送達處分書", "處分書", "違反臺灣地區與大陸地區人民關係條例",
    "違反台灣地區與大陸地區人民關係條例", "身分證統一編號",
    "撤銷營業登記", "個人罰鍰", "行政執行", "催繳通知",
)
PAGE_TITLES = (
    "版權所有", "著作權所有", "copyright", "所有權利保留", "網站地圖", "隱私權政策",
    "公告訊息", "新聞稿", "活動花絮", "全球商機資訊", "網站導覽", "更多資訊",
    "知識經濟產業組業務內容", "經貿資訊網", "重要連結", "首頁", "最新消息",
)
PROMOTIONAL = (
    "美股交易", "多元資產", "外匯交易平台", "槓桿交易", "開戶優惠", "投資廣告",
    "品牌置入", "業配", "廣編特輯", "贊助內容",
    "etf", "募集", "開募", "申購", "股價", "stock after", "is a buy",
    "投資組合", "選股", "基金推薦", "哪檔", "買進", "賣出", "股利",
)
GENERAL_POLITICS = (
    "midterms", "democrats", "blue wave", "landslide win", "scapegoat",
    "美國期中選舉", "國會選舉", "政治評論", "election prediction",
)
SUBSTANTIVE = (
    "製造", "工業生產", "工廠", "供應鏈", "出口", "外銷", "進口",
    "關稅", "匯率", "新台幣", "日圓", "歐元", "外匯", "能源", "油價", "原油", "航運", "運費", "港口", "物流", "原物料",
    "鋼", "銅", "鋁", "機械", "工具", "水五金", "汽車", "自行車", "無人", "機器人",
    "factory", "manufacturer", "manufacturing", "industrial production", "supply chain",
    "tariff", "exchange rate", "currency", "forex", "exports", "imports", "trade", "energy", "oil", "crude",
    "shipping", "freight", "port", "steel", "copper", "aluminum", "robot",
    "automotive", "bicycle", "machine tool", "hardware",
)

# Reject chip/server stories if no tangible link to one of six industries.
# Generic "export controls", "supply chain" or "policy" is NOT a link.
ICT_SUBJECTS=("晶片","半導體","伺服器","資料中心","數據中心","記憶體","晶圓","台積電","晶圓代工","hbm","gpu","semiconductor","chip","data center","datacenter","server","dram","foundry")
INDUSTRIAL_BRIDGES=("工具機","金屬加工","機械加工","精密機械","木工機","車床","加工中心","cnc","機床","線性滑軌","滾珠螺桿","沖壓","鍛造","鑄造","machine tool","metalworking","工業機器人","機器人","機械手臂","人形機器人","協作機器人","robot","無人機","無人載具","無人船","uav","drone","unmanned","自行車","電動二輪車","電動三輪車","e-bike","bicycle","bike","電動機車","汽車零組件","汽車零配件","汽配","汽車零件","車用零件","車用零組件","車載","automotive parts","auto parts","手工具","汽修工具","電動工具","氣動工具","扳手","套筒","五金工具","hand tool","power tool","鋼鐵","鋼價","鋁價","銅價","航運","運價","貨櫃","海運","油價","原油")
def ict_out_of_scope(title):
    """True for ICT-centric headlines with no explicit industrial product/sector."""
    low=(title or "").casefold()
    return any(term in low for term in ICT_SUBJECTS) and not any(term in low for term in INDUSTRIAL_BRIDGES)

def should_keep(title, industry=None):
    text = re.sub(r"\s+", " ", title or "").strip()
    low = text.casefold()
    if len(text) < 12:
        return False, "short_or_empty_title"
    if ict_out_of_scope(text):
        return False, "ict_only_without_six_sector_industry_connection"
    if re.search(r"(?:^|[\s｜|:：-])(?:版權所有|著作權所有|Copyright(?: ©)?|All Rights Reserved)(?:[\s。｜|:：-]|$)",text,re.I):
        return False, "copyright_footer_or_navigation"
    # Exclude university publicity about recruitment or talent programs when
    # it lacks a concrete factory, actual order or industrial product.
    university=(("大學" in text or "學院" in text) and
                any(word in text for word in ("培育", "招生", "人才", "名校", "國際合作", "學術交流")))
    tangible=any(word in text for word in ("量產", "出貨", "接單", "製程", "設備訂單", "生產線", "廠房投資", "商用產品"))
    if university and not tangible:
        return False, "academic_pr_not_industrial_news"
    if any(p.casefold() in low for p in ADMIN_EXCLUSIONS):
        return False, "individual_administrative_notice"
    # Generic homepages and category directories are not dated news articles.
    stripped = re.sub(r"\s*[-–|｜]\s*[^-–|｜]+$", "", text).strip()
    if any(stripped == p or stripped.startswith(p + " -") for p in PAGE_TITLES):
        return False, "website_navigation_page"
    if re.search(r"(?:^|\s)[(（]?(?:[A-Z][a-z]+ Republic|The Netherlands|Argentine Republic|Oriental Republic of Uruguay)", text):
        if "經貿檔" in text:
            return False, "static_country_profile"
    if "經貿檔" in text:
        return False, "static_country_profile"
    if any(p in low for p in PROMOTIONAL):
        return False, "investment_or_sales_promotion"
    if industry == "總體情勢":
        if any(p in low for p in GENERAL_POLITICS) and not any(p in low for p in ("manufactur","industrial","supply chain","產業","製造","工業","供應鏈")):
            return False, "general_political_commentary"
        if not any(p in low for p in SUBSTANTIVE):
            return False, "no_concrete_economic_or_industry_subject"
    return True, "industry_relevant_candidate"

# Exclude direct government publishing. This does NOT exclude private-sector
# reporting about a policy, tariff, budget or ministry decision.
GOVERNMENT_SOURCE_LABELS = (
    "經濟部", "財政部", "產業發展署", "關務署", "國際貿易署",
    "行政院", "交通部", "勞動部", "國家發展委員會", "國發會",
    "農業部", "環境部", "能源署", "工業局", "中央銀行",
)
def is_government_source(source="", url=""):
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").casefold()
    if any(host == t or host.endswith("." + t) for t in ("gov.tw", "gov.jp", "gov.hk", "gov.sg", "gov.uk", "gov")):
        return True
    # For Google News RSS proxy links, source title is the only available
    # publisher indicator until the URL can be resolved.
    name = (source or "").strip()
    if any(name == label or name.startswith(label+" -") or name.startswith(label+"｜") or name.startswith(label+"（") for label in GOVERNMENT_SOURCE_LABELS):
        return True
    if name in ("經濟部產業發展署", "經濟部統計處", "財政部關務署"):
        return True
    return False
