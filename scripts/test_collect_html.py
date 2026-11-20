"""Offline regression test: direct HTML source needs a date and relevant business event."""
from datetime import datetime, timezone
from collect_html import publish_date, extract
now=datetime(2026,11,20,tzinfo=timezone.utc)
source={"name":"DIY International","industry":"手工具","region":"歐洲","type":"html",
        "url":"https://www.diyinternational.com/news.html","hosts":["diyinternational.com"],"url_patterns":["/content/"]}
page="""<html><body><main><article>
<a href="/content/news/2026/11/19/stanley-tools-orders.html">Stanley Black & Decker reports new power tools orders</a>
<time datetime="2026-11-19T08:00:00Z">19 November 2026</time>
<p>Manufacturing orders have increased in the power tools segment according to the company's quarterly operational update, with volumes and future market demand still under review.</p>
</article>
<article><a href="/content/news/2026/06/03/old.html">Makita tools factory expands production</a>
<time datetime="2026-06-03">3 June 2026</time></article>
<article><a href="https://example.com/article">Stanley Black & Decker reports tools sales</a>
<time datetime="2026-11-19">19 Nov 2026</time></article>
<article><a href="/content/news/2026/11/19/ai-tools.html">Top AI tools for writing emails</a>
<time datetime="2026-11-19">19 Nov 2026</time></article>
</main></body></html>"""
found=extract(source,page,now)
assert len(found)==1,found
assert found[0]["link"].startswith("https://www.diyinternational.com/content/news/"),found
assert found[0]["published_at"][:10]=="2026-11-19",found
assert publish_date("7. August 2026").date().isoformat()=="2026-08-07"
print("PASS: exact publisher URLs, explicit dates, relevant companies, non-tools excluded")

# CTIMES publishes dates like 2026.11.18 in its machine-tool topic list.
assert publish_date("日本工具機訂單年增 (2026.11.18)").date().isoformat()=="2026-11-18"
ctimes={"name":"CTIMES","industries":["機械與金屬加工","無人載具及機器人"],"region":"台灣",
 "url":"https://www.ctimes.com.tw/ART/articleindex.asp?F=機械",
 "hosts":["ctimes.com.tw"],"url_patterns":[".shtml"]}
page2="""<html><body><article>
<a href="/工具機/2611180930AB.shtml">日本工具機訂單年增42.5% 精密零組件與高階設備迎新商機</a>
<time datetime="2026-11-18">2026.11.18</time>
<p>精密機械設備與出口訂單的發展需要追蹤工業應用。</p>
</article></body></html>"""
ct=extract(ctimes,page2,now)
assert len(ct)==1 and "機械與金屬加工" in ct[0]["industries"],ct
# Only substantive TEDIBOA industry news: a mere invitation must not
# become a sourced article even when it has an explicit publication date.
tediboa={"name":"TEDIBOA 台灣卓越無人機海外商機聯盟",
 "industries":["無人載具及機器人"],"region":"台灣",
 "url":"https://www.tediboa.com.tw/News","hosts":["tediboa.com.tw"],
 "url_patterns":["/News/Article/"]}
page3="""<html><body>
<article><a href="/News/Article/21">歡迎報名無人機展覽資訊交流規劃</a>
<time datetime="2026-11-19">2026-11-19</time><p>歡迎踴躍參加產業交流。</p></article>
<article><a href="/News/Article/22">台灣無人機供應鏈關鍵零組件取得國際認證</a>
<time datetime="2026-11-19">2026-11-19</time><p>產業零組件製造及認證進展。</p></article>
</body></html>"""
ta=extract(tediboa,page3,now)
assert len(ta)==1 and "零組件" in ta[0]["title"],ta
print("PASS CTIMES dotted date and industry selection; TEDIBOA substantive-news-only filter")

# TEDIBOA listing puts "了解更多" on the anchor and the title in a
# sibling heading. The article URL and heading must remain in the same card.
page4="""<html><body><section><article>
<h3>台灣無人機供應鏈關鍵零組件取得國際認證</h3>
<p>2026-11-19</p>
<p>無人機關鍵零組件製造廠商分享供應鏈與出口認證進展。</p>
<a href="/News/Article/16200">了解更多</a>
</article></section></body></html>"""
headings=extract(tediboa,page4,now)
assert len(headings)==1 and headings[0]["link"].endswith("/News/Article/16200"),headings
print("PASS TEDIBOA: article title extracted from same-card heading, not generic 了解更多")
