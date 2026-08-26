from unittest.mock import Mock

import pytest

from core.utils import UserInputError
from gadmin.admin_tools import (
    create_directory_group,
    delete_directory_user_alias,
    get_directory_group,
    get_directory_group_member,
    get_group_settings,
    insert_directory_group_member,
    insert_directory_user_alias,
    list_directory_group_aliases,
    list_directory_group_members,
    list_directory_groups,
    list_directory_users,
    patch_group_settings,
    _settings_confirmation,
)


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


@pytest.mark.asyncio
async def test_list_directory_users_preserves_cursor_and_reduces_fields():
    service = Mock()
    users_resource = service.users.return_value
    users_resource.list.return_value.execute.return_value = {
        "users": [
            {"id": "u1", "primaryEmail": "a@example.com", "name": {"fullName": "A"}}
        ],
        "nextPageToken": "next",
    }
    result = await _unwrap(list_directory_users)(
        service=service,
        user_google_email="admin@example.com",
        page_size=25,
    )
    assert result["nextPageToken"] == "next"
    assert result["users"][0]["primaryEmail"] == "a@example.com"
    users_resource.list.assert_called_once_with(
        customer="my_customer",
        maxResults=25,
        orderBy="email",
        projection="basic",
    )


@pytest.mark.asyncio
async def test_get_directory_group_returns_mirroring_fields():
    service = Mock()
    groups_resource = service.groups.return_value
    groups_resource.get.return_value.execute.return_value = {
        "id": "g1",
        "email": "registrations@example.com",
        "name": "Registrations",
        "description": "General mail",
        "adminCreated": True,
        "directMembersCount": "2",
        "aliases": ["registrations@example.net"],
        "nonEditableAliases": ["registrations@example.org"],
        "etag": "hidden",
    }

    result = await _unwrap(get_directory_group)(
        service=service,
        user_google_email="admin@example.com",
        group_key="registrations@example.com",
    )

    assert result == {
        "id": "g1",
        "email": "registrations@example.com",
        "name": "Registrations",
        "description": "General mail",
        "adminCreated": True,
        "directMembersCount": "2",
        "aliases": ["registrations@example.net"],
        "nonEditableAliases": ["registrations@example.org"],
    }
    groups_resource.get.assert_called_once_with(groupKey="registrations@example.com")


@pytest.mark.asyncio
async def test_list_directory_groups_preserves_cursor_and_reduces_fields():
    service = Mock()
    groups_resource = service.groups.return_value
    groups_resource.list.return_value.execute.return_value = {
        "groups": [
            {
                "id": "g1",
                "email": "registrations@example.com",
                "name": "Registrations",
                "description": "",
                "adminCreated": False,
                "directMembersCount": "2",
            }
        ],
        "nextPageToken": "next",
    }

    result = await _unwrap(list_directory_groups)(
        service=service,
        user_google_email="admin@example.com",
        domain="example.com",
        page_size=25,
    )

    assert result["nextPageToken"] == "next"
    assert result["groups"][0]["email"] == "registrations@example.com"
    groups_resource.list.assert_called_once_with(
        domain="example.com",
        maxResults=25,
        orderBy="email",
    )


@pytest.mark.asyncio
async def test_list_directory_group_aliases_returns_all_alias_records():
    service = Mock()
    aliases_resource = service.groups.return_value.aliases.return_value
    aliases_resource.list.return_value.execute.return_value = {
        "aliases": [
            {
                "id": "g1",
                "primaryEmail": "registrations@example.com",
                "alias": "registrations@example.net",
            }
        ]
    }

    result = await _unwrap(list_directory_group_aliases)(
        service=service,
        user_google_email="admin@example.com",
        group_key="registrations@example.com",
    )

    assert result["count"] == 1
    assert result["aliases"][0]["alias"] == "registrations@example.net"
    aliases_resource.list.assert_called_once_with(groupKey="registrations@example.com")


@pytest.mark.asyncio
async def test_list_directory_group_members_preserves_cursor_and_fields():
    service = Mock()
    members_resource = service.members.return_value
    members_resource.list.return_value.execute.return_value = {
        "members": [
            {
                "id": "u1",
                "email": "owner@example.com",
                "role": "OWNER",
                "type": "USER",
                "status": "ACTIVE",
                "delivery_settings": "ALL_MAIL",
            }
        ],
        "nextPageToken": "next",
    }

    result = await _unwrap(list_directory_group_members)(
        service=service,
        user_google_email="admin@example.com",
        group_key="registrations@example.com",
        page_size=25,
        include_derived_membership=True,
        roles="OWNER",
    )

    assert result["nextPageToken"] == "next"
    assert result["members"][0]["deliverySettings"] == "ALL_MAIL"
    members_resource.list.assert_called_once_with(
        groupKey="registrations@example.com",
        maxResults=25,
        includeDerivedMembership=True,
        roles="OWNER",
    )


@pytest.mark.asyncio
async def test_get_directory_group_member_returns_delivery_subscription():
    service = Mock()
    members_resource = service.members.return_value
    members_resource.get.return_value.execute.return_value = {
        "id": "u1",
        "email": "owner@example.com",
        "role": "OWNER",
        "type": "USER",
        "status": "ACTIVE",
        "delivery_settings": "ALL_MAIL",
    }

    result = await _unwrap(get_directory_group_member)(
        service=service,
        user_google_email="admin@example.com",
        group_key="registrations@example.com",
        member_key="owner@example.com",
    )

    assert result["groupKey"] == "registrations@example.com"
    assert result["member"]["deliverySettings"] == "ALL_MAIL"
    members_resource.get.assert_called_once_with(
        groupKey="registrations@example.com",
        memberKey="owner@example.com",
    )


@pytest.mark.asyncio
async def test_get_group_settings_returns_complete_resource():
    service = Mock()
    groups_resource = service.groups.return_value
    groups_resource.get.return_value.execute.return_value = {
        "email": "registrations@example.com",
        "whoCanPostMessage": "ANYONE_CAN_POST",
        "replyTo": "REPLY_TO_SENDER",
        "enableCollaborativeInbox": "false",
    }

    result = await _unwrap(get_group_settings)(
        service=service,
        user_google_email="admin@example.com",
        group_email="registrations@example.com",
    )

    assert result["settings"]["whoCanPostMessage"] == "ANYONE_CAN_POST"
    assert result["settings"]["replyTo"] == "REPLY_TO_SENDER"
    groups_resource.get.assert_called_once_with(
        groupUniqueId="registrations@example.com"
    )


@pytest.mark.asyncio
async def test_group_writes_default_to_preview_and_bind_exact_confirmation():
    service = Mock()

    create_preview = await _unwrap(create_directory_group)(
        service=service,
        user_google_email="admin@example.com",
        group_email="logistics@example.com",
        name="Logistics",
    )
    member_preview = await _unwrap(insert_directory_group_member)(
        service=service,
        user_google_email="admin@example.com",
        group_key="logistics@example.com",
        member_email="owner@example.com",
        role="OWNER",
        delivery_settings="ALL_MAIL",
    )
    settings_preview = await _unwrap(patch_group_settings)(
        service=service,
        user_google_email="admin@example.com",
        group_email="logistics@example.com",
        settings={"whoCanPostMessage": "ANYONE_CAN_POST"},
    )

    assert create_preview["requiredConfirmation"] == (
        "CREATE_GROUP:logistics@example.com"
    )
    assert member_preview["requiredConfirmation"] == (
        "ADD_GROUP_MEMBER:logistics@example.com:owner@example.com:OWNER:ALL_MAIL"
    )
    assert settings_preview["requiredConfirmation"] == _settings_confirmation(
        "logistics@example.com",
        {"whoCanPostMessage": "ANYONE_CAN_POST"},
    )
    service.groups.return_value.insert.assert_not_called()
    service.members.return_value.insert.assert_not_called()
    service.groups.return_value.patch.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_group_writes_call_google_with_exact_payloads():
    directory_service = Mock()
    directory_service.groups.return_value.insert.return_value.execute.return_value = {
        "email": "logistics@example.com",
        "name": "Logistics",
    }
    directory_service.members.return_value.insert.return_value.execute.return_value = {
        "email": "owner@example.com",
        "role": "OWNER",
        "delivery_settings": "ALL_MAIL",
    }
    settings_service = Mock()
    settings_service.groups.return_value.patch.return_value.execute.return_value = {
        "email": "logistics@example.com",
        "whoCanPostMessage": "ANYONE_CAN_POST",
    }

    await _unwrap(create_directory_group)(
        service=directory_service,
        user_google_email="admin@example.com",
        group_email="logistics@example.com",
        name="Logistics",
        dry_run=False,
        confirmation="CREATE_GROUP:logistics@example.com",
    )
    await _unwrap(insert_directory_group_member)(
        service=directory_service,
        user_google_email="admin@example.com",
        group_key="logistics@example.com",
        member_email="owner@example.com",
        role="OWNER",
        delivery_settings="ALL_MAIL",
        dry_run=False,
        confirmation=(
            "ADD_GROUP_MEMBER:logistics@example.com:owner@example.com:OWNER:ALL_MAIL"
        ),
    )
    await _unwrap(patch_group_settings)(
        service=settings_service,
        user_google_email="admin@example.com",
        group_email="logistics@example.com",
        settings={"whoCanPostMessage": "ANYONE_CAN_POST"},
        dry_run=False,
        confirmation=_settings_confirmation(
            "logistics@example.com",
            {"whoCanPostMessage": "ANYONE_CAN_POST"},
        ),
    )

    directory_service.groups.return_value.insert.assert_called_once_with(
        body={
            "email": "logistics@example.com",
            "name": "Logistics",
            "description": "",
        }
    )
    directory_service.members.return_value.insert.assert_called_once_with(
        groupKey="logistics@example.com",
        body={
            "email": "owner@example.com",
            "role": "OWNER",
            "delivery_settings": "ALL_MAIL",
        },
    )
    settings_service.groups.return_value.patch.assert_called_once_with(
        groupUniqueId="logistics@example.com",
        body={"whoCanPostMessage": "ANYONE_CAN_POST"},
    )


@pytest.mark.asyncio
async def test_patch_group_settings_rejects_read_only_fields():
    with pytest.raises(UserInputError, match="unsupported fields"):
        await _unwrap(patch_group_settings)(
            service=Mock(),
            user_google_email="admin@example.com",
            group_email="logistics@example.com",
            settings={"email": "attacker@example.com"},
        )


@pytest.mark.asyncio
async def test_patch_group_settings_confirmation_is_bound_to_exact_payload():
    safe_settings = {"whoCanPostMessage": "ALL_IN_DOMAIN_CAN_POST"}
    changed_settings = {"whoCanPostMessage": "ANYONE_CAN_POST"}

    with pytest.raises(UserInputError, match="Refusing mutation"):
        await _unwrap(patch_group_settings)(
            service=Mock(),
            user_google_email="admin@example.com",
            group_email="logistics@example.com",
            settings=changed_settings,
            dry_run=False,
            confirmation=_settings_confirmation(
                "logistics@example.com",
                safe_settings,
            ),
        )


@pytest.mark.asyncio
async def test_alias_writes_are_preview_only_by_default():
    service = Mock()
    result = await _unwrap(insert_directory_user_alias)(
        service=service,
        user_google_email="admin@example.com",
        user_key="user@example.com",
        alias="alias@example.com",
    )
    assert result["dryRun"] is True
    assert result["requiredConfirmation"] == "INSERT:user@example.com:alias@example.com"
    service.users().aliases().insert.assert_not_called()


@pytest.mark.asyncio
async def test_alias_delete_rejects_inexact_confirmation():
    service = Mock()
    with pytest.raises(Exception, match="exact confirmation"):
        await _unwrap(delete_directory_user_alias)(
            service=service,
            user_google_email="admin@example.com",
            user_key="user@example.com",
            alias="alias@example.com",
            dry_run=False,
            confirmation="DELETE",
        )
    service.users().aliases().delete.assert_not_called()
