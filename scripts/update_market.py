"""Update only the market price JSON. No news search, publisher reading or AI calls.

FX: Bank of Taiwan indicative *spot selling* board rates.
Oil: EIA Brent Europe daily spot (FOB), delivered via FRED public CSV.
Quote date is preserved. Missing/unparseable data are never invented.
"""
import csv
import io
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "market.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CentralIndustryMarket/1.0)"}
FX_URL = "https://rate.bot.com.tw/xrt?Lang=zh-TW"
FX_BACKUP_URL = "https://rate.bot.com.tw/xrt/all/day?page=print"
BRENT_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
BRENT_TEXT_URL = "https://fred.stlouisfed.org/data/DCOILBRENTEU.txt"
BR = "https://fred.stlouisfed.org/series/DCOILBRENTEU"
CODES = ("USD", "EUR", "JPY", "CNY")

def parse_fx(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    stamps = re.findall(r"(20\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})", text)
    if not stamps:
        raise ValueError("Bank of Taiwan quotation timestamp missing")
    stamp = stamps[-1][0] + " " + stamps[-1][1]
    rows = {}
    for tr in soup.select("tr"):
        cells = tr.find_all("td", recursive=False)
        if not cells: 
            continue
        label = tr.get_text(" ", strip=True)
        for code in CODES:
            if not re.search(r"\b"+code+r"\b",label):
                continue
            # On BOT's four-rate table, first currency td is followed by
            # cash buy, cash sell, spot buy, spot sell (not cash sell).
            values = [td.get_text(" ", strip=True).replace(",","") for td in cells]
            numerical = [float(x) for x in values if re.fullmatch(r"\d+(?:\.\d+)?",x)]
            if len(numerical) < 4:
                raise ValueError("Missing four numeric quote columns for "+code)
            value = numerical[3]
            if not 0 < value < 200:
                raise ValueError("Invalid spot selling quote for "+code)
            rows[code] = value
    if set(rows) != set(CODES):
        raise ValueError("Missing currency rows: "+str(set(CODES)-set(rows)))
    return {"source":"臺灣銀行","quote_type":"即期賣出","quote_time":stamp,
            "source_url":FX_URL,"currency":"TWD","rates":rows}

def parse_brent_csv(contents):
    rows = list(csv.DictReader(io.StringIO(contents)))
    if not rows:
        raise ValueError("Brent source CSV has no rows")
    valid = []
    for item in rows:
        date = item.get("observation_date") or item.get("DATE") or item.get("Date") or ""
        value = item.get("DCOILBRENTEU") or ""
        try:
            d = datetime.strptime(date[:10],"%Y-%m-%d").date()
            p = float(value)
            if 0 < p < 1000: valid.append((d,p))
        except (ValueError,TypeError):
            pass
    if not valid:
        raise ValueError("No numeric Brent observations")
    day, value = max(valid,key=lambda x:x[0])
    def compare(days_back):
        target=day-timedelta(days=days_back)
        # Nearest available trading day, either side of calendar target.
        # A 30-day target may fall on a weekend or non-trading day.
        candidates=[(d,p) for d,p in valid if abs((target-d).days)<=4]
        if not candidates:
            return None
        base_date,base_price=min(candidates,key=lambda dp:(abs((target-dp[0]).days),dp[0]>target))
        if base_price<=0:return None
        return {"pct":round((value/base_price-1)*100,2),
                "base_date":base_date.isoformat(),"base_price":base_price}
    week=compare(7)
    month=compare(30)
    return {"source":"美國能源資訊署 EIA（經 FRED 公開資料）",
            "benchmark":"Brent","quote_type":"歐洲布蘭特原油現貨 FOB",
            "quote_date":day.isoformat(),"price_usd_per_barrel":value,
            "change_week":week,"change_month":month,
            "source_url":BR}


def parse_brent_text(contents):
    # FRED's second published format is a whitespace-delimited table with
    # DATE VALUE rows, preceded by descriptive metadata.
    rows=[]
    for line in contents.splitlines():
        match=re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s+(\d+(?:\.\d+)?)\s*$",line)
        if match: rows.append({"observation_date":match.group(1),"DCOILBRENTEU":match.group(2)})
    if not rows: raise ValueError("FRED text contained no daily prices")
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=("observation_date","DCOILBRENTEU"))
    writer.writeheader()
    writer.writerows(rows)
    return parse_brent_csv(output.getvalue())

def main():
    old=json.loads(DEST.read_text(encoding="utf-8")) if DEST.exists() else {}
    updated=dict(old)
    now=datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    failed=[]
    for name, endpoints in [
        ("fx",[(FX_URL,parse_fx),(FX_BACKUP_URL,parse_fx)]),
        ("oil",[(BRENT_CSV_URL,parse_brent_csv),(BRENT_TEXT_URL,parse_brent_text)]),
    ]:
        for url, parse in endpoints:
            try:
                r=requests.get(url,headers=HEADERS,timeout=25)
                r.raise_for_status()
                fresh=parse(r.text)
                fresh["fetched_at"]=now
                # Never replace the latest stored quote with a known older one.
                old_date=(updated.get(name) or {}).get("quote_time") or (updated.get(name) or {}).get("quote_date") or ""
                new_date=fresh.get("quote_time") or fresh.get("quote_date") or ""
                if old_date and new_date and new_date<old_date:
                    print("MARKET_OLDER_IGNORED",name,new_date,"stored",old_date)
                    break
                updated[name]=fresh
                print("MARKET_UPDATED",name,new_date)
                break
            except (requests.RequestException,ValueError,KeyError) as exc:
                print("MARKET_SOURCE_FAILED",name,url,str(exc)[:180])
        else:
            failed.append(name)
            print("MARKET_FETCH_FAILED",name,"all sources failed, previously verified quote retained")
    updated["checked_at"]=now
    updated["fetch_failed"]=failed
    DEST.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Market-only update complete; no news processed")

if __name__=="__main__":
    main()
