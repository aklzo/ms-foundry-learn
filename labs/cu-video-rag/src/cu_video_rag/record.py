"""データセット生成: 台本 TTS → 画面スクリーンショット列 → ffmpeg で mp4 合成。

Playwright の record_video(webm)は録画開始と操作開始の時刻差が測れず、
音声との同期ずれ(〜1 秒)が正解時刻の精度を落とす。そのため **スクリーンショット
+ ffmpeg concat demuxer で各フレームの表示秒数を明示指定**する方式にした。
音声タイムラインと映像タイムラインが完全に一致し、ステップ境界の正解時刻
(ground truth)が決定的になる。CU は約 1 FPS サンプリングなので動きの滑らかさは
評価に影響しない。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import tts
from .pagegen import generate_page, render_page
from .corpus import SCENARIOS
from .scenarios import Scenario

LEAD_SEC = 1.2  # 冒頭の無音(初期画面)
TAIL_SEC = 1.0  # 末尾の無音
OP_SEC = 0.9  # 1 操作あたりの表示秒数


def scenario_fingerprint(scenario: Scenario) -> str:
    """シナリオ定義(台本・画面 op・仕込み値)のハッシュ。定義が変わった動画の再生成判定に使う。"""
    payload = {  # 画面・音声に現れるものだけ(screen_only_facts は注釈なので含めない)
        "title": scenario.title,
        "app": scenario.app_name,
        "steps": [{"narration": st.narration, "ops": st.ops} for st in scenario.steps],
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _make_silence(path: Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tts.SAMPLE_RATE)
        w.writeframes(b"")


def build_video(
    scenario: Scenario, data_dir: Path, *, speech_key: str, region: str, prev_gt: dict | None = None
) -> dict:
    """1 本生成。prev_gt(旧 ground truth)のナレーションが同じステップは TTS wav を再利用する
    (画面の仕込み値だけ変えたときに音声合成の課金と時間を掛けない)。"""
    pages_dir = data_dir / "pages"
    audio_dir = data_dir / "audio" / scenario.id
    frames_dir = data_dir / "audio" / scenario.id / "frames"
    videos_dir = data_dir / "videos"
    for d in (audio_dir, frames_dir, videos_dir):
        d.mkdir(parents=True, exist_ok=True)

    page_path = generate_page(scenario, pages_dir)

    # 1) ナレーション TTS(実測秒数からステップの表示秒数を決める)。
    #    無音ステップ(narration="")はテロップの読み時間で表示秒数を決める
    silence = audio_dir / "silence.wav"
    _make_silence(silence)
    holds: list[float] = []
    wavs: list[Path] = []
    durs: list[float] = []  # ナレーション実時間(ground truth に narration_s として記録)
    prev_steps = (prev_gt or {}).get("steps", [])
    for i, step in enumerate(scenario.steps):
        if step.narration:
            wav = audio_dir / f"step{i}.wav"
            if wav.exists() and i < len(prev_steps) and prev_steps[i].get("narration") == step.narration:
                dur = tts.wav_duration(wav)
            else:
                dur = tts.synthesize(step.narration, wav, key=speech_key, region=region)
            holds.append(max(dur + 0.8, OP_SEC * len(step.ops) + 2.2))
            wavs.append(wav)
            durs.append(dur)
        else:
            durs.append(0.0)
            caption_chars = sum(
                len(op.get("text", "")) for op in step.ops if op.get("op") == "caption"
            )
            holds.append(max(2.5 + caption_chars * 0.18, OP_SEC * len(step.ops) + 2.2))
            wavs.append(silence)

    # 2) 画面フレーム(op 適用ごとに 1 枚。最後のフレームで残り時間を埋める)
    frame_entries: list[tuple[Path, float]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(page_path.resolve().as_uri())
        idx = 0

        def shot(duration: float) -> None:
            nonlocal idx
            f = frames_dir / f"f{idx:04d}.png"
            page.screenshot(path=str(f))
            frame_entries.append((f, duration))
            idx += 1

        shot(LEAD_SEC)
        for step, hold in zip(scenario.steps, holds):
            for j, op in enumerate(step.ops):
                page.evaluate("op => window.applyOp(op)", op)
                page.wait_for_timeout(120)
                last = j == len(step.ops) - 1
                shot(hold - OP_SEC * (len(step.ops) - 1) if last else OP_SEC)
        shot(TAIL_SEC)
        browser.close()

    # 3) 音声(各 wav の後ろに表示秒数まで無音パディング)
    audio_path = audio_dir / "narration.wav"
    clips = [(silence, LEAD_SEC), *zip(wavs, holds), (silence, TAIL_SEC)]
    total_sec = tts.concat_with_padding(clips, audio_path)

    # 4) ffmpeg concat demuxer で合成(最終行のファイル再掲は concat の仕様)
    concat_txt = frames_dir / "frames.txt"
    lines = []
    for f, dur in frame_entries:
        lines.append(f"file '{f.resolve()}'")
        lines.append(f"duration {dur:.3f}")
    lines.append(f"file '{frame_entries[-1][0].resolve()}'")
    concat_txt.write_text("\n".join(lines), encoding="utf-8")

    mp4 = videos_dir / f"{scenario.id}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-i", str(audio_path),
            "-vf", "fps=8,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
            "-shortest", str(mp4),
        ],
        check=True,
    )

    # 5) ground truth(書き起こし正解+ステップ境界時刻)
    t = LEAD_SEC
    steps_meta = []
    for i, (step, hold) in enumerate(zip(scenario.steps, holds)):
        steps_meta.append(
            {"index": i, "narration": step.narration, "start_s": round(t, 2), "end_s": round(t + hold, 2),
             "narration_s": round(durs[i], 2)}
        )
        t += hold
    gt = {
        "video_id": scenario.id,
        "fingerprint": scenario_fingerprint(scenario),
        "title": scenario.title,
        "duration_s": round(total_sec, 2),
        "full_transcript": "".join(s.narration for s in scenario.steps),
        "screen_only_facts": scenario.screen_only_facts,
        "steps": steps_meta,
    }
    gt_dir = data_dir / "ground_truth"
    gt_dir.mkdir(exist_ok=True)
    (gt_dir / f"{scenario.id}.json").write_text(
        json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return gt


def _page_ops(html: str) -> list | None:
    """生成済みページに埋め込まれた window.SCENARIO の steps(op 列)を取り出す。
    テンプレート(CSS 等)だけが変わった場合に動画を作り直さないための比較用。"""
    marker = "window.SCENARIO = "
    i = html.find(marker)
    if i < 0:
        return None
    j = html.find(";\n</script>", i)
    try:
        return json.loads(html[i + len(marker) : j])["steps"]
    except (ValueError, KeyError):
        return None


def build_all(
    data_dir: Path, *, speech_key: str, region: str, only: str | None = None, logs_dir: Path | None = None
) -> None:
    """全シナリオを生成。生成済み(mp4 + ground truth あり、かつ定義が同じ)はスキップ = 再開可能。

    定義が変わった動画(fingerprint 不一致)は作り直し、その動画の古い CU 解析結果
    (logs/cu/*/<id>.json)を削除して analyze で再解析されるようにする。
    fingerprint の無い旧 ground truth は、仕込み値とナレーションが同じなら現行とみなす。
    """
    skipped = 0
    rebuilt = []
    for sc in SCENARIOS:
        if only and sc.id != only:
            continue
        mp4 = data_dir / "videos" / f"{sc.id}.mp4"
        gt_path = data_dir / "ground_truth" / f"{sc.id}.json"
        prev_gt = json.loads(gt_path.read_text(encoding="utf-8")) if gt_path.exists() else None
        if mp4.exists() and prev_gt:
            fp = scenario_fingerprint(sc)
            page_path = data_dir / "pages" / f"{sc.id}.html"
            legacy_same = (
                "fingerprint" not in prev_gt
                and [s["narration"] for s in prev_gt["steps"]] == [s.narration for s in sc.steps]
                and page_path.exists()
                and _page_ops(page_path.read_text(encoding="utf-8")) == [st.ops for st in sc.steps]
            )
            if prev_gt.get("fingerprint") == fp or legacy_same:
                # 動画は現行どおり。注釈(fingerprint / screen_only_facts)だけ同期する
                if prev_gt.get("fingerprint") != fp or prev_gt.get("screen_only_facts") != sc.screen_only_facts:
                    prev_gt["fingerprint"] = fp
                    prev_gt["screen_only_facts"] = sc.screen_only_facts
                    gt_path.write_text(json.dumps(prev_gt, ensure_ascii=False, indent=2), encoding="utf-8")
                skipped += 1
                continue
        if prev_gt:
            shutil.rmtree(data_dir / "audio" / sc.id / "frames", ignore_errors=True)
        gt = build_video(sc, data_dir, speech_key=speech_key, region=region, prev_gt=prev_gt)
        rebuilt.append(sc.id)
        if logs_dir:
            for stale in (logs_dir / "cu").glob(f"*/{sc.id}.json"):
                stale.unlink()
                print(f"  removed stale CU result {stale.relative_to(logs_dir)}")
        print(f"built {sc.id}: {gt['duration_s']}s, {len(gt['steps'])} steps", flush=True)
    if skipped:
        print(f"({skipped} 本は生成済みスキップ)")
    if rebuilt:
        print(f"rebuilt {len(rebuilt)}: {rebuilt}")
