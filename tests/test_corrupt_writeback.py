#!/usr/bin/env python3
"""Tests for the corrupt-file write-back guard (upstream 2.4.10 principle).

The loaders for session/contacts/seen/unknown-senders degrade a corrupt
file to empty (pinned in test_consistency.py) — but the read-modify-write
callers used to save that empty dict straight back over the file,
silently destroying the original contents (worst case: a cursor-only
session write wiping bot_token). `_json_file_readable` guards every
write-back site: a present-but-unparseable file is left in place for
operator inspection and the save is skipped.

Bind's two session/contacts sites share the same guard expressions as
cmd_commit/cmd_poll and are covered by those tests here; the bind flow
itself is not re-driven.

Run from the repo root:

    python3 -m unittest discover -s tests -v
    # or: python3 tests/test_corrupt_writeback.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA_DIR = tempfile.mkdtemp(prefix="ilink-test-writeback-")
os.environ["ILINK_DATA_DIR"] = DATA_DIR
import ilink  # noqa: E402

GARBAGE = "garbage{"


def _pin_paths():
    ilink.BRIDGE = DATA_DIR
    ilink.SESSION_FILE = os.path.join(DATA_DIR, "session.json")
    ilink.CONTACTS_FILE = os.path.join(DATA_DIR, "contacts.json")
    ilink.SEEN_FILE = os.path.join(DATA_DIR, "seen_ids.json")
    ilink.SEND_AUDIT_FILE = os.path.join(DATA_DIR, "send_audit.jsonl")
    ilink.SEND_LEDGER_FILE = os.path.join(DATA_DIR, "send_ledger.json")
    ilink.SEND_LEDGER_LOCK_FILE = os.path.join(DATA_DIR, "send_ledger.lock")
    ilink.DELIVERY_PENDING_FILE = os.path.join(DATA_DIR,
                                               "delivery_pending.json")
    ilink.QUOTE_CACHE_FILE = os.path.join(DATA_DIR, "quote_cache.json")
    ilink.QUOTE_CACHE_LOCK_FILE = os.path.join(DATA_DIR, "quote_cache.lock")
    with open(ilink.SESSION_FILE, "w") as f:
        json.dump({"bot_token": "tok"}, f)
    with open(ilink.CONTACTS_FILE, "w") as f:
        json.dump({"u1": {"context_token": "ctx-1"}}, f)
    with open(os.path.join(DATA_DIR, "owner.json"), "w") as f:
        json.dump({"owner_id": "u1", "owner_ids": ["u1"]}, f)
    for p in (ilink.SEEN_FILE, ilink.SEND_AUDIT_FILE, ilink.SEND_LEDGER_FILE,
              ilink.SEND_LEDGER_LOCK_FILE, ilink.DELIVERY_PENDING_FILE,
              ilink.QUOTE_CACHE_FILE,
              os.path.join(DATA_DIR, "unknown_senders.json")):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def _run(func, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = func(*args, **kwargs)
    return code, buf.getvalue()


def _run_commit(commit_block):
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(commit_block))
    try:
        return _run(ilink.cmd_commit)
    finally:
        sys.stdin = old_stdin


def _read(path):
    with open(path) as f:
        return f.read()


class HelperTest(unittest.TestCase):
    def setUp(self):
        _pin_paths()

    def test_readable(self):
        self.assertTrue(ilink._json_file_readable(
            os.path.join(DATA_DIR, "missing.json")))
        self.assertTrue(ilink._json_file_readable(ilink.SESSION_FILE))
        with open(ilink.SESSION_FILE, "w") as f:
            f.write(GARBAGE)
        self.assertFalse(ilink._json_file_readable(ilink.SESSION_FILE))


class CommitTest(unittest.TestCase):
    def setUp(self):
        _pin_paths()

    def test_corrupt_session_left_in_place(self):
        with open(ilink.SESSION_FILE, "w") as f:
            f.write(GARBAGE)
        code, out = _run_commit({"cursor": "BUF-9", "ids": ["m1"]})
        self.assertEqual(code, 0)
        self.assertIn("COMMIT_OK", out)
        self.assertEqual(_read(ilink.SESSION_FILE), GARBAGE)
        self.assertEqual(ilink.load_seen(), ["m1"])

    def test_healthy_session_still_saves_cursor(self):
        code, _ = _run_commit({"cursor": "BUF-9", "ids": ["m1"]})
        self.assertEqual(code, 0)
        with open(ilink.SESSION_FILE) as f:
            s = json.load(f)
        self.assertEqual((s.get("bot_token"), s.get("cursor")),
                         ("tok", "BUF-9"))


class PollContactsTest(unittest.TestCase):
    def setUp(self):
        _pin_paths()

    def _owner_msg_round(self):
        msg = {"message_id": "4242", "message_type": 1,
               "from_user_id": "u1", "context_token": "ctx-2",
               "item_list": [{"type": 1, "text_item": {"text": "hi"}}]}
        payload = {"msgs": [msg], "get_updates_buf": "BUF-2"}
        with mock.patch.object(ilink, "api", return_value=payload):
            return _run(ilink.cmd_poll)

    def test_corrupt_contacts_left_in_place(self):
        with open(ilink.CONTACTS_FILE, "w") as f:
            f.write(GARBAGE)
        code, out = self._owner_msg_round()
        self.assertEqual(code, 0)
        json.loads(out)  # poll output stays valid JSON
        self.assertEqual(_read(ilink.CONTACTS_FILE), GARBAGE)

    def test_healthy_contacts_still_saved(self):
        code, _ = self._owner_msg_round()
        self.assertEqual(code, 0)
        with open(ilink.CONTACTS_FILE) as f:
            contacts = json.load(f)
        self.assertEqual(contacts["u1"]["context_token"], "ctx-2")


class SeenTest(unittest.TestCase):
    def setUp(self):
        _pin_paths()

    def test_corrupt_seen_left_in_place(self):
        with open(ilink.SEEN_FILE, "w") as f:
            f.write(GARBAGE)
        ilink.mark_seen(["m1"])
        self.assertEqual(_read(ilink.SEEN_FILE), GARBAGE)

    def test_healthy_seen_still_saved(self):
        ilink.mark_seen(["m1"])
        self.assertEqual(ilink.load_seen(), ["m1"])


class UnknownSendersTest(unittest.TestCase):
    def setUp(self):
        _pin_paths()

    def test_corrupt_queue_left_in_place(self):
        path = os.path.join(DATA_DIR, "unknown_senders.json")
        with open(path, "w") as f:
            f.write(GARBAGE)
        ilink.note_unknown_sender("u9")
        self.assertEqual(_read(path), GARBAGE)

    def test_healthy_queue_still_saved(self):
        ilink.note_unknown_sender("u9")
        path = os.path.join(DATA_DIR, "unknown_senders.json")
        with open(path) as f:
            book = json.load(f)
        self.assertIn("u9", book)


if __name__ == "__main__":
    unittest.main()
