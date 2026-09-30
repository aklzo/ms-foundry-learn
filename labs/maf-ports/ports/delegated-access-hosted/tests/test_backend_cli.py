"""利用者側 CLI — バックエンドの応答の見せ方(claims チャレンジを含む)とキャッシュ。

MSAL のサインイン(デバイスコード)は実 Entra が要るのでここでは扱わない。
``ask`` はトークンの取り出し口と HTTP クライアントを差し替えて検証する。
"""

from __future__ import annotations

import base64
import io
import json

import httpx
import pytest

from delegated_access_maf.cli import (
    CliError,
    CliSettings,
    UserCache,
    ask,
    build_parser,
    check_alias,
    decode_claims,
    parse_www_authenticate,
)

CLAIMS = '{"access_token":{"acrs":{"essential":true,"value":"c1"}}}'


@pytest.fixture
def settings(tmp_path) -> CliSettings:
    return CliSettings(
        tenant_id="t", backend_api_client_id="b", backend_url="http://backend", cache_dir=tmp_path
    )


def run_ask(settings, cache, handler, **kwargs) -> tuple[int, str, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    out = io.StringIO()
    with httpx.Client(transport=httpx.MockTransport(recording)) as http:
        code = ask(
            settings, cache, "質問", out, token_source=lambda: "user-token", http=http, **kwargs
        )
    return code, out.getvalue(), seen


def test_answer_is_printed_and_response_id_is_remembered(settings) -> None:
    cache = UserCache(settings.cache_dir, "employee")
    body = {
        "answer": "取引先は 2 社です",
        "response_id": "caresp_1",
        "user": {"upn": "employee@contoso.example"},
        "visible_servers": ["docs", "suppliers"],
        "hidden_servers": ["supplier-admin"],
    }
    code, out, seen = run_ask(
        settings, cache, lambda r: httpx.Response(200, json=body), previous_response_id="caresp_0"
    )

    assert code == 0
    assert "取引先は 2 社です" in out
    assert "見えなかったツール: supplier-admin" in out
    assert seen[0].headers["authorization"] == "Bearer user-token"
    assert json.loads(seen[0].content) == {"message": "質問", "previous_response_id": "caresp_0"}
    assert cache.last_response_id() == "caresp_1"


def test_claims_challenge_is_shown_and_saved_for_the_next_login(settings) -> None:
    cache = UserCache(settings.cache_dir, "finance")
    claims_b64 = base64.b64encode(CLAIMS.encode()).decode()
    response = httpx.Response(
        401,
        json={"error": "insufficient_claims", "claims": claims_b64},
        headers={"WWW-Authenticate": f'Bearer error="insufficient_claims", claims="{claims_b64}"'},
    )
    code, out, _ = run_ask(settings, cache, lambda r: response)

    assert code == 3
    assert "claims チャレンジ" in out
    assert '"acrs"' in out
    assert "delegated-access login --user finance" in out
    assert cache.pending_claims() == CLAIMS
    assert oct(cache.claims_path.stat().st_mode & 0o777) == "0o600"


def test_plain_401_asks_for_login(settings) -> None:
    cache = UserCache(settings.cache_dir, "employee")
    response = httpx.Response(
        401,
        json={"error": "reauth_required", "message": "もう一度サインインしてください。"},
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )
    code, out, _ = run_ask(settings, cache, lambda r: response)
    assert code == 3
    assert "login --user employee" in out
    assert cache.pending_claims() is None


def test_other_errors_exit_nonzero(settings) -> None:
    cache = UserCache(settings.cache_dir, "employee")
    code, out, _ = run_ask(
        settings,
        cache,
        lambda r: httpx.Response(502, json={"message": "エージェントを呼び出せません"}),
    )
    assert code == 1
    assert "502" in out


def test_helpers() -> None:
    params = parse_www_authenticate('Bearer error="insufficient_claims", claims="eyJ4Ijp7fX0="')
    assert params == {"error": "insufficient_claims", "claims": "eyJ4Ijp7fX0="}
    assert decode_claims(base64.b64encode(CLAIMS.encode()).decode().rstrip("=")) == CLAIMS
    assert check_alias("finance") == "finance"
    with pytest.raises(CliError):
        check_alias("../etc")


def test_cache_files_are_per_user_and_clearable(tmp_path) -> None:
    a, b = UserCache(tmp_path, "employee"), UserCache(tmp_path, "finance")
    a.save_msal("{}")
    b.save_response_id("caresp_b")
    assert a.msal_path != b.msal_path
    assert a.last_response_id() is None and b.last_response_id() == "caresp_b"
    a.clear()
    assert not a.msal_path.exists() and b.state_path.exists()


def test_settings_and_parser() -> None:
    with pytest.raises(CliError):
        CliSettings.from_env({})
    settings = CliSettings.from_env({"ENTRA_TENANT_ID": "t", "BACKEND_API_CLIENT_ID": "b"})
    assert settings.scopes == ["api://b/access_as_user"]
    assert settings.backend_url == "http://localhost:8000"
    assert settings.authority == "https://login.microsoftonline.com/t"
    args = build_parser().parse_args(["ask", "--user", "finance", "--continue", "続き"])
    assert (args.command, args.user, args.cont, args.question) == ("ask", "finance", True, "続き")
