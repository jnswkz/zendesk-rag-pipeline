import re
from pathlib import Path
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import unicodedata
import json

def clean_soup(soup: BeautifulSoup) -> BeautifulSoup:

    for tag in soup(["script", "style"]):
        tag.decompose()


    for tag in soup.find_all("span"):
        tag.unwrap()

    for a in soup.find_all("a"):
        if a.has_attr("name") and not a.get_text(strip=True) and not a.has_attr("href"):

            a.replace_with(soup.new_string(f"\n<!-- anchor:{a['name']} -->\n"))

    for p in soup.find_all("p"):
        if not p.get_text(strip=True) and not p.find("img"):
            p.decompose()

    return soup

def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html5lib")
    soup = clean_soup(soup)


    markdown = md(
        str(soup),
        heading_style="ATX", 
        bullets="-",
        strip=["figure"],     
    )

    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

    return markdown

def safe_slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[-\s]+", "-", s)
    return s or "article"

def convert_article_to_md(article: dict, out_dir: str = "data/md", allow_overwrite: bool = False) -> Path:
    """
    Docstring for convert_article_to_md
    
    :param article: Article data
    :type article: dict
    :param out_dir: Output directory
    :type out_dir: str
    :return: Path to the generated markdown file
    :rtype: Path
    """
    article_id = article.get("id")
    title = article.get("title") or f"article-{article_id}"
    url = article.get("html_url") or article.get("url") or ""
    updated_at = article.get("updated_at") or ""
    labels = article.get("label_names") or []

    body_html = article.get("body") or ""
    body_md = html_to_markdown(body_html)

    # YAML front matter 
    front = (
        "---\n"
        f"id: {article_id}\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"url: {url}\n"
        f"updated_at: {updated_at}\n"
        f"labels: {json.dumps(labels, ensure_ascii=False)}\n"
        "---\n\n"
    )

    content = "\n".join([
        front.rstrip(),
        f"# {title}",
        "",
        f"Article URL: {url}",
        "",
        body_md.strip(),
        ""
    ])

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    fname = f"{article_id}-{safe_slug(title)}.md" if article_id else f"{safe_slug(title)}.md"

    md_path = out_path / fname

    if md_path.exists() and not allow_overwrite:
        return md_path

    md_path.write_text(content, encoding="utf-8")
    return md_path
