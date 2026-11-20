"""Offline tests for market-only price parsers, no news or live requests."""
from update_market import parse_fx, parse_brent_csv
sample='''<html><body><span>牌價最新掛牌時間：2026/11/20 09:05</span><table><tbody>
<tr><td>美金 (USD)</td><td>32.00</td><td>33.00</td><td>32.30</td><td>32.50</td></tr>
<tr><td>歐元 (EUR)</td><td>36.00</td><td>37.00</td><td>36.30</td><td>36.50</td></tr>
<tr><td>日圓 (JPY)</td><td>0.20</td><td>0.23</td><td>0.21</td><td>0.22</td></tr>
<tr><td>人民幣 (CNY)</td><td>4.20</td><td>4.30</td><td>4.24</td><td>4.27</td></tr>
</tbody></table></body></html>'''
fx=parse_fx(sample)
assert fx["quote_type"]=="即期賣出"
assert fx["quote_time"]=="2026/11/20 09:05"
assert fx["rates"]=={"USD":32.50,"EUR":36.50,"JPY":0.22,"CNY":4.27},fx
oil=parse_brent_csv("observation_date,DCOILBRENTEU\n2026-11-18,94.10\n2026-11-19,.\n2026-11-17,93.75\n")
assert oil["quote_date"]=="2026-11-18" and oil["price_usd_per_barrel"]==94.10,oil
oil2=parse_brent_csv("observation_date,DCOILBRENTEU\n2026-10-20,80\n2026-11-13,90\n2026-11-20,99\n")
assert oil2["change_week"]["pct"]==10.0,oil2
assert oil2["change_month"]["pct"]==23.75,oil2
assert oil2["change_week"]["base_date"]=="2026-11-13",oil2
assert oil2["change_month"]["base_date"]=="2026-10-20",oil2
print("PASS market FX, Brent history and comparative changes")
