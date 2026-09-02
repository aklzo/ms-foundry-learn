"""検証パイプライン CLI。

  uv run python scripts/run_pipeline.py dataset            # 動画データセット生成(TTS+録画+合成。定義変更分だけ作り直す)
  uv run python scripts/run_pipeline.py defaults           # CU defaults にモデルデプロイ紐づけ
  uv run python scripts/run_pipeline.py upload             # 動画を Blob へ+SAS URL 生成
  uv run python scripts/run_pipeline.py analyze [--analyzer prebuilt-videoSearch --tag prebuilt]
  uv run python scripts/run_pipeline.py cer --tag prebuilt # 書き起こし CER
  uv run python scripts/run_pipeline.py index --config A   # A0/A/B/C/D
  uv run python scripts/run_pipeline.py eval --configs A0,A,B,C,D  # 検索評価(hit@k/MRR/ans@k + 構成間の信頼区間)
  uv run python scripts/run_pipeline.py rag-answer --config C     # 回答生成(U タイプ含む)
  uv run python scripts/run_pipeline.py ragas --config C          # ragas 5 指標(U タイプ除外)
  uv run python scripts/run_pipeline.py offline-metrics    # Azure 不要: セグメント境界一致・転記率・棄権率・usage/コスト
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
from cu_video_rag import cost as cost_mod  # noqa: E402
from cu_video_rag import evaluate as ev  # noqa: E402
from cu_video_rag import record, search_index  # noqa: E402
from cu_video_rag.corpus import ALL_QUERIES, FORM_OF_VIDEO, QUERIES, SCENARIOS, fact_positions, validate  # noqa: E402
from cu_video_rag.cu_client import CuClient  # noqa: E402

DATA = ROOT / "data"
LOGS = ROOT / "logs"

# A0 は書き起こしの再配分なし(CU の割り当てのまま)。findings 1-10 の影響測定用
CONFIG_MODES = {"A0": "transcript_raw", "A": "transcript", "B": "full", "C": "full", "D": "split"}
CONFIG_TAGS = {"A0": "prebuilt", "A": "prebuilt", "B": "prebuilt", "C": "custom", "D": "custom"}
CONFIG_PROFILES = {"D": "boost-screen"}  # D は screen_texts 重み付けプロファイルで検索
COMPARE_PAIRS = [("A", "C"), ("B", "C"), ("C", "D"), ("A0", "A")]


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"missing env: {name} (scripts/setup_azure.sh を先に実行)")
    return v


def cu() -> CuClient:
    return CuClient(env("FOUNDRY_ENDPOINT"), env("AI_KEY"))


def load_ground_truths() -> dict[str, dict]:
    """ground truth を読む。旧形式(narration_s なし)はローカルの TTS wav から発話秒数を補う。"""
    from cu_video_rag.tts import wav_duration

    gts = {}
    for p in (DATA / "ground_truth").glob("*.json"):
        gt = json.loads(p.read_text(encoding="utf-8"))
        for st in gt["steps"]:
            if "narration_s" not in st and st.get("narration"):
                wav = DATA / "audio" / p.stem / f"step{st['index']}.wav"
                if wav.exists():
                    st["narration_s"] = round(wav_duration(wav), 2)
        gts[p.stem] = gt
    return gts


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _add_usage(name: str, entry: dict) -> None:
    """検索・回答生成・判定のトークン使用量を logs/usage_other.json に追記(コスト集計用)。"""
    path = LOGS / "usage_other.json"
    cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cur[name] = {**entry, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _write_json(path, cur)


def cmd_dataset(_args) -> None:
    problems = validate()
    if problems:
        raise SystemExit("dataset validation failed:\n  " + "\n  ".join(problems))
    record.build_all(DATA, speech_key=env("AI_KEY"), region=env("REGION"), logs_dir=LOGS)


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
    _write_json(DATA / "eval" / "video_urls.json", urls)
    print(f"uploaded + SAS for {len(urls)} videos")


def _analyze_one(client, analyzer: str, vid: str, url: str, out_path: Path) -> dict:
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
        _write_json(out_path, result)
        n_seg = len(result.get("result", {}).get("contents", []))
        return {"vid": vid, "sec": round(sec, 1), "segments": n_seg, "retries": attempt,
                "usage": result.get("usage")}
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
    _write_json(tpath, list(merged.values()))
    if failed:
        print(f"failed: {failed}")
        raise SystemExit(1)


def _load_raw(tag: str) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (LOGS / "cu" / tag).glob("*.json")}


def _load_segments(tag: str) -> dict[str, list[dict]]:
    return {vid: chunks_mod.parse_segments(raw, vid) for vid, raw in _load_raw(tag).items()}


def cmd_cer(args) -> None:
    gts = load_ground_truths()
    hyps = {vid: chunks_mod.full_transcript(raw) for vid, raw in _load_raw(args.tag).items()}
    result = ev.eval_transcripts(gts, hyps)
    print(json.dumps({k: v for k, v in result.items() if k != "per_video"}, ensure_ascii=False))
    if result["missing"]:
        print(f"WARNING: CU 結果が無い動画 {len(result['missing'])} 本を CER から除外: {result['missing']}")
    _write_json(LOGS / f"cer_{args.tag}.json", result)


def _embedder() -> search_index.Embedder:
    return search_index.Embedder(env("AOAI_ENDPOINT"), env("AI_KEY"), env("EMBED_DEPLOYMENT"))


def cmd_index(args) -> None:
    config = args.config
    segments = _load_segments(args.tag or CONFIG_TAGS[config])
    all_chunks = []
    for segs in segments.values():
        all_chunks.extend(chunks_mod.to_chunks(segs, CONFIG_MODES[config]))
    emb = _embedder()
    n = search_index.upload_chunks(
        env("SEARCH_ENDPOINT"), env("SEARCH_ADMIN_KEY"),
        f"cuvrag-{config.lower()}", all_chunks, emb,
    )
    _add_usage(f"index_{config}", {"chunks": len(all_chunks), "embedding_tokens": emb.total_tokens})
    print(f"config {config}: uploaded {n}/{len(all_chunks)} chunks (embedding tokens {emb.total_tokens})")


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
        _write_json(LOGS / f"eval_{config}.json", results[config])
    _add_usage("eval_queries", {"configs": list(results), "embedding_tokens": embedder.total_tokens})
    print(ev.format_table(results))
    # 構成間差の信頼区間(対応ありブートストラップ)。評価済みの構成があるペアだけ計算
    loaded = {c: results.get(c) for c in set(sum(COMPARE_PAIRS, ()))}
    for c in loaded:
        p = LOGS / f"eval_{c}.json"
        if loaded[c] is None and p.exists():
            loaded[c] = json.loads(p.read_text(encoding="utf-8"))
    compare = {f"{a}->{b}": ev.compare_configs(loaded[a], loaded[b]) for a, b in COMPARE_PAIRS if loaded.get(a) and loaded.get(b)}
    _write_json(LOGS / "eval_compare.json", compare)
    for pair, metrics in compare.items():
        sig = {m: f"{v['diff']:+.3f} [{v['ci95'][0]:+.3f},{v['ci95'][1]:+.3f}]{'*' if v['significant'] else ''}" for m, v in metrics.items() if v}
        print(f"[{pair}] {sig}")
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
    """検索 top-3 をコンテキストに回答を生成 → logs/rag_answers_<config>.json(U タイプ含む)"""
    from cu_video_rag import rag_eval

    embedder = _embedder()
    config = args.config
    index_name = f"cuvrag-{config.lower()}"
    profile = CONFIG_PROFILES.get(config)
    out = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for i, q in enumerate(ALL_QUERIES):
        hits = search_index.hybrid_search(
            env("SEARCH_ENDPOINT"), env("SEARCH_ADMIN_KEY"), index_name, q["text"],
            embedder, top=3, scoring_profile=profile,
        )
        contexts = [
            f"動画『{h['video_id']}』 {h['start_s']:.0f}〜{h['end_s']:.0f}秒:\n{h['content']}"
            for h in hits
        ]
        answer, u = rag_eval.generate_answer(
            env("AOAI_ENDPOINT"), env("AI_KEY"), env("COMPLETION_DEPLOYMENT"),
            q["text"], contexts,
        )
        usage["prompt_tokens"] += u["prompt_tokens"]
        usage["completion_tokens"] += u["completion_tokens"]
        out.append({
            "qid": q["qid"], "type": q["type"], "question": q["text"], "video": q.get("video"),
            "answer": answer, "contexts": contexts, "reference": q["ref_answer"],
        })
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(ALL_QUERIES)}", flush=True)
    _write_json(LOGS / f"rag_answers_{config}.json", out)
    _add_usage(f"rag_answer_{config}", {"n": len(out), **usage, "embedding_tokens": embedder.total_tokens})
    print(f"config {config}: {len(out)} answers generated (tokens {usage})")


def cmd_ragas(args) -> None:
    """生成済み回答を ragas の 5 指標で評価 → logs/ragas_<config>.json(U タイプは対象外)"""
    from cu_video_rag import rag_eval

    config = args.config
    samples = [s for s in json.loads((LOGS / f"rag_answers_{config}.json").read_text(encoding="utf-8")) if s["type"] != "U"]
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
    _write_json(LOGS / f"ragas_{config}.json", result)
    _add_usage(f"ragas_{config}", {"n": result["n"], **result.get("judge_usage", {})})
    print(f"config {config} (n={result['n']}):")
    for k, v in result["summary"].items():
        print(f"  {k}: {v}")


def cmd_offline_metrics(_args) -> None:
    """Azure を使わずに logs/ から算出する指標(再現・レポート生成に使う)。"""
    gts = load_ground_truths()
    segments = {tag: _load_segments(tag) for tag in ("prebuilt", "custom") if (LOGS / "cu" / tag).exists()}

    # 1) セグメント境界の一致(正解ステップ境界 ±2 秒)
    seg = {tag: ev.eval_segmentation(gts, segs, form_of_video=FORM_OF_VIDEO) for tag, segs in segments.items()}
    # 同一音声の 2 系統書き起こしで CER が食い違う動画 = 実行依存の発話欠落(findings 1-13)
    cer_p, cer_c = LOGS / "cer_prebuilt.json", LOGS / "cer_custom.json"
    if cer_p.exists() and cer_c.exists():
        seg["transcript_divergence"] = ev.transcript_divergence(
            json.loads(cer_p.read_text(encoding="utf-8")), json.loads(cer_c.read_text(encoding="utf-8")),
            seg.get("prebuilt"), seg.get("custom"),
        )
        print("transcript divergence (prebuilt vs custom, |ΔCER|>5pt):", seg["transcript_divergence"])
    _write_json(LOGS / "segmentation.json", seg)
    for tag in segments:
        print(f"segmentation[{tag}]: {seg[tag]['overall']}")

    # 2) 画面のみ情報の転記率(検索を介さない直接測定。表示ステップの時刻は ground truth から)
    facts = []
    for f in fact_positions():
        gt = gts.get(f["video"])
        if not gt or not f["steps"]:
            continue
        steps = [gt["steps"][i] for i in f["steps"]]
        facts.append({**f, "start_s": min(s["start_s"] for s in steps), "end_s": max(s["end_s"] for s in steps)})
    fact = {tag: ev.eval_fact_transcription(facts, segs) for tag, segs in segments.items()}
    _write_json(LOGS / "fact_transcription.json", fact)
    for tag, r in fact.items():
        print(f"fact_transcription[{tag}]: {r['overall']} missing={len(r['missing'])}")

    # 3) 棄権率(根拠なし質問 U と正解あり質問)
    abst = {}
    for config in ("A", "C"):
        p = LOGS / f"rag_answers_{config}.json"
        if p.exists():
            abst[config] = ev.eval_abstention(json.loads(p.read_text(encoding="utf-8")))
            print(f"abstention[{config}]: {abst[config]['unanswerable']} / answerable {abst[config]['answerable']}")
    _write_json(LOGS / "abstention.json", abst)

    # 4) usage とコスト概算(CU の usage + 検索・回答生成・判定のトークン)
    usage = {tag: cost_mod.summarize_usage(LOGS / "cu" / tag) for tag in segments}
    est = {tag: cost_mod.estimate_cu_cost(u) for tag, u in usage.items()}
    other_p = LOGS / "usage_other.json"
    other = json.loads(other_p.read_text(encoding="utf-8")) if other_p.exists() else {}
    prices = cost_mod.PRICES_USD
    other_cost = {}
    for name, u in other.items():
        c = u.get("embedding_tokens", 0) / 1e6 * prices["text-embedding-3-small_per_1m"]
        if name.startswith("rag_answer"):
            c += u.get("prompt_tokens", 0) / 1e6 * prices["gpt-5.4-mini_input_per_1m"]
            c += u.get("completion_tokens", 0) / 1e6 * prices["gpt-5.4-mini_output_per_1m"]
        if name.startswith("ragas"):
            c += u.get("prompt_tokens", 0) / 1e6 * prices["gpt-4.1-mini_input_per_1m"]
            c += u.get("completion_tokens", 0) / 1e6 * prices["gpt-4.1-mini_output_per_1m"]
        other_cost[name] = round(c, 4)
    summary = {
        "prices_usd": prices,
        "prices_source": cost_mod.PRICES_SOURCE,
        "cu_usage": usage,
        "cu_cost_usd": est,
        "other_usage": other,
        "other_cost_usd": other_cost,
        "total_variable_usd": round(sum(e["total"] for e in est.values()) + sum(other_cost.values()), 4),
    }
    _write_json(LOGS / "usage_cost.json", summary)
    print("cu usage:", json.dumps(usage, ensure_ascii=False))
    print("cu cost (USD):", json.dumps(est))
    print("other cost (USD):", json.dumps(other_cost), "total variable:", summary["total_variable_usd"])


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
    p.add_argument("--configs", default="A0,A,B,C,D")
    p = sub.add_parser("rag-answer")
    p.add_argument("--config", required=True, choices=list(CONFIG_MODES))
    p = sub.add_parser("ragas")
    p.add_argument("--config", required=True, choices=list(CONFIG_MODES))
    sub.add_parser("offline-metrics")
    args = ap.parse_args()
    globals()[f"cmd_{args.cmd.replace('-', '_')}"](args)


if __name__ == "__main__":
    main()
