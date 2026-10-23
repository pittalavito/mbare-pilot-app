"""HTTP plumbing shared by the Jira and Confluence clients: one httpx client
per Atlassian Cloud site (``https://<site>.atlassian.net``), basic auth with
email + API token, HTTP errors mapped to AppErrors, pagination helpers."""
from typing import Any, Iterator

import httpx

from core.error import NotFoundError, UpstreamError, ValidationError

_DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


class AtlassianHttp:

    def __init__(self, base_url: str, email: str, api_token: str, transport: httpx.BaseTransport | None = None):
        """``transport`` is only for tests (httpx.MockTransport)."""
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            timeout=_DEFAULT_TIMEOUT,
            transport=transport,
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` (relative to the site) and return the JSON body."""
        # None (not {}) when there is nothing to add: an empty dict would wipe the
        # query string already in ``path`` (e.g. Confluence ``_links.next`` cursors).
        query = {k: v for k, v in (params or {}).items() if v is not None} or None
        try:
            response = self._client.get(path, params=query)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Atlassian non raggiungibile ({self.base_url}): {exc}") from exc
        self._raise_for_status(response)
        return response.json()

    def paginate_offset(self, path: str, params: dict[str, Any], limit: int, page_size: int = 50) -> Iterator[dict]:
        """``startAt``/``maxResults`` pagination (Jira): yields up to ``limit`` items of ``values``."""
        start, yielded = 0, 0
        while yielded < limit:
            body = self.get(path, {**params, "startAt": start, "maxResults": min(page_size, limit - yielded)})
            values = body.get("values", [])
            for value in values:
                yield value
                yielded += 1
            if body.get("isLast", True) or not values:
                return
            start += len(values)

    def paginate_cursor(self, path: str, params: dict[str, Any], limit: int, page_size: int = 50) -> Iterator[dict]:
        """Cursor pagination (Confluence v2): follows ``_links.next`` and yields
        up to ``limit`` items of ``results``."""
        next_path: str | None = path
        next_params: dict[str, Any] | None = {**params, "limit": min(page_size, limit)}
        yielded = 0
        while next_path and yielded < limit:
            body = self.get(next_path, next_params)
            for result in body.get("results", []):
                if yielded >= limit:
                    return
                yield result
                yielded += 1
            next_path = body.get("_links", {}).get("next")
            next_params = None  # the next link already carries cursor and limit

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = _error_detail(response)
        if response.status_code in (401, 403):
            raise ValidationError(f"Atlassian ha rifiutato le credenziali o i permessi ({response.status_code}): {detail}")
        if response.status_code == 404:
            raise NotFoundError(f"Risorsa Atlassian non trovata: {detail}")
        if response.status_code == 400:
            raise ValidationError(f"Richiesta non valida per Atlassian: {detail}")
        if response.status_code == 429:
            retry = response.headers.get("Retry-After", "?")
            raise UpstreamError(f"Troppe richieste ad Atlassian, riprova tra {retry}s.")
        raise UpstreamError(f"Errore Atlassian {response.status_code}: {detail}")


def _error_detail(response: httpx.Response) -> str:
    """Best-effort message from Jira (errorMessages/errors) or Confluence (message/errors)."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason_phrase
    messages = list(body.get("errorMessages", [])) if isinstance(body, dict) else []
    if isinstance(body, dict):
        if isinstance(body.get("errors"), dict):
            messages += [f"{k}: {v}" for k, v in body["errors"].items()]
        elif isinstance(body.get("errors"), list):
            messages += [str(e.get("title") or e.get("detail") or e) for e in body["errors"]]
        if body.get("message"):
            messages.append(str(body["message"]))
    return "; ".join(messages) or response.reason_phrase
