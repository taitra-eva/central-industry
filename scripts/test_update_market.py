"""Offline tests for market-only price parsers, no news or live requests."""
from update_market import parse_fx, parse_brent_csv, parse_brent_text, parse_fx_text, parse_fx_csv, parse_fx_verified_mirror, parse_brent_eia_html, parse_brent_datahub_csv
sample='''<html><body><span>牌價最新掛牌時間：2026/11/20 09:05</span><table><tbody>
<tr><td>美金 (USD)</td><td>32.00</td><td>33.00</td><td>32.30</td><td>32.50</td></tr>
<tr><td>歐元 (EUR)</td><td>36.00</td><td>37.00</td><td>36.30</td><td>36.50</td></tr>
<tr><td>日圓 (JPY)</td><td>0.20</td><td>0.23</td><td>0.21</td><td>0.22</td></tr>
<tr><td>人民幣 (CNY)</td><td>4.20</td><td>4.30</td><td>4.24</td><td>4.27</td></tr>
</tbody></table></body></html>'''
fx=parse_fx(sample)
assert fx["quote_type"]=="即期買入"
assert fx["quote_time"]=="2026/11/20 09:05"
assert fx["rates"]=={"USD":32.30,"EUR":36.30,"JPY":0.21,"CNY":4.24},fx
oil=parse_brent_csv("observation_date,DCOILBRENTEU\n2026-11-18,94.10\n2026-11-19,.\n2026-11-17,93.75\n")
assert oil["quote_date"]=="2026-11-18" and oil["price_usd_per_barrel"]==94.10,oil
oil2=parse_brent_csv("observation_date,DCOILBRENTEU\n2026-10-20,80\n2026-11-13,90\n2026-11-20,99\n")
assert oil2["change_week"]["pct"]==10.0,oil2
assert oil2["change_month"]["pct"]==23.75,oil2
assert oil2["change_week"]["base_date"]=="2026-11-13",oil2
assert oil2["change_month"]["base_date"]=="2026-10-20",oil2
fallback=parse_brent_text("Some FRED metadata\nDATE VALUE\n2026-11-10 90.16\n2026-11-17 92.94\n2026-10-19 118.82\n")
assert fallback["quote_date"]=="2026-11-17",fallback
assert fallback["change_week"]["pct"]==3.08,fallback
assert fallback["change_month"]["pct"]==-21.78,fallback
print("PASS market FX, Brent history, fallback text and comparative changes")

bot_txt="""Currency Rate Cash Spot Forward
USD         Buying       32.50000    32.85000        32.90000 Selling 33.00 32.95
EUR         Buying       36.00000    36.15000        36.19000 Selling 37.00 36.45
JPY         Buying        0.20000     0.20430         0.20500 Selling 0.21 0.208
CNY         Buying        4.86000     4.92100         4.93100 Selling 5.01 4.97
"""
fx2=parse_fx_text(bot_txt)
assert fx2["rates"]=={"USD":32.85,"EUR":36.15,"JPY":0.2043,"CNY":4.921},fx2
assert fx2["quote_time"] is None and fx2["quote_type"]=="即期買入"
eia_html="""<table><tr><th>Week Of</th><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th></tr>
<tr><td>2026 Oct-19 to Oct-23</td><td>80</td><td>81</td><td>82</td><td>83</td><td>84</td></tr>
<tr><td>2026 Nov- 9 to Nov-13</td><td>87</td><td>88</td><td>89</td><td>90</td><td>91</td></tr>
<tr><td>2026 Nov-16 to Nov-20</td><td>94</td><td>95</td><td>96</td><td>97</td><td>99</td></tr></table>"""
eia=parse_brent_eia_html(eia_html)
assert eia["quote_date"]=="2026-11-20" and eia["price_usd_per_barrel"]==99,eia
assert eia["change_week"] is not None and eia["change_month"] is not None,eia
print("PASS official BOT TXT spot-buy fallback and direct EIA HTML Brent fallback")

hub=parse_brent_datahub_csv("Date,Price\n2026-11-13,95.5\n2026-11-20,99.7\n2026-10-20,90.1\n")
assert hub["quote_date"]=="2026-11-20" and hub["price_usd_per_barrel"]==99.7,hub
assert "DataHub" in hub["source"] and "datahub.io" in hub["source_url"]
print("PASS EIA-derived DataHub fallback retains provenance and dated quote")

sample_csv='''Currency,Rate,Cash,Spot,Forward-10Days
USD,Buying,32.50000,32.85000,32.90000
EUR,Buying,36.00000,36.15000,36.19000
JPY,Buying,0.20000,0.20430,0.20500
CNY,Buying,4.86000,4.92100,4.93100
'''
fx_csv=parse_fx_csv(sample_csv)
assert fx_csv["rates"]==fx2["rates"],fx_csv
print("PASS BOT public CSV strict named Buying/Spot row parser")

import json
from datetime import datetime, timezone
mirror_doc={
 "base":"TWD","source":"Taiwan Bank (臺灣銀行牌告匯率)",
 "sourceUrl":"https://rate.bot.com.tw/xrt",
 "sourcePublishedAt":datetime.now(timezone.utc).isoformat(),
 "details":{
  "USD":{"spot":{"buy":32.935,"sell":33.035}},
  "EUR":{"spot":{"buy":36.03,"sell":36.43}},
  "JPY":{"spot":{"buy":0.2056,"sell":0.2096}},
  "CNY":{"spot":{"buy":4.915,"sell":4.965}}
 }
}
verified=parse_fx_verified_mirror(json.dumps(mirror_doc))
assert verified["quote_type"]=="即期買入" and verified["rates"]=={
 "USD":32.935,"EUR":36.03,"JPY":0.2056,"CNY":4.915},verified
assert verified["provenance"].startswith("third_party_mirror")
mirror_doc["sourcePublishedAt"]="2023-11-23T03:01:00Z"
try:
 parse_fx_verified_mirror(json.dumps(mirror_doc))
 raise AssertionError("Stale mirror must be rejected")
except ValueError:pass
print("PASS verified BOT third-party mirror spot-buy schema and stale-data guard")
