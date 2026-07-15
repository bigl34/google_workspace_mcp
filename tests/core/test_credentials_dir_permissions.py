"""Regression tests for check_credentials_directory_permissions.

Multiple server processes can initialize the same credentials directory
concurrently. These tests pin the concurrency-safe, non-destructive behavior.
"""

import os
import stat
import threading

from core.utils import check_credentials_directory_permissions


def test_concurrent_checks_on_shared_dir_all_succeed(tmp_path):
    """Many processes initializing the same (initially missing) credentials dir
    at once must all succeed."""
    target = str(tmp_path / "credentials")  # does not exist yet
    errors: list[str] = []
    n = 24
    barrier = threading.Barrier(n)

    def worker():
        try:
            barrier.wait()
            for _ in range(5):
                check_credentials_directory_permissions(target)
        except Exception as e:  # noqa: BLE001 - capture for assertion
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"{len(errors)} concurrent failures, e.g. {errors[:3]}"
    assert os.path.isdir(target)


def test_check_preserves_existing_dir_and_contents(tmp_path):
    """The check must never delete the credentials dir or its contents, and must
    not leave probe files behind."""
    target = tmp_path / "credentials"
    target.mkdir()
    keep = target / "token.json"
    keep.write_text("secret")

    check_credentials_directory_permissions(str(target))

    assert target.is_dir()
    assert keep.read_text() == "secret"
    assert not list(target.glob(".permission_test*"))


def test_check_creates_missing_dir(tmp_path):
    target = tmp_path / "nested" / "credentials"
    check_credentials_directory_permissions(str(target))
    assert target.is_dir()


def test_check_hardens_existing_directory_and_secret_files(tmp_path):
    target = tmp_path / "credentials"
    target.mkdir(mode=0o755)
    token = target / "user@example.com.json"
    client = target / "oauth_credentials.json"
    token.write_text("token")
    client.write_text("client")
    token.chmod(0o644)
    client.chmod(0o755)

    check_credentials_directory_permissions(str(target))

    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    assert stat.S_IMODE(client.stat().st_mode) == 0o600


def test_check_does_not_follow_symlinks_when_hardening_files(tmp_path):
    target = tmp_path / "credentials"
    target.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("not a credential")
    outside.chmod(0o644)
    (target / "linked.json").symlink_to(outside)

    check_credentials_directory_permissions(str(target))

    assert stat.S_IMODE(outside.stat().st_mode) == 0o644
