"""CU analyzeResult → 検索チャンク変換。

チャンク単位 = CU が返すセグメント(contents[] の 1 要素)。ベストプラクティス
(video/overview の RAG 節)どおり「セグメント=検索単位」とし、時間範囲を
メタデータとして持たせる。

実測で分かった CU の挙動(findings 1-10):
  セグメントの transcriptPhrases は「フレーズの開始時刻が属するセグメント」に
  丸ごと付き、フレーズはセグメント境界で分割されない。無音の短いナレーションでは
  1 フレーズが 20〜30 秒に伸びるため、隣のセグメントの書き起こしが空になり、
  チャンクの本文と時間範囲がずれる(104 本で 277 セグメント中 115 が書き起こし空)。
  そこで **単語タイムスタンプ(words[])でセグメントの時間範囲へ再配分**する。
  旧挙動(そのまま)は transcript_raw に残し、構成 A0 で影響を実測する。
  また prebuilt はセグメントが時間的に重なることがあり(vpn-setup: 56.6〜71.0 と 58.3〜71.4)、
  同じフレーズが両方に付く。単語・フレーズとも (開始, 終了, テキスト) で重複除去する。

インデックス構成(評価の比較軸):
- A0 transcript_raw : CU の割り当てのままの書き起こし(再配分なし。ずれの影響測定用)
- A  transcript     : 単語タイムスタンプで再配分した書き起こしのみ(自前 STT 相当のベースライン)
- B  full           : transcript + CU 生成フィールド(セグメント記述など)
- C  custom         : B と同じ抽出ロジックをカスタムアナライザーの結果に適用
                      (追加フィールドは fields に乗ってくるのでコードは共通)
- D  split          : C の screenTexts を独立フィールドに分離(重み付け用)
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


def _segment_index(ms: int, bounds: list[tuple[int, int]]) -> int | None:
    """時刻 ms が属するセグメント。セグメント間の隙間は最も近い境界のセグメントへ寄せる。"""
    for i, (s, e) in enumerate(bounds):
        if s <= ms < e:
            return i
    if not bounds:
        return None
    return min(
        range(len(bounds)),
        key=lambda i: (bounds[i][0] - ms) if ms < bounds[i][0] else (ms - bounds[i][1]),
    )


def resplit_transcripts(contents: list[dict]) -> list[str]:
    """全フレーズの単語を時刻でセグメントへ再配分し、セグメントごとの書き起こしを返す。

    words[] が無いフレーズはフレーズ中央時刻のセグメントへ丸ごと入れる(フォールバック)。
    """
    bounds = [(c.get("startTimeMs", 0), c.get("endTimeMs", 0)) for c in contents]
    buckets: list[list[tuple[int, str]]] = [[] for _ in contents]
    seen: set[tuple] = set()
    for c in contents:
        for p in c.get("transcriptPhrases") or []:
            words = p.get("words") or []
            if not words:
                mid = (p.get("startTimeMs", 0) + p.get("endTimeMs", 0)) // 2
                i = _segment_index(mid, bounds)
                if i is not None:
                    buckets[i].append((p.get("startTimeMs", 0), p.get("text", "")))
                continue
            for w in words:
                key = (w.get("startTimeMs"), w.get("endTimeMs"), w.get("text"))
                if key in seen:
                    continue
                seen.add(key)
                mid = (w.get("startTimeMs", 0) + w.get("endTimeMs", 0)) // 2
                i = _segment_index(mid, bounds)
                if i is not None:
                    buckets[i].append((w.get("startTimeMs", 0), w.get("text", "")))
    return ["".join(t for _, t in sorted(b, key=lambda x: x[0])) for b in buckets]


def full_transcript(analyze_result: dict) -> str:
    """動画全体の書き起こし(CER 用)。フレーズを開始時刻順に連結する(句読点つき)。"""
    contents = analyze_result.get("result", {}).get("contents", [])
    # セグメントが時間的に重なると同じフレーズが複数セグメントに付く(prebuilt で実測)ため重複を除く
    seen: set[tuple] = set()
    phrases = []
    for c in contents:
        for p in c.get("transcriptPhrases") or []:
            key = (p.get("startTimeMs"), p.get("endTimeMs"), p.get("text"))
            if key not in seen:
                seen.add(key)
                phrases.append(p)
    phrases.sort(key=lambda p: p.get("startTimeMs", 0))
    return "".join(p.get("text", "") for p in phrases)


def parse_segments(analyze_result: dict, video_id: str) -> list[dict]:
    """analyzerResults 応答 → セグメントのリスト(全構成共通の中間表現)。"""
    contents = analyze_result.get("result", {}).get("contents", [])
    resplit = resplit_transcripts(contents)
    segments = []
    for i, c in enumerate(contents):
        raw = "".join(p.get("text", "") for p in c.get("transcriptPhrases") or [])
        fields_text = {
            name: field_to_text(v) for name, v in (c.get("fields") or {}).items()
        }
        segments.append(
            {
                "video_id": video_id,
                "segment_index": i,
                "start_s": c.get("startTimeMs", 0) / 1000,
                "end_s": c.get("endTimeMs", 0) / 1000,
                "transcript": resplit[i],
                "transcript_raw": raw,
                "fields": {k: v for k, v in fields_text.items() if v},
                "markdown": c.get("markdown", ""),
            }
        )
    return segments


def to_chunks(segments: list[dict], config: str) -> list[dict]:
    """中間表現 → インデックス投入ドキュメント。config: transcript_raw | transcript | full | split

    split は screenTexts を独立フィールドへ分離する(スコアリングプロファイルで
    重み付けし、回答値を持つセグメントを動画内で上位に押し上げる構成 D 用)。
    """
    chunks = []
    for s in segments:
        screen_texts = ""
        if config == "transcript_raw":
            content = s["transcript_raw"]
        elif config == "transcript":
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
