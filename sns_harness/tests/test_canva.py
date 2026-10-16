from urllib.parse import parse_qs, urlparse

import responses

from sns_harness.canva import AUTHORIZATION_URL, TOKEN_URL, CanvaOAuth


def test_authorization_request_uses_pkce_and_configured_redirect() -> None:
    request = CanvaOAuth(
        "client-id", "client-secret", "http://127.0.0.1:8080/callback"
    ).authorization_request()
    query = parse_qs(urlparse(request.url).query)

    assert urlparse(request.url).scheme == "https"
    assert urlparse(request.url).netloc == urlparse(AUTHORIZATION_URL).netloc
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8080/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(request.code_verifier) >= 43
    assert query["state"] == [request.state]


@responses.activate
def test_exchange_code_uses_basic_auth_and_pkce() -> None:
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "access", "refresh_token": "refresh", "expires_in": 14400},
        status=200,
    )
    oauth = CanvaOAuth("client-id", "client-secret", "http://127.0.0.1:8080/callback")

    result = oauth.exchange_code("auth-code", "verifier")

    assert result["access_token"] == "access"
    request = responses.calls[0].request
    assert request.body is not None
    assert "grant_type=authorization_code" in request.body
    assert "code_verifier=verifier" in request.body
    assert request.headers["Authorization"].startswith("Basic ")
