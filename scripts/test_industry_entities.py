"""Regression checks for brand-driven candidate discovery; run without network."""
from industry_entities import entity_event, entity_sectors
cases=[
 ("Stanley Black & Decker reports quarterly earnings","手工具",True),
 ("Makita manufacturing capacity expansion","手工具",True),
 ("Bosch Power Tools reports 2026 sales","手工具",True),
 ("Milwaukee weather forecast for tomorrow","手工具",False),
 ("Bosch invests in software services","手工具",False),
 ("Best AI tools for writing emails","手工具",False),
 ("Giant Bicycles reports declining sales","自行車",True),
 ("Shimano fishing tackle sales outlook","自行車",False),
 ("Shimano bicycle components demand rises","自行車",True),
 ("TYC automotive lighting orders rise","汽配",True),
 ("DMG MORI machine tool orders rise","機械與金屬加工",True),
 ("Skydio drone factory expansion","無人載具及機器人",True),
 ("DJI camera accessories review","無人載具及機器人",False),
 ("Toyota car plant expansion","汽配",False),
]
for title,sector,want in cases:
    got=entity_event(title,sector)
    assert got==want, f"{title}: {sector}: expected {want}, got {got}"
print("PASS",len(cases),"entity candidate tests")
