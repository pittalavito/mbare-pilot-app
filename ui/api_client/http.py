"""HTTP plumbing to the backend: one httpx client, errors turned into
``ApiError`` with the backend's message, so views only show ``str(exc)``."""
from typing import Any
from urllib.parse import quote

import httpx

_TIMEOUT = httpx.Timeout(60.0, connect=3.0)


class ApiError(Exception):
    """The API answered with an error (``status``) or could not be reached (``status`` 0)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ApiUnavailable(ApiError):
    """The API is not running (or not at the configured URL)."""


class ApiClient:

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None):
        """``transport`` is for tests (httpx.MockTransport)."""
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=_TIMEOUT, transport=transport)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Any = None) -> Any:
        return self._request("POST", path, json=json)

    def put(self, path: str, json: Any = None) -> Any:
        return self._request("PUT", path, json=json)

    def patch(self, path: str, json: Any = None) -> Any:
        return self._request("PATCH", path, json=json)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def get_bytes(self, path: str) -> bytes:
        """A download: the raw response body."""
        return self._send("GET", path).content

    def put_bytes(self, path: str, data: bytes) -> Any:
        """An upload: ``data`` as the raw request body."""
        return self._request("PUT", path, content=data, headers={"Content-Type": "application/octet-stream"})

    def _request(self, method: str, path: str, **kwargs) -> Any:
        response = self._send(method, path, **kwargs)
        return response.json() if response.content else None

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ApiUnavailable(0, (
                f"API non raggiungibile su {self.base_url}. "
                "Avviala dal pannello Backend nella barra laterale."
            )) from exc
        if response.is_success:
            return response
        raise ApiError(response.status_code, _detail(response))


def _detail(response: httpx.Response) -> str:
    """The backend's ``detail``: a message for app errors, a list of field
    errors for invalid requests (422)."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        return response.text[:200] or response.reason_phrase
    if isinstance(detail, list):
        return "; ".join(f"{'.'.join(str(p) for p in item.get('loc', [])[1:])}: {item.get('msg')}" for item in detail)
    return str(detail or response.reason_phrase)


def segment(value: str) -> str:
    """``value`` as one URL path segment (``/`` and spaces encoded)."""
    return quote(value, safe="")
