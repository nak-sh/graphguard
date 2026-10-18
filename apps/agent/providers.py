"""Provider-agnostic tool selection and narrative edges.

The deterministic selector is the supported offline path. Anthropic and
OpenAI-compatible selection is intentionally a small HTTP adapter so the core
does not make a vendor SDK part of the graph-analysis source of truth.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx


READ_ONLY_TOOLS = (
    "get_entity_summary",
    "get_neighborhood",
    "find_shared_infrastructure_device",
    "find_shared_infrastructure_ip",
    "trace_money_paths",
    "detect_transfer_cycles",
)


@dataclass(frozen=True)
class ToolChoice:
    name: str
    reason: str


class ToolSelector:
    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self.provider = (provider or os.getenv("GRAPHGUARD_LLM_PROVIDER", "none")).lower()
        self.model = model or os.getenv("GRAPHGUARD_LLM_MODEL", "")
        self.api_key = api_key or os.getenv("GRAPHGUARD_LLM_API_KEY")
        self.base_url = base_url or os.getenv("GRAPHGUARD_LLM_BASE_URL")
        self.timeout_seconds = timeout_seconds

    @property
    def online(self) -> bool:
        return self.provider in {"anthropic", "openai"} and bool(self.api_key and self.model)

    @staticmethod
    def _fallback(visited: Sequence[str]) -> ToolChoice:
        order = list(READ_ONLY_TOOLS)
        for tool in order:
            if tool not in visited:
                return ToolChoice(tool, "deterministic offline playbook")
        return ToolChoice("detect_transfer_cycles", "no new read-only tool remains")

    def choose(self, *, entity_id: str, evidence: Sequence[Mapping[str, Any]], visited: Sequence[str], remaining_steps: int) -> ToolChoice:
        fallback = self._fallback(visited)
        if not self.online or remaining_steps <= 0:
            return fallback
        prompt = {
            "entity_id": entity_id,
            "visited_tools": list(visited),
            "remaining_steps": remaining_steps,
            "evidence_kinds": [item.get("kind") for item in evidence],
            "allowed_tools": list(READ_ONLY_TOOLS),
        }
        try:
            if self.provider == "anthropic":
                payload = {
                    "model": self.model,
                    "max_tokens": 160,
                    "system": "Choose exactly one next read-only GraphGuard tool. Never invent a tool name.",
                    "messages": [{"role": "user", "content": json.dumps(prompt)}],
                    "tools": [{"name": name, "description": name, "input_schema": {"type": "object"}} for name in READ_ONLY_TOOLS],
                }
                headers = {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}
                url = self.base_url or "https://api.anthropic.com/v1/messages"
                response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
                response.raise_for_status()
                data = response.json()
                for block in data.get("content", []):
                    if block.get("type") == "tool_use" and block.get("name") in READ_ONLY_TOOLS:
                        return ToolChoice(block["name"], "LLM structured tool choice")
            else:
                payload = {
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": "Return JSON with one field name containing one allowed GraphGuard read-only tool."},
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "response_format": {"type": "json_object"},
                }
                url = self.base_url or "https://api.openai.com/v1/chat/completions"
                response = httpx.post(url, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=self.timeout_seconds)
                response.raise_for_status()
                content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
                name = json.loads(content).get("name")
                if name in READ_ONLY_TOOLS:
                    return ToolChoice(name, "LLM structured tool choice")
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            # A provider failure must never prevent the offline demo or cause
            # an unvalidated tool to run.
            return ToolChoice(fallback.name, "provider failed; deterministic fallback")
        return fallback


def deterministic_narrative(entity_id: str, score: int, tier: str, evidence: Sequence[Mapping[str, Any]], findings: Sequence[str]) -> str:
    citations = ", ".join(f"[{item.get('id')}]" for item in evidence if item.get("id")) or "[no-evidence]"
    lead = "No action is proposed" if tier == "NO_ACTION" else f"The evidence supports a {tier.replace('_', ' ').lower()} disposition"
    details = " ".join(findings) if findings else "No escalation signal crossed the configured policy threshold."
    return f"Synthetic-data investigation for {entity_id}: score {score}. {lead}. {details} Evidence: {citations}. Findings are leads, not proof."
