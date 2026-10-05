from __future__ import annotations

import unittest
from collections import Counter

from backend.helpers import catalog
from backend.main import get_all_tool_specs, list_available_tools


class ClassTableTests(unittest.TestCase):
    def test_every_registered_tool_has_exactly_one_class(self) -> None:
        listed = [
            name
            for names in (
                catalog._READ_TOOLS,
                catalog._WRITE_TOOLS,
                catalog._DESTRUCTIVE_TOOLS,
            )
            for name in names.split()
        ]

        self.assertEqual(sorted(listed), list_available_tools())
        self.assertEqual(len(listed), 191)

    def test_class_counts(self) -> None:
        counts = Counter(catalog.TOOL_CLASSES.values())

        self.assertEqual(
            counts, {catalog.READ: 107, catalog.WRITE: 69, catalog.DESTRUCTIVE: 15}
        )

    def test_names_the_verb_rule_gets_wrong_are_classified_by_hand(self) -> None:
        expected = {
            "github_actions_run_trigger": catalog.WRITE,
            "github_pull_request_read": catalog.READ,
            "github_run_secret_scanning": catalog.READ,
            "github_mark_all_notifications_read": catalog.WRITE,
            "github_merge_pull_request": catalog.DESTRUCTIVE,
            "GOOGLEDRIVE_GENERATE_IDS": catalog.READ,
            "GOOGLECALENDAR_CALENDAR_LIST_INSERT": catalog.WRITE,
            "GMAIL_MOVE_TO_TRASH": catalog.DESTRUCTIVE,
            "slack_conversations_history": catalog.READ,
            "slack_users_info": catalog.READ,
            "perplexity_search": catalog.READ,
        }

        for name, tool_class in expected.items():
            self.assertEqual(catalog.get_info(name).tool_class, tool_class, name)

    def test_bulk_tools_are_registered_and_never_reads(self) -> None:
        self.assertEqual(
            set(catalog.BULK_KEYWORDS),
            {
                "GOOGLECALENDAR_CLEAR_CALENDAR",
                "GOOGLEDRIVE_EMPTY_TRASH",
                "GOOGLEDRIVE_DELETE_DRIVE",
                "GOOGLECALENDAR_CALENDARS_DELETE",
                "github_mark_all_notifications_read",
            },
        )
        for name in catalog.BULK_KEYWORDS:
            info = catalog.get_info(name)
            self.assertTrue(info.bulk)
            self.assertNotEqual(info.tool_class, catalog.READ)
        self.assertFalse(catalog.get_info("slack_send_message").bulk)

    def test_a_delete_method_makes_a_write_tool_destructive(self) -> None:
        self.assertEqual(
            catalog.effective_class("github_label_write", {"method": "create"}),
            catalog.WRITE,
        )
        self.assertEqual(
            catalog.effective_class("github_label_write", {"method": "delete"}),
            catalog.DESTRUCTIVE,
        )
        for name in catalog.DESTRUCTIVE_METHODS:
            self.assertEqual(catalog.TOOL_CLASSES[name], catalog.WRITE)
            self.assertIn("method", get_all_tool_specs()[name].args_model.model_fields)

    def test_unclassified_tool_is_treated_as_destructive(self) -> None:
        self.assertEqual(catalog.effective_class("not_a_tool", {}), catalog.DESTRUCTIVE)


class ReferenceArgumentTests(unittest.TestCase):
    def test_reference_arguments(self) -> None:
        for tool, arg in [
            ("slack_send_message", "channel"),
            ("slack_send_message", "thread_ts"),
            ("GMAIL_CREATE_EMAIL_DRAFT", "recipient_email"),
            ("GMAIL_CREATE_EMAIL_DRAFT", "extra_recipients"),
            ("GOOGLECALENDAR_REMOVE_ATTENDEE", "attendee_email"),
            ("GOOGLEDRIVE_ADD_FILE_SHARING_PREFERENCE", "email_address"),
            ("GOOGLEDRIVE_DELETE_DRIVE", "driveId"),
            ("linear_create_comment", "issueId"),
            ("github_merge_pull_request", "pullNumber"),
            ("github_dismiss_notification", "threadID"),
            ("github_delete_file", "path"),
            ("github_delete_file", "branch"),
        ]:
            self.assertTrue(catalog.is_reference_arg(tool, arg), f"{tool}.{arg}")

    def test_arguments_that_are_not_references(self) -> None:
        for tool, arg in [
            ("slack_send_message", "text"),
            ("linear_create_issue", "title"),
            ("GOOGLEDRIVE_CREATE_DRIVE", "requestId"),
            ("GOOGLECALENDAR_CALENDAR_LIST_UPDATE", "colorId"),
            ("GOOGLECALENDAR_EVENTS_WATCH", "id"),
            ("github_create_branch", "branch"),
            ("github_create_or_update_file", "path"),
            ("GOOGLECALENDAR_CALENDAR_LIST_INSERT", "hidden"),
        ]:
            self.assertFalse(catalog.is_reference_arg(tool, arg), f"{tool}.{arg}")

    def test_per_tool_exceptions_name_real_tools(self) -> None:
        registered = set(list_available_tools())

        self.assertLessEqual(set(catalog.REFERENCE_ARG_TOOL_EXCEPTIONS), registered)


if __name__ == "__main__":
    unittest.main()
