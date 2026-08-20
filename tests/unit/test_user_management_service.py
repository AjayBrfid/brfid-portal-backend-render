"""Unit tests for UserManagementService — repository mocked out, no database involved."""
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import CannotModifySelfStatusException, EmailAlreadyExistsException, RoleNotCreatableException
from app.services.auth.user_management_service import UserManagementService


@pytest.fixture
def service():
    svc = UserManagementService(session=MagicMock())
    svc.users = MagicMock()
    svc.tokens = MagicMock()
    return svc


def test_create_user_rejects_non_creatable_role(service):
    service.users.get_by_portal_email.return_value = None
    with pytest.raises(RoleNotCreatableException):
        service.create_user("warehouse", entity_id="wh-1", first_name="A", last_name="B", email="a@test.com", role="wh-admin", phone="+91 9000000000", temporary_password="x")


def test_create_user_rejects_duplicate_email(service):
    service.users.get_by_portal_email.return_value = MagicMock()  # an existing user
    with pytest.raises(EmailAlreadyExistsException):
        service.create_user("warehouse", entity_id="wh-1", first_name="A", last_name="B", email="dup@test.com", role="wh-manager", phone="+91 9000000000", temporary_password="x")


def test_update_status_rejects_self_deactivation(service):
    caller = MagicMock()
    caller.id = "user-1"
    with pytest.raises(CannotModifySelfStatusException):
        service.update_status("warehouse", entity_id="wh-1", user_id="user-1", status="inactive", caller=caller)
