"""ハッシュ連鎖監査ログ(元 trust_gated_agent_team ``AuditTrail`` の移植)。

各エントリは自身の全フィールド+直前エントリのハッシュから SHA-256 を計算する。
どこか 1 件でも改変されると、その entry_hash 再計算が一致しなくなるか、後続の
previous_hash 連鎖が破れる — 改ざん検知(tamper-evident)。

元との差分:
- ``trust_score: int`` フィールドを汎用の ``detail: str`` に置換(ポリシー判定
  ``deny:AMT-001`` と信頼ゲート ``pass:75`` の両方を同じ連鎖に載せるため)
- 検証をモジュール関数 ``verify_entries``(dict の列に対して動く)に分離し、
  エクスポート済み JSON を単体で(AuditTrail インスタンス無しで)検証できる
- 生の入出力は保存せずハッシュのみ(元と同じ)。内容の追跡はトレース
  (App Insights)側の仕事で、監査連鎖は「順序と非改ざんの証明」に徹する
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass

GENESIS_HASH = "0" * 64

_CHAIN_FIELDS = (
    "sequence",
    "timestamp",
    "actor",
    "action",
    "input_hash",
    "output_hash",
    "detail",
    "previous_hash",
)


def sha256_text(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _chain_data(entry: Mapping[str, object]) -> str:
    """entry_hash の入力文字列(元実装と同じ「全フィールドの : 連結」方式)。"""
    return ":".join(str(entry[field]) for field in _CHAIN_FIELDS)


@dataclass(frozen=True)
class AuditEntry:
    """改ざん検知連鎖の 1 エントリ(イミュータブル)。"""

    sequence: int
    timestamp: float
    actor: str
    action: str
    input_hash: str
    output_hash: str
    detail: str
    previous_hash: str
    entry_hash: str


def verify_entries(entries: Sequence[Mapping[str, object]]) -> tuple[bool, str | None]:
    """エントリ列(dict / AuditEntry.asdict どちらでも)の連鎖整合性を検証する。

    エクスポート済み JSON を ``json.loads`` した列をそのまま渡せる —
    検証に必要なのは SHA-256 だけで、本モジュールの実装にも依存しない。
    """
    previous = GENESIS_HASH
    for i, entry in enumerate(entries):
        if entry["sequence"] != i:
            return False, f"entry {i}: sequence mismatch ({entry['sequence']})"
        if entry["previous_hash"] != previous:
            return False, f"entry {i}: previous_hash mismatch"
        if sha256_text(_chain_data(entry)) != entry["entry_hash"]:
            return False, f"entry {i}: entry_hash mismatch"
        previous = str(entry["entry_hash"])
    return True, None


class AuditTrail:
    """ハッシュ連鎖の監査ログ。``time_fn`` 注入でテストは決定論になる。"""

    def __init__(self, time_fn: Callable[[], float] = time.time) -> None:
        self._entries: list[AuditEntry] = []
        self._time_fn = time_fn

    def record(
        self,
        *,
        actor: str,
        action: str,
        input_text: str,
        output_text: str,
        detail: str = "",
    ) -> AuditEntry:
        sequence = len(self._entries)
        previous_hash = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
        fields = {
            "sequence": sequence,
            "timestamp": self._time_fn(),
            "actor": actor,
            "action": action,
            "input_hash": sha256_text(input_text),
            "output_hash": sha256_text(output_text),
            "detail": detail,
            "previous_hash": previous_hash,
        }
        entry = AuditEntry(**fields, entry_hash=sha256_text(_chain_data(fields)))
        self._entries.append(entry)
        return entry

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def verify_chain(self) -> tuple[bool, str | None]:
        return verify_entries([asdict(e) for e in self._entries])

    def to_json(self) -> str:
        """独立検証可能な JSON(``verify_entries(json.loads(...))`` が通る形)。"""
        return json.dumps([asdict(e) for e in self._entries], indent=2)


def load_entries(json_text: str) -> list[dict[str, object]]:
    entries = json.loads(json_text)
    if not isinstance(entries, list):
        raise TypeError("audit export must be a JSON list")
    return entries
