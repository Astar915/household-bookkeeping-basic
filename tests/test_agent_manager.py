from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bookkeeping.agent_manager import _parse_route
from bookkeeping.request_worker import _run_smart_assistant_turn


class AgentManagerTests(unittest.TestCase):
    def test_route_parser_accepts_supported_agent_and_rejects_unknown_route(self) -> None:
        self.assertEqual(_parse_route('{"route":"ledger_query","reply":""}')['route'], "ledger_query")
        with self.assertRaises(ValueError):
            _parse_route('{"route":"delete_everything","reply":""}')

    def test_chat_route_keeps_route_tagged_history_and_does_not_touch_ledger(self) -> None:
        database = SimpleNamespace()
        with patch(
            "bookkeeping.agent_manager.route_assistant_turn",
            return_value={"route": "chat", "reply": "你好", "usage": {"prompt_tokens": 2}},
        ):
            answer, history, pending, usage = _run_smart_assistant_turn(
                database,
                Path("unused.sqlite3"),
                {"api_url": "https://example.invalid/v1", "model": "router"},
                "你好",
                [], None, [], "", [], "zh-CN", opener=object(), time_zone="Asia/Tokyo",
            )
        self.assertEqual(answer, "你好")
        self.assertIsNone(pending)
        self.assertEqual([item["route"] for item in history], ["chat", "chat"])
        self.assertEqual(usage["_cost_breakdown"][0]["model"], "router")

    def test_query_route_receives_only_its_own_context(self) -> None:
        database = SimpleNamespace(get_billing_cycle_start_day=lambda: 15)
        old_query = {"period": "last_month"}
        history = [
            {"role": "user", "content": "另一笔记账", "route": "bookkeeping"},
            {"role": "user", "content": "上月支出", "route": "ledger_query"},
            {"role": "assistant", "content": "上一月结果", "route": "ledger_query", "query_context": old_query},
        ]
        with (
            patch(
                "bookkeeping.agent_manager.route_assistant_turn",
                return_value={"route": "ledger_query", "reply": "", "usage": None},
            ),
            patch(
                "bookkeeping.ledger_query.run_ledger_query",
                return_value={"answer": "本月消费 1000", "context": {"period": "this_month"}, "usage": None},
            ) as query,
        ):
            answer, result_history, pending, _usage = _run_smart_assistant_turn(
                database,
                Path("readonly.sqlite3"),
                {"api_url": "https://example.invalid/v1", "model": "router"},
                "那这个月呢",
                history,
                None,
                [],
                "",
                [],
                "zh-CN",
                opener=object(),
                time_zone="Asia/Tokyo",
            )
        self.assertEqual(answer, "本月消费 1000")
        self.assertIsNone(pending)
        args = query.call_args.kwargs
        self.assertEqual(args["conversation"], {"queryContext": old_query})
        self.assertEqual(args["history"], [
            {"role": "user", "content": "上月支出"},
            {"role": "assistant", "content": "上一月结果"},
        ])
        self.assertEqual(result_history[-1]["route"], "ledger_query")


if __name__ == "__main__":
    unittest.main()
