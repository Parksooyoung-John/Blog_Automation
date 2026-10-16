from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTHORIZATION_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
API_BASE_URL = "https://api.canva.com/rest/v1"

CANVA_SCOPES = (
    "asset:read",
    "asset:write",
    "brandtemplate:content:read",
    "brandtemplate:meta:read",
    "design:content:read",
    "design:content:write",
    "design:meta:read",
)


@dataclass(frozen=True)
class OAuthRequest:
    url: str
    state: str
    code_verifier: str


class CanvaAPIError(RuntimeError):
    """Raised when Canva returns a non-success response."""


class CanvaOAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        timeout: float = 20.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.timeout = timeout

    def authorization_request(self, scopes: tuple[str, ...] = CANVA_SCOPES) -> OAuthRequest:
        verifier = secrets.token_urlsafe(72)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(32)
        query = urlencode(
            {
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": " ".join(scopes),
                "response_type": "code",
                "client_id": self.client_id,
                "state": state,
                "redirect_uri": self.redirect_uri,
            }
        )
        return OAuthRequest(f"{AUTHORIZATION_URL}?{query}", state, verifier)

    def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        response = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": self.redirect_uri,
            },
            timeout=self.timeout,
        )
        return _json_response(response)

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        response = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=self.timeout,
        )
        return _json_response(response)


class CanvaClient:
    def __init__(self, access_token: str, *, timeout: float = 20.0) -> None:
        if not access_token:
            raise ValueError("Canva access token is required")
        self.access_token = access_token
        self.timeout = timeout

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.access_token}"
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            headers=headers,
            timeout=self.timeout,
            **kwargs,
        )
        return _json_response(response)

    def brand_template_dataset(self, template_id: str) -> dict[str, Any]:
        return self.request("GET", f"/brand-templates/{template_id}/dataset")

    def create_autofill(
        self, template_id: str, data: dict[str, Any], *, title: str = "MoneyBrief 카드"
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/autofills",
            json={
                "type": "create_from_brand_template",
                "brand_template_id": template_id,
                "title": title,
                "data": data,
            },
        )

    def autofill_status(self, job_id: str) -> dict[str, Any]:
        return self.request("GET", f"/autofills/{job_id}")

    def export_design(self, design_id: str, *, file_type: str = "png") -> dict[str, Any]:
        return self.request(
            "POST", "/exports", json={"design_id": design_id, "format": {"type": file_type}}
        )

    def export_status(self, job_id: str) -> dict[str, Any]:
        return self.request("GET", f"/exports/{job_id}")

    def wait_for_job(
        self, fetch_status: Any, job_id: str, *, timeout: float = 120.0
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = fetch_status(job_id)
            status = result.get("job", {}).get("status")
            if status in {"success", "failed"}:
                return result
            time.sleep(1)
        raise TimeoutError(f"Canva job did not finish within {timeout:.0f}s: {job_id}")


def save_tokens(path: Path, tokens: dict[str, Any]) -> None:
    path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tokens(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_local_oauth(
    oauth: CanvaOAuth, token_path: Path, *, open_browser: bool = True
) -> dict[str, Any]:
    redirect = urlparse(oauth.redirect_uri)
    if redirect.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("local OAuth requires a loopback redirect URI")
    if redirect.path != "/callback":
        raise ValueError("local OAuth redirect URI must end with /callback")
    request = oauth.authorization_request()
    result: dict[str, Any] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [None])[0] != request.state:
                result["error"] = "OAuth state mismatch"
            elif query.get("error"):
                result["error"] = query["error"][0]
            else:
                code = query.get("code", [None])[0]
                if not code:
                    result["error"] = "Canva callback did not include an authorization code"
                else:
                    result.update(oauth.exchange_code(code, request.code_verifier))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h1>Canva authorization complete</h1>"
                b"<p>You can close this window.</p>"
            )

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer((redirect.hostname, redirect.port or 80), CallbackHandler)
    print(f"Open this URL to authorize Canva: {request.url}", flush=True)
    if open_browser:
        webbrowser.open(request.url)
    server.handle_request()
    server.server_close()
    if "error" in result:
        raise CanvaAPIError(str(result["error"]))
    save_tokens(token_path, result)
    return result


def _json_response(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise CanvaAPIError(
            f"Canva returned non-JSON response (HTTP {response.status_code})"
        ) from exc
    if not response.ok:
        message = body.get("message") or body.get("error") or "unknown Canva error"
        raise CanvaAPIError(f"Canva API error (HTTP {response.status_code}): {message}")
    return body
