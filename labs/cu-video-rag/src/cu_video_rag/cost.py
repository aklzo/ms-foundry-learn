"""CU の usage(analyzerResults 応答)からのコスト集計と概算。

一次情報:
- 課金モデル(動画 = コンテンツ抽出 [時間課金] + 標準コンテキスト化トークン + 紐づけモデルのトークン):
  https://learn.microsoft.com/azure/ai-services/content-understanding/pricing-explainer
- 単価: Azure Retail Prices API(https://prices.azure.com/api/retail/prices、japaneast、USD、
  取得日 2026-09-03)。単価は変動するため、見積もり時は必ず最新を確認すること。

usage の形(GA 2025-11-01、動画):
  {"videoHours": 0.021, "contextualizationTokens": 20555,
   "tokens": {"gpt-5.4-mini-input": 20095, "gpt-5.4-mini-output": 797}}
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

# USD。キーはレポート表示用の名前も兼ねる
PRICES_USD = {
    "cu_video_extraction_per_hour": 1.00,  # Video Content Extraction
    "cu_std_contextualization_per_1m_tokens": 1.00,  # Std Contextualization Tokens ($0.001/1K)
    "gpt-5.4-mini_input_per_1m": 0.75,  # 5.4 mini Inp Gl(Global Standard)
    "gpt-5.4-mini_output_per_1m": 4.50,  # 5.4 mini Opt Gl
    "gpt-4.1-mini_input_per_1m": 0.40,  # ragas 判定(Global Standard)
    "gpt-4.1-mini_output_per_1m": 1.60,
    "text-embedding-3-small_per_1m": 0.02,  # text-embedding-3-small-glbl
    "search_basic_per_hour": 0.133,  # AI Search Basic Unit
    "speech_neural_tts_per_1m_chars": 15.0,  # S1 Neural Text To Speech Characters
}
PRICES_SOURCE = "Azure Retail Prices API(japaneast, USD, 2026-09-03 取得)"


def summarize_usage(cu_dir: Path) -> dict:
    """logs/cu/<tag>/*.json の usage を合算する。"""
    agg: dict[str, float] = defaultdict(float)
    tokens: dict[str, int] = defaultdict(int)
    n = 0
    for p in sorted(cu_dir.glob("*.json")):
        u = json.loads(p.read_text(encoding="utf-8")).get("usage") or {}
        n += 1
        for k, v in u.items():
            if k == "tokens":
                for mk, mv in v.items():
                    tokens[mk] += int(mv)
            elif isinstance(v, (int, float)):
                agg[k] += v
    return {"videos": n, **{k: round(v, 4) for k, v in agg.items()}, "tokens": dict(tokens)}


def estimate_cu_cost(usage: dict, prices: dict = PRICES_USD) -> dict:
    """1 アナライザー分の usage → 費目別 USD。"""
    video_h = usage.get("videoHours", 0.0)
    ctx = usage.get("contextualizationTokens", 0.0)
    items = {
        "video_extraction": video_h * prices["cu_video_extraction_per_hour"],
        "contextualization": ctx / 1e6 * prices["cu_std_contextualization_per_1m_tokens"],
    }
    for mk, mv in usage.get("tokens", {}).items():
        model, kind = mk.rsplit("-", 1)  # "gpt-5.4-mini-input" → ("gpt-5.4-mini", "input")
        key = f"{model}_{kind}_per_1m"
        if key in prices:
            items[f"model_{kind}"] = items.get(f"model_{kind}", 0.0) + mv / 1e6 * prices[key]
    items["total"] = sum(v for k, v in items.items() if k != "total")
    return {k: round(v, 4) for k, v in items.items()}
