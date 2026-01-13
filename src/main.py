import argparse
import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.jota.info"
TAG_URL_TEMPLATE = BASE_URL + "/tudo-sobre/{tag}"
OUTPUT_DIR = "public"
DEFAULT_MAX_PAGES = 3
REQUEST_TIMEOUT = 30
USER_AGENT = "JotaRSSBot/1.0 (+https://github.com/jota-rss-feed)"


@dataclass
class Article:
    title: str
    url: str
    authors: list[str]
    category: str
    image_url: str | None = None


def load_tags_from_file(filepath: str) -> list[str]:
    try:
        with open(filepath) as f:
            tags = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        logger.info(f"Loaded {len(tags)} tags from {filepath}")
        return tags
    except FileNotFoundError:
        logger.error(f"Tags file not found: {filepath}")
        return []
    except Exception as e:
        logger.error(f"Error loading tags from {filepath}: {e}")
        return []


def load_tags_from_env(env_var_name: str) -> list[str]:
    env_val = os.environ.get(env_var_name)
    if env_val:
        tags = [t.strip() for t in env_val.split(",") if t.strip()]
        logger.info(f"Loaded {len(tags)} tags from env var {env_var_name}")
        return tags
    logger.warning(f"Environment variable {env_var_name} not found or empty")
    return []


def extract_next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if script and script.string:
        try:
            return json.loads(script.string)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse __NEXT_DATA__: {e}")
    return None


def parse_articles_from_next_data(data: dict) -> list[Article]:
    articles = []
    page_props = data.get("props", {}).get("pageProps", {})
    posts = page_props.get("posts", [])

    for post in posts:
        title = post.get("title", "")
        permalink = post.get("permalink", "")

        if not title or not permalink:
            continue

        url = BASE_URL + permalink if not permalink.startswith("http") else permalink

        authors = []
        author_data = post.get("author")
        if isinstance(author_data, dict):
            author_name = author_data.get("name", "")
            if author_name:
                authors = [author_name]
        elif isinstance(author_data, list):
            authors = [a.get("name", "") for a in author_data if a.get("name")]

        category = post.get("category", {}).get("name", "") if post.get("category") else ""
        image_url = post.get("image", {}).get("url") if post.get("image") else None

        article = Article(
            title=title, url=url, authors=authors, category=category, image_url=image_url
        )
        articles.append(article)
        logger.debug(f"Parsed article: {title}")

    return articles


def get_total_pages_from_next_data(data: dict) -> int:
    page_props = data.get("props", {}).get("pageProps", {})
    return page_props.get("totalPages", 1)


def parse_article_from_element(heading: BeautifulSoup, base_url: str) -> Article | None:
    link = heading.find("a")
    if not link:
        return None

    title = link.get_text(strip=True)
    url = link.get("href", "")
    if not url.startswith("http"):
        url = urljoin(base_url, url)

    parent = heading.find_parent()
    for _ in range(5):
        if parent is None:
            break
        parent = parent.find_parent()

    authors = []
    category = ""
    image_url = None

    if parent:
        author_links = parent.find_all("a", href=re.compile(r"/autor/"))
        authors = [a.get_text(strip=True).rstrip(",") for a in author_links]

        img = parent.find("img")
        if img:
            image_url = img.get("src")

        category_elem = parent.find(string=re.compile(r"^[A-ZÁÉÍÓÚÂÊÎÔÛÀÈÌÒÙÃÕ\s]+$"))
        if category_elem and len(category_elem.strip()) > 2:
            category = category_elem.strip()

    if not title or not url:
        return None

    return Article(title=title, url=url, authors=authors, category=category, image_url=image_url)


def parse_articles_from_html(html: str, base_url: str) -> list[Article]:
    soup = BeautifulSoup(html, "lxml")
    articles = []

    headings = soup.find_all("h2")
    for heading in headings:
        article = parse_article_from_element(heading, base_url)
        if article:
            articles.append(article)
            logger.debug(f"Parsed article: {article.title}")

    return articles


def get_total_pages_from_html(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    page_numbers = soup.find_all(string=re.compile(r"^\d+$"))
    max_page = 1
    for num_text in page_numbers:
        try:
            num = int(num_text.strip())
            if num > max_page and num < 100:
                max_page = num
        except ValueError:
            continue
    return max_page


async def fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        logger.debug(f"Fetching: {url}")
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error fetching {url}: {e}")
        return None


async def scrape_tag(
    client: httpx.AsyncClient, tag: str, max_pages: int = DEFAULT_MAX_PAGES
) -> list[Article]:
    base_url = TAG_URL_TEMPLATE.format(tag=tag)
    logger.info(f"Scraping tag: {tag}")

    first_page_html = await fetch_page(client, base_url)
    if not first_page_html:
        logger.warning(f"Failed to fetch first page for tag: {tag}")
        return []

    next_data = extract_next_data(first_page_html)
    if next_data:
        all_articles = parse_articles_from_next_data(next_data)
        total_pages = get_total_pages_from_next_data(next_data)
    else:
        logger.warning(f"No __NEXT_DATA__ found for tag: {tag}, falling back to HTML parsing")
        all_articles = parse_articles_from_html(first_page_html, base_url)
        total_pages = get_total_pages_from_html(first_page_html)

    pages_to_fetch = min(total_pages, max_pages)

    logger.info(f"Tag {tag}: found {total_pages} pages, will fetch {pages_to_fetch}")

    if pages_to_fetch > 1:
        tasks = [fetch_page(client, f"{base_url}?page={p}") for p in range(2, pages_to_fetch + 1)]
        results = await asyncio.gather(*tasks)

        for html in results:
            if html:
                page_next_data = extract_next_data(html)
                if page_next_data:
                    articles = parse_articles_from_next_data(page_next_data)
                else:
                    articles = parse_articles_from_html(html, base_url)
                all_articles.extend(articles)

    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        if article.url not in seen_urls:
            seen_urls.add(article.url)
            unique_articles.append(article)

    logger.info(f"Tag {tag}: scraped {len(unique_articles)} unique articles")
    return unique_articles


async def scrape_all_tags(
    tags: list[str], max_pages: int = DEFAULT_MAX_PAGES
) -> dict[str, list[Article]]:
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        trust_env=False,
    ) as client:
        tasks = [scrape_tag(client, tag, max_pages) for tag in tags]
        results = await asyncio.gather(*tasks)
        return dict(zip(tags, results, strict=True))


def generate_feed_for_tag(tag: str, articles: list[Article], output_dir: str) -> str:
    fg = FeedGenerator()
    feed_url = f"{BASE_URL}/tudo-sobre/{tag}"

    fg.id(feed_url)
    fg.title(f"JOTA - {tag.upper().replace('-', ' ')}")
    fg.author({"name": "JOTA Info", "email": "contato@jota.info"})
    fg.link(href=feed_url, rel="alternate")
    fg.link(href=f"{tag}.xml", rel="self")
    fg.subtitle(f"Últimas notícias sobre {tag.replace('-', ' ')} no JOTA")
    fg.language("pt-BR")
    fg.lastBuildDate(datetime.now(UTC))

    for article in articles:
        fe = fg.add_entry()
        fe.id(article.url)
        fe.title(article.title)
        fe.link(href=article.url)

        description_parts = []
        if article.category:
            description_parts.append(f"[{article.category}]")
        if article.authors:
            description_parts.append(f"Por {', '.join(article.authors)}")
        fe.description(" - ".join(description_parts) if description_parts else article.title)

    output_path = os.path.join(output_dir, f"{tag}.xml")
    fg.rss_file(output_path)
    logger.info(f"Generated feed: {output_path} with {len(articles)} articles")
    return output_path


def generate_combined_feed(
    tag_articles: dict[str, list[Article]], output_dir: str, filename: str = "feed.xml"
) -> str:
    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("JOTA - Combined Feed")
    fg.author({"name": "JOTA Info", "email": "contato@jota.info"})
    fg.link(href=BASE_URL, rel="alternate")
    fg.link(href=filename, rel="self")
    fg.subtitle("Últimas notícias de múltiplos temas no JOTA")
    fg.language("pt-BR")
    fg.lastBuildDate(datetime.now(UTC))

    all_articles: list[tuple[str, Article]] = []
    for tag, articles in tag_articles.items():
        for article in articles:
            all_articles.append((tag, article))

    seen_urls = set()
    unique_articles = []
    for tag, article in all_articles:
        if article.url not in seen_urls:
            seen_urls.add(article.url)
            unique_articles.append((tag, article))

    for tag, article in unique_articles:
        fe = fg.add_entry()
        fe.id(article.url)
        fe.title(f"[{tag.upper()}] {article.title}")
        fe.link(href=article.url)

        description_parts = []
        if article.category:
            description_parts.append(f"[{article.category}]")
        if article.authors:
            description_parts.append(f"Por {', '.join(article.authors)}")
        fe.description(" - ".join(description_parts) if description_parts else article.title)

    output_path = os.path.join(output_dir, filename)
    fg.rss_file(output_path)
    logger.info(f"Generated combined feed: {output_path} with {len(unique_articles)} articles")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JOTA RSS Feed Generator")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tags", nargs="+", help="List of tags to scrape")
    group.add_argument("--tags-file", help="Path to file with tags (one per line)")
    group.add_argument("--tags-env", help="Environment variable with comma-separated tags")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory for feeds")
    parser.add_argument(
        "--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Max pages to scrape per tag"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


async def async_main(tags: list[str], output_dir: str, max_pages: int) -> dict[str, list[Article]]:
    logger.info(f"Starting JOTA RSS feed generator with tags: {tags}")

    os.makedirs(output_dir, exist_ok=True)

    tag_articles = await scrape_all_tags(tags, max_pages)

    for tag, articles in tag_articles.items():
        if articles:
            generate_feed_for_tag(tag, articles, output_dir)
        else:
            logger.warning(f"No articles found for tag: {tag}")

    if any(tag_articles.values()):
        generate_combined_feed(tag_articles, output_dir)

    total_articles = sum(len(articles) for articles in tag_articles.values())
    logger.info(f"Done. Generated feeds for {len(tags)} tags, {total_articles} total articles")

    return tag_articles


def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    tags: list[str] = []
    if args.tags:
        tags = args.tags
        logger.info(f"Using {len(tags)} tags from command line")
    elif args.tags_file:
        tags = load_tags_from_file(args.tags_file)
    elif args.tags_env:
        tags = load_tags_from_env(args.tags_env)

    if not tags:
        logger.error("No tags provided. Use --tags, --tags-file, or --tags-env")
        return

    asyncio.run(async_main(tags, args.output_dir, args.max_pages))


if __name__ == "__main__":
    main()
