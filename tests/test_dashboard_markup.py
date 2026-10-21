"""Static surface contracts: local assets, accessible controls, and safe rendering."""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DashboardMarkupTests(unittest.TestCase):
    def test_accessible_static_dashboard_and_no_network_dependencies(self):
        index = ROOT / "dashboard/index.html"
        self.assertTrue(index.exists(), "dashboard entry point is missing")
        html = index.read_text()
        parser = Markup()
        parser.feed(html)
        ids = {attrs.get("id") for _, attrs in parser.tags}
        self.assertTrue({"plan-search", "language-filter", "status-filter", "plan-version",
            "source-select", "plan-rows", "detail-panel", "load-state", "reload-data",
            "index-status", "work-items", "provenance"}.issubset(ids))
        self.assertTrue(any(tag == "html" and attrs.get("lang") == "zh-CN" for tag, attrs in parser.tags))
        self.assertTrue(any(tag == "main" for tag, _ in parser.tags))
        self.assertTrue(any(tag == "a" and attrs.get("href") == "#main" for tag, attrs in parser.tags))
        labels = {attrs.get("for") for tag, attrs in parser.tags if tag == "label"}
        self.assertTrue({"plan-search", "language-filter", "status-filter", "plan-version", "source-select"}.issubset(labels))
        for tag, attrs in parser.tags:
            if tag in ("script", "link", "img"):
                url = attrs.get("src", attrs.get("href", ""))
                self.assertFalse(re.match(r"^(https?:)?//", url), url)
            if tag == "script":
                self.assertNotEqual(attrs.get("type"), "module", "file mode needs classic scripts")
        app = (ROOT / "dashboard/app.js").read_text()
        self.assertNotRegex(app, r"(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write)\s*(?:[=(])")
        self.assertIn("textContent", app)
        css = (ROOT / "dashboard/styles.css").read_text()
        self.assertIn("@media", css)
        self.assertIn(":focus-visible", css)
        self.assertNotIn("@import", css)
        self.assertIn("NGD", html)
        self.assertIn("计划不等于", html)


if __name__ == "__main__":
    unittest.main()
