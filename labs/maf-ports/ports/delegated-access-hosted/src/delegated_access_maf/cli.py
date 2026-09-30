"""利用者側の CLI: サインイン(デバイスコード)と質問。

    uv run delegated-access login --user employee      # 利用者ごとにトークンをキャッシュ
    uv run delegated-access ask --user employee "与信限度額の見直し頻度は?"
    uv run delegated-access ask --user finance --continue "では S-001 の支払条件を 60 日に"
    uv run delegated-access logout --user employee

``--user`` は**このマシン上のキャッシュの名前**(``.cache/msal-<user>.json``)。どの Entra
利用者でサインインするかはデバイスコードの画面で決まる(2 人の検証なら別アカウントで 2 回
login する)。トークンはバックエンド API 宛て(``api://<BACKEND_API_CLIENT_ID>/access_as_user``)で、
ツール API のトークンは CLI には来ない(中間層が OBO で取る)。

条件付きアクセスが追加の認証を求めると、バックエンドは 401 と claims チャレンジを返す。
CLI はそれを ``.cache/claims-<user>.txt`` に保存し、次の ``login`` がそのチャレンジ付きで
サインインする(MFA などを満たしたトークンになる)。

環境変数: ``ENTRA_TENANT_ID`` / ``BACKEND_API_CLIENT_ID`` / ``BACKEND_URL``(既定
``http://localhost:8000``)/ ``DELEGATED_ACCESS_CACHE_DIR``(既定 ``./.cache``)。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import httpx

from .agent.signals import parse_www_authenticate
from .contracts import BACKEND_API_SCOPE_NAME
from .jwt_validation import AUTHORITY_HOST

DEFAULT_BACKEND_URL = "http://localhost:8000"
_ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class CliError(Exception):
    """利用者に見せて終了するエラー(終了コード付き)。"""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CliSettings:
    tenant_id: str
    backend_api_client_id: str
    backend_url: str = DEFAULT_BACKEND_URL
    cache_dir: Path = Path(".cache")

    @property
    def scopes(self) -> list[str]:
        return [f"api://{self.backend_api_client_id}/{BACKEND_API_SCOPE_NAME}"]

    @property
    def authority(self) -> str:
        return f"{AUTHORITY_HOST}/{self.tenant_id}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> CliSettings:
        env = os.environ if env is None else env
        missing = [
            n
            for n in ("ENTRA_TENANT_ID", "BACKEND_API_CLIENT_ID")
            if not (env.get(n) or "").strip()
        ]
        if missing:
            raise CliError(f"環境変数が未設定: {', '.join(missing)}(.env を確認)", code=2)
        return cls(
            tenant_id=env["ENTRA_TENANT_ID"].strip(),
            backend_api_client_id=env["BACKEND_API_CLIENT_ID"].strip(),
            backend_url=(env.get("BACKEND_URL") or DEFAULT_BACKEND_URL).strip().rstrip("/"),
            cache_dir=Path(env.get("DELEGATED_ACCESS_CACHE_DIR") or ".cache"),
        )


def check_alias(alias: str) -> str:
    if not _ALIAS_RE.fullmatch(alias):
        raise CliError("--user は英数字・_・- の 32 文字以内にしてください", code=2)
    return alias


class UserCache:
    """1 利用者分のファイル(MSAL のトークンキャッシュ・保留中の claims・直前の応答 ID)。"""

    def __init__(self, cache_dir: Path, alias: str) -> None:
        self.dir = cache_dir
        self.alias = check_alias(alias)

    @property
    def msal_path(self) -> Path:
        return self.dir / f"msal-{self.alias}.json"

    @property
    def claims_path(self) -> Path:
        return self.dir / f"claims-{self.alias}.txt"

    @property
    def state_path(self) -> Path:
        return self.dir / f"state-{self.alias}.json"

    def _write_private(self, path: Path, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)

    def load_msal(self) -> str | None:
        return self.msal_path.read_text(encoding="utf-8") if self.msal_path.is_file() else None

    def save_msal(self, serialized: str) -> None:
        self._write_private(self.msal_path, serialized)

    def pending_claims(self) -> str | None:
        if not self.claims_path.is_file():
            return None
        return self.claims_path.read_text(encoding="utf-8").strip() or None

    def save_claims(self, claims_json: str) -> None:
        self._write_private(self.claims_path, claims_json)

    def clear_claims(self) -> None:
        self.claims_path.unlink(missing_ok=True)

    def last_response_id(self) -> str | None:
        if not self.state_path.is_file():
            return None
        return json.loads(self.state_path.read_text(encoding="utf-8")).get("last_response_id")

    def save_response_id(self, response_id: str | None) -> None:
        if response_id:
            self._write_private(self.state_path, json.dumps({"last_response_id": response_id}))

    def clear(self) -> None:
        for path in (self.msal_path, self.claims_path, self.state_path):
            path.unlink(missing_ok=True)


# --- MSAL(公開クライアント)-----------------------------------------------------------


def _public_app(settings: CliSettings, cache: UserCache) -> tuple[Any, Any]:
    import msal

    token_cache = msal.SerializableTokenCache()
    if (serialized := cache.load_msal()) is not None:
        token_cache.deserialize(serialized)
    app = msal.PublicClientApplication(
        settings.backend_api_client_id, authority=settings.authority, token_cache=token_cache
    )
    return app, token_cache


def _persist(cache: UserCache, token_cache: Any) -> None:
    if token_cache.has_state_changed:
        cache.save_msal(token_cache.serialize())


def login(
    settings: CliSettings, cache: UserCache, out: TextIO, *, claims: str | None = None
) -> dict[str, Any]:
    """デバイスコードでサインインする(保留中の claims チャレンジがあれば付ける)。"""
    app, token_cache = _public_app(settings, cache)
    claims = claims or cache.pending_claims()
    flow = app.initiate_device_flow(scopes=settings.scopes, claims_challenge=claims)
    if "user_code" not in flow:
        raise CliError(
            f"デバイスコードを開始できませんでした: {flow.get('error_description') or flow}"
        )
    if claims:
        print("(追加の認証要求 = claims チャレンジを付けてサインインします)", file=out)
    print(flow["message"], file=out, flush=True)
    result = app.acquire_token_by_device_flow(flow, claims_challenge=claims)
    if result.get("error") in ("authorization_pending", "expired_token", "code_expired"):
        # MSAL はコードの有効期限(既定 15 分)まで待ち、切れると最後のポーリング結果(pending)を返す
        raise CliError(
            "デバイスコードの有効期限内にサインインが完了しませんでした。"
            f"もう一度 `delegated-access login --user {cache.alias}` を実行してください"
        )
    if "access_token" not in result:
        raise CliError(
            f"サインインに失敗しました: {result.get('error')}: {result.get('error_description')}"
        )
    _persist(cache, token_cache)
    cache.clear_claims()
    who = (result.get("id_token_claims") or {}).get("preferred_username", "?")
    print(f"サインインしました: {who}(キャッシュ: {cache.msal_path})", file=out)
    return result


def cached_token(settings: CliSettings, cache: UserCache) -> str:
    """キャッシュからバックエンド宛てのトークンを取る(期限切れはリフレッシュトークンで更新)。"""
    app, token_cache = _public_app(settings, cache)
    accounts = app.get_accounts()
    if not accounts:
        raise CliError(
            f"未サインインです。先に `delegated-access login --user {cache.alias}` を実行してください"
        )
    result = app.acquire_token_silent(settings.scopes, account=accounts[0])
    _persist(cache, token_cache)
    if not result or "access_token" not in result:
        raise CliError(
            f"トークンを更新できません。`delegated-access login --user {cache.alias}` をやり直してください"
        )
    return result["access_token"]


# --- 質問 -------------------------------------------------------------------------------


def decode_claims(claims_b64: str) -> str:
    padded = claims_b64 + "=" * (-len(claims_b64) % 4)
    try:
        return base64.b64decode(padded).decode()
    except (ValueError, UnicodeDecodeError):
        return base64.urlsafe_b64decode(padded).decode()


def ask(
    settings: CliSettings,
    cache: UserCache,
    question: str,
    out: TextIO,
    *,
    token_source: Callable[[], str],
    http: httpx.Client,
    previous_response_id: str | None = None,
) -> int:
    """バックエンドの ``/chat`` を呼んで結果を表示する。戻り値は終了コード。"""
    body: dict[str, Any] = {"message": question}
    if previous_response_id:
        body["previous_response_id"] = previous_response_id
    response = http.post(
        f"{settings.backend_url}/chat",
        json=body,
        headers={"Authorization": f"Bearer {token_source()}"},
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code == 200:
        print(payload.get("answer", ""), file=out)
        user = payload.get("user") or {}
        visible = ", ".join(payload.get("visible_servers") or []) or "(なし)"
        hidden = ", ".join(payload.get("hidden_servers") or []) or "(なし)"
        print(
            f"\n--- 利用者: {user.get('upn') or user.get('oid')} / 使えたツール: {visible} / "
            f"見えなかったツール: {hidden}",
            file=out,
        )
        cache.save_response_id(payload.get("response_id"))
        return 0

    challenge = parse_www_authenticate(response.headers.get("www-authenticate", ""))
    if response.status_code == 401 and challenge.get("error") == "insufficient_claims":
        claims_json = decode_claims(challenge.get("claims") or payload.get("claims") or "")
        cache.save_claims(claims_json)
        print("追加の認証が必要です(条件付きアクセスの claims チャレンジ)。", file=out)
        print(f"  要求された claims: {claims_json}", file=out)
        print(
            f"  `delegated-access login --user {cache.alias}` で再サインインしてから、もう一度質問してください"
            "(保存したチャレンジを自動で付けます)。",
            file=out,
        )
        return 3
    if response.status_code == 401:
        print(payload.get("message") or "サインインし直してください。", file=out)
        print(f"  `delegated-access login --user {cache.alias}` を実行してください。", file=out)
        return 3
    print(
        f"エラー(HTTP {response.status_code}): {payload.get('message') or response.text[:200]}",
        file=out,
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delegated-access", description="委任アクセスの hosted agent を呼ぶ CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="デバイスコードでサインインする")
    p_login.add_argument("--user", required=True, help="キャッシュ名(例: employee / finance)")
    p_login.add_argument(
        "--claims", default=None, help="claims チャレンジ(JSON か base64)。通常は自動"
    )

    p_ask = sub.add_parser("ask", help="質問する")
    p_ask.add_argument("--user", required=True)
    p_ask.add_argument("question")
    group = p_ask.add_mutually_exclusive_group()
    group.add_argument("--continue", dest="cont", action="store_true", help="直前の会話を続ける")
    group.add_argument("--previous-response-id", default=None)

    p_logout = sub.add_parser("logout", help="キャッシュを消す")
    p_logout.add_argument("--user", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - 実 Entra を使う経路
    from dotenv import load_dotenv

    load_dotenv()
    args = build_parser().parse_args(argv)
    out = sys.stdout
    try:
        settings = CliSettings.from_env()
        cache = UserCache(settings.cache_dir, args.user)
        if args.command == "login":
            claims = args.claims
            if claims and not claims.lstrip().startswith("{"):
                claims = decode_claims(claims)
            login(settings, cache, out, claims=claims)
            return 0
        if args.command == "logout":
            cache.clear()
            print(f"キャッシュを削除しました: {args.user}", file=out)
            return 0
        previous = args.previous_response_id or (cache.last_response_id() if args.cont else None)
        with httpx.Client(timeout=200.0, follow_redirects=False) as http:
            return ask(
                settings,
                cache,
                args.question,
                out,
                token_source=lambda: cached_token(settings, cache),
                http=http,
                previous_response_id=previous,
            )
    except CliError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return ex.code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
