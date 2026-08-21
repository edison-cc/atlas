"""HTTP client for Jira and Confluence Cloud REST APIs."""

import sys

import requests


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

    def confluence_upload(self, page_id: str, filename: str, data: bytes, content_type: str) -> dict:
        """Upload or update an attachment on a Confluence page (multipart form)."""
        headers = {"X-Atlassian-Token": "no-check", "Accept": "application/json"}
        base = f"{self.base_url}/wiki/rest/api/content/{page_id}/child/attachment"

        resp = requests.post(
            base,
            auth=self.session.auth,
            headers=headers,
            files={"file": (filename, data, content_type)},
            timeout=30,
        )
        if resp.ok:
            return resp.json()

        if resp.status_code == 400 and "same file name" in resp.text:
            att_id = self._find_attachment_id(page_id, filename)
            if att_id:
                resp2 = requests.post(
                    f"{base}/{att_id}/data",
                    auth=self.session.auth,
                    headers=headers,
                    files={"file": (filename, data, content_type)},
                    timeout=30,
                )
                if resp2.ok:
                    return resp2.json()
                print(f"Attachment update failed ({resp2.status_code}): {resp2.text}", file=sys.stderr)
                sys.exit(1)

        print(f"Upload failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)

    def _find_attachment_id(self, page_id: str, filename: str) -> str | None:
        data = self._request(
            "GET",
            f"/wiki/rest/api/content/{page_id}/child/attachment",
            params={"filename": filename},
        )
        results = data.get("results", [])
        return results[0]["id"] if results else None

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", 30)
        resp = self.session.request(method, url, **kwargs)
        if not resp.ok:
            print(f"API error ({resp.status_code}): {resp.text}", file=sys.stderr)
            sys.exit(1)
        if resp.status_code == 204:
            return {}
        return resp.json()
