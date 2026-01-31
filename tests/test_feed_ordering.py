"""Tests for RSS feed article ordering.

The feedgen library prepends entries (LIFO), so articles added last appear first in the XML.
Since typical news sites show newest articles on page 1, the scraper produces articles in
[newest...oldest] order. To counteract feedgen's prepending and get newest-first in the feed,
we use reversed() to add articles in [oldest...newest] order.
"""

import os
import xml.etree.ElementTree as ET

from src.main import Article, generate_combined_feed, generate_feed_for_tag


class TestFeedOrdering:
    """Tests to verify that feeds show most recent articles first."""

    def test_generate_feed_for_tag_orders_articles_correctly(self, tmp_path):
        """Test that articles from newest to oldest (from scraper) are shown
        newest-first in feed.
        """
        # Simulating articles as scraped from JOTA: page 1 has newest, page 2 has older
        articles = [
            Article(
                title="Article from Jan 15 (newest)",
                url="https://www.jota.info/article-3",
                authors=["Author 3"],
                category="TRIBUTOS",
            ),
            Article(
                title="Article from Jan 10 (middle)",
                url="https://www.jota.info/article-2",
                authors=["Author 2"],
                category="TRIBUTOS",
            ),
            Article(
                title="Article from Jan 5 (oldest)",
                url="https://www.jota.info/article-1",
                authors=["Author 1"],
                category="TRIBUTOS",
            ),
        ]

        output_path = generate_feed_for_tag("test-tag", articles, str(tmp_path))
        assert os.path.exists(output_path)

        # Parse the XML to check order
        tree = ET.parse(output_path)
        root = tree.getroot()

        # Get all item titles in the order they appear in the feed
        items = root.findall(".//item/title")
        titles = [item.text for item in items]

        # Verify newest article appears first in the feed
        assert len(titles) == 3
        assert titles[0] == "Article from Jan 15 (newest)"
        assert titles[1] == "Article from Jan 10 (middle)"
        assert titles[2] == "Article from Jan 5 (oldest)"

    def test_generate_combined_feed_orders_articles_correctly(self, tmp_path):
        """Test that combined feed shows newest articles first across all tags."""
        # Simulating articles as scraped: newest to oldest per tag
        tag_articles = {
            "tag1": [
                Article(
                    title="Tag1 newest",
                    url="https://www.jota.info/tag1-article-2",
                    authors=["Author"],
                    category="TRIBUTOS",
                ),
                Article(
                    title="Tag1 oldest",
                    url="https://www.jota.info/tag1-article-1",
                    authors=["Author"],
                    category="TRIBUTOS",
                ),
            ],
            "tag2": [
                Article(
                    title="Tag2 newest",
                    url="https://www.jota.info/tag2-article-2",
                    authors=["Author"],
                    category="STF",
                ),
                Article(
                    title="Tag2 oldest",
                    url="https://www.jota.info/tag2-article-1",
                    authors=["Author"],
                    category="STF",
                ),
            ],
        }

        output_path = generate_combined_feed(tag_articles, str(tmp_path))
        assert os.path.exists(output_path)

        # Parse the XML to check order
        tree = ET.parse(output_path)
        root = tree.getroot()

        # Get all item titles in the order they appear in the feed
        items = root.findall(".//item/title")
        titles = [item.text for item in items]

        # Combined order after flattening: tag1-newest, tag1-oldest, tag2-newest, tag2-oldest
        # With reversed() and feedgen prepending: tag2-oldest, tag2-newest, tag1-oldest, tag1-newest
        # Wait, that's not right either...
        # Let me trace through:
        #   all_articles = [('tag1', tag1-newest), ('tag1', tag1-oldest),
        #                   ('tag2', tag2-newest), ('tag2', tag2-oldest)]
        #   reversed = [('tag2', tag2-oldest), ('tag2', tag2-newest),
        #               ('tag1', tag1-oldest), ('tag1', tag1-newest)]
        #   feedgen adds in that order, prepending each:
        #     Add tag2-oldest -> [tag2-oldest]
        #     Add tag2-newest -> [tag2-newest, tag2-oldest]
        #     Add tag1-oldest -> [tag1-oldest, tag2-newest, tag2-oldest]
        #     Add tag1-newest -> [tag1-newest, tag1-oldest, tag2-newest, tag2-oldest]
        # So final order: tag1-newest, tag1-oldest, tag2-newest, tag2-oldest
        assert len(titles) == 4
        # The newest from each tag should appear before the oldest from that tag
        tag1_newest_idx = next(i for i, t in enumerate(titles) if "Tag1 newest" in t)
        tag1_oldest_idx = next(i for i, t in enumerate(titles) if "Tag1 oldest" in t)
        tag2_newest_idx = next(i for i, t in enumerate(titles) if "Tag2 newest" in t)
        tag2_oldest_idx = next(i for i, t in enumerate(titles) if "Tag2 oldest" in t)

        # Within each tag, newest should come before oldest
        assert tag1_newest_idx < tag1_oldest_idx
        assert tag2_newest_idx < tag2_oldest_idx

    def test_generate_feed_with_single_article(self, tmp_path):
        """Test that single article feeds work correctly."""
        articles = [
            Article(
                title="Single Article",
                url="https://www.jota.info/single",
                authors=["Author"],
                category="TRIBUTOS",
            ),
        ]

        output_path = generate_feed_for_tag("test-tag", articles, str(tmp_path))
        assert os.path.exists(output_path)

        tree = ET.parse(output_path)
        root = tree.getroot()

        items = root.findall(".//item/title")
        titles = [item.text for item in items]

        assert len(titles) == 1
        assert titles[0] == "Single Article"
