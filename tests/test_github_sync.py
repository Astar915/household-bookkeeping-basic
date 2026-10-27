from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from bookkeeping.github_sync import (
    GitHubClient,
    GitHubSyncConflict,
    GitHubSyncSettingsStore,
)


class GitHubSyncSettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "github_sync.json"
        self.store = GitHubSyncSettingsStore(self.path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_loads_legacy_settings_without_checkpoint(self) -> None:
        self.path.write_text(
            json.dumps({"version": 2, "repository_name": "data", "repository": "owner/repo"}),
            encoding="utf-8",
        )

        self.assertEqual(self.store.load()["last_sync_sha"], "")

    def test_saves_checkpoint_and_preserves_it_for_same_repository(self) -> None:
        self.store.save(repository_name="data", repository="owner/repo", last_sync_sha="sha-1")
        self.store.save(repository_name="data", repository="OWNER/REPO")

        self.assertEqual(self.store.load()["last_sync_sha"], "sha-1")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], 3)

    def test_changing_repository_clears_checkpoint(self) -> None:
        self.store.save(repository_name="data", repository="owner/old", last_sync_sha="sha-1")
        self.store.save(repository_name="data", repository="owner/new")

        self.assertEqual(self.store.load()["last_sync_sha"], "")


class GitHubSnapshotRevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GitHubClient("ghu_test-token")

    def test_auto_upload_refuses_to_replace_a_newer_cloud_snapshot(self) -> None:
        self.client.request = Mock(return_value={"sha": "newer-sha"})  # type: ignore[method-assign]

        with self.assertRaises(GitHubSyncConflict):
            self.client.upload_bundle("owner/repo", b"snapshot", expected_sha="older-sha")

        self.client.request.assert_called_once()
        self.assertEqual(self.client.request.call_args.kwargs.get("method", "GET"), "GET")

    def test_first_upload_refuses_if_another_snapshot_already_exists(self) -> None:
        self.client.request = Mock(return_value={"sha": "already-there"})  # type: ignore[method-assign]

        with self.assertRaises(GitHubSyncConflict):
            self.client.upload_bundle("owner/repo", b"snapshot", expected_sha=None)

        self.client.request.assert_called_once()

    def test_upload_uses_current_sha_as_github_write_precondition(self) -> None:
        self.client.request = Mock(
            side_effect=[{"sha": "current-sha"}, {"content": {"sha": "uploaded-sha"}}]
        )  # type: ignore[method-assign]

        result = self.client.upload_bundle("owner/repo", b"snapshot", expected_sha="current-sha")

        self.assertEqual(result, "uploaded-sha")
        put_call = self.client.request.call_args_list[1]
        self.assertEqual(put_call.kwargs["method"], "PUT")
        self.assertEqual(put_call.kwargs["payload"]["sha"], "current-sha")

    def test_download_returns_the_sha_of_a_stable_snapshot(self) -> None:
        self.client.request = Mock(side_effect=[{"sha": "stable-sha"}, {"sha": "stable-sha"}])  # type: ignore[method-assign]
        self.client.request_raw = Mock(return_value=b"bundle")  # type: ignore[method-assign]

        self.assertEqual(self.client.download_bundle_with_revision("owner/repo"), (b"bundle", "stable-sha"))

    def test_download_retries_and_rejects_a_snapshot_that_keeps_changing(self) -> None:
        self.client.request = Mock(
            side_effect=[
                {"sha": "sha-1"}, {"sha": "sha-2"},
                {"sha": "sha-2"}, {"sha": "sha-3"},
                {"sha": "sha-3"}, {"sha": "sha-4"},
            ]
        )  # type: ignore[method-assign]
        self.client.request_raw = Mock(return_value=b"bundle")  # type: ignore[method-assign]

        with self.assertRaises(GitHubSyncConflict):
            self.client.download_bundle_with_revision("owner/repo")

        self.assertEqual(self.client.request_raw.call_count, 3)


if __name__ == "__main__":
    unittest.main()
