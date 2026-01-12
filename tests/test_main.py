import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import httpx
import pytest

from src.main import (
    Article,
    async_main,
    extract_next_data,
    fetch_page,
    generate_combined_feed,
    generate_feed_for_tag,
    get_total_pages_from_html,
    get_total_pages_from_next_data,
    load_tags_from_env,
    load_tags_from_file,
    main,
    parse_args,
    parse_article_from_element,
    parse_articles_from_html,
    parse_articles_from_next_data,
    scrape_all_tags,
    scrape_tag,
)


class TestLoadTagsFromFile:
    def test_load_tags_success(self):
        mock_content = "itcmd\nreforma-tributaria\nstf\n"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            tags = load_tags_from_file("tags.txt")
            assert len(tags) == 3
            assert "itcmd" in tags
            assert "reforma-tributaria" in tags
            assert "stf" in tags

    def test_load_tags_with_comments(self):
        mock_content = "itcmd\n# this is a comment\nstf\n"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            tags = load_tags_from_file("tags.txt")
            assert len(tags) == 2
            assert "itcmd" in tags
            assert "stf" in tags

    def test_load_tags_with_empty_lines(self):
        mock_content = "itcmd\n\n\nstf\n\n"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            tags = load_tags_from_file("tags.txt")
            assert len(tags) == 2

    def test_load_tags_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            tags = load_tags_from_file("nonexistent.txt")
            assert tags == []

    def test_load_tags_permission_error(self):
        with patch("builtins.open", side_effect=PermissionError):
            tags = load_tags_from_file("forbidden.txt")
            assert tags == []


class TestLoadTagsFromEnv:
    def test_load_tags_from_env_success(self):
        with patch.dict(os.environ, {"JOTA_TAGS": "itcmd,reforma-tributaria,stf"}):
            tags = load_tags_from_env("JOTA_TAGS")
            assert len(tags) == 3
            assert "itcmd" in tags

    def test_load_tags_from_env_with_spaces(self):
        with patch.dict(os.environ, {"JOTA_TAGS": "itcmd, reforma-tributaria , stf"}):
            tags = load_tags_from_env("JOTA_TAGS")
            assert len(tags) == 3
            assert "reforma-tributaria" in tags

    def test_load_tags_from_env_not_found(self):
        with patch.dict(os.environ, {}, clear=True):
            tags = load_tags_from_env("NONEXISTENT_VAR")
            assert tags == []

    def test_load_tags_from_env_empty(self):
        with patch.dict(os.environ, {"JOTA_TAGS": ""}):
            tags = load_tags_from_env("JOTA_TAGS")
            assert tags == []


class TestExtractNextData:
    def test_extract_next_data_success(self):
        html = """
        <html>
        <head>
            <script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"posts":[{"title":"Test"}],"totalPages":5}}}
            </script>
        </head>
        <body></body>
        </html>
        """
        data = extract_next_data(html)
        assert data is not None
        assert data["props"]["pageProps"]["totalPages"] == 5

    def test_extract_next_data_no_script(self):
        html = "<html><body>No next data</body></html>"
        data = extract_next_data(html)
        assert data is None

    def test_extract_next_data_invalid_json(self):
        html = """
        <html>
        <script id="__NEXT_DATA__">invalid json</script>
        </html>
        """
        data = extract_next_data(html)
        assert data is None


class TestParseArticlesFromNextData:
    def test_parse_articles_success(self):
        data = {
            "props": {
                "pageProps": {
                    "posts": [
                        {
                            "title": "Test Article",
                            "permalink": "/tributos/test-article",
                            "author": {"name": "Author Name"},
                            "category": {"name": "TRIBUTOS"},
                            "image": {"url": "https://example.com/img.jpg"},
                        }
                    ]
                }
            }
        }
        articles = parse_articles_from_next_data(data)
        assert len(articles) == 1
        assert articles[0].title == "Test Article"
        assert articles[0].url == "https://www.jota.info/tributos/test-article"
        assert articles[0].authors == ["Author Name"]
        assert articles[0].category == "TRIBUTOS"
        assert articles[0].image_url == "https://example.com/img.jpg"

    def test_parse_articles_with_multiple_authors(self):
        data = {
            "props": {
                "pageProps": {
                    "posts": [
                        {
                            "title": "Test",
                            "permalink": "/test",
                            "author": [{"name": "Author 1"}, {"name": "Author 2"}],
                        }
                    ]
                }
            }
        }
        articles = parse_articles_from_next_data(data)
        assert len(articles) == 1
        assert articles[0].authors == ["Author 1", "Author 2"]

    def test_parse_articles_empty_posts(self):
        data = {"props": {"pageProps": {"posts": []}}}
        articles = parse_articles_from_next_data(data)
        assert len(articles) == 0

    def test_parse_articles_missing_fields(self):
        data = {"props": {"pageProps": {"posts": [{"title": "", "permalink": ""}]}}}
        articles = parse_articles_from_next_data(data)
        assert len(articles) == 0


class TestGetTotalPagesFromNextData:
    def test_get_total_pages(self):
        data = {"props": {"pageProps": {"totalPages": 14}}}
        assert get_total_pages_from_next_data(data) == 14

    def test_get_total_pages_default(self):
        data = {"props": {"pageProps": {}}}
        assert get_total_pages_from_next_data(data) == 1


class TestParseArticle:
    def test_parse_article_from_element_success(self):
        from bs4 import BeautifulSoup

        html = """
        <div>
            <a href="/autor/test-author">TEST AUTHOR</a>
            <img src="https://example.com/image.jpg">
            <h2><a href="/tributos/test-article">Test Article Title</a></h2>
            <span>TRIBUTOS</span>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        heading = soup.find("h2")
        article = parse_article_from_element(heading, "https://www.jota.info")
        assert article is not None
        assert article.title == "Test Article Title"
        assert "test-article" in article.url

    def test_parse_article_no_link(self):
        from bs4 import BeautifulSoup

        html = "<h2>No Link Here</h2>"
        soup = BeautifulSoup(html, "lxml")
        heading = soup.find("h2")
        article = parse_article_from_element(heading, "https://www.jota.info")
        assert article is None

    def test_parse_article_absolute_url(self):
        from bs4 import BeautifulSoup

        html = '<h2><a href="https://www.jota.info/full-url">Full URL Article</a></h2>'
        soup = BeautifulSoup(html, "lxml")
        heading = soup.find("h2")
        article = parse_article_from_element(heading, "https://www.jota.info")
        assert article is not None
        assert article.url == "https://www.jota.info/full-url"


class TestParseArticlesFromHtml:
    def test_parse_multiple_articles(self):
        html = """
        <html>
        <body>
            <h2><a href="/article-1">Article 1</a></h2>
            <h2><a href="/article-2">Article 2</a></h2>
            <h2><a href="/article-3">Article 3</a></h2>
        </body>
        </html>
        """
        articles = parse_articles_from_html(html, "https://www.jota.info")
        assert len(articles) == 3

    def test_parse_empty_html(self):
        html = "<html><body></body></html>"
        articles = parse_articles_from_html(html, "https://www.jota.info")
        assert len(articles) == 0

    def test_parse_no_h2_headings(self):
        html = "<html><body><h1>Not an article</h1></body></html>"
        articles = parse_articles_from_html(html, "https://www.jota.info")
        assert len(articles) == 0


class TestGetTotalPages:
    def test_get_total_pages_with_pagination(self):
        html = """
        <div>
            <span>1</span>
            <span>2</span>
            <span>...</span>
            <span>14</span>
            <span>PRÓXIMA</span>
        </div>
        """
        total = get_total_pages_from_html(html)
        assert total == 14

    def test_get_total_pages_single_page(self):
        html = "<div>No pagination here</div>"
        total = get_total_pages_from_html(html)
        assert total == 1

    def test_get_total_pages_ignores_large_numbers(self):
        html = "<div><span>1</span><span>2</span><span>999</span></div>"
        total = get_total_pages_from_html(html)
        assert total == 2


class TestFetchPage:
    @pytest.mark.asyncio
    async def test_fetch_page_success(self):
        mock_response = MagicMock()
        mock_response.text = "<html>content</html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        result = await fetch_page(mock_client, "https://example.com")
        assert result == "<html>content</html>"

    @pytest.mark.asyncio
    async def test_fetch_page_http_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_client.get.return_value = mock_response

        result = await fetch_page(mock_client, "https://example.com/404")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_page_request_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.RequestError("Connection failed")

        result = await fetch_page(mock_client, "https://example.com")
        assert result is None


class TestScrapeTag:
    @pytest.mark.asyncio
    async def test_scrape_tag_success(self):
        html_page1 = """
        <html>
        <body>
            <h2><a href="/article-1">Article 1</a></h2>
            <span>1</span><span>2</span><span>3</span>
        </body>
        </html>
        """
        html_page2 = """
        <html>
        <body>
            <h2><a href="/article-2">Article 2</a></h2>
        </body>
        </html>
        """

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response1 = MagicMock()
        mock_response1.text = html_page1
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.text = html_page2
        mock_response2.raise_for_status = MagicMock()

        mock_client.get.side_effect = [mock_response1, mock_response2]

        articles = await scrape_tag(mock_client, "itcmd", max_pages=2)
        assert len(articles) >= 1

    @pytest.mark.asyncio
    async def test_scrape_tag_first_page_fails(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.RequestError("Connection failed")

        articles = await scrape_tag(mock_client, "itcmd")
        assert articles == []

    @pytest.mark.asyncio
    async def test_scrape_tag_removes_duplicates(self):
        html = """
        <html>
        <body>
            <h2><a href="/article-1">Article 1</a></h2>
            <h2><a href="/article-1">Article 1 Duplicate</a></h2>
        </body>
        </html>
        """
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        articles = await scrape_tag(mock_client, "itcmd", max_pages=1)
        assert len(articles) == 1


class TestScrapeAllTags:
    @pytest.mark.asyncio
    async def test_scrape_all_tags(self):
        html = '<html><body><h2><a href="/art">Art</a></h2></body></html>'

        with patch("src.main.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await scrape_all_tags(["itcmd", "stf"], max_pages=1)
            assert "itcmd" in result
            assert "stf" in result


class TestGenerateFeed:
    def test_generate_feed_for_tag(self, tmp_path):
        articles = [
            Article(
                title="Test Article 1",
                url="https://www.jota.info/article-1",
                authors=["Author 1"],
                category="TRIBUTOS",
            ),
            Article(
                title="Test Article 2",
                url="https://www.jota.info/article-2",
                authors=["Author 2", "Author 3"],
                category="STF",
            ),
        ]

        output_path = generate_feed_for_tag("itcmd", articles, str(tmp_path))
        assert os.path.exists(output_path)
        assert output_path.endswith("itcmd.xml")

        with open(output_path) as f:
            content = f.read()
            assert "Test Article 1" in content
            assert "Test Article 2" in content

    def test_generate_feed_empty_articles(self, tmp_path):
        output_path = generate_feed_for_tag("empty", [], str(tmp_path))
        assert os.path.exists(output_path)

    def test_generate_combined_feed(self, tmp_path):
        tag_articles = {
            "itcmd": [
                Article(
                    title="ITCMD Article",
                    url="https://www.jota.info/itcmd-1",
                    authors=["Author"],
                    category="TRIBUTOS",
                ),
            ],
            "stf": [
                Article(
                    title="STF Article",
                    url="https://www.jota.info/stf-1",
                    authors=["Author"],
                    category="STF",
                ),
            ],
        }

        output_path = generate_combined_feed(tag_articles, str(tmp_path))
        assert os.path.exists(output_path)
        assert output_path.endswith("feed.xml")

        with open(output_path) as f:
            content = f.read()
            assert "[ITCMD]" in content
            assert "[STF]" in content

    def test_generate_combined_feed_removes_duplicates(self, tmp_path):
        tag_articles = {
            "itcmd": [
                Article(
                    title="Shared Article",
                    url="https://www.jota.info/shared",
                    authors=["Author"],
                    category="TRIBUTOS",
                ),
            ],
            "stf": [
                Article(
                    title="Shared Article",
                    url="https://www.jota.info/shared",
                    authors=["Author"],
                    category="STF",
                ),
            ],
        }

        output_path = generate_combined_feed(tag_articles, str(tmp_path))
        with open(output_path) as f:
            content = f.read()
            # URL appears in both <link> and <guid> tags, so once per entry = 2
            # Duplicates should be removed, so only one entry with this URL
            assert content.count("<item>") == 1


class TestParseArgs:
    def test_parse_args_tags(self):
        with patch("sys.argv", ["main.py", "--tags", "itcmd", "stf"]):
            args = parse_args()
            assert args.tags == ["itcmd", "stf"]

    def test_parse_args_tags_file(self):
        with patch("sys.argv", ["main.py", "--tags-file", "tags.txt"]):
            args = parse_args()
            assert args.tags_file == "tags.txt"

    def test_parse_args_tags_env(self):
        with patch("sys.argv", ["main.py", "--tags-env", "JOTA_TAGS"]):
            args = parse_args()
            assert args.tags_env == "JOTA_TAGS"

    def test_parse_args_debug(self):
        with patch("sys.argv", ["main.py", "--tags", "itcmd", "--debug"]):
            args = parse_args()
            assert args.debug is True

    def test_parse_args_max_pages(self):
        with patch("sys.argv", ["main.py", "--tags", "itcmd", "--max-pages", "5"]):
            args = parse_args()
            assert args.max_pages == 5

    def test_parse_args_output_dir(self):
        with patch("sys.argv", ["main.py", "--tags", "itcmd", "--output-dir", "output"]):
            args = parse_args()
            assert args.output_dir == "output"


class TestAsyncMain:
    @pytest.mark.asyncio
    async def test_async_main_success(self, tmp_path):
        html = '<html><body><h2><a href="/art">Art</a></h2></body></html>'

        with patch("src.main.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await async_main(["itcmd"], str(tmp_path), max_pages=1)
            assert "itcmd" in result
            assert os.path.exists(tmp_path / "itcmd.xml")
            assert os.path.exists(tmp_path / "feed.xml")

    @pytest.mark.asyncio
    async def test_async_main_no_articles(self, tmp_path):
        html = "<html><body></body></html>"

        with patch("src.main.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await async_main(["itcmd"], str(tmp_path), max_pages=1)
            assert result["itcmd"] == []


class TestMain:
    def test_main_with_tags(self, tmp_path):
        with (
            patch("sys.argv", ["main.py", "--tags", "itcmd", "--output-dir", str(tmp_path)]),
            patch("src.main.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_with_tags_file(self, tmp_path):
        with (
            patch(
                "sys.argv", ["main.py", "--tags-file", "tags.txt", "--output-dir", str(tmp_path)]
            ),
            patch("src.main.load_tags_from_file", return_value=["itcmd"]),
            patch("src.main.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_with_tags_env(self, tmp_path):
        with (
            patch(
                "sys.argv", ["main.py", "--tags-env", "JOTA_TAGS", "--output-dir", str(tmp_path)]
            ),
            patch("src.main.load_tags_from_env", return_value=["itcmd"]),
            patch("src.main.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_no_tags(self, tmp_path):
        with (
            patch("sys.argv", ["main.py", "--output-dir", str(tmp_path)]),
            patch("src.main.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_not_called()

    def test_main_debug_mode(self, tmp_path):
        with (
            patch(
                "sys.argv",
                ["main.py", "--tags", "itcmd", "--debug", "--output-dir", str(tmp_path)],
            ),
            patch("src.main.asyncio.run"),
        ):
            main()


class TestArticleDataclass:
    def test_article_creation(self):
        article = Article(
            title="Test",
            url="https://example.com",
            authors=["Author"],
            category="TRIBUTOS",
        )
        assert article.title == "Test"
        assert article.url == "https://example.com"
        assert article.authors == ["Author"]
        assert article.category == "TRIBUTOS"
        assert article.image_url is None

    def test_article_with_image(self):
        article = Article(
            title="Test",
            url="https://example.com",
            authors=[],
            category="",
            image_url="https://example.com/img.jpg",
        )
        assert article.image_url == "https://example.com/img.jpg"
