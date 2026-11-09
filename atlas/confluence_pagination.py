"""Follow pagination links on Confluence collection endpoints."""

from urllib.parse import parse_qsl, urlsplit


def iter_results(client, path, params):
    initial_params = params
    seen = set()
    while True:
        query = tuple(sorted((key, str(value)) for key, value in params.items()))
        if query in seen:
            raise SystemExit("Confluence repeated a pagination link. Results are incomplete.")
        seen.add(query)

        data = client.confluence_get(path, params=params)
        yield from data.get("results") or []

        next_link = data.get("_links", {}).get("next")
        if not next_link:
            return
        # Keep the original endpoint and filters, even when the API returns
        # an absolute URL or a link with only the next page parameters.
        next_params = dict(parse_qsl(urlsplit(next_link).query, keep_blank_values=True))
        params = {**initial_params, **next_params}
