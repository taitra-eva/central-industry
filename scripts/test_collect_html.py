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
