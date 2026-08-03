"""埋め込みのエンドポイントルーティング検証(survey 08 の注記の実測)。

survey 08:「プロジェクトエンドポイント経由 /openai/v1/responses も可(ただし
embeddings はプロジェクトエンドポイント未ルーティング)」。この非対称性を
実際に叩いて確認する。

観点:
  A. アカウント openai/v1 で embeddings.create(成功するはず)
  B. プロジェクト経由 client で embeddings.create(失敗するか / 何エラーか)
  C. アカウント経由で chat/responses(成功するはず。対称性の確認)
"""

from __future__ import annotations

import sys

from foundry_probes.common import Settings, bearer_token, section, show

EMBED_MODEL = "text-embedding-3-small"


def main() -> int:
    settings = Settings.from_env()
    from openai import OpenAI

    key = settings.api_key or bearer_token()
    account = OpenAI(base_url=settings.openai_v1_endpoint, api_key=key)

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(endpoint=settings.project_endpoint, credential=DefaultAzureCredential())
    project_openai = project.get_openai_client()

    section("A. アカウント openai/v1 で embeddings.create")
    try:
        e = account.embeddings.create(model=EMBED_MODEL, input="埋め込みルーティングの検証")
        show("成功", {"dims": len(e.data[0].embedding), "model": e.model, "usage": e.usage.model_dump()})
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {str(exc)[:250]}")

    section("B. プロジェクト経由 client で embeddings.create(未ルーティングの実測)")
    try:
        e = project_openai.embeddings.create(model=EMBED_MODEL, input="埋め込みルーティングの検証")
        show("成功(survey の記載と異なる)", {"dims": len(e.data[0].embedding), "model": e.model})
    except Exception as exc:
        show("失敗(survey どおり)", {"type": type(exc).__name__, "text": str(exc)[:300]})
        print(f"  base_url={project_openai.base_url}")

    section("C. アカウント経由で responses(対称性の確認)")
    try:
        r = account.responses.create(model=settings.model, input="1+1 は?")
        show("アカウント経由 responses 成功", r.output_text)
    except Exception as exc:
        show("失敗", {"type": type(exc).__name__, "text": str(exc)[:300]})

    return 0


if __name__ == "__main__":
    sys.exit(main())
