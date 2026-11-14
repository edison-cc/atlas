"""Cursor pagination for Jira enhanced search."""


def has_next_search_page(page):
    last = page.get("isLast")
    return last is False or (last is not True and bool(page.get("nextPageToken")))


def iter_search_pages(client, query):
    seen = set()
    while True:
        # POST supports JQL expressions that are too large for a GET URL.
        page = client.jira_post("search/jql", json_body=query)
        yield page
        if not has_next_search_page(page):
            return

        token = page.get("nextPageToken")
        if not isinstance(token, str) or not token or token in seen:
            raise SystemExit("Jira returned an invalid pagination token. Results are incomplete.")
        seen.add(token)
        query = {**query, "nextPageToken": token}
