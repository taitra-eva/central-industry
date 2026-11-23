"""Update only the market price JSON. No news search, publisher reading or AI calls.

FX: E.SUN Bank official published spot buying board rates (USD/EUR/JPY/CNY).
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
FX_ESUN_URL = "https://accessible.esunbank.com.tw/Accessibility/ForeignExchangeRate"
BRENT_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
BRENT_TEXT_URL = "https://fred.stlouisfed.org/data/DCOILBRENTEU.txt"
BR = "https://fred.stlouisfed.org/series/DCOILBRENTEU"
BRENT_EIA_URL = "https://www.eia.gov/dnav/pet/hist/RBRTED.htm"
BRENT_DATAHUB_URL = "https://datahub.io/core/oil-prices/_r/-/data/brent-daily.csv"
CODES = ("USD", "EUR", "JPY", "CNY")

def parse_fx_esun(html):
    """E.SUN official accessibility table: Currency | 買入 | 賣出.

    No intermediate market/mirror and never silently use the selling price.
    Reject login/error pages, incomplete currency sets or stale timestamps.
    """
    soup=BeautifulSoup(html,"html.parser")
    text=soup.get_text(" ",strip=True)
    if "玉山銀行即期外匯匯率表" not in text:
        raise ValueError("E.SUN official rate table heading missing")
    match=re.search(r"資料日期\s*[：:]\s*(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)",text)
    if not match:
        raise ValueError("E.SUN official rate publication timestamp missing")
    datepart=match.group(1).replace("/","-")
    dt=datetime.strptime(datepart+" "+match.group(2),"%Y-%m-%d %H:%M:%S" if match.group(2).count(":")==2 else "%Y-%m-%d %H:%M")
    dt=dt.replace(tzinfo=ZoneInfo("Asia/Taipei"))
    elapsed=datetime.now(ZoneInfo("Asia/Taipei"))-dt
    if elapsed>timedelta(days=5) or elapsed<timedelta(minutes=-20):
        raise ValueError("E.SUN source publication date is older than five days or future-dated")
    rates={}
    for tr in soup.select("tr"):
        cells=tr.find_all(["th","td"],recursive=False)
        if len(cells)<3:
            continue
        cell0=cells[0].get_text(" ",strip=True)
        cm=re.search(r"\b(USD|EUR|JPY|CNY)\b",cell0)
        if not cm:
            continue
        code=cm.group(1)
        # Explicitly verify buy/sell column order using the table headers.
        table=tr.find_parent("table")
        if table is None:
            continue
        head=" ".join(th.get_text(" ",strip=True) for th in table.select("th"))
        if "買入" not in head or "賣出" not in head:
            raise ValueError("E.SUN buy/sell table headers not confirmed")
        num=cells[1].get_text(" ",strip=True).replace(",","")
        if not re.fullmatch(r"\d+(?:\.\d+)?",num):
            raise ValueError("Non-numeric E.SUN buying rate for "+code)
        value=float(num)
        if not 0<value<200:
            raise ValueError("Invalid E.SUN spot buying rate for "+code)
        rates[code]=value
    if set(rates)!=set(CODES):
        raise ValueError("E.SUN official table missing rates for "+str(set(CODES)-set(rates)))
    return {"source":"玉山銀行","quote_type":"即期買入",
            "quote_time":dt.strftime("%Y/%m/%d %H:%M"),
            "source_url":FX_ESUN_URL,"currency":"TWD","rates":rates,
            "data_status":"official_esun_spot_buying_board"}
    
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


def parse_brent_eia_html(contents):
    """Read Brent Europe daily spot from official EIA dated weekly rows."""
    months={m:i+1 for i,m in enumerate(("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"))}
    data={}
    for tr in BeautifulSoup(contents,"html.parser").select("tr"):
        cells=[td.get_text(" ",strip=True) for td in tr.find_all(["td","th"],recursive=False)]
        if len(cells)<6:continue
        m=re.search(r"(\d{4})\s+([A-Za-z]{3})\s*-\s*(\d{1,2})\s+to\b",cells[0],re.I)
        if not m:continue
        try: day=datetime(int(m.group(1)),months[m.group(2).lower()],int(m.group(3))).date()
        except (ValueError,KeyError):continue
        for delta,val in enumerate(cells[1:6]):
            try:
                price=float(val.replace(",",""))
                if 0<price<1000:data[(day+timedelta(days=delta)).isoformat()]=price
            except ValueError:continue
    if not data:raise ValueError("EIA Brent HTML rows were not parsed")
    buffer=io.StringIO()
    writer=csv.DictWriter(buffer,fieldnames=["observation_date","DCOILBRENTEU"])
    writer.writeheader()
    for day,price in sorted(data.items()):
        writer.writerow({"observation_date":day,"DCOILBRENTEU":price})
    result=parse_brent_csv(buffer.getvalue())
    result.update({"source":"美國能源資訊署 EIA（官方網站）","source_url":BRENT_EIA_URL})
    return result


def parse_brent_datahub_csv(contents):
    """Independent public EIA-derived Brent daily CSV mirror from DataHub.

    Only explicitly named Date/Price fields are accepted. This may lag the
    original EIA; normal date checks reject any older observations.
    """
    reader=csv.DictReader(io.StringIO(contents.lstrip("\ufeff")))
    if not reader.fieldnames or not {"Date","Price"}.issubset(reader.fieldnames):
        raise ValueError("DataHub Brent CSV does not contain Date and Price columns")
    buf=io.StringIO()
    writer=csv.DictWriter(buf,fieldnames=["observation_date","DCOILBRENTEU"])
    writer.writeheader()
    for row in reader:
        if row.get("Date") and row.get("Price"):
            writer.writerow({"observation_date":row["Date"],"DCOILBRENTEU":row["Price"]})
    item=parse_brent_csv(buf.getvalue())
    item["source"]="EIA Brent 日現貨（DataHub 公開資料鏡像）"
    item["source_url"]=BRENT_DATAHUB_URL
    return item

def main():
    old=json.loads(DEST.read_text(encoding="utf-8")) if DEST.exists() else {}
    updated=dict(old)
    # Different banks have different rates. Never label old BOT rates as E.SUN.
    if (updated.get("fx") or {}).get("source")!="玉山銀行":
        updated["fx"]=None
    now=datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    failed=[]
    for name, endpoints in [
        ("fx",[(FX_ESUN_URL,parse_fx_esun)]),
        ("oil",[(BRENT_CSV_URL,parse_brent_csv),(BRENT_TEXT_URL,parse_brent_text),(BRENT_EIA_URL,parse_brent_eia_html),(BRENT_DATAHUB_URL,parse_brent_datahub_csv)]),
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
                    continue
                updated[name]=fresh
                print("MARKET_UPDATED" if new_date!=old_date or not old_date else "MARKET_VERIFIED_UNCHANGED",name,new_date)
                break
            except (requests.RequestException,ValueError,KeyError) as exc:
                print("MARKET_SOURCE_FAILED",name,url,str(exc)[:180])
        else:
            failed.append(name)
            print("MARKET_FETCH_FAILED",name,"all sources failed, previously verified quote retained")
    updated["checked_at"]=now
    updated["fetch_failed"]=failed
    updated["status"]="ok" if not failed else ("failed" if len(failed)==2 else "partial")
    DEST.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Market-only update complete; no news processed; status:",updated["status"])
    if len(failed)==2:
        raise RuntimeError("MARKET_DATA_STALE: both market sources failed; previous quotes retained")

if __name__=="__main__":
    main()
