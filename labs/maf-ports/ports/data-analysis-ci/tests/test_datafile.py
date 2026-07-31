"""ファイル検証とアップロード配線のオフラインテスト。

元アプリの preprocess_and_save のうちクライアント側に残った責務
(形式チェック)と、新しい責務(Files API へのアップロード)を固定する。
Files API は記録フェイクで置き換える(実接続はライブスモークのみ)。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from data_analysis_ci_maf.datafile import (
    UPLOAD_PURPOSE,
    UnsupportedFileError,
    upload_data_file,
    validate_data_file,
)

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample_sales.csv"


# --- validate_data_file(元アプリの csv / xlsx / それ以外の分岐)---


def test_sample_csv_is_valid() -> None:
    assert validate_data_file(SAMPLE_CSV) == SAMPLE_CSV


def test_xlsx_suffix_is_accepted(tmp_path: Path) -> None:
    xlsx = tmp_path / "report.XLSX"  # 大文字拡張子も許容
    xlsx.write_bytes(b"dummy")

    assert validate_data_file(xlsx) == xlsx


def test_unsupported_format_matches_original_error(tmp_path: Path) -> None:
    other = tmp_path / "data.json"
    other.write_text("{}")

    with pytest.raises(UnsupportedFileError) as excinfo:
        validate_data_file(other)

    # 元アプリの st.error 文言を踏襲
    assert "Unsupported file format. Please upload a CSV or Excel file." in str(excinfo.value)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        validate_data_file("/nonexistent/data.csv")


# --- upload_data_file(Files API への配線)---


@dataclass
class FakeUploaded:
    id: str


class FakeFilesApi:
    """AsyncOpenAI().files 互換の記録フェイク。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, *, file: Any, purpose: str) -> FakeUploaded:
        self.calls.append({"filename": Path(file.name).name, "purpose": purpose})
        return FakeUploaded(id="file-test123")


async def test_upload_passes_file_and_assistants_purpose() -> None:
    files_api = FakeFilesApi()

    file_id = await upload_data_file(files_api, SAMPLE_CSV)

    assert file_id == "file-test123"
    assert files_api.calls == [
        # purpose="assistants" が code_interpreter コンテナの file_ids の前提
        {"filename": "sample_sales.csv", "purpose": UPLOAD_PURPOSE},
    ]
    assert UPLOAD_PURPOSE == "assistants"


# --- サンプルデータ自体の健全性(live smoke の期待値の根拠)---


def test_sample_csv_shape_and_totals() -> None:
    """live smoke が問う「合計と上位カテゴリ」の正解値をローカルで固定する。"""
    import csv

    with SAMPLE_CSV.open() as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 30
    for row in rows:
        assert int(row["revenue"]) == int(row["quantity"]) * int(row["unit_price"])

    total = sum(int(row["revenue"]) for row in rows)
    by_category: dict[str, int] = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + int(row["revenue"])

    assert total == 3225050
    assert max(by_category, key=by_category.get) == "Electronics"  # type: ignore[arg-type]
    assert by_category["Electronics"] == 1863500
