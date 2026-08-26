"""Conservative Admin SDK Directory read and alias-management tools."""

import asyncio
import hashlib
import json
from typing import Any, Dict, Optional

from mcp.types import ToolAnnotations

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import UserInputError, handle_http_errors


GROUP_MEMBER_ROLES = {"OWNER", "MANAGER", "MEMBER"}
GROUP_MEMBER_DELIVERY_SETTINGS = {"ALL_MAIL", "DAILY", "DIGEST", "DISABLED", "NONE"}
GROUP_SETTINGS_WRITABLE_FIELDS = {
    "name",
    "description",
    "whoCanJoin",
    "whoCanViewMembership",
    "whoCanViewGroup",
    "whoCanInvite",
    "whoCanAdd",
    "allowExternalMembers",
    "whoCanAddExternalMembers",
    "whoCanPostMessage",
    "allowWebPosting",
    "primaryLanguage",
    "maxMessageBytes",
    "isArchived",
    "archiveOnly",
    "messageModerationLevel",
    "spamModerationLevel",
    "replyTo",
    "customReplyTo",
    "includeCustomFooter",
    "customFooterText",
    "sendMessageDenyNotification",
    "defaultMessageDenyNotificationText",
    "showInGroupDirectory",
    "allowGoogleCommunication",
    "membersCanPostAsTheGroup",
    "messageDisplayFont",
    "includeInGlobalAddressList",
    "whoCanLeaveGroup",
    "whoCanContactOwner",
    "whoCanAddReferences",
    "whoCanAssignTopics",
    "whoCanUnassignTopic",
    "whoCanTakeTopics",
    "whoCanMarkDuplicate",
    "whoCanMarkNoResponseNeeded",
    "whoCanMarkFavoriteReplyOnAnyTopic",
    "whoCanMarkFavoriteReplyOnOwnTopic",
    "whoCanUnmarkFavoriteReplyOnAnyTopic",
    "whoCanEnterFreeFormTags",
    "whoCanModifyTagsAndCategories",
    "favoriteRepliesOnTop",
    "whoCanApproveMembers",
    "whoCanBanUsers",
    "whoCanModifyMembers",
    "whoCanApproveMessages",
    "whoCanDeleteAnyPost",
    "whoCanDeleteTopics",
    "whoCanLockTopics",
    "whoCanMoveTopicsIn",
    "whoCanMoveTopicsOut",
    "whoCanPostAnnouncements",
    "whoCanHideAbuse",
    "whoCanMakeTopicsSticky",
    "whoCanModerateMembers",
    "whoCanModerateContent",
    "whoCanAssistContent",
    "enableCollaborativeInbox",
    "whoCanDiscoverGroup",
    "defaultSender",
}


def _user_summary(user: Dict[str, Any]) -> Dict[str, Any]:
    name = user.get("name") or {}
    return {
        "id": user.get("id"),
        "primaryEmail": user.get("primaryEmail"),
        "name": {
            "fullName": name.get("fullName"),
            "givenName": name.get("givenName"),
            "familyName": name.get("familyName"),
        },
        "aliases": user.get("aliases", []),
        "suspended": user.get("suspended"),
        "archived": user.get("archived"),
        "orgUnitPath": user.get("orgUnitPath"),
        "isAdmin": user.get("isAdmin"),
        "lastLoginTime": user.get("lastLoginTime"),
        "creationTime": user.get("creationTime"),
    }


def _group_summary(group: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": group.get("id"),
        "email": group.get("email"),
        "name": group.get("name"),
        "description": group.get("description"),
        "adminCreated": group.get("adminCreated"),
        "directMembersCount": group.get("directMembersCount"),
        "aliases": group.get("aliases", []),
        "nonEditableAliases": group.get("nonEditableAliases", []),
    }


def _member_summary(member: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": member.get("id"),
        "email": member.get("email"),
        "role": member.get("role"),
        "type": member.get("type"),
        "status": member.get("status"),
        "deliverySettings": member.get("delivery_settings"),
    }


@server.tool(
    title="List Directory Users",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors("list_directory_users", is_read_only=True, service_type="admin")
@require_google_service("admin", "admin_user_read")
async def list_directory_users(
    service,
    user_google_email: str,
    customer: str = "my_customer",
    domain: Optional[str] = None,
    query: Optional[str] = None,
    page_size: int = 100,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """List directory users with stable pagination metadata."""
    if page_size < 1 or page_size > 500:
        raise UserInputError("page_size must be between 1 and 500")
    params: Dict[str, Any] = {
        "customer": customer,
        "maxResults": page_size,
        "orderBy": "email",
        "projection": "basic",
    }
    if domain:
        params.pop("customer")
        params["domain"] = domain
    if query:
        params["query"] = query
    if page_token:
        params["pageToken"] = page_token
    response = await asyncio.to_thread(service.users().list(**params).execute)
    users = [_user_summary(user) for user in (response or {}).get("users", [])]
    next_page_token = (response or {}).get("nextPageToken")
    return {
        "returnedCount": len(users),
        "users": users,
        "nextPageToken": next_page_token,
        "hasMore": bool(next_page_token),
    }


@server.tool(
    title="Get Directory User",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors("get_directory_user", is_read_only=True, service_type="admin")
@require_google_service("admin", "admin_user_read")
async def get_directory_user(
    service, user_google_email: str, user_key: str
) -> Dict[str, Any]:
    """Get one directory user by ID, primary email, or alias."""
    response = await asyncio.to_thread(
        service.users().get(userKey=user_key, projection="basic").execute
    )
    return _user_summary(response or {})


@server.tool(
    title="List Directory User Aliases",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "list_directory_user_aliases", is_read_only=True, service_type="admin"
)
@require_google_service("admin", "admin_alias_read")
async def list_directory_user_aliases(
    service, user_google_email: str, user_key: str
) -> Dict[str, Any]:
    """List aliases for one directory user."""
    response = await asyncio.to_thread(
        service.users().aliases().list(userKey=user_key).execute
    )
    aliases = (response or {}).get("aliases", [])
    return {"userKey": user_key, "count": len(aliases), "aliases": aliases}


@server.tool(
    title="List Directory Groups",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors("list_directory_groups", is_read_only=True, service_type="admin")
@require_google_service("admin", "admin_group_read")
async def list_directory_groups(
    service,
    user_google_email: str,
    customer: str = "my_customer",
    domain: Optional[str] = None,
    query: Optional[str] = None,
    page_size: int = 200,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """List directory groups with stable pagination metadata."""
    if page_size < 1 or page_size > 200:
        raise UserInputError("page_size must be between 1 and 200")
    params: Dict[str, Any] = {
        "customer": customer,
        "maxResults": page_size,
        "orderBy": "email",
    }
    if domain:
        params.pop("customer")
        params["domain"] = domain
    if query:
        params["query"] = query
    if page_token:
        params["pageToken"] = page_token
    response = await asyncio.to_thread(service.groups().list(**params).execute)
    groups = [_group_summary(group) for group in (response or {}).get("groups", [])]
    next_page_token = (response or {}).get("nextPageToken")
    return {
        "returnedCount": len(groups),
        "groups": groups,
        "nextPageToken": next_page_token,
        "hasMore": bool(next_page_token),
    }


@server.tool(
    title="Get Directory Group",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors("get_directory_group", is_read_only=True, service_type="admin")
@require_google_service("admin", "admin_group_read")
async def get_directory_group(
    service, user_google_email: str, group_key: str
) -> Dict[str, Any]:
    """Get one directory group by primary email, alias, or unique group ID."""
    response = await asyncio.to_thread(service.groups().get(groupKey=group_key).execute)
    return _group_summary(response or {})


@server.tool(
    title="List Directory Group Aliases",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "list_directory_group_aliases", is_read_only=True, service_type="admin"
)
@require_google_service("admin", "admin_group_read")
async def list_directory_group_aliases(
    service,
    user_google_email: str,
    group_key: str,
) -> Dict[str, Any]:
    """List all editable aliases for one directory group."""
    response = await asyncio.to_thread(
        service.groups().aliases().list(groupKey=group_key).execute
    )
    aliases = (response or {}).get("aliases", [])
    return {"groupKey": group_key, "count": len(aliases), "aliases": aliases}


@server.tool(
    title="List Directory Group Members",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "list_directory_group_members", is_read_only=True, service_type="admin"
)
@require_google_service("admin", "admin_group_read")
async def list_directory_group_members(
    service,
    user_google_email: str,
    group_key: str,
    page_size: int = 200,
    page_token: Optional[str] = None,
    include_derived_membership: bool = False,
    roles: Optional[str] = None,
) -> Dict[str, Any]:
    """List members of one directory group with stable pagination metadata."""
    if page_size < 1 or page_size > 200:
        raise UserInputError("page_size must be between 1 and 200")
    params: Dict[str, Any] = {
        "groupKey": group_key,
        "maxResults": page_size,
        "includeDerivedMembership": include_derived_membership,
    }
    if page_token:
        params["pageToken"] = page_token
    if roles:
        params["roles"] = roles
    response = await asyncio.to_thread(service.members().list(**params).execute)
    members = [
        _member_summary(member) for member in (response or {}).get("members", [])
    ]
    next_page_token = (response or {}).get("nextPageToken")
    return {
        "groupKey": group_key,
        "returnedCount": len(members),
        "members": members,
        "nextPageToken": next_page_token,
        "hasMore": bool(next_page_token),
    }


@server.tool(
    title="Get Directory Group Member",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "get_directory_group_member", is_read_only=True, service_type="admin"
)
@require_google_service("admin", "admin_group_read")
async def get_directory_group_member(
    service,
    user_google_email: str,
    group_key: str,
    member_key: str,
) -> Dict[str, Any]:
    """Get one group member, including its mail delivery subscription."""
    response = await asyncio.to_thread(
        service.members()
        .get(
            groupKey=group_key,
            memberKey=member_key,
        )
        .execute
    )
    return {
        "groupKey": group_key,
        "member": _member_summary(response or {}),
    }


@server.tool(
    title="Get Group Settings",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "get_group_settings", is_read_only=True, service_type="groupssettings"
)
@require_google_service("groupssettings", "groups_settings")
async def get_group_settings(
    service,
    user_google_email: str,
    group_email: str,
) -> Dict[str, Any]:
    """Get the complete Groups Settings resource for one group email address."""
    response = await asyncio.to_thread(
        service.groups().get(groupUniqueId=group_email).execute
    )
    return {"groupEmail": group_email, "settings": response or {}}


def _require_confirmation(
    expected: str,
    dry_run: bool,
    confirmation: Optional[str],
) -> str:
    if not dry_run and confirmation != expected:
        raise UserInputError(
            f"Refusing mutation without exact confirmation '{expected}'"
        )
    return expected


def _settings_confirmation(group_email: str, settings: Dict[str, Any]) -> str:
    canonical = json.dumps(
        settings,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"PATCH_GROUP_SETTINGS:{group_email}:{digest}"


@server.tool(
    title="Create Directory Group",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
@handle_http_errors("create_directory_group", is_read_only=False, service_type="admin")
@require_google_service("admin", "admin_group_write")
async def create_directory_group(
    service,
    user_google_email: str,
    group_email: str,
    name: str,
    description: str = "",
    dry_run: bool = True,
    confirmation: Optional[str] = None,
) -> Dict[str, Any]:
    """Preview or create one Google Workspace directory group."""
    if "@" not in group_email:
        raise UserInputError("group_email must be an email address")
    expected = _require_confirmation(
        f"CREATE_GROUP:{group_email}",
        dry_run,
        confirmation,
    )
    body = {
        "email": group_email,
        "name": name,
        "description": description,
    }
    if dry_run:
        return {
            "dryRun": True,
            "group": body,
            "requiredConfirmation": expected,
        }
    response = await asyncio.to_thread(service.groups().insert(body=body).execute)
    return {"dryRun": False, "group": _group_summary(response or {})}


@server.tool(
    title="Insert Directory Group Member",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "insert_directory_group_member", is_read_only=False, service_type="admin"
)
@require_google_service("admin", "admin_group_write")
async def insert_directory_group_member(
    service,
    user_google_email: str,
    group_key: str,
    member_email: str,
    role: str = "MEMBER",
    delivery_settings: str = "ALL_MAIL",
    dry_run: bool = True,
    confirmation: Optional[str] = None,
) -> Dict[str, Any]:
    """Preview or add one direct group member with role and delivery settings."""
    if role not in GROUP_MEMBER_ROLES:
        raise UserInputError(f"role must be one of {sorted(GROUP_MEMBER_ROLES)}")
    if delivery_settings not in GROUP_MEMBER_DELIVERY_SETTINGS:
        raise UserInputError(
            f"delivery_settings must be one of {sorted(GROUP_MEMBER_DELIVERY_SETTINGS)}"
        )
    expected = _require_confirmation(
        f"ADD_GROUP_MEMBER:{group_key}:{member_email}:{role}:{delivery_settings}",
        dry_run,
        confirmation,
    )
    body = {
        "email": member_email,
        "role": role,
        "delivery_settings": delivery_settings,
    }
    if dry_run:
        return {
            "dryRun": True,
            "groupKey": group_key,
            "member": body,
            "requiredConfirmation": expected,
        }
    response = await asyncio.to_thread(
        service.members().insert(groupKey=group_key, body=body).execute
    )
    return {
        "dryRun": False,
        "groupKey": group_key,
        "member": _member_summary(response or {}),
    }


@server.tool(
    title="Patch Group Settings",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "patch_group_settings", is_read_only=False, service_type="groupssettings"
)
@require_google_service("groupssettings", "groups_settings")
async def patch_group_settings(
    service,
    user_google_email: str,
    group_email: str,
    settings: Dict[str, Any],
    dry_run: bool = True,
    confirmation: Optional[str] = None,
) -> Dict[str, Any]:
    """Preview or patch an allowlisted set of Google Groups settings."""
    if not settings:
        raise UserInputError("settings must contain at least one field")
    unsupported = sorted(set(settings) - GROUP_SETTINGS_WRITABLE_FIELDS)
    if unsupported:
        raise UserInputError(f"settings contains unsupported fields: {unsupported}")
    expected = _require_confirmation(
        _settings_confirmation(group_email, settings),
        dry_run,
        confirmation,
    )
    if dry_run:
        return {
            "dryRun": True,
            "groupEmail": group_email,
            "settings": settings,
            "requiredConfirmation": expected,
        }
    response = await asyncio.to_thread(
        service.groups()
        .patch(
            groupUniqueId=group_email,
            body=settings,
        )
        .execute
    )
    return {
        "dryRun": False,
        "groupEmail": group_email,
        "settings": response or {},
    }


def _require_alias_confirmation(
    action: str, user_key: str, alias: str, dry_run: bool, confirmation: Optional[str]
) -> str:
    expected = f"{action}:{user_key}:{alias}"
    if not dry_run and confirmation != expected:
        raise UserInputError(
            f"Refusing alias mutation without exact confirmation '{expected}'"
        )
    return expected


@server.tool(
    title="Insert Directory User Alias",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "insert_directory_user_alias", is_read_only=False, service_type="admin"
)
@require_google_service("admin", "admin_alias_write")
async def insert_directory_user_alias(
    service,
    user_google_email: str,
    user_key: str,
    alias: str,
    dry_run: bool = True,
    confirmation: Optional[str] = None,
) -> Dict[str, Any]:
    """Preview or insert one alias."""
    expected = _require_alias_confirmation(
        "INSERT", user_key, alias, dry_run, confirmation
    )
    if dry_run:
        return {
            "dryRun": True,
            "userKey": user_key,
            "alias": alias,
            "requiredConfirmation": expected,
        }
    response = await asyncio.to_thread(
        service.users()
        .aliases()
        .insert(userKey=user_key, body={"alias": alias})
        .execute
    )
    return {"dryRun": False, "alias": response}


@server.tool(
    title="Delete Directory User Alias",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
@handle_http_errors(
    "delete_directory_user_alias", is_read_only=False, service_type="admin"
)
@require_google_service("admin", "admin_alias_write")
async def delete_directory_user_alias(
    service,
    user_google_email: str,
    user_key: str,
    alias: str,
    dry_run: bool = True,
    confirmation: Optional[str] = None,
) -> Dict[str, Any]:
    """Preview or delete one alias."""
    expected = _require_alias_confirmation(
        "DELETE", user_key, alias, dry_run, confirmation
    )
    if dry_run:
        return {
            "dryRun": True,
            "userKey": user_key,
            "alias": alias,
            "requiredConfirmation": expected,
        }
    await asyncio.to_thread(
        service.users().aliases().delete(userKey=user_key, alias=alias).execute
    )
    return {"dryRun": False, "deleted": alias, "userKey": user_key}
