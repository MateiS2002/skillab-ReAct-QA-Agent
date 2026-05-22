from datetime import date as system_date, timedelta, datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlencode, urlparse
from xml.etree import ElementTree

import requests

from tools.params_models import CalculatorParams, DateParams, LatestNewsParams, PageParams, TimeParams
from tools.registry import register_tool


class ReadableTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._ignored_depth = 0
        self.title = ""
        self._in_title = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self._ignored_depth += 1

        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        text = data.strip()

        if not text:
            return

        if self._in_title:
            self.title = f"{self.title} {text}".strip()
            return

        if self._ignored_depth == 0:
            self.parts.append(text)


@register_tool
def calculator(params: CalculatorParams) -> str:
    """Evaluates a simple mathematical expression."""
    allowed_characters = set("0123456789+-*/(). ")

    if any(character not in allowed_characters for character in params.expression):
        return "Invalid expression: only numbers and basic arithmetic operators are allowed."

    try:
        result = eval(params.expression, {"__builtins__": {}}, {})
    except Exception as error:
        return f"Invalid expression used in the calculator tool: {error}"

    return str(result)

@register_tool
def get_date(params: DateParams) -> str:
    """Provides the correct date in the format DD-MM-YYYY"""
    target_date = system_date.today() + timedelta(days=params.day_offset)

    return target_date.strftime("%d-%m-%Y")

@register_tool
def get_time(params: TimeParams) -> str:
    """Provides the current local time in HH:MM or HH:MM:SS format."""
    current_time = datetime.now()

    if params.include_seconds:
        return current_time.strftime("%H:%M:%S")

    return current_time.strftime("%H:%M")

@register_tool
def get_latest_news(params: LatestNewsParams) -> str:
    """Return a list of recent article titles, URLs, publish dates, and short snippets from RSS/search feeds."""
    query = params.location

    if params.topic:
        query = f"{params.location} {params.topic}"

    rss_url = "https://news.google.com/rss/search?" + urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )

    try:
        response = requests.get(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 ReActHomeworkAgent/1.0"},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return f"Error: could not fetch news RSS feed: {error}"

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError as error:
        return f"Error: could not parse news RSS feed: {error}"

    articles = []

    for item in root.findall("./channel/item")[: params.max_results]:
        description_html = item.findtext("description", default="")
        source = item.find("source")
        source_name = source.text if source is not None and source.text else "Unknown source"

        articles.append(
            {
                "title": item.findtext("title", default="Untitled").strip(),
                "url": item.findtext("link", default="").strip(),
                "published": item.findtext("pubDate", default="Unknown date").strip(),
                "source": source_name.strip(),
                "snippet": _clean_text(description_html),
            }
        )

    if not articles:
        return f"No recent news found for query: {query}"

    return json.dumps(
        {
            "query": query,
            "note": "Results come from RSS headlines/snippets. Full article content was not fetched.",
            "articles": articles,
        },
        indent=2,
    )


@register_tool
def get_page(params: PageParams) -> str:
    """Fetch a page URL and extract readable text."""
    parsed_url = urlparse(params.url)

    if parsed_url.scheme not in {"http", "https"}:
        return "Error: only http and https URLs are supported."

    try:
        response = requests.get(
            params.url,
            headers={"User-Agent": "Mozilla/5.0 ReActHomeworkAgent/1.0"},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return (
            "Error: could not fetch page. The site may block automated requests, "
            f"require browser verification, or be unavailable. Details: {error}"
        )

    content_type = response.headers.get("content-type", "")

    if "html" not in content_type.lower():
        return f"Error: expected an HTML page but received content type: {content_type}"

    parser = ReadableTextParser()
    parser.feed(response.text)

    text = _clean_text(" ".join(parser.parts))

    if not text:
        return "Error: no readable text could be extracted from the page."

    return json.dumps(
        {
            "url": params.url,
            "title": _clean_text(parser.title) or "Untitled page",
            "text": text[: params.max_chars],
            "truncated": len(text) > params.max_chars,
        },
        indent=2,
    )


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()
