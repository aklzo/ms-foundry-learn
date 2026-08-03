"""probe 共通ヘルパー: .env 読み込み・Entra ID 認証・観察結果の整形出力。

probe は「観点ごとにリクエストを投げて生の挙動を観察する」スクリプト。
出力はそのまま NOTES.md の根拠になるので、リクエスト内容と応答の要点を
必ず対で表示する。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

LAB_ROOT = Path(__file__).resolve().parents[2]

#: openai v1 エンドポイント(モデル推論)の Entra スコープ
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
#: プロジェクトエンドポイント(Agent Service / evals 等)の Entra スコープ
AI_SCOPE = "https://ai.azure.com/.default"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    openai_v1_endpoint: str
    model: str
    api_key: str | None

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(LAB_ROOT / ".env")
        project = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
        v1 = os.environ.get("FOUNDRY_OPENAI_V1_ENDPOINT", "")
        model = os.environ.get("FOUNDRY_MODEL", "")
        if not (project and v1 and model):
            raise ConfigError("FOUNDRY_PROJECT_ENDPOINT / FOUNDRY_OPENAI_V1_ENDPOINT / FOUNDRY_MODEL を .env に設定(雛形 .env.example)")
        return cls(
            project_endpoint=project,
            openai_v1_endpoint=v1,
            model=model,
            api_key=os.environ.get("FOUNDRY_API_KEY") or None,
        )


def bearer_token(scope: str = COGNITIVE_SCOPE) -> str:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential().get_token(scope).token


def make_openai_client(settings: Settings) -> Any:
    """openai v1 エンドポイント用クライアント。Entra トークンを api_key に渡す
    (probe は短命プロセスなのでリフレッシュ不要)。"""
    from openai import OpenAI

    key = settings.api_key or bearer_token(COGNITIVE_SCOPE)
    return OpenAI(base_url=settings.openai_v1_endpoint, api_key=key)


def make_project_client(settings: Settings) -> Any:
    """プロジェクトエンドポイント用 AIProjectClient(azure-ai-projects 2.x)。"""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(endpoint=settings.project_endpoint, credential=DefaultAzureCredential())


# --- 出力整形 ---


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n== {title}\n{'=' * 70}")


def show(label: str, value: Any, limit: int = 800) -> None:
    """観察値を JSON っぽく短く表示(長文は切って全長を併記)。"""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, indent=2)
    if len(text) > limit:
        text = f"{text[:limit]} …(全{len(text)}文字)"
    print(f"--- {label}\n{text}")
