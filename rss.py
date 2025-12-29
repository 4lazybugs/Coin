import feedparser
from bs4 import BeautifulSoup

def clean_html(html):
    return BeautifulSoup(html, "html.parser").get_text().strip()

def shorten(text, n=300):
    return text if len(text) <= n else text[:n] + "..."

feed = feedparser.parse("https://cryptopotato.com/feed/")

for i, e in enumerate(feed.entries, 1):
    summary = clean_html(e.get("summary", "N/A"))

    # content는 보통 리스트 형태
    if "content" in e:
        content = clean_html(e.content[0].value)
    else:
        content = "N/A"

    print(f"[{i:02d}] {e.title}")
    print(f"     📝 Summary : {shorten(summary, 200)}")
    print(f"     📄 Content : {shorten(content, 300)}")
    print(f"     🔗 {e.link}")
    print(f"     🕒 {e.get('published', 'N/A')}")
    print("-" * 80)
