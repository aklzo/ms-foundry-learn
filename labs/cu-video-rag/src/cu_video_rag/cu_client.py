"""Content Understanding GA REST クライアント(最小)。

一次情報:
- クイックスタート(REST): https://learn.microsoft.com/azure/ai-services/content-understanding/quickstart/use-rest-api
- GA API バージョン 2025-11-01: https://learn.microsoft.com/azure/ai-services/content-understanding/whats-new
- 事前準備(defaults へのモデルデプロイ紐づけ):
  マネージドモデル容量は GA で廃止 → 自前デプロイ(補完+埋め込み)の紐づけが必須

API 形:
- PATCH {ep}/contentunderstanding/defaults?api-version=...
    {"modelDeployments": {"<モデル名>": "<デプロイ名>", ...}}
- POST {ep}/contentunderstanding/analyzers/{analyzerId}:analyze?api-version=...
    {"inputs": [{"url": "<SAS URL>"}]}  → 202 + Operation-Location
- GET  {ep}/contentunderstanding/analyzerResults/{id}?api-version=...
    status: NotStarted / Running / Succeeded / Failed
- PUT  {ep}/contentunderstanding/analyzers/{id}?api-version=...(カスタムアナライザー作成)
"""

from __future__ import annotations

import time

import httpx

GA_VERSION = "2025-11-01"


class CuClient:
    def __init__(self, endpoint: str, key: str, api_version: str = GA_VERSION):
        self.endpoint = endpoint.rstrip("/")
        self.api_version = api_version
        self.http = httpx.Client(
            headers={"Ocp-Apim-Subscription-Key": key}, timeout=120
        )

    def _url(self, path: str) -> str:
        return f"{self.endpoint}/contentunderstanding/{path}?api-version={self.api_version}"

    def patch_defaults(self, model_deployments: dict[str, str]) -> dict:
        r = self.http.patch(
            self._url("defaults"),
            json={"modelDeployments": model_deployments},
            headers={"Content-Type": "application/merge-patch+json"},
        )
        r.raise_for_status()
        return r.json()

    def get_defaults(self) -> dict:
        r = self.http.get(self._url("defaults"))
        r.raise_for_status()
        return r.json()

    def put_analyzer(self, analyzer_id: str, body: dict) -> dict:
        r = self.http.put(self._url(f"analyzers/{analyzer_id}"), json=body)
        if r.status_code not in (200, 201, 202):
            raise RuntimeError(f"put_analyzer {r.status_code}: {r.text[:2000]}")
        # 作成も LRO(Operation-Location)の場合がある
        op = r.headers.get("Operation-Location")
        if op and r.status_code == 202:
            return self._poll_url(op)
        return r.json()

    def delete_analyzer(self, analyzer_id: str) -> None:
        self.http.delete(self._url(f"analyzers/{analyzer_id}"))

    def analyze_url(self, analyzer_id: str, video_url: str) -> dict:
        """動画 URL を解析し、完了までポーリングして結果 JSON を返す。"""
        r = self.http.post(
            self._url(f"analyzers/{analyzer_id}:analyze"),
            json={"inputs": [{"url": video_url}]},
        )
        if r.status_code != 202:
            raise RuntimeError(f"analyze {r.status_code}: {r.text[:2000]}")
        op = r.headers.get("Operation-Location")
        if not op:
            raise RuntimeError("no Operation-Location header")
        return self._poll_url(op)

    def _poll_url(self, url: str, interval: float = 10, timeout_s: float = 1800) -> dict:
        deadline = time.monotonic() + timeout_s
        while True:
            r = self.http.get(url)
            r.raise_for_status()
            body = r.json()
            status = body.get("status", "")
            if status.lower() == "succeeded":
                return body
            if status.lower() in ("failed", "canceled"):
                raise RuntimeError(f"operation {status}: {str(body)[:2000]}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"polling timed out (last status={status})")
            time.sleep(interval)
