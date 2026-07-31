"""信頼スコアとゲート(元 trust_gated_agent_team ``TrustRegistry`` の移植)。

元はエージェントごとの静的スコア(registry)を閾値と比較して「参加前に
ブロック」していた。移植では **段の出力そのもの**を決定論検査してスコアを
出す — 「このエージェントを信じるか」から「この段の出力を次段に渡してよいか」
への意味づけの移動(README 設計判断)。

- ベーススコアは元の registry に対応(intake 75 / inspection 70)
- 出力の不備(欠落項目・低確信・重大所見)が減点になる
- 階層(gold/silver/bronze/none)と境界値(60/40/20)は元と同一
- 閾値未満はブロックではなく **人間承認キューへのエスカレーション**(hitl.py)
"""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import NOT_SPECIFIED, ExpenseClaim, InspectionReport

INTAKE_BASE_SCORE = 75
INSPECTION_BASE_SCORE = 70
DEFAULT_TRUST_THRESHOLD = 40  # silver 境界(元デモの既定 30 より一段厳しめ)


def score_to_tier(score: int) -> str:
    """元 ``_score_to_tier`` そのまま。"""
    if score >= 60:
        return "gold"
    if score >= 40:
        return "silver"
    if score >= 20:
        return "bronze"
    return "none"


@dataclass(frozen=True)
class StageTrust:
    """段の出力に対する信頼スコア(減点内訳つき)。"""

    stage: str
    base_score: int
    score: int
    tier: str
    deductions: tuple[str, ...]


def _build(stage: str, base: int, deductions: list[tuple[str, int]]) -> StageTrust:
    score = max(0, min(100, base - sum(points for _, points in deductions)))
    return StageTrust(
        stage=stage,
        base_score=base,
        score=score,
        tier=score_to_tier(score),
        deductions=tuple(f"{label} (-{points})" for label, points in deductions),
    )


def score_intake(claim: ExpenseClaim) -> StageTrust:
    """申請段の出力検査: 構造化に必要な事実がどれだけ埋まっているか。"""
    deductions: list[tuple[str, int]] = []
    if claim.amount_usd is None:
        deductions.append(("amount missing", 25))
    if claim.employee_id == NOT_SPECIFIED:
        deductions.append(("employee_id missing", 20))
    if not claim.has_receipt:
        deductions.append(("no receipt", 15))
    if claim.category == "other":
        deductions.append(("category unresolved", 10))
    if claim.missing_or_uncertain:
        points = min(15, 5 * len(claim.missing_or_uncertain))
        deductions.append((f"{len(claim.missing_or_uncertain)} uncertain facts", points))
    return _build("intake", INTAKE_BASE_SCORE, deductions)


def score_inspection(report: InspectionReport) -> StageTrust:
    """検査段の出力検査: 検査自体の確信度と所見の重さ。"""
    deductions: list[tuple[str, int]] = []
    if report.confidence < 0.5:
        deductions.append((f"low confidence {report.confidence:.2f}", 30))
    elif report.confidence < 0.7:
        deductions.append((f"moderate confidence {report.confidence:.2f}", 10))
    criticals = sum(1 for f in report.findings if f.severity == "critical")
    warnings = sum(1 for f in report.findings if f.severity == "warning")
    if criticals:
        deductions.append((f"{criticals} critical findings", min(30, 15 * criticals)))
    if warnings:
        deductions.append((f"{warnings} warning findings", min(15, 5 * warnings)))
    return _build("inspection", INSPECTION_BASE_SCORE, deductions)


@dataclass(frozen=True)
class TrustVerdict:
    trust: StageTrust
    threshold: int
    passed: bool
    reason: str

    @property
    def tag(self) -> str:
        """監査ログの detail 欄(例 ``pass:75`` / ``escalate:15``)。"""
        return f"{'pass' if self.passed else 'escalate'}:{self.trust.score}"


@dataclass(frozen=True)
class TrustGate:
    """閾値ゲート(元 ``TrustRegistry.verify`` に相当)。"""

    threshold: int = DEFAULT_TRUST_THRESHOLD

    def check(self, trust: StageTrust) -> TrustVerdict:
        passed = trust.score >= self.threshold
        if passed:
            reason = f"{trust.stage} trusted: score {trust.score} >= {self.threshold}"
        else:
            detail = "; ".join(trust.deductions) or "no deductions"
            reason = (
                f"{trust.stage} score {trust.score} below threshold {self.threshold} ({detail})"
            )
        return TrustVerdict(trust=trust, threshold=self.threshold, passed=passed, reason=reason)
