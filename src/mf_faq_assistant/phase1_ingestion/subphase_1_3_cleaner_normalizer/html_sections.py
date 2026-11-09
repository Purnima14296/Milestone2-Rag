from __future__ import annotations

from bs4 import BeautifulSoup


def extract_meta_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return ""
