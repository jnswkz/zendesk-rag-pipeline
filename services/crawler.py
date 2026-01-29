import requests

def list_articles(base_helpcenter_url: str, locale: str | None = None, limit: int = 30):
    """
    Docstring for list_articles
    
    :param base_helpcenter_url: Description
    :type base_helpcenter_url: str
    :param locale: Description
    :type locale: str | None
    :param limit: Description
    :type limit: int
    """ 
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    path = f"/api/v2/help_center/{locale}/articles.json" if locale else "/api/v2/help_center/articles.json"
    url = base_helpcenter_url.rstrip("/") + path

    out = []
    while url and len(out) < limit:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

        out.extend(data.get("articles", []))
        url = data.get("next_page")  # Zendesk commonly returns absolute next_page

    return out #list of articles with length up to limit