"""Offline market parser tests; no Groq, requests or live endpoints."""
from datetime import datetime
from zoneinfo import ZoneInfo
from update_market import parse_fx_esun, parse_brent_csv, parse_brent_text, parse_brent_eia_html, parse_brent_datahub_csv
now=datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
sample=f'''<html><body><h2>玉山銀行即期外匯匯率表</h2>
<span>資料日期：{now}</span><table>
<thead><tr><th>幣別</th><th>買入</th><th>賣出</th></tr></thead><tbody>
<tr><td>人民幣(CNY)</td><td>4.919</td><td>4.969</td></tr>
<tr><td>歐元(EUR)</td><td>36.04</td><td>36.44</td></tr>
<tr><td>日圓(JPY)</td><td>0.2056</td><td>0.2096</td></tr>
<tr><td>美元(USD)</td><td>32.94</td><td>33.04</td></tr>
</tbody></table></body></html>'''
fx=parse_fx_esun(sample)
assert fx["source"]=="玉山銀行" and fx["quote_type"]=="即期買入",fx
assert fx["rates"]=={"USD":32.94,"EUR":36.04,"JPY":0.2056,"CNY":4.919},fx
assert fx["quote_time"]==now[:16].replace("-","/"),fx
for broken in (sample.replace("買入",""),sample.replace("<td>美元(USD)</td>","<td>另一種幣別</td>"),
               sample.replace("32.94","abc"),sample.replace(now,"2025-01-01 09:00:00")):
    try:
        parse_fx_esun(broken)
        raise AssertionError("incomplete, stale or unlabeled E.SUN bank rates accepted")
    except ValueError:pass
print("PASS official E.SUN spot BUY four currencies; stale, missing & ambiguous rejected")
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
print("PASS Brent history, fallback text and comparative changes")


eia_html="""<table><tr><th>Week Of</th><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th></tr>
<tr><td>2026 Oct-19 to Oct-23</td><td>80</td><td>81</td><td>82</td><td>83</td><td>84</td></tr>
<tr><td>2026 Nov- 9 to Nov-13</td><td>87</td><td>88</td><td>89</td><td>90</td><td>91</td></tr>
<tr><td>2026 Nov-16 to Nov-20</td><td>94</td><td>95</td><td>96</td><td>97</td><td>99</td></tr></table>"""
eia=parse_brent_eia_html(eia_html)
assert eia["quote_date"]=="2026-11-20" and eia["price_usd_per_barrel"]==99,eia
assert eia["change_week"] is not None and eia["change_month"] is not None,eia
print("PASS direct EIA HTML Brent fallback")

hub=parse_brent_datahub_csv("Date,Price\n2026-11-13,95.5\n2026-11-20,99.7\n2026-10-20,90.1\n")
assert hub["quote_date"]=="2026-11-20" and hub["price_usd_per_barrel"]==99.7,hub
assert "DataHub" in hub["source"] and "datahub.io" in hub["source_url"]
print("PASS EIA-derived DataHub fallback retains provenance and dated quote")

