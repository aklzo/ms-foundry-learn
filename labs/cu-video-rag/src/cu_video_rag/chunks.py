"""CU analyzeResult → 検索チャンク変換。

チャンク単位 = CU が返すセグメント(contents[] の 1 要素)。ベストプラクティス
(video/overview の RAG 節)どおり「セグメント=検索単位」とし、時間範囲を
メタデータとして持たせる。

インデックス構成(評価の比較軸):
- A transcript : transcriptPhrases のテキストのみ(自前 STT 相当のベースライン)
- B full       : transcript + CU 生成フィールド(セグメント記述など)
- C custom     : B と同じ抽出ロジックをカスタムアナライザーの結果に適用
                 (追加フィールドは fields に乗ってくるのでコードは共通)
"""

from __future__ import annotations

from typing import Any


def field_to_text(value: Any) -> str:
    """CU の field 値(型付き)を検索用テキストへ平坦化する。"""
    if not isinstance(value, dict):
        return str(value) if value else ""
    for k in ("valueString", "valueNumber", "valueInteger", "valueBoolean", "valueDate"):
        if k in value:
            return str(value[k])
    if "valueArray" in value:
        return " / ".join(filter(None, (field_to_text(v) for v in value["valueArray"])))
    if "valueObject" in value:
        return " ".join(
            f"{k}: {field_to_text(v)}" for k, v in value["valueObject"].items()
        )
    return ""


def parse_segments(analyze_result: dict, video_id: str) -> list[dict]:
    """analyzerResults 応答 → セグメントのリスト(全構成共通の中間表現)。"""
    contents = analyze_result.get("result", {}).get("contents", [])
    segments = []
    for i, c in enumerate(contents):
        transcript = "".join(p.get("text", "") for p in c.get("transcriptPhrases", []))
        fields_text = {
            name: field_to_text(v) for name, v in (c.get("fields") or {}).items()
        }
        segments.append(
            {
                "video_id": video_id,
                "segment_index": i,
                "start_s": c.get("startTimeMs", 0) / 1000,
                "end_s": c.get("endTimeMs", 0) / 1000,
                "transcript": transcript,
                "fields": {k: v for k, v in fields_text.items() if v},
                "markdown": c.get("markdown", ""),
            }
        )
    return segments


def to_chunks(segments: list[dict], config: str) -> list[dict]:
    """中間表現 → インデックス投入ドキュメント。config: transcript | full | split

    split は screenTexts を独立フィールドへ分離する(スコアリングプロファイルで
    重み付けし、回答値を持つセグメントを動画内で上位に押し上げる構成 D 用)。
    """
    chunks = []
    for s in segments:
        screen_texts = ""
        if config == "transcript":
            content = s["transcript"]
        elif config == "split":
            screen_texts = s["fields"].get("screenTexts", "")
            parts = [s["transcript"]] + [
                f"{k}: {v}" for k, v in s["fields"].items() if k != "screenTexts"
            ]
            content = "\n".join(p for p in parts if p)
        else:  # full(fields も本文に含める)
            parts = [s["transcript"]]
            parts += [f"{k}: {v}" for k, v in s["fields"].items()]
            content = "\n".join(p for p in parts if p)
        if not (content.strip() or screen_texts.strip()):
            continue
        chunks.append(
            {
                "id": f"{s['video_id']}-{s['segment_index']}",
                "video_id": s["video_id"],
                "start_s": s["start_s"],
                "end_s": s["end_s"],
                "content": content,
                "screen_texts": screen_texts,
            }
        )
    return chunks
