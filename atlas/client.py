"""HTTP client for Jira and Confluence Cloud REST APIs."""

from time import sleep

import requests


def request_error_message(error: requests.RequestException) -> str:
    if isinstance(error, requests.Timeout):
        return "Atlassian request timed out."
    if isinstance(error, requests.ConnectionError):
        return "Could not connect to Atlassian. Check your connection and configured site URL."
    if isinstance(error, requests.JSONDecodeError):
        return "Atlassian returned an invalid JSON response."
    if not isinstance(error, requests.HTTPError) or error.response is None:
        return "Atlassian request failed."

    response = error.response
    if response.status_code == 401:
        return "API error (401): Atlassian rejected the credentials. Check the email, token, and site URL."
    if response.status_code == 403:
        return f"{error}\nCheck that the account can access this Atlassian resource."
    if response.status_code == 409:
        return f"{error}\nReview the latest resource before trying again."
    if response.status_code == 429:
        seconds = _retry_after(response)
        wait = f" Wait at least {seconds} seconds before trying again." if seconds is not None else ""
        return f"API error (429): Atlassian rate limit reached.{wait}"
    return str(error)


def _retry_after(response) -> int | None:
    value = response.headers.get("Retry-After", "")
    if value.isascii() and value.isdecimal() and len(value) <= 10:
        return int(value)
    return None


class AtlassianClient:
    """Thin wrapper around requests.Session with Basic Auth and base URL."""

    def __init__(self, config: dict):
        self.base_url = config["atlassian_base_url"]
        self.session = requests.Session()
        self.session.auth = (config["atlassian_email"], config["atlassian_api_token"])
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def jira_get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", f"/rest/api/3/{path}", params=params)

    def jira_post(self, path: str, json_body: dict | None = None) -> dict:
        return self._request("POST", f"/rest/api/3/{path}", json=json_body)

    def jira_put(self, path: str, json_body: dict | None = None) -> dict:
        return self._request("PUT", f"/rest/api/3/{path}", json=json_body)

    def confluence_get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", f"/wiki/rest/api/{path}", params=params)

    def confluence_post(self, path: str, json_body: dict | None = None) -> dict:
        return self._request("POST", f"/wiki/rest/api/{path}", json=json_body)

    def confluence_put(self, path: str, json_body: dict | None = None) -> dict:
        return self._request("PUT", f"/wiki/rest/api/{path}", json=json_body)

    def confluence_upload(self, page_id: str, filename: str, data: bytes, content_type: str) -> bool:
        """Create a content-addressed attachment. Return False if it already exists."""
        path = f"/wiki/rest/api/content/{page_id}/child/attachment"
        try:
            self._request(
                "POST", path,
                headers={"X-Atlassian-Token": "nocheck", "Content-Type": None},
                files={"file": (filename, data, content_type)},
            )
        except requests.HTTPError as error:
            if error.response.status_code not in (400, 409):
                raise
            existing = self._request("GET", path, params={"filename": filename})
            if any(item.get("title") == filename for item in existing.get("results", [])):
                return False
            raise
        return True

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", 30)
        resp = self.session.request(method, url, **kwargs)
        read_only = method == "GET" or (method == "POST" and path in (
            "/rest/api/3/search/jql", "/rest/api/3/issue/bulkfetch",
        ))
        if read_only and resp.status_code in (429, 503):
            seconds = _retry_after(resp)
            if seconds is not None and seconds <= 5:
                sleep(seconds)
                resp = self.session.request(method, url, **kwargs)
        if not resp.ok:
            raise requests.HTTPError(f"API error ({resp.status_code}): {resp.text}", response=resp)
        if resp.status_code == 204:
            return {}
        return resp.json()
