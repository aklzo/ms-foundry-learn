"""LLM 2 段(抽出・分類)のエージェント組み立て。

元アプリの ADK ``LlmAgent`` 2 体に対応する:

- NormalizeClaimNarrative(``output_schema=ClaimNarrative``)→ extractor
- ClassifyClaimTypeAndSeverity(``output_schema=ClaimClassification``)→ classifier

instructions は原文を流用。ADK はセッション state のテンプレート補間
(``{normalized_claim}`` / ``{field_validation}``)で分類器へ前段の結果を
渡していたが、MAF ではワークフローが実行プロンプトに JSON を埋め込む
(workflow.py)。``output_schema`` は MAF のネイティブ構造化出力
``ChatOptions(response_format=...)`` に対応する(research-handoff の型)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .config import FoundrySettings


class SupportsRun(Protocol):
    """ワークフローが必要とする最小面: ``await run(text)`` → ``.text``(と
    構造化出力の ``.value``)を持つ応答。テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


@dataclass
class ClaimIntakeAgents:
    extractor: SupportsRun
    classifier: SupportsRun


#: 元 create_normalizer() の instruction(原文そのまま)。
EXTRACTOR_INSTRUCTIONS = """\
You are the intake specialist for an AI Insurance Claim Intake Agent.

Read the user's messy insurance claim narrative and produce a structured
ClaimNarrative. Preserve facts exactly when possible. Do not invent policy
numbers, contacts, dates, locations, evidence, or dollar amounts.

Extraction rules:
- policyholder_name: claimant or policyholder name, otherwise "not specified".
- policy_number: policy/member number, otherwise "not specified".
- contact_method: phone, email, mailing address, or preferred channel, otherwise "not specified".
- date_of_loss: date or date range of the loss, otherwise "not specified".
- reported_date: date the user says they are reporting the claim, otherwise "not specified".
- loss_location: address, city, intersection, provider, or travel route, otherwise "not specified".
- loss_description: concise factual description of what happened.
- estimated_loss_usd: numeric USD estimate only if supplied.
- injuries_or_safety_concerns: include injuries, urgent medical care, unsafe housing, electrical hazards, sewage, mold, or no place to live.
- evidence_available: photos, video, receipts, report numbers, estimates, bills, carrier notices, EOBs, proof of payment, serial numbers, or similar evidence already mentioned.
- documents_mentioned: specific documents mentioned whether available or missing.
- missing_or_uncertain_facts: key facts the narrative says are unknown, vague, or incomplete.

This is an intake normalization step only. Do not confirm coverage or payment.
"""

#: 元 create_classifier() の instruction。ADK の state 補間部分
#: ({normalized_claim} / {field_validation})は実行プロンプト側へ移した。
CLASSIFIER_INSTRUCTIONS = """\
Classify the normalized insurance claim you are given for intake routing.

Supported claim types:
- home_water_damage
- auto_collision
- theft_property_loss
- health_medical_reimbursement
- travel_delay_cancellation
- other

Severity rubric:
- low: complete, low-dollar, no injury/safety issue, routine documentation.
- medium: missing documents or moderate complexity.
- high: high estimated loss, unclear liability, missing core facts, or specialized handling likely.
- urgent: injury, unsafe living condition, emergency medical/safety concern, or time-sensitive mitigation.

Return only the structured ClaimClassification. This is classification, not a
coverage decision.
"""


def build_chat_client(settings: FoundrySettings) -> Any:
    """共有基盤の OpenAI v1 互換エンドポイント+API キーのチャットクライアント。"""
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(chat_client: Any) -> ClaimIntakeAgents:
    """抽出・分類の 2 エージェントをネイティブ構造化出力付きで組み立てる。"""
    from agent_framework import Agent, ChatOptions

    from .schemas import ClaimClassification, ClaimNarrative

    return ClaimIntakeAgents(
        extractor=Agent(
            chat_client,
            instructions=EXTRACTOR_INSTRUCTIONS,
            name="claim_narrative_extractor",
            default_options=ChatOptions(response_format=ClaimNarrative),
        ),
        classifier=Agent(
            chat_client,
            instructions=CLASSIFIER_INSTRUCTIONS,
            name="claim_type_classifier",
            default_options=ChatOptions(response_format=ClaimClassification),
        ),
    )
