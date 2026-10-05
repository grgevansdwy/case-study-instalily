"""Compact index of the registered tools, plus the reviewed safety data about them.

The index is what the router and agent read instead of schemas. The class
table, bulk flags and reference-argument rules are explicit data, reviewed by
hand, and drive the executor's checks before a write.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

READ = "read"
WRITE = "write"
DESTRUCTIVE = "destructive"

_READ_TOOLS = """
GMAIL_FETCH_EMAILS GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID GMAIL_FETCH_MESSAGE_BY_THREAD_ID
GMAIL_GET_ATTACHMENT GMAIL_GET_CONTACTS GMAIL_GET_PEOPLE GMAIL_GET_PROFILE
GMAIL_LIST_DRAFTS GMAIL_LIST_LABELS GMAIL_LIST_THREADS

GOOGLECALENDAR_EVENTS_INSTANCES GOOGLECALENDAR_EVENTS_LIST GOOGLECALENDAR_FIND_EVENT
GOOGLECALENDAR_FIND_FREE_SLOTS GOOGLECALENDAR_FREE_BUSY_QUERY GOOGLECALENDAR_GET_CALENDAR
GOOGLECALENDAR_GET_CURRENT_DATE_TIME GOOGLECALENDAR_LIST_ACL_RULES
GOOGLECALENDAR_LIST_CALENDARS GOOGLECALENDAR_SETTINGS_LIST GOOGLECALENDAR_SYNC_EVENTS

GOOGLEDRIVE_DOWNLOAD_FILE GOOGLEDRIVE_FIND_FILE GOOGLEDRIVE_FIND_FOLDER
GOOGLEDRIVE_GENERATE_IDS

slack_token_status slack_health_check slack_list_conversations
slack_conversations_history slack_get_full_conversation slack_search_messages
slack_get_thread slack_users_info slack_list_users

linear_list_comments linear_list_cycles linear_get_document linear_list_documents
linear_get_issue linear_list_issues linear_list_issue_statuses linear_get_issue_status
linear_list_issue_labels linear_list_projects linear_get_project
linear_list_project_labels linear_list_teams linear_get_team linear_list_users
linear_get_user linear_search_documentation

perplexity_search

github_actions_get github_actions_list github_pull_request_read
github_list_pull_requests github_issue_read github_list_issues github_list_issue_types
github_get_file_contents github_get_repository_tree github_search_code
github_list_starred_repositories github_get_latest_release
github_get_notification_details github_list_notifications
github_get_code_scanning_alert github_list_code_scanning_alerts
github_get_dependabot_alert github_list_dependabot_alerts
github_get_secret_scanning_alert github_list_secret_scanning_alerts
github_run_secret_scanning github_get_release_by_tag github_list_releases
github_get_tag github_list_tags github_get_commit github_list_commits
github_get_discussion github_get_discussion_comments github_list_discussions
github_list_discussion_categories github_get_gist github_list_gists
github_search_issues github_search_pull_requests github_search_repositories
github_search_users github_search_orgs github_get_label github_list_label
github_get_global_security_advisory github_list_global_security_advisories
github_list_repository_security_advisories
github_list_org_repository_security_advisories github_projects_get
github_projects_list github_get_me github_get_teams github_get_team_members
github_list_branches github_get_copilot_job_status github_get_copilot_space
github_list_copilot_spaces github_get_job_logs github_support_docs_search
"""

_WRITE_TOOLS = """
GMAIL_ADD_LABEL_TO_EMAIL GMAIL_CREATE_EMAIL_DRAFT GMAIL_CREATE_LABEL
GMAIL_MODIFY_THREAD_LABELS GMAIL_PATCH_LABEL GMAIL_REPLY_TO_THREAD

GOOGLECALENDAR_ACL_PATCH GOOGLECALENDAR_CALENDAR_LIST_INSERT
GOOGLECALENDAR_CALENDAR_LIST_UPDATE GOOGLECALENDAR_CALENDARS_UPDATE
GOOGLECALENDAR_CREATE_EVENT GOOGLECALENDAR_DUPLICATE_CALENDAR
GOOGLECALENDAR_EVENTS_MOVE GOOGLECALENDAR_EVENTS_WATCH GOOGLECALENDAR_PATCH_CALENDAR
GOOGLECALENDAR_PATCH_EVENT GOOGLECALENDAR_QUICK_ADD GOOGLECALENDAR_SETTINGS_WATCH
GOOGLECALENDAR_UPDATE_ACL_RULE GOOGLECALENDAR_UPDATE_EVENT

GOOGLEDRIVE_ADD_FILE_SHARING_PREFERENCE GOOGLEDRIVE_COPY_FILE
GOOGLEDRIVE_CREATE_COMMENT GOOGLEDRIVE_CREATE_DRIVE GOOGLEDRIVE_CREATE_FILE
GOOGLEDRIVE_CREATE_FILE_FROM_TEXT GOOGLEDRIVE_CREATE_FOLDER GOOGLEDRIVE_CREATE_REPLY
GOOGLEDRIVE_CREATE_SHORTCUT_TO_FILE GOOGLEDRIVE_EDIT_FILE
GOOGLEDRIVE_FILES_MODIFY_LABELS

slack_send_message

linear_create_comment linear_create_document linear_update_document
linear_create_issue linear_update_issue linear_create_issue_label
linear_create_project linear_update_project

github_actions_run_trigger github_add_comment_to_pending_review
github_add_reply_to_pull_request_comment github_create_pull_request
github_create_pull_request_with_copilot github_pull_request_review_write
github_update_pull_request github_update_pull_request_branch
github_add_issue_comment github_assign_copilot_to_issue github_issue_write
github_sub_issue_write github_triage_issue github_create_branch
github_create_or_update_file github_push_files github_create_repository
github_fork_repository github_star_repository github_unstar_repository
github_dismiss_notification github_manage_notification_subscription
github_manage_repository_notification_subscription
github_mark_all_notifications_read github_create_gist github_update_gist
github_label_write github_projects_write github_request_copilot_review
"""

_DESTRUCTIVE_TOOLS = """
GMAIL_DELETE_DRAFT GMAIL_DELETE_MESSAGE GMAIL_MOVE_TO_TRASH GMAIL_REMOVE_LABEL

GOOGLECALENDAR_CALENDARS_DELETE GOOGLECALENDAR_CLEAR_CALENDAR
GOOGLECALENDAR_DELETE_EVENT GOOGLECALENDAR_REMOVE_ATTENDEE

GOOGLEDRIVE_DELETE_COMMENT GOOGLEDRIVE_DELETE_DRIVE GOOGLEDRIVE_DELETE_PERMISSION
GOOGLEDRIVE_DELETE_REPLY GOOGLEDRIVE_EMPTY_TRASH

github_merge_pull_request github_delete_file
"""

# Every registered tool has exactly one class here; a test checks the coverage.
TOOL_CLASSES: dict[str, str] = {
    name: tool_class
    for tool_class, names in (
        (READ, _READ_TOOLS),
        (WRITE, _WRITE_TOOLS),
        (DESTRUCTIVE, _DESTRUCTIVE_TOOLS),
    )
    for name in names.split()
}

# Write tools that delete when called with one of these `method` values.
DESTRUCTIVE_METHODS: dict[str, frozenset[str]] = {
    "github_actions_run_trigger": frozenset({"delete_workflow_run_logs"}),
    "github_pull_request_review_write": frozenset({"delete_pending"}),
    "github_sub_issue_write": frozenset({"remove"}),
    "github_label_write": frozenset({"delete"}),
    "github_projects_write": frozenset({"delete_project_item"}),
}

# Tools that act on a whole collection. The user's last message must contain
# every word of at least one group, as whole words, before one may run.
BULK_KEYWORDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "GOOGLECALENDAR_CLEAR_CALENDAR": (
        ("clear",), ("wipe",), ("all",), ("every",), ("everything",), ("entire",),
    ),
    "GOOGLEDRIVE_EMPTY_TRASH": (
        ("empty",), ("clear",), ("all",), ("everything",), ("entire",),
    ),
    "GOOGLEDRIVE_DELETE_DRIVE": (("delete", "drive"), ("remove", "drive")),
    "GOOGLECALENDAR_CALENDARS_DELETE": (("delete", "calendar"), ("remove", "calendar")),
    "github_mark_all_notifications_read": (("all",), ("every",), ("everything",)),
}

# Arguments that point at an existing resource or person. On a write, each
# value must come from a tool result or the conversation, never from a guess.
REFERENCE_ARG_NAMES = frozenset(
    """
    id ids channel thread_ts owner repo team project assignee assignees to cc bcc
    recipient_email extra_recipients attendees attendee_email email emailAddress
    email_address reviewers lead delegate destination parents organization
    pull_number pullNumber issue_number sub_issue_number sha branch from_branch
    base head base_ref ref path
    """.split()
)
REFERENCE_ARG_SUFFIXES = ("_id", "_ids", "Id", "Ids", "ID", "IDs")

# Names that match the rule above but hold a value the caller picks or invents.
REFERENCE_ARG_EXCLUDED = frozenset({"requestId", "colorId", "color_id", "themeId"})

# Arguments that name something the call creates, so there is nothing to look up.
REFERENCE_ARG_TOOL_EXCEPTIONS: dict[str, frozenset[str]] = {
    "GOOGLECALENDAR_EVENTS_WATCH": frozenset({"id"}),
    "GOOGLECALENDAR_SETTINGS_WATCH": frozenset({"id"}),
    "github_create_branch": frozenset({"branch"}),
    "github_create_or_update_file": frozenset({"path"}),
    "github_push_files": frozenset({"path"}),
}

# Values that are safe without a lookup: service aliases, the default branch
# and Gmail's built-in labels. Compared in lower case.
GROUNDING_EXEMPT = frozenset(
    """
    me primary root default main
    inbox unread starred important sent draft spam trash
    category_personal category_social category_promotions category_updates
    category_forums
    """.split()
) | {""}

# Arguments that carry the text of a write; a blank one is a mistake.
CONTENT_ARG_NAMES = frozenset(
    "text body message subject title content summary message_body text_content".split()
)

# Start and end arguments that must be in order when both are given.
TIME_RANGE_ARGS = (
    ("start_time", "end_time"),
    ("start_datetime", "end_datetime"),
    ("startDate", "targetDate"),
)


@dataclass(frozen=True)
class ToolInfo:
    name: str
    service: str
    description: str
    tool_class: str
    bulk: bool


@lru_cache(maxsize=1)
def _catalog() -> dict[str, ToolInfo]:
    # Imported here because backend.main imports backend.solution at module load.
    from backend.main import get_all_tool_specs

    return {
        name: ToolInfo(
            name=name,
            service=spec.service,
            description=spec.description,
            # A tool missing from the table is treated as destructive, so a new
            # tool gets every check until someone classifies it.
            tool_class=TOOL_CLASSES.get(name, DESTRUCTIVE),
            bulk=name in BULK_KEYWORDS,
        )
        for name, spec in get_all_tool_specs().items()
    }


def all_names() -> list[str]:
    return list(_catalog())


def get_info(name: str) -> ToolInfo | None:
    return _catalog().get(name)


def names_for_service(service: str) -> list[str]:
    return [info.name for info in _catalog().values() if info.service == service]


def effective_class(name: str, args: dict[str, Any]) -> str:
    """The tool's class for this call: some write tools delete by `method`."""
    if args.get("method") in DESTRUCTIVE_METHODS.get(name, ()):
        return DESTRUCTIVE
    info = get_info(name)
    return info.tool_class if info else DESTRUCTIVE


def is_reference_arg(tool: str, arg: str) -> bool:
    if arg in REFERENCE_ARG_EXCLUDED or arg in REFERENCE_ARG_TOOL_EXCEPTIONS.get(tool, ()):
        return False
    return arg in REFERENCE_ARG_NAMES or arg.endswith(REFERENCE_ARG_SUFFIXES)


@lru_cache(maxsize=1)
def get_index_text() -> str:
    """One line per tool, `name | description`, grouped under a service heading."""
    by_service: dict[str, list[ToolInfo]] = {}
    for info in _catalog().values():
        by_service.setdefault(info.service, []).append(info)
    lines: list[str] = []
    for service, infos in by_service.items():
        lines.append(f"## {service}")
        lines.extend(f"{info.name} | {' '.join(info.description.split())}" for info in infos)
    return "\n".join(lines)
