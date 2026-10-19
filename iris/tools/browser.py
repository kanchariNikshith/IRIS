"""Safe browser requests; dispatch alone cannot verify the loaded page."""
from urllib.parse import urlencode, urlsplit
import webbrowser

from iris.tools.registry import ToolResult


def open_url(url: str) -> ToolResult:
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
        return ToolResult("failed", "The URL is invalid.")
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return ToolResult("failed", "Only HTTP and HTTPS website URLs are allowed.")
        _ = parsed.port  # Reject malformed ports before calling the browser.
    except ValueError:
        return ToolResult("failed", "The URL is invalid.")
    if not webbrowser.open(url, new=2):
        return ToolResult("failed", "The browser did not accept the website request.")
    return ToolResult("unverified", "I asked the browser to open the website, but couldn't confirm the page loaded.")


def web_search(query: str) -> ToolResult:
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return ToolResult("failed", "The search request is invalid.")
    result = open_url("https://www.google.com/search?" + urlencode({"q": query.strip()}))
    if result.status == "failed":
        return result
    return ToolResult("unverified", "I asked the browser to open search results, but couldn't confirm they loaded.")
