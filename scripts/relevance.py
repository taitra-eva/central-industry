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
    "公告訊息", "新聞稿", "活動花絮", "全球商機資訊", "網站導覽", "更多資訊",
    "知識經濟產業組業務內容", "經貿資訊網", "重要連結", "首頁", "最新消息",
)
PROMOTIONAL = (
    "etf", "募集", "開募", "申購", "股價", "stock after", "is a buy",
    "投資組合", "選股", "基金推薦", "哪檔", "買進", "賣出", "股利",
)
GENERAL_POLITICS = (
    "midterms", "democrats", "blue wave", "landslide win", "scapegoat",
    "美國期中選舉", "國會選舉", "政治評論", "election prediction",
)
SUBSTANTIVE = (
    "製造", "工業", "產業", "企業", "廠商", "供應鏈", "出口", "外銷", "進口",
    "關稅", "能源", "油價", "原油", "航運", "運費", "港口", "物流", "原物料",
    "鋼", "銅", "鋁", "機械", "工具", "水五金", "汽車", "自行車", "無人", "機器人",
    "factory", "manufacturer", "manufacturing", "industrial", "industry", "supply",
    "tariff", "exports", "imports", "trade", "energy", "oil", "crude",
    "shipping", "freight", "port", "steel", "copper", "aluminum", "robot",
    "automotive", "bicycle", "machine tool", "hardware",
)

def should_keep(title, industry=None):
    text = re.sub(r"\s+", " ", title or "").strip()
    low = text.casefold()
    if len(text) < 12:
        return False, "short_or_empty_title"
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
