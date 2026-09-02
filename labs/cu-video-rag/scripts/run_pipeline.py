"""検証パイプライン CLI。

  uv run python scripts/run_pipeline.py dataset            # 動画データセット生成(TTS+録画+合成)
  uv run python scripts/run_pipeline.py defaults           # CU defaults にモデルデプロイ紐づけ
  uv run python scripts/run_pipeline.py upload             # 動画を Blob へ+SAS URL 生成
  uv run python scripts/run_pipeline.py analyze [--analyzer prebuilt-videoSearch --tag prebuilt]
  uv run python scripts/run_pipeline.py cer --tag prebuilt # 書き起こし CER
  uv run python scripts/run_pipeline.py index --config A --tag prebuilt
  uv run python scripts/run_pipeline.py eval --configs A,B,C,D  # 検索評価(hit@k/MRR/ans@k)
  uv run python scripts/run_pipeline.py create-analyzer --id X --file def.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from cu_video_rag import chunks as chunks_mod  # noqa: E402
from cu_video_rag import evaluate as ev  # noqa: E402
from cu_video_rag import record, search_index  # noqa: E402
from cu_video_rag.cu_client import CuClient  # noqa: E402
from cu_video_rag.scenarios import QUERIES, SCENARIOS  # noqa: E402

DATA = ROOT / "data"
LOGS = ROOT / "logs"

CONFIG_MODES = {"A": "transcript", "B": "full", "C": "full", "D": "split"}  # C/D はカスタム結果
CONFIG_TAGS = {"A": "prebuilt", "B": "prebuilt", "C": "custom", "D": "custom"}
CONFIG_PROFILES = {"D": "boost-screen"}  # D は screen_texts 重み付けプロファイルで検索


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"missing env: {name} (scripts/setup_azure.sh を先に実行)")
    return v


def cu() -> CuClient:
    return CuClient(env("FOUNDRY_ENDPOINT"), env("AI_KEY"))


def load_ground_truths() -> dict[str, dict]:
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in (DATA / "ground_truth").glob("*.json")
    }


def cmd_dataset(_args) -> None:
    record.build_all(DATA, speech_key=env("AI_KEY"), region=env("REGION"))


def cmd_defaults(_args) -> None:
    client = cu()
    mapping = {
        env("COMPLETION_MODEL"): env("COMPLETION_DEPLOYMENT"),
        env("EMBED_MODEL"): env("EMBED_DEPLOYMENT"),
    }
    try:
        print(json.dumps(client.patch_defaults(mapping), ensure_ascii=False))
    except Exception as e:  # GA 版で通らない場合は preview 版で再試行(結果は NOTES に記録)
        print(f"GA version failed: {e}; retrying with 2026-06-01-preview", file=sys.stderr)
        client.api_version = "2026-06-01-preview"
        print(json.dumps(client.patch_defaults(mapping), ensure_ascii=False))
    print(json.dumps(client.get_defaults(), ensure_ascii=False))


def cmd_upload(_args) -> None:
    """mp4 を Blob へアップロードし、読み取り SAS URL を data/eval/video_urls.json へ。"""
    account, key = env("STORAGE_NAME"), env("STORAGE_KEY")
    urls = {}
    expiry = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%MZ")
    for sc in SCENARIOS:
        mp4 = DATA / "videos" / f"{sc.id}.mp4"
        blob = f"{sc.id}.mp4"
        subprocess.run(
            ["az", "storage", "blob", "upload", "--account-name", account, "--account-key", key,
             "-c", "videos", "-n", blob, "-f", str(mp4), "--overwrite", "-o", "none"],
            check=True,
        )
        sas = subprocess.run(
            ["az", "storage", "blob", "generate-sas", "--account-name", account,
             "--account-key", key, "-c", "videos", "-n", blob, "--permissions", "r",
             "--expiry", expiry, "--https-only", "-o", "tsv"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        urls[sc.id] = f"https://{account}.blob.core.windows.net/videos/{blob}?{sas}"
        print(f"uploaded {blob}")
    (DATA / "eval").mkdir(exist_ok=True)
    (DATA / "eval" / "video_urls.json").write_text(json.dumps(urls, indent=2), encoding="utf-8")


def cmd_analyze(args) -> None:
    client = cu()
    urls = json.loads((DATA / "eval" / "video_urls.json").read_text(encoding="utf-8"))
    out_dir = LOGS / "cu" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    for vid, url in urls.items():
        if args.only and vid != args.only:
            continue
        print(f"analyzing {vid} with {args.analyzer} ...")
        t0 = datetime.now(timezone.utc)
        result = client.analyze_url(args.analyzer, url)
        sec = (datetime.now(timezone.utc) - t0).total_seconds()
        (out_dir / f"{vid}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        n_seg = len(result.get("result", {}).get("contents", []))
        print(f"  done in {sec:.0f}s, segments={n_seg}")


def _load_segments(tag: str) -> dict[str, list[dict]]:
    out = {}
    for p in (LOGS / "cu" / tag).glob("*.json"):
        out[p.stem] = chunks_mod.parse_segments(
            json.loads(p.read_text(encoding="utf-8")), p.stem
        )
    return out


def cmd_cer(args) -> None:
    gts = load_ground_truths()
    segments = _load_segments(args.tag)
    hyps = {vid: "".join(s["transcript"] for s in segs) for vid, segs in segments.items()}
    result = ev.eval_transcripts(gts, hyps)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    (LOGS / f"cer_{args.tag}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _embedder() -> search_index.Embedder:
    return search_index.Embedder(env("AOAI_ENDPOINT"), env("AI_KEY"), env("EMBED_DEPLOYMENT"))


def cmd_index(args) -> None:
    config = args.config
    segments = _load_segments(args.tag or CONFIG_TAGS[config])
    all_chunks = []
    for segs in segments.values():
        all_chunks.extend(chunks_mod.to_chunks(segs, CONFIG_MODES[config]))
    n = search_index.upload_chunks(
        env("SEARCH_ENDPOINT"), env("SEARCH_ADMIN_KEY"),
        f"cuvrag-{config.lower()}", all_chunks, _embedder(),
    )
    print(f"config {config}: uploaded {n}/{len(all_chunks)} chunks")


def cmd_eval(args) -> None:
    gts = load_ground_truths()
    embedder = _embedder()
    results = {}
    for config in args.configs.split(","):
        index_name = f"cuvrag-{config.lower()}"

        profile = CONFIG_PROFILES.get(config)

        def search_fn(q: str, _idx=index_name, _prof=profile):
            return search_index.hybrid_search(
                env("SEARCH_ENDPOINT"), env("SEARCH_ADMIN_KEY"), _idx, q, embedder,
                scoring_profile=_prof,
            )

        results[config] = ev.eval_retrieval(QUERIES, gts, search_fn)
        (LOGS / f"eval_{config}.json").write_text(
            json.dumps(results[config], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(ev.format_table(results))
    for config, res in results.items():
        misses = [r for r in res["per_query"] if not r["hit1"]]
        if misses:
            print(f"\n[{config}] hit@1 を外したクエリ:")
            for r in misses:
                print(f"  {r['qid']} rank={r['rank']} top1={r['top1']}")


def cmd_create_analyzer(args) -> None:
    body = json.loads(Path(args.file).read_text(encoding="utf-8"))
    print(json.dumps(cu().put_analyzer(args.id, body), ensure_ascii=False)[:1500])


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-analyzer")
    p.add_argument("--id", required=True)
    p.add_argument("--file", required=True)
    sub.add_parser("dataset")
    sub.add_parser("defaults")
    sub.add_parser("upload")
    p = sub.add_parser("analyze")
    p.add_argument("--analyzer", default="prebuilt-videoSearch")
    p.add_argument("--tag", default="prebuilt")
    p.add_argument("--only")
    p = sub.add_parser("cer")
    p.add_argument("--tag", default="prebuilt")
    p = sub.add_parser("index")
    p.add_argument("--config", required=True, choices=list(CONFIG_MODES))
    p.add_argument("--tag")
    p = sub.add_parser("eval")
    p.add_argument("--configs", default="A,B")
    args = ap.parse_args()
    globals()[f"cmd_{args.cmd.replace('-', '_')}"](args)


if __name__ == "__main__":
    main()
