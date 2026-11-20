"""Collect public RSS article metadata only, with no paid API or article copying."""
import hashlib, json, re, time, os
from html import unescape
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo
import requests, feedparser
from relevance import should_keep, is_government_source
from topic_taxonomy import normalize_article
from industry_entities import entity_sectors, entity_event
ROOT=Path(__file__).resolve().parents[1]
NOW=datetime.now(timezone.utc)
CUTOFF=NOW-timedelta(days=30)
PUBLICATION_WINDOW=NOW-timedelta(days=14)
cfg=json.loads((ROOT/'config/queries.json').read_text(encoding='utf8'))['queries']
# Secondary discovery only: four regions per sector, at most 24 requests,
# versus the former 126 Google News queries. Direct publishers run first.
max_google=int(os.environ.get("GOOGLE_NEWS_FALLBACK_MAX","24"))
if max_google<0:raise ValueError("GOOGLE_NEWS_FALLBACK_MAX must be >=0")
if max_google<len(cfg):
    picked=[]
    for industry in ("總體情勢","機械與金屬加工","自行車","汽配","手工具","無人載具及機器人"):
        for region in ("台灣","北美","歐洲","亞洲"):
            entry=next((x for x in cfg if x.get("industry")==industry and x.get("region")==region),None)
            if entry and entry not in picked:picked.append(entry)
    cfg=picked[:max_google]
print("Google News fallback queries:",len(cfg),"max",max_google)
EXCLUDED=set(json.loads((ROOT/'config/excluded_news_ids.json').read_text(encoding='utf8'))['ids'])
path=ROOT/'data/news.json'
previous=json.loads(path.read_text(encoding='utf8'))
blocked=('經濟部國際貿易署','國際貿易署經貿資訊網','國貿署','international trade administration','indexbox','bloomberg','financial times','wall street journal','nikkei asia','the information','market research future')
news={n['id']:n for n in previous.get('items',[]) if n['id'] not in EXCLUDED and datetime.fromisoformat(n.get('discovered_at',NOW.isoformat())) >= CUTOFF and not any(word in (n.get('source','')+' '+n.get('url','')).casefold() for word in blocked) and 'trade.gov.tw' not in n.get('url','').lower() and not is_government_source(n.get('source',''), n.get('source_url') or n.get('url','')) and should_keep(n.get('title',''), '總體情勢' if '總體情勢' in n.get('industries',[]) else None)[0]}
for entry in news.values():
    if entry.get('region')=='日本':entry['region']='亞洲'
    # A hand-tool firm can be described as a "工具" company without the
    # literal words 手工具. Industry-specific evidence should override a
    # generic macro discovery query; retain machining as a cross-sector tag.
    headline=(entry.get('title_zh') or entry.get('title') or '')
    if '伯鑫工具' in headline or ('六強聯盟' in headline and '工具' in headline):
        entry['industries']=[v for v in entry.get('industries',[]) if v!='總體情勢']
        for sector in ('手工具','機械與金屬加工'):
            if sector not in entry['industries']: entry['industries'].append(sector)
        entry['topic']='產業動態'
success=0
counts={}
for query in cfg:
    locale=query.get('locale','zh-TW')
    params=('&hl=en-US&gl=US&ceid=US:en' if locale=='en-US' else
            '&hl=ja&gl=JP&ceid=JP:ja' if locale=='ja-JP' else
            '&hl=zh-TW&gl=TW&ceid=TW:zh-Hant')
    url='https://news.google.com/rss/search?q='+quote(query['q'])+params
    try:
        r=requests.get(url,timeout=20,headers={'User-Agent':'Central-Industry-News/1.0'})
        r.raise_for_status()
        feed=feedparser.parse(r.content)
        if not feed.entries and feed.bozo: raise ValueError('invalid feed')
        success+=1
        counts[query['q']]={'rss_entries':len(feed.entries),'new_items':0}
        for e in feed.entries[:35]:
            title=re.sub('<[^>]*>','',e.get('title','')).strip()
            link=e.get('link','')
            if not title or not link.startswith('https://'):continue
            if not should_keep(title, query['industry'])[0]:continue
            published=None
            if e.get('published_parsed'):
                import calendar
                published=datetime.fromtimestamp(calendar.timegm(e.published_parsed),timezone.utc).isoformat()
                if datetime.fromisoformat(published)<PUBLICATION_WINDOW:continue
            norm=re.sub(r'\W+','',title.casefold())
            uid=hashlib.sha256(norm.encode()).hexdigest()[:20]
            if uid in EXCLUDED:continue
            if uid in news:
                if query['industry'] not in news[uid]['industries']:news[uid]['industries'].append(query['industry'])
                continue
            source=e.get('source',{}).get('title','') if e.get('source') else 'Google News'
            # Exclude clearly paywalled / market-research lead-generation domains or sources.
            if any(word in source.casefold() for word in blocked):continue
            if is_government_source(source,link):continue
            if 'trade.gov.tw' in link.lower() or 'trade.moea.gov.tw' in link.lower():continue
            low=title.casefold()
            # Google News RSS descriptions are often just a list of article links. They
            # should never be represented as meaningful article-body evidence.
            plain=unescape(re.sub(r'<[^>]+>',' ',e.get('summary','')))
            plain=' '.join(plain.split())
            excerpt=plain if len(plain)>120 and title.casefold() not in plain.casefold() and len(re.findall(r'http',plain))==0 else ''
            topics=[('匯率與出口競爭力',['匯率','新台幣','日圓','歐元','exchange rate','forex','currency']),('政策與貿易措施',['tariff','關稅','regulation','policy','法規','補貼']),('供應鏈與原物料',['steel','鋼','鋁','material','supply chain','原料']),('進出口與訂單趨勢',['export','import','出口','進口','訂單','orders']),('市場需求與景氣',['market','demand','sales','庫存','需求','景氣']),('技術發展與產業轉型',['automation','technology','技術','自動化'])]
            topic=next((t for t,terms in topics if any(term in low for term in terms)),'產業動態')
            # Shared macro/policy events are a separate discovery category. Add other
            # industry labels only when the headline explicitly names their subject.
            extra_industries=[]
            if query['industry']=='總體情勢':
                industry_terms={
                    '機械與金屬加工':['工具機','機械','木工機','木工機械','精密機械','金屬加工','精密加工','鈑金','沖壓','鍛造','鑄造','metal fabrication','precision machining','woodworking machinery','machine tool','machinery','cnc'],
                    '自行車':['自行車','電動自行車','電動輔助自行車','電動二輪車','電動三輪車','三輪車','電動機車','bicycle','e-bike','ebike','electric bicycle','electric two-wheeler','electric tricycle','e-trike','pedelec'],
                    '汽配':['汽車零件','汽車零組件','auto parts','automotive parts','aftermarket'],
                    '手工具':['手工具','五金工具','氣動工具','電動工具','園藝工具','園林工具','汽修工具','汽車維修工具','特殊工具','專用工具','special tools','special tool','specialty tools','special service tools','hand tool','repair tools','power tools','pneumatic tools','garden tools','outdoor power equipment'],
                    '無人載具及機器人':['無人機','機器人','drone','robotics','unmanned']
                }
                extra_industries=[industry for industry,terms in industry_terms.items() if any(t in low for t in terms)]
                # Company/brand signals can reveal sector headlines without generic product terms.
                for sector in entity_sectors(title):
                    if sector not in extra_industries: extra_industries.append(sector)
                # Product-independent contract machining partners often appear
                # alongside hand-tool maker names, not generic 手工具 keywords.
                if ('伯鑫工具' in title or ('六強聯盟' in title and '工具' in title)):
                    for sector in ('手工具','機械與金屬加工'):
                        if sector not in extra_industries:extra_industries.append(sector)
            # Articles found under one sector may legitimately concern several others.
            for sector in entity_sectors(title):
                if sector!=query['industry'] and sector not in extra_industries: extra_industries.append(sector)
            tags=[]
            for tag,words in {
                '國內政策':['法規','補助','政策','經濟部','產發署'],
                '國際政策':['tariff','關稅','sanctions','制裁','trade policy'],
                '地緣政治':['war','conflict','戰爭','地緣'],
                '上游原物料':['鋼鐵','鋁','銅','能源','oil price','steel','raw material'],
                '物流供應鏈':['航運','運費','物流','shipping','supply chain'],
                '台灣產業':['台灣','臺灣','taiwan']
            }.items():
                if any(word in low for word in words):tags.append(tag)
            counts[query['q']]['new_items']+=1
            news[uid]={'id':uid,'title':title,'url':link,'source':source,'published_at':published,'discovered_at':NOW.isoformat(),'industries':[query['industry']]+extra_industries,'tags':tags,'priority':'taiwan' if query['region']=='台灣' else 'international','region':query['region'],'language_hint':'ja' if locale=='ja-JP' else None,'topic':topic,'access_status':'not_verified','excerpt':excerpt}
    except Exception as ex:print('FAILED',query['q'],str(ex)[:150])
    time.sleep(1.0)
if not success:print('All Google News fallback queries failed or were disabled; prior/direct publisher news retained.')
items=sorted((normalize_article(n) for n in news.values() if datetime.fromisoformat(n.get('discovered_at',NOW.isoformat()))>=CUTOFF and should_keep(n.get('title',''), '總體情勢' if n.get('industries')==['總體情勢'] else None)[0]),key=lambda n:n.get('published_at') or n['discovered_at'],reverse=True)
# News.json is the 30-day online archive. Avoid daily duplicate snapshots
# to reduce repository growth. Existing snapshots are removed from the working tree;
# historical Git commits may still retain those blobs until repository maintenance.
archive=ROOT/'data/archive'
if archive.exists():
    for old in archive.glob('????-??-??.json'):
        old.unlink()
result={'updated_at':NOW.isoformat(),'status':'ok' if success==len(cfg) else 'partial','sources_checked':len(cfg),'sources_successful':success,'items':items}
path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('success',success,'/',len(cfg),'items',len(items))
for q,stat in counts.items(): print('SEARCH',q,stat)
