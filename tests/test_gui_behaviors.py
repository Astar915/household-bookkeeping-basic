from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bookkeeping.gui import BookkeepingWindow


class ChatImageAttachmentTests(unittest.TestCase):
    def test_late_cancel_callback_cannot_discard_a_new_request(self) -> None:
        window = object.__new__(BookkeepingWindow)
        window._request_cancelled = False
        window._cleanup_request_worker = lambda: self.fail('new request was discarded')
        # A second cancellation callback arrives after the first completed and
        # the user is already typing/sending the next request.
        window._finish_cancelled_request()

    def test_removing_pending_image_is_immediate_without_confirmation(self) -> None:
        window = object.__new__(BookkeepingWindow)
        window.root = object()
        window.image_attachments = [SimpleNamespace(name="receipt.jpg")]
        refreshed: list[bool] = []
        window._refresh_image_attachments = lambda: refreshed.append(True)

        with patch("bookkeeping.gui.messagebox.askyesno") as confirm:
            window._remove_image_attachment(0)

        confirm.assert_not_called()
        self.assertEqual(window.image_attachments, [])
        self.assertEqual(refreshed, [True])

    def test_invalid_image_index_does_nothing(self) -> None:
        window = object.__new__(BookkeepingWindow)
        window.root = object()
        attachment = SimpleNamespace(name="receipt.jpg")
        window.image_attachments = [attachment]
        refreshed: list[bool] = []
        window._refresh_image_attachments = lambda: refreshed.append(True)

        with patch("bookkeeping.gui.messagebox.askyesno") as confirm:
            window._remove_image_attachment(1)

        confirm.assert_not_called()
        self.assertEqual(window.image_attachments, [attachment])
        self.assertEqual(refreshed, [])


if __name__ == "__main__":
    unittest.main()
