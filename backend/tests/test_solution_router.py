from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import openai
from backend.helpers import catalog, config
from backend.helpers.executor import TurnState, run_tool
from backend.helpers.router import keyword_fallback, validate_names
from backend.main import app, list_available_tools, reset_all_mock_state
from backend.tests.fakes import ScriptedClient, calls_response, router_response, text_response
from fastapi.testclient import TestClient

MAX_SCHEMAS_PER_REQUEST = config.CHAT_MAX_ACTIVE_TOOLS + 1  # plus load_more_tools


class CatalogTests(unittest.TestCase):
    def test_index_has_one_line_for_every_registered_tool(self) -> None:
        names = list_available_tools()
        lines = [line for line in catalog.get_index_text().splitlines() if " | " in line]

        self.assertEqual(len(names), 191)
        self.assertEqual(sorted(line.split(" | ")[0] for line in lines), names)


class ValidateNamesTests(unittest.TestCase):
    def test_unknown_and_wrongly_cased_names_are_dropped(self) -> None:
        names = validate_names(
            ["slack_list_users", "slack_delete_everything", "gmail_fetch_emails", None, 7]
        )

        self.assertEqual(names, ["slack_list_users"])

    def test_duplicates_are_removed_in_order(self) -> None:
        names = validate_names(["GMAIL_FETCH_EMAILS", "slack_send_message", "GMAIL_FETCH_EMAILS"])

        self.assertEqual(names, ["GMAIL_FETCH_EMAILS", "slack_send_message"])

    def test_selection_is_capped_at_15(self) -> None:
        registered = list_available_tools()

        self.assertEqual(validate_names(registered), registered[:15])


class KeywordFallbackTests(unittest.TestCase):
    def test_named_service_gives_only_its_read_tools(self) -> None:
        names = keyword_fallback("What conversations do I have in Slack?")

        self.assertIn("slack_list_conversations", names)
        self.assertNotIn("slack_send_message", names)
        self.assertTrue(all(catalog.get_info(name).service == "slack" for name in names))

    def test_shared_keyword_splits_the_cap_across_services(self) -> None:
        names = keyword_fallback("Show me the open issues")

        services = {catalog.get_info(name).service for name in names}
        self.assertEqual(services, {"linear", "github"})
        self.assertEqual(len(names), 15)
        self.assertNotIn("github_mark_all_notifications_read", names)

    def test_no_keyword_gives_no_tools(self) -> None:
        self.assertEqual(keyword_fallback("Hello there"), [])


class LoadMoreToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_mock_state()
        self.state = TurnState(active_tools=["slack_list_users"])

    def load(self, names: list[str]) -> dict:
        outcome = run_tool("load_more_tools", json.dumps({"names": names}), self.state)
        self.assertFalse(outcome.invoked)
        return json.loads(outcome.model_view)

    def test_valid_names_are_added_and_nothing_is_logged(self) -> None:
        view = self.load(["GMAIL_FETCH_EMAILS", "slack_list_users"])

        self.assertEqual(view["added"], ["GMAIL_FETCH_EMAILS"])
        self.assertEqual(self.state.active_tools, ["slack_list_users", "GMAIL_FETCH_EMAILS"])
        self.assertEqual(self.state.tool_calls, [])

    def test_unknown_names_are_rejected(self) -> None:
        view = self.load(["gmail_fetch_emails", "slack_delete_everything"])

        self.assertEqual(view["added"], [])
        self.assertEqual(
            [item["name"] for item in view["rejected"]],
            ["gmail_fetch_emails", "slack_delete_everything"],
        )
        self.assertEqual(self.state.active_tools, ["slack_list_users"])

    def test_active_tools_stop_at_25(self) -> None:
        view = self.load(list_available_tools())

        self.assertEqual(len(self.state.active_tools), 25)
        self.assertEqual(len(view["added"]), 24)
        self.assertEqual(len(view["rejected"]), 191 - 25)
        self.assertEqual(self.state.tool_calls, [])

    def test_a_loaded_tool_can_then_be_called(self) -> None:
        before = run_tool("GMAIL_FETCH_EMAILS", "{}", self.state)
        self.load(["GMAIL_FETCH_EMAILS"])
        after = run_tool("GMAIL_FETCH_EMAILS", "{}", self.state)

        self.assertEqual(before.error_type, "tool_not_loaded")
        self.assertFalse(before.invoked)
        self.assertTrue(after.ok)
        self.assertEqual([call.name for call in self.state.tool_calls], ["GMAIL_FETCH_EMAILS"])


class RoutedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_mock_state()
        self.client = TestClient(app)

    def post(self, model: ScriptedClient, content: str = "What conversations are in Slack?"):
        with patch("backend.helpers.llm.get_client", return_value=model):
            return self.client.post(
                "/chat", json={"messages": [{"role": "user", "content": content}]}
            )

    def tool_names(self, request: dict) -> list[str]:
        return [tool["name"] for tool in request["tools"]]

    def test_router_request_carries_the_index_and_no_tool_schemas(self) -> None:
        model = ScriptedClient([text_response("ok")], router=["slack_list_conversations"])

        self.post(model)

        self.assertEqual(len(model.router_requests), 1)
        request = model.router_requests[0]
        self.assertEqual(request["tools"], [])
        self.assertEqual(request["model"], config.OPENAI_ROUTER_MODEL)
        self.assertIn("slack_list_conversations | ", request["instructions"])
        enum = request["text"]["format"]["schema"]["properties"]["tools"]["items"]["enum"]
        self.assertEqual(sorted(enum), list_available_tools())

    def test_agent_sees_only_validated_router_picks(self) -> None:
        picks = ["slack_list_users", "not_a_tool", "slack_list_users", "GMAIL_FETCH_EMAILS"]
        model = ScriptedClient(
            [text_response("ok")], router=lambda index: router_response(picks)
        )

        self.post(model)

        self.assertEqual(
            self.tool_names(model.requests[0]),
            ["slack_list_users", "GMAIL_FETCH_EMAILS", "load_more_tools"],
        )

    def test_oversized_router_pick_is_capped_at_15(self) -> None:
        model = ScriptedClient(
            [text_response("ok")],
            router=lambda index: router_response(list_available_tools()),
        )

        self.post(model)

        self.assertEqual(len(model.requests[0]["tools"]), 16)

    def test_empty_selection_sends_only_load_more_tools(self) -> None:
        model = ScriptedClient([text_response("Hi!")])

        payload = self.post(model, "Hello!").json()

        self.assertEqual(self.tool_names(model.requests[0]), ["load_more_tools"])
        self.assertEqual(payload["tool_calls"], [])

    def test_tool_that_is_not_active_is_rejected_and_not_logged(self) -> None:
        model = ScriptedClient(
            [
                calls_response([("GMAIL_FETCH_EMAILS", {"query": "budget"})]),
                text_response("I could not search email."),
            ],
            router=["slack_list_users"],
        )

        payload = self.post(model).json()

        self.assertEqual(payload["tool_calls"], [])
        self.assertIn("tool_not_loaded", model.requests[1]["input"][-1]["output"])

    def test_loaded_tool_appears_on_the_next_request_and_only_real_calls_are_logged(self) -> None:
        model = ScriptedClient(
            [
                calls_response([("load_more_tools", {"names": ["GMAIL_FETCH_EMAILS"]})]),
                calls_response([("GMAIL_FETCH_EMAILS", {"query": "revenue"})], prefix="b"),
                text_response("Found them."),
            ],
            router=["slack_list_users"],
        )

        payload = self.post(model).json()

        self.assertEqual(self.tool_names(model.requests[0]), ["slack_list_users", "load_more_tools"])
        self.assertEqual(
            self.tool_names(model.requests[1]),
            ["slack_list_users", "GMAIL_FETCH_EMAILS", "load_more_tools"],
        )
        self.assertEqual([call["name"] for call in payload["tool_calls"]], ["GMAIL_FETCH_EMAILS"])
        self.assertIsNone(payload["tool_calls"][0]["error"])

    def test_no_request_ever_carries_more_than_26_schemas(self) -> None:
        everything = list_available_tools()
        model = ScriptedClient(
            [
                calls_response([("load_more_tools", {"names": everything[:100]})]),
                calls_response([("load_more_tools", {"names": everything[100:]})], prefix="b"),
                calls_response([("slack_list_users", {})], prefix="c"),
                text_response("done"),
            ],
            router=lambda index: router_response(everything),
        )

        self.post(model)

        self.assertEqual(len(model.requests), 4)
        counts = [len(request["tools"]) for request in model.requests]
        self.assertEqual(counts, [16, 26, 26, 26])
        for request in [*model.requests, *model.router_requests]:
            self.assertLessEqual(len(request["tools"]), MAX_SCHEMAS_PER_REQUEST)

    def test_invalid_router_output_twice_falls_back_to_keywords(self) -> None:
        model = ScriptedClient(
            [
                calls_response([("slack_list_conversations", {})]),
                text_response("You have four conversations."),
            ],
            router=lambda index: text_response("not json"),
        )

        response = self.post(model)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(model.router_requests), 2)
        routed = self.tool_names(model.requests[0])[:-1]
        self.assertIn("slack_list_conversations", routed)
        self.assertNotIn("slack_send_message", routed)
        self.assertEqual(
            [call["name"] for call in response.json()["tool_calls"]],
            ["slack_list_conversations"],
        )

    def test_router_provider_error_twice_falls_back_to_keywords(self) -> None:
        model = ScriptedClient(
            [text_response("ok")],
            router=lambda index: openai.OpenAIError("router down"),
        )

        response = self.post(model)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(model.router_requests), 2)
        self.assertIn("slack_list_conversations", self.tool_names(model.requests[0]))

    def test_router_recovers_on_the_second_attempt(self) -> None:
        model = ScriptedClient(
            [text_response("ok")],
            router=lambda index: (
                text_response("not json") if index == 0 else router_response(["slack_list_users"])
            ),
        )

        self.post(model)

        self.assertEqual(len(model.router_requests), 2)
        self.assertEqual(self.tool_names(model.requests[0]), ["slack_list_users", "load_more_tools"])


if __name__ == "__main__":
    unittest.main()
