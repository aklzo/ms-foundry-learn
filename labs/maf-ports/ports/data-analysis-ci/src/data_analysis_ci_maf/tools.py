"""Code Interpreter ツール定義の組み立て(元アプリの DuckDbTools + PandasTools の置き換え)。

元(agno): ``Agent(tools=[DuckDbTools(), PandasTools()])`` — DuckDB の SQL 実行も
pandas 操作も**ローカルプロセス内**で行うツール群。CSV は
``load_local_csv_to_table`` でローカル DuckDB のテーブルになる。

移植後(MAF): サーバー側サンドボックスの **code_interpreter コンテナツール**
1 つに集約する。installed package(agent-framework-core 1.13.0 /
agent-framework-openai 1.12.0)の精読結果:

- かつての ``HostedCodeInterpreterTool`` クラスは**存在しない**(_tools.py /
  _types.py に定義なし)。現行 API は「クライアントごとのファクトリ」方式:
  ``SupportsCodeInterpreterTool`` プロトコル(_clients.py 668 行)を実装する
  クライアントが ``get_code_interpreter_tool(**kwargs)`` を静的メソッドとして
  提供する
- ``OpenAIChatClient.get_code_interpreter_tool(file_ids=..., container="auto")``
  (agent_framework_openai/_chat_client.py 1005 行)は openai SDK の
  ``CodeInterpreter`` TypedDict — つまり**素の dict**
  ``{"type": "code_interpreter", "container": {"type": "auto", "file_ids": [...]}}``
  を返す
- dict ツールは ``normalize_tools`` をそのまま通過し(_tools.py 990 行)、
  ``_prepare_tools_for_openai`` も「dict / SDK 型は無変換でパススルー」
  (_chat_client.py 983 行)— Responses API の ``tools`` 配列にそのまま載る
- 応答側: Responses の ``code_interpreter_call`` 出力アイテムは
  ``code_interpreter_tool_call``(inputs = 生成コード)と
  ``code_interpreter_tool_result``(outputs = logs / 画像)の Content に
  パースされる(_chat_client.py 2685 行)→ 抽出は analysis.py

ファイルの渡し方はコンテナ設定の ``file_ids``(Files API にアップロード済みの
id)。アップロードは datafile.py、ここは**ツール dict の組み立てだけ**を担う
純関数で、テストでは ``factory`` に記録フェイクを注入する。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class CodeInterpreterUnsupportedError(RuntimeError):
    """チャットクライアントが code_interpreter ツールを提供しない場合。

    その場合は openai クライアント直(Responses API)へ切り替える判断になる
    (README「Responses API 直との使い分け」参照)。
    """


def build_code_interpreter_tool(
    chat_client: Any,
    file_ids: list[str],
    *,
    factory: Callable[..., Any] | None = None,
) -> Any:
    """アップロード済みファイルを参照する code_interpreter ツール dict を作る。

    ``factory`` はテスト用の注入シーム(既定はクライアント自身の
    ``get_code_interpreter_tool``)。実接続はここでは起きない — 返る dict が
    Agent 経由で Responses API の ``tools`` に載り、実行時にサーバー側で
    コンテナが作られる(コンテナはセッション課金。README 参照)。
    """
    if factory is None:
        from agent_framework import SupportsCodeInterpreterTool

        if not isinstance(chat_client, SupportsCodeInterpreterTool):
            raise CodeInterpreterUnsupportedError(
                f"{type(chat_client).__name__} は code_interpreter ツールを提供しない"
                "(SupportsCodeInterpreterTool 未実装)。openai クライアント直の"
                " Responses API 呼び出しへの切り替えを検討"
            )
        factory = chat_client.get_code_interpreter_tool

    return factory(file_ids=file_ids)
