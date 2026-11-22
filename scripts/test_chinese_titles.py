"""Regression checks for already-Chinese publisher headlines.

Runs offline: no news fetch, Groq call, or third-party models.
"""
from translate import language, title_language
from build_brief import display_title as brief_title
from generate_ai_insights import display_title as insight_title

CASES=[
    "限空令擋不住台股跌勢！卓榮泰提4點裁示 國安基金強化穩市、央行緊盯匯率",
    "6,076億元追加預算過關 油價、民生電價凍漲到2028年1月底",
    "智慧製造研發計畫促投資逾154億 經部助攻高階工具機自主化",
    "稅率最高27% 歐課鋼材反傾銷稅 中鋼、中鴻承壓",
    "雷虎科技董事長陳冠如：無人機非藝術品 消耗戰須具大量生產能力【專訪】",
]
for title in CASES:
    article={"title":title,"title_zh":"{\\fn黑體\\fs22}亂碼!","language_hint":"en",
             "translation_method":"argos_offline_machine_translation"}
    assert language(title) is None,title
    assert title_language(article) is None,title
    assert brief_title(article)==title,title
    assert insight_title(article)==title,title

assert language("New machine tool orders rise")=="en"
assert language("日本の工作機械受注が増加")=="ja"
assert title_language({"title":"Semiconductor exports","language_hint":"en"})=="en"
print("PASS: Chinese publisher headlines override corrupted English hints and translations")
