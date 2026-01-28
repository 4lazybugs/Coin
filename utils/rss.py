import feedparser
from bs4 import BeautifulSoup

def clean_html(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text().strip()

def shorten(text: str, n: int = 300) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n] + "..."

def fetch_rss_news(feed_url: str, limit: int=10, summary_len: int=300, content_len: int=600,):
    """
    RSS에서 최신 뉴스들을 가져와 LLM 입력에 적합한 dict 리스트로 반환.
    - title, summary, content, link, published 필드를 포함
    """
    feed = feedparser.parse(feed_url)

    news_items = []
    entries = getattr(feed, "entries", []) or []
    for e in entries[:limit]:
        summary = clean_html(e.get("summary", ""))
        if "content" in e and e.content:
            content = clean_html(getattr(e.content[0], "value", ""))
        else:
            content = ""

        news_items.append({
            "title": e.get("title", "N/A"),
            "summary": shorten(summary, summary_len),
            "content": shorten(content, content_len),
            "link": e.get("link", "N/A"),
            "published": e.get("published", "N/A"),
            "source": feed_url,
        })

    return news_items

if __name__ == "__main__":
    FEED_URL = "https://www.cryptobreaking.com/feed/"

    news = fetch_rss_news(
        feed_url=FEED_URL,
        limit=10,
        summary_len=300,
        content_len=600,
    )

    print(f"Fetched {len(news)} news items\n")

    for idx, item in enumerate(news, 1):
        print(f"--- News Item {idx} ---")
        print(f"Title: {item['title']}")
        print(f"Published: {item['published']}")
        print(f"Link: {item['link']}")
        print(f"Summary: {item['summary']}")
        print(f"Content: {item['content']}")
        print()

