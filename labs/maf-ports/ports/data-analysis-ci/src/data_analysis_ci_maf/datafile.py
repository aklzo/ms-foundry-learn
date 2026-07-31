"""データファイルの検証とアップロード — 元アプリの preprocess_and_save の置き換え。

元(ai_data_analyst.py 11-46 行): アップロードされた CSV/Excel を pandas で
読み、日付・数値の型変換と文字列のクオート処理をした一時 CSV を作って
DuckDB にロードしていた(前処理は**クライアント側の pandas**)。

移植後: 前処理は **Code Interpreter サンドボックス内の pandas に移る**ため、
クライアント側の仕事は 2 つに縮む:

1. 形式チェック(CSV / Excel 以外は元アプリ同様エラー)
2. OpenAI Files API へのアップロード(``purpose="assistants"`` — code_interpreter
   コンテナの ``file_ids`` が参照できる purpose)

アップロード先クライアントは MAF ``OpenAIChatClient`` が内包する
``AsyncOpenAI``(``chat_client.client``)を再利用する — Foundry の v1
エンドポイントと API キーの設定を二重に持たないため。テストでは
``files_api`` に記録フェイクを注入する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

#: 元アプリがサポートする形式(file.name.endswith('.csv') / ('.xlsx'))と同値
SUPPORTED_SUFFIXES = frozenset({".csv", ".xlsx"})

#: code_interpreter コンテナの file_ids が参照できるアップロード purpose
UPLOAD_PURPOSE = "assistants"


class UnsupportedFileError(ValueError):
    """元アプリの st.error("Unsupported file format...") に対応。"""


class SupportsFileCreate(Protocol):
    """アップロードが必要とする最小面(``AsyncOpenAI().files`` 互換)。"""

    async def create(self, *, file: Any, purpose: str) -> Any: ...


def validate_data_file(path: str | Path) -> Path:
    """存在と形式(CSV / Excel)を検証して Path を返す。

    元アプリの分岐(csv → read_csv / xlsx → read_excel / それ以外 → エラー)の
    「それ以外 → エラー」部分に対応する。読み込み・型変換はしない —
    それは Code Interpreter 内の pandas の仕事になった。
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"データファイルが見つからない: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise UnsupportedFileError(
            "Unsupported file format. Please upload a CSV or Excel file."
            f"(指定: {resolved.name})"
        )
    return resolved


async def upload_data_file(files_api: SupportsFileCreate, path: Path) -> str:
    """データファイルを Files API にアップロードし file id を返す。

    サンドボックス内ではアップロード時のファイル名のまま /mnt/data 配下に
    見えるため、ファイルオブジェクト(name 属性 = パス)をそのまま渡す。
    """
    with path.open("rb") as fh:
        uploaded = await files_api.create(file=fh, purpose=UPLOAD_PURPOSE)
    return uploaded.id
