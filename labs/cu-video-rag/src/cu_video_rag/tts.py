"""Azure Speech TTS(ja-JP)でナレーション wav を生成する。

- AIServices(Foundry)リソースはマルチサービスなので、リージョンの Speech
  エンドポイント+リソースキーで TTS が使える(個別 Speech リソース不要)
- 出力は riff-24khz-16bit-mono-pcm(wave モジュールでそのまま連結できる形式)
- 参考: https://learn.microsoft.com/azure/ai-services/speech-service/rest-text-to-speech
"""

from __future__ import annotations

import wave
from pathlib import Path
from xml.sax.saxutils import escape

import httpx

VOICE = "ja-JP-NanamiNeural"
FORMAT = "riff-24khz-16bit-mono-pcm"
SAMPLE_RATE = 24000


def synthesize(text: str, out_path: Path, *, key: str, region: str = "japaneast") -> float:
    """text を wav に合成して秒数を返す。"""
    ssml = (
        '<speak version="1.0" xml:lang="ja-JP">'
        f'<voice name="{VOICE}">{escape(text)}</voice></speak>'  # & < > を SSML でエスケープ
    )
    resp = httpx.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        content=ssml.encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": FORMAT,
            "User-Agent": "cu-video-rag",
        },
        timeout=60,
    )
    resp.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    return wav_duration(out_path)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def concat_with_padding(clips: list[tuple[Path, float]], out_path: Path) -> float:
    """(wav, そのステップの表示秒数) のリストを、各 wav の後ろに無音を足して 1 本に連結。

    表示秒数 >= wav 秒数 が前提(record.py 側で保証)。返り値は合計秒数。
    """
    total_frames = 0
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for clip, hold_sec in clips:
            with wave.open(str(clip), "rb") as w:
                frames = w.readframes(w.getnframes())
                out.writeframes(frames)
                n = w.getnframes()
            pad = int(hold_sec * SAMPLE_RATE) - n
            if pad > 0:
                out.writeframes(b"\x00\x00" * pad)
                n += pad
            total_frames += n
    return total_frames / SAMPLE_RATE
