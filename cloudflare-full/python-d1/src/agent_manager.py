"""Natural-language router for the web app's unified assistant entry."""

from __future__ import annotations

import json
import re
from typing import Any

from bookkeeping.natural_language import OpenAICompatibleClient


_ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {
            "type": "string",
            "enum": ["chat", "ledger_query", "bookkeeping", "food_health"],
        },
        "reply": {"type": "string"},
    },
    "required": ["route", "reply"],
    "additionalProperties": False,
}


def _parse_route(raw: str) -> dict[str, str]:
    value = str(raw or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            route = str(parsed.get("route", "")).strip()
            if route in {"chat", "ledger_query", "bookkeeping", "food_health"}:
                return {"route": route, "reply": str(parsed.get("reply", "")).strip()}
    raise ValueError("助手暂时没能判断该使用哪项能力，请重试或换种说法。")


def route_assistant_turn(
    client_config: dict[str, Any],
    text: str,
    language: str,
    history: list[dict[str, Any]],
    images: list[Any],
    *,
    opener: Any,
) -> dict[str, Any]:
    """Choose a specialist or answer ordinary chat using the configured model.

    The router receives the current request and a short conversation window,
    never a full ledger export. Ledger facts are retrieved separately only
    after the model selects the read-only query path.
    """
    language = language if language in {"zh-CN", "ja-JP", "en-US"} else "zh-CN"
    language_name = {"zh-CN": "简体中文", "ja-JP": "日本語", "en-US": "English"}[language]
    client = OpenAICompatibleClient(
        str(client_config.get("api_key", "")),
        api_url=str(client_config["api_url"]),
        model=str(client_config["model"]),
        thinking_enabled=client_config.get("thinking_enabled", False),
        reasoning_effort=str(client_config.get("reasoning_effort", "low")),
        timeout=float(client_config.get("timeout", 90)),
        opener=opener,
    )
    recent = []
    for item in history[-8:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = str(item.get("text", "")).strip()
        if content:
            recent.append({
                "role": item["role"],
                "text": content[:1600],
                "route": str(item.get("route", ""))[:24],
            })
    payload = {
        "recent_messages": recent,
        "current_message": str(text or "")[:24000],
        "has_images": bool(images),
    }
    system = (
        "你是家庭记账软件里的总助手。你可以自然聊天，并按需调用现有专用 Agent。"
        "你只负责选择路由；账本查询、记账与饮食专用回复由对应 Agent 完成。"
        "route=ledger_query：用户想了解自己已经记录的流水、余额、预算、收入支出、趋势，"
        "或要根据账本制定建议/计划。只要回答依赖用户账本数据，就选它。"
        "route=bookkeeping：用户要新增、修改、删除或核对账目、余额、账户，或要识别并记录小票/消费。"
        "写入时会交给现有记账 Agent，由它继续追问必要信息并按现有流程同步。"
        "route=food_health：用户想记录饮食、查询饮食历史或咨询饮食健康。"
        "route=chat：问候、闲聊、一般知识、功能介绍，或无需读取账本的其他话题。"
        "不要因为用户没说‘查询’‘记账’等固定关键词就拒绝；要结合上下文理解口语、简称和省略表达。"
        "当前消息是路由判断的首要依据；recent_messages 只用于判断当前消息是否明确在回答上一条追问或指代其中的内容。"
        "只有当前消息明显是‘是/不是/用这个/刚才那笔/按你说的’等承接语，且上一轮只有一个明确待答事项时，才沿用上一条专用 Agent 的 route。"
        "如果当前消息提出了新的商品、金额、币种、账户、日期或新问题，就按当前消息重新判断；不得从旧对话补入金额、币种、商品、账户、日期或未完成操作。"
        "用户开启新对话后，旧对话中的待确认记账意图不再有效。网络或汇率失败后，也不能把之后的新记账请求当成重试，除非用户明确说要重试刚才那笔。"
        "若 route 为 chat，请直接、友好地回答当前问题；不要解释路由，不要声称已经读取账本。"
        "若 route 为专用 Agent，reply 留空。不要虚构账本数据，不要替专用 Agent 承诺操作结果。"
        f"使用{language_name}。只返回符合JSON Schema的对象。"
    )
    user_message: dict[str, Any] = {
        "role": "user",
        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }
    if images:
        user_message["images"] = images
    raw = client.complete(
        [{"role": "system", "content": system}, user_message],
        response_schema=_ROUTE_SCHEMA,
        max_tokens=1000,
        structured_output=True,
    )
    result = _parse_route(raw)
    if result["route"] == "chat" and not result["reply"]:
        result["reply"] = {
            "zh-CN": "我在。你可以直接聊天、问账本里的收支和余额，也可以让我帮你记账。",
            "ja-JP": "はい、います。気軽に話しかけてください。台帳の収支や残高の確認、記帳もできます。",
            "en-US": "I’m here. Chat with me, ask about your ledger, or tell me what you’d like to record.",
        }[language]
    result["usage"] = client.usage_snapshot()
    return result
