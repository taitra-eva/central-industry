"""Offline scope regression tests: exclude pure ICT but preserve relevant downstream news."""
from relevance import should_keep, ict_out_of_scope
block=(
 "傳美出口管制新規衝擊 台積電、三星暫停部分對中晶片出貨",
 "美擴大先進半導體出口管制 馬來西亞尋求釐清資料中心服務規範",
 "美國 BIS 對超級智慧晶片、伺服器遠端存取出口管制升級",
 "BIS強化AI晶片管制 供應鏈洗牌…台鏈穩站受惠第一排",
 "記憶體教父養出小金雞 下一步要建立本土特殊氣體供應鏈",
 "台積電強化整頓供應鏈 沒改善就掉單",
)
keep=(
 "移民署警政署無人機採購案混陸晶片 內政部朝解約處理",
 "搶攻無人化晶圓廠 三星海力士美光聯手制定機器人充電標準",
 "元太電子紙打進Google機器人鏈 串聯人機介面",
 "機械工具機廠商供應半導體設備精密金屬零組件",
 "電動汽車車用晶片短缺 衝擊汽車零組件廠商",
 "自行車零件及手工具外銷面臨美國關稅調整",
 "運價大漲影響機械出口運送成本",
)
for t in block:
 assert ict_out_of_scope(t),t
 assert not should_keep(t,"總體情勢")[0],t
for t in keep:
 assert not ict_out_of_scope(t),t
 assert should_keep(t)[0],t
print("PASS ICT only excluded; robotics, drones, machine tools, cycling, automotive and macro logistics kept")
