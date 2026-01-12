# JOTA RSS Feed Generator

A Python CLI tool that generates RSS feeds from [JOTA Info](https://www.jota.info/) tag pages.

## Features

- 🔍 **Tag-based feeds**: Generate RSS feeds from any JOTA "Tudo Sobre" tag page
- ⚡ **Async scraping**: Uses asyncio and httpx for fast concurrent requests
- 📰 **RSS feed generation**: Creates valid RSS 2.0 feeds
- ⏰ **Automated updates**: Updates feed via GitHub Actions
- 🌐 **GitHub Pages deployment**: Publishes RSS feeds to a public URL

## Requirements

- Python 3.12+
- Dependencies managed via `uv`

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/jota-rss-feed.git
cd jota-rss-feed
uv sync
```

## Usage

### Running Locally

Generate RSS feeds for tags in `tags.txt`:

```bash
uv run python src/main.py --tags-file tags.txt
```

Or specify tags directly:

```bash
uv run python src/main.py --tags itcmd reforma-tributaria stf
```

Or via environment variable:

```bash
export JOTA_TAGS="itcmd,reforma-tributaria,stf"
uv run python src/main.py --tags-env JOTA_TAGS
```

Generated feeds will be saved to `public/` directory.

### Command Line Options

```
--tags TAG [TAG ...]     List of tags to generate feeds for
--tags-file FILE         Path to file with tags (one per line)
--tags-env VAR           Environment variable with comma-separated tags
--output-dir DIR         Output directory (default: public)
--max-pages N            Max pages to scrape per tag (default: 3)
--debug                  Enable debug logging
```

## Configuration

### Tags File

Create a `tags.txt` file with one tag per line:

```
itcmd
reforma-tributaria
stf
tributos
```

### Automated Updates

The repository uses GitHub Actions to:
- Run every 6 hours
- Generate fresh RSS feeds
- Deploy to GitHub Pages

## RSS Feed URL

Once deployed, feeds are available at:

```
https://<username>.github.io/jota-rss-feed/<tag>.xml
```

A combined feed with all tags is at:

```
https://<username>.github.io/jota-rss-feed/feed.xml
```

## Development

### Running Tests

```bash
uv run pytest --cov=src --cov-report=term-missing
```

### Linting

```bash
uv run ruff check .
uv run ruff format .
```

## License

MIT
