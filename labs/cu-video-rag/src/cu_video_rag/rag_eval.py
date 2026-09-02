"""RAG end-to-end 評価: 回答生成 + ragas(業界標準の RAG 評価ライブラリ)。

- 回答生成: ハイブリッド検索 top-3 をコンテキストに gpt-5.4-mini で日本語回答を生成
  (コンテキスト外のことは答えない指示。実サービスの回答段を模す)
- 評価: ragas 0.4 系の 5 指標(LLM-as-a-judge は gpt-4.1-mini、温度 0)
    faithfulness          回答がコンテキストに忠実か(捏造がないか)
    answer_relevancy      回答が質問に answering しているか
    context_precision     取得コンテキストの上位が正解に関連しているか
    context_recall        参照回答の根拠がコンテキストで網羅されているか
    answer_correctness    参照回答と意味的に一致するか
  参考: https://docs.ragas.io/en/stable/concepts/metrics/
"""

from __future__ import annotations

import httpx

ANSWER_PROMPT = """あなたは社内 IT ヘルプデスクのアシスタントです。
以下の「研修動画からの抜粋」だけを根拠に、質問に日本語で簡潔に答えてください。
抜粋に根拠がない場合は「提供された情報からは分かりません」と答えてください。

# 研修動画からの抜粋
{contexts}

# 質問
{question}
"""


def generate_answer(
    aoai_endpoint: str, key: str, deployment: str, question: str, contexts: list[str]
) -> tuple[str, dict]:
    """→ (回答, usage{prompt_tokens, completion_tokens})。usage はコスト集計用。"""
    ctx = "\n\n".join(f"[抜粋 {i + 1}]\n{c}" for i, c in enumerate(contexts))
    r = httpx.post(
        f"{aoai_endpoint.rstrip('/')}/openai/deployments/{deployment}"
        "/chat/completions?api-version=2024-10-21",
        headers={"api-key": key},
        json={
            "messages": [
                {"role": "user", "content": ANSWER_PROMPT.format(contexts=ctx, question=question)}
            ],
            "max_completion_tokens": 2000,
        },
        timeout=120,
    )
    r.raise_for_status()
    body = r.json()
    usage = body.get("usage") or {}
    return body["choices"][0]["message"]["content"] or "", {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    }


def run_ragas(
    samples: list[dict],
    *,
    aoai_endpoint: str,
    key: str,
    judge_deployment: str,
    embed_deployment: str,
) -> dict:
    """samples: [{question, answer, contexts, reference}] → 指標ごとの平均と明細。"""
    from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics._answer_correctness import AnswerCorrectness
    from ragas.metrics._answer_relevance import ResponseRelevancy
    from ragas.metrics._context_precision import LLMContextPrecisionWithReference
    from ragas.metrics._context_recall import LLMContextRecall
    from ragas.metrics._faithfulness import Faithfulness

    llm = LangchainLLMWrapper(
        AzureChatOpenAI(
            azure_endpoint=aoai_endpoint,
            api_key=key,
            azure_deployment=judge_deployment,
            api_version="2024-10-21",
            temperature=0,
        )
    )
    emb = LangchainEmbeddingsWrapper(
        AzureOpenAIEmbeddings(
            azure_endpoint=aoai_endpoint,
            api_key=key,
            azure_deployment=embed_deployment,
            api_version="2024-10-21",
        )
    )
    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=s["question"],
                response=s["answer"],
                retrieved_contexts=s["contexts"],
                reference=s["reference"],
            )
            for s in samples
        ]
    )
    metrics = [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithReference(),
        LLMContextRecall(),
        AnswerCorrectness(),
    ]
    from langchain_community.callbacks.manager import get_openai_callback

    with get_openai_callback() as cb:  # 判定 LLM のトークン使用量(コスト集計用)
        result = evaluate(dataset, metrics=metrics, llm=llm, embeddings=emb, show_progress=True)
    df = result.to_pandas()
    metric_cols = [c for c in df.columns if c not in ("user_input", "response", "retrieved_contexts", "reference")]
    summary = {c: round(float(df[c].mean()), 4) for c in metric_cols}
    details = df[metric_cols].round(4).to_dict(orient="records")
    usage = {"prompt_tokens": cb.prompt_tokens, "completion_tokens": cb.completion_tokens, "requests": cb.successful_requests}
    return {"summary": summary, "n": len(df), "details": details, "judge_usage": usage}
