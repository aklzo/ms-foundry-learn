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
from cu_video_rag.corpus import FORM_OF_VIDEO, QUERIES, SCENARIOS  # noqa: E402

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
        # prebuilt アナライザーはエイリアス名で解決する(findings 1-1)
        "prebuilt-analyzer-completion-mini": env("COMPLETION_DEPLOYMENT"),
        "prebuilt-analyzer-embedding": env("EMBED_DEPLOYMENT"),
    }
    try:
        print(json.dumps(client.patch_defaults(mapping), ensure_ascii=False))
    except Exception as e:  # GA 版で通らない場合は preview 版で再試行(結果は NOTES に記録)
        print(f"GA version failed: {e}; retrying with 2026-06-01-preview", file=sys.stderr)
        client.api_version = "2026-06-01-preview"
        print(json.dumps(client.patch_defaults(mapping), ensure_ascii=False))
    print(json.dumps(client.get_defaults(), ensure_ascii=False))


def cmd_upload(_args) -> None:
    """mp4 を upload-batch で Blob へ一括アップロードし、コンテナ SAS で URL を組む。"""
    account, key = env("STORAGE_NAME"), env("STORAGE_KEY")
    subprocess.run(
        ["az", "storage", "blob", "upload-batch", "--account-name", account,
         "--account-key", key, "-d", "videos", "-s", str(DATA / "videos"),
         "--pattern", "*.mp4", "--overwrite", "-o", "none"],
        check=True,
    )
    expiry = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%MZ")
    sas = subprocess.run(
        ["az", "storage", "container", "generate-sas", "--account-name", account,
         "--account-key", key, "-n", "videos", "--permissions", "r",
         "--expiry", expiry, "--https-only", "-o", "tsv"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    urls = {
        sc.id: f"https://{account}.blob.core.windows.net/videos/{sc.id}.mp4?{sas}"
        for sc in SCENARIOS
    }
    (DATA / "eval").mkdir(exist_ok=True)
    (DATA / "eval" / "video_urls.json").write_text(json.dumps(urls, indent=2), encoding="utf-8")
    print(f"uploaded + SAS for {len(urls)} videos")


def _analyze_one(client, analyzer: str, vid: str, url: str, out_path: Path) -> str:
    """1 本解析(429 は指数バックオフで最大 5 回リトライ)。"""
    import time as _time

    delay = 30
    for attempt in range(5):
        t0 = datetime.now(timezone.utc)
        try:
            result = client.analyze_url(analyzer, url)
        except RuntimeError as e:
            transient = "RateLimit" in str(e) or "DeploymentIdNotFound" in str(e)
            if transient and attempt < 4:
                _time.sleep(delay)
                delay = min(delay * 2, 240)
                continue
            raise
        sec = (datetime.now(timezone.utc) - t0).total_seconds()
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        n_seg = len(result.get("result", {}).get("contents", []))
        return {"vid": vid, "sec": round(sec, 1), "segments": n_seg, "retries": attempt}
    raise RuntimeError(f"{vid}: retries exhausted")


def cmd_analyze(args) -> None:
    """全動画を並列解析。解析済み(JSON あり)はスキップ = 再開可能。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    client = cu()
    urls = json.loads((DATA / "eval" / "video_urls.json").read_text(encoding="utf-8"))
    out_dir = LOGS / "cu" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = {}
    for vid, url in urls.items():
        if args.only and vid != args.only:
            continue
        out_path = out_dir / f"{vid}.json"
        if out_path.exists() and not args.force:
            continue
        todo[vid] = (url, out_path)
    print(f"analyzing {len(todo)} videos with {args.analyzer} (parallel={args.parallel})", flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futs = {
            pool.submit(_analyze_one, client, args.analyzer, vid, url, out_path): vid
            for vid, (url, out_path) in todo.items()
        }
        timings = []
        for fut in as_completed(futs):
            vid = futs[fut]
            try:
                r = fut.result()
                timings.append(r)
                print(f"  done {r['vid']}: {r['sec']}s, segments={r['segments']}, retries={r['retries']}", flush=True)
            except Exception as e:
                failed.append(vid)
                print(f"  FAILED {vid}: {str(e)[:300]}", flush=True)
    tpath = LOGS / f"timings_{args.tag}.json"
    old_t = json.loads(tpath.read_text(encoding="utf-8")) if tpath.exists() else []
    merged = {t2_["vid"]: t2_ for t2_ in old_t}
    merged.update({t2_["vid"]: t2_ for t2_ in timings})
    tpath.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    if failed:
        print(f"failed: {failed}")
        raise SystemExit(1)


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

        results[config] = ev.eval_retrieval(QUERIES, gts, search_fn, form_of_video=FORM_OF_VIDEO)
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


def cmd_rag_answer(args) -> None:
    """検索 top-3 をコンテキストに回答を生成 → logs/rag_answers_<config>.json"""
    from cu_video_rag import rag_eval

    embedder = _embedder()
    config = args.config
    index_name = f"cuvrag-{config.lower()}"
    profile = CONFIG_PROFILES.get(config)
    out = []
    for i, q in enumerate(QUERIES):
        hits = search_index.hybrid_search(
            env("SEARCH_ENDPOINT"), env("SEARCH_ADMIN_KEY"), index_name, q["text"],
            embedder, top=3, scoring_profile=profile,
        )
        contexts = [
            f"動画『{h['video_id']}』 {h['start_s']:.0f}〜{h['end_s']:.0f}秒:\n{h['content']}"
            for h in hits
        ]
        answer = rag_eval.generate_answer(
            env("AOAI_ENDPOINT"), env("AI_KEY"), env("COMPLETION_DEPLOYMENT"),
            q["text"], contexts,
        )
        out.append({
            "qid": q["qid"], "type": q["type"], "question": q["text"],
            "answer": answer, "contexts": contexts, "reference": q["ref_answer"],
        })
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(QUERIES)}", flush=True)
    (LOGS / f"rag_answers_{config}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"config {config}: {len(out)} answers generated")


def cmd_ragas(args) -> None:
    """生成済み回答を ragas の 5 指標で評価 → logs/ragas_<config>.json"""
    from cu_video_rag import rag_eval

    config = args.config
    samples = json.loads((LOGS / f"rag_answers_{config}.json").read_text(encoding="utf-8"))
    result = rag_eval.run_ragas(
        samples,
        aoai_endpoint=env("AOAI_ENDPOINT"),
        key=env("AI_KEY"),
        judge_deployment=env("JUDGE_DEPLOYMENT"),
        embed_deployment=env("EMBED_DEPLOYMENT"),
    )
    for s, d in zip(samples, result["details"]):
        d["qid"] = s["qid"]
        d["type"] = s["type"]
    (LOGS / f"ragas_{config}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"config {config} (n={result['n']}):")
    for k, v in result["summary"].items():
        print(f"  {k}: {v}")


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
    p.add_argument("--parallel", type=int, default=4)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("cer")
    p.add_argument("--tag", default="prebuilt")
    p = sub.add_parser("index")
    p.add_argument("--config", required=True, choices=list(CONFIG_MODES))
    p.add_argument("--tag")
    p = sub.add_parser("eval")
    p.add_argument("--configs", default="A,B")
    p = sub.add_parser("rag-answer")
    p.add_argument("--config", required=True, choices=list(CONFIG_MODES))
    p = sub.add_parser("ragas")
    p.add_argument("--config", required=True, choices=list(CONFIG_MODES))
    args = ap.parse_args()
    globals()[f"cmd_{args.cmd.replace('-', '_')}"](args)


if __name__ == "__main__":
    main()
