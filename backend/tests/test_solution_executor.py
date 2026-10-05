from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from backend.helpers.executor import TurnState, run_tool
from backend.main import get_tool_spec, reset_all_mock_state

ACTIVE = [
    "slack_list_conversations",
    "slack_list_users",
    "slack_users_info",
    "GMAIL_FETCH_EMAILS",
]


class RunToolTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_mock_state()
        self.state = TurnState(active_tools=list(ACTIVE))

    def test_calls_are_logged_in_order_with_exact_arguments(self) -> None:
        run_tool("slack_list_users", "{}", self.state)
        run_tool("GMAIL_FETCH_EMAILS", '{"query": "Q3 budget"}', self.state)
        run_tool("slack_users_info", '{"user": "U001"}', self.state)

        self.assertEqual(
            [(call.name, call.arguments) for call in self.state.tool_calls],
            [
                ("slack_list_users", {}),
                ("GMAIL_FETCH_EMAILS", {"query": "Q3 budget"}),
                ("slack_users_info", {"user": "U001"}),
            ],
        )

    def test_successful_call_logs_the_inner_result(self) -> None:
        outcome = run_tool("slack_list_users", "{}", self.state)

        expected = get_tool_spec("slack_list_users").invoke().model_dump(mode="json")
        log = self.state.tool_calls[0]
        self.assertTrue(outcome.ok)
        self.assertTrue(outcome.invoked)
        self.assertEqual(log.result, expected["result"])
        self.assertIsNone(log.error)
        self.assertTrue(
            outcome.model_view.startswith('<tool_result name="slack_list_users" trust="data">')
        )

    def test_missing_resource_logs_error_and_null_result(self) -> None:
        outcome = run_tool("slack_users_info", '{"user": "U_NOPE"}', self.state)

        log = self.state.tool_calls[0]
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error_type, "not_found")
        self.assertFalse(outcome.retryable)
        self.assertIsNone(log.result)
        self.assertEqual(log.error, "Unknown Slack user: U_NOPE")
        self.assertEqual(log.arguments, {"user": "U_NOPE"})

    def test_bad_argument_type_logs_error_and_null_result(self) -> None:
        outcome = run_tool("slack_list_conversations", '{"limit": "many"}', self.state)

        log = self.state.tool_calls[0]
        self.assertEqual(outcome.error_type, "bad_arguments")
        self.assertTrue(outcome.retryable)
        self.assertIsNone(log.result)
        self.assertTrue(log.error)

    def test_unexpected_exception_is_logged_without_a_traceback(self) -> None:
        with patch(
            "backend.tooling.ToolSpec.invoke", side_effect=RuntimeError("disk on fire")
        ):
            outcome = run_tool("slack_list_users", "{}", self.state)

        log = self.state.tool_calls[0]
        self.assertEqual(outcome.error_type, "unexpected_error")
        self.assertIsNone(log.result)
        self.assertEqual(log.error, "disk on fire")
        self.assertEqual(
            json.loads(outcome.model_view),
            {"error": "unexpected_error", "detail": "disk on fire", "retryable": True},
        )

    def test_null_arguments_are_dropped_and_tool_default_applies(self) -> None:
        outcome = run_tool(
            "slack_list_conversations",
            '{"limit": null, "types": "public_channel", "discover_dms": null}',
            self.state,
        )

        log = self.state.tool_calls[0]
        self.assertTrue(outcome.ok)
        self.assertEqual(log.arguments, {"types": "public_channel"})
        expected = get_tool_spec("slack_list_conversations").invoke(types="public_channel")
        self.assertEqual(log.result, expected.model_dump(mode="json")["result"])

    def test_registered_casing_is_preserved(self) -> None:
        run_tool("GMAIL_FETCH_EMAILS", "{}", self.state)
        run_tool("slack_list_conversations", "{}", self.state)

        self.assertEqual(
            [call.name for call in self.state.tool_calls],
            ["GMAIL_FETCH_EMAILS", "slack_list_conversations"],
        )

    def test_wrong_case_name_is_rejected_and_not_logged(self) -> None:
        for name in ("gmail_fetch_emails", "SLACK_LIST_CONVERSATIONS"):
            outcome = run_tool(name, "{}", self.state)
            self.assertEqual(outcome.error_type, "unknown_tool")
            self.assertFalse(outcome.invoked)
        self.assertEqual(self.state.tool_calls, [])

    def test_inactive_tool_is_rejected_and_not_logged(self) -> None:
        outcome = run_tool("slack_send_message", '{"channel": "C001", "text": "hi"}', self.state)

        self.assertEqual(outcome.error_type, "tool_not_loaded")
        self.assertFalse(outcome.invoked)
        self.assertEqual(self.state.tool_calls, [])

    def test_unparseable_arguments_are_rejected_and_not_logged(self) -> None:
        for raw in ("{not json", "[1, 2]"):
            outcome = run_tool("slack_list_users", raw, self.state)
            self.assertEqual(outcome.error_type, "bad_arguments")
            self.assertFalse(outcome.invoked)
        self.assertEqual(self.state.tool_calls, [])

    def test_large_result_view_is_capped_but_log_is_complete(self) -> None:
        with patch("backend.helpers.executor.MODEL_VIEW_MAX_CHARS", 50):
            outcome = run_tool("slack_list_users", "{}", self.state)

        self.assertLess(len(outcome.model_view), 200)
        self.assertIn("more characters not shown", outcome.model_view)
        self.assertGreater(len(json.dumps(self.state.tool_calls[0].result)), 50)


if __name__ == "__main__":
    unittest.main()
