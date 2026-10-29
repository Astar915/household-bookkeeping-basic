from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from bookkeeping.github_sync import (
    GitHubClient,
    GitHubSyncConflict,
    GitHubSyncSettingsStore,
    _http_json,
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
        body = b"bundle"
        sha = hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()
        self.client.request_with_headers = Mock(side_effect=[
            ({"sha": sha, "content": base64.b64encode(body).decode(), "encoding": "base64", "size": len(body)},
             {"etag": '"etag-1"'}),
            ({}, {"x-household-not-modified": "true", "etag": '"etag-1"'}),
        ])  # type: ignore[method-assign]
        self.client.request_raw = Mock(return_value=b"bundle")  # type: ignore[method-assign]

        self.assertEqual(self.client.download_bundle_with_revision("owner/repo"), (body, sha))
        self.client.request_raw.assert_not_called()
        self.assertEqual(self.client.request_with_headers.call_count, 2)

    def test_download_retries_and_rejects_a_snapshot_that_keeps_changing(self) -> None:
        bodies = [b"bundle-1", b"bundle-2", b"bundle-3"]
        shas = [hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest() for body in bodies]
        changing_shas = [shas[0], shas[1], shas[1], shas[2], shas[2], "different-sha"]
        self.client.request_with_headers = Mock(side_effect=[
            ({"sha": sha}, {"etag": f'"etag-{index}"'})
            for index, sha in enumerate(changing_shas)
        ])  # type: ignore[method-assign]
        self.client.request_raw = Mock(side_effect=bodies)  # type: ignore[method-assign]

        with self.assertRaises(GitHubSyncConflict):
            self.client.download_bundle_with_revision("owner/repo")

        self.assertEqual(self.client.request_raw.call_count, 3)

    def test_bundle_sha_with_etag_returns_cached_version_on_not_modified(self) -> None:
        self.client.request_with_headers = Mock(return_value=(
            {}, {"x-household-not-modified": "true", "etag": '"etag-1"'}
        ))  # type: ignore[method-assign]

        self.assertEqual(
            self.client.bundle_sha_with_etag("owner/repo", '"etag-1"'),
            (None, '"etag-1"', True),
        )
        headers = self.client.request_with_headers.call_args.kwargs["headers"]
        self.assertEqual(headers["If-None-Match"], '"etag-1"')

    def test_download_reuses_initial_contents_body_and_revalidates_with_etag(self) -> None:
        body = b"bundle"
        sha = hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()
        self.client.request_with_headers = Mock(return_value=(
            {}, {"x-household-not-modified": "true", "etag": '"etag-1"'}
        ))  # type: ignore[method-assign]
        self.client.request_raw = Mock()  # type: ignore[method-assign]

        self.assertEqual(
            self.client.download_bundle_with_revision(
                "owner/repo", initial_sha=sha, initial_etag='"etag-1"', initial_data=body
            ),
            (body, sha),
        )
        self.client.request_raw.assert_not_called()
        self.client.request_with_headers.assert_called_once()
        self.assertEqual(
            self.client.request_with_headers.call_args.kwargs["headers"]["If-None-Match"],
            '"etag-1"',
        )

    def test_http_json_treats_github_304_as_an_unchanged_response(self) -> None:
        not_modified = urllib.error.HTTPError(
            "https://api.github.com/repos/owner/repo/contents/file",
            304,
            "Not Modified",
            {"ETag": '"etag-1"'},
            None,
        )
        try:
            with patch("bookkeeping.github_sync.urllib.request.urlopen", side_effect=not_modified):
                result, headers = _http_json("https://api.github.com/repos/owner/repo/contents/file")
        finally:
            not_modified.close()

        self.assertEqual(result, {})
        self.assertEqual(headers["etag"], '"etag-1"')
        self.assertEqual(headers["x-household-not-modified"], "true")


if __name__ == "__main__":
    unittest.main()
