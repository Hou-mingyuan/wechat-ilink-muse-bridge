#!/usr/bin/env python3
"""Tests for async echo confirmation of sent messages (issue #8, item 3).

A send that returns message_id is only "accepted by the server". The
poll round echoes the bot's own messages back (message_type 2, same
message_id), so a later poll can confirm the send actually landed in
the conversation stream. This is async on purpose: sends record a
pending entry and return at once; cmd_poll matches the round's echoes
against pending entries, confirms matches, and reports entries older
than DELIVERY_ECHO_TIMEOUT with no echo as no_echo in the audit log.
It never resends: an unconfirmed message may still have been
delivered.

Run from the repo root:

    python3 -m unittest discover -s tests -v
    # or: python3 tests/test_delivery_echo.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA_DIR = tempfile.mkdtemp(prefix="ilink-test-echo-")
os.environ["ILINK_DATA_DIR"] = DATA_DIR
import ilink  # noqa: E402


def _pin_paths(testcase):
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
    for p in (ilink.SEND_AUDIT_FILE, ilink.SEND_LEDGER_FILE,
              ilink.SEND_LEDGER_LOCK_FILE, ilink.DELIVERY_PENDING_FILE,
              ilink.QUOTE_CACHE_FILE):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def _run(func, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = func(*args, **kwargs)
    return code, buf.getvalue()


def _pending():
    try:
        with open(ilink.DELIVERY_PENDING_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _audit_entries():
    try:
        with open(ilink.SEND_AUDIT_FILE) as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


class RecordCheckTest(unittest.TestCase):
    def setUp(self):
        _pin_paths(self)

    def test_echo_confirms_and_removes(self):
        ilink._record_delivery_pending("m1", "u1", "c1", "text")
        ilink._record_delivery_pending("m2", "u1", "c2", "text")
        confirmed, unconfirmed = ilink._check_delivery_pending({"m1"})
        self.assertEqual(confirmed, ["m1"])
        self.assertEqual(unconfirmed, [])
        self.assertEqual(list(_pending()), ["m2"])

    def test_expire_reports_no_echo(self):
        now = int(time.time())
        with open(ilink.DELIVERY_PENDING_FILE, "w") as f:
            json.dump({"m-old": {"to": "u1", "client_id": "c-old",
                                  "at": now - 200, "kind": "text"}}, f)
        confirmed, unconfirmed = ilink._check_delivery_pending(set(),
                                                               now=now)
        self.assertEqual(confirmed, [])
        self.assertEqual(unconfirmed, ["m-old"])
        self.assertEqual(_pending(), {})
        no_echo = [e for e in _audit_entries()
                   if e.get("result") == "no_echo"]
        self.assertEqual(len(no_echo), 1)
        self.assertEqual(no_echo[0]["direction"], "delivery")
        self.assertEqual(no_echo[0]["to"], "u1")
        self.assertEqual(no_echo[0]["client_id"], "c-old")

    def test_fresh_without_echo_stays_pending(self):
        ilink._record_delivery_pending("m1", "u1", "c1", "text")
        confirmed, unconfirmed = ilink._check_delivery_pending(set())
        self.assertEqual((confirmed, unconfirmed), ([], []))
        self.assertIn("m1", _pending())
        self.assertEqual(_audit_entries(), [])

    def test_corrupt_file_tolerated(self):
        with open(ilink.DELIVERY_PENDING_FILE, "w") as f:
            f.write("garbage{")
        self.assertEqual(ilink._load_delivery_pending(), {})
        self.assertEqual(ilink._check_delivery_pending({"m1"}), ([], []))
        ilink._record_delivery_pending("m1", "u1", "c1", "text")
        self.assertIn("m1", _pending())

    def test_record_failure_never_changes_send_outcome(self):
        ilink.DELIVERY_PENDING_FILE = os.path.join(
            DATA_DIR, "no-such-dir", "delivery_pending.json")
        ilink._record_delivery_pending("m1", "u1", "c1", "text")  # no raise
        with mock.patch.object(
                ilink, "api",
                return_value={"code": 0, "message_id": "m9"}):
            code, out = _run(ilink.cmd_send, "u1", "ctx-1", "hi")
        self.assertEqual(code, 0)
        self.assertIn("SEND_OK", out)


class SendRecordsPendingTest(unittest.TestCase):
    def setUp(self):
        _pin_paths(self)

    def test_send_records_pending(self):
        with mock.patch.object(
                ilink, "api",
                return_value={"code": 0, "message_id": "m1"}):
            code, out = _run(ilink.cmd_send, "u1", "ctx-1", "hi")
        self.assertEqual(code, 0)
        self.assertIn("SEND_OK", out)
        ent = _pending().get("m1")
        self.assertIsNotNone(ent)
        self.assertEqual((ent["to"], ent["kind"]), ("u1", "text"))

    def test_proactive_records_pending(self):
        with mock.patch.object(
                ilink, "api",
                return_value={"code": 0, "message_id": "m2"}):
            code, out = _run(ilink.cmd_proactive, "u1", "hello")
        self.assertEqual(code, 0)
        self.assertIn("PROACTIVE_OK", out)
        self.assertIn("m2", _pending())


class PollMatchTest(unittest.TestCase):
    def setUp(self):
        _pin_paths(self)

    def test_poll_confirms_echo_and_expires_stale(self):
        now = int(time.time())
        with open(ilink.DELIVERY_PENDING_FILE, "w") as f:
            json.dump({
                "m1": {"to": "u1", "client_id": "c1", "at": now,
                       "kind": "text"},
                "m-old": {"to": "u1", "client_id": "c-old",
                          "at": now - 200, "kind": "text"},
            }, f)
        echo = {"message_id": "m1", "message_type": 2,
                "item_list": [{"type": 1,
                               "text_item": {"text": "hi"}}]}
        payload = {"msgs": [echo], "get_updates_buf": "BUF-2"}
        with mock.patch.object(ilink, "api", return_value=payload):
            code, out = _run(ilink.cmd_poll)
        self.assertEqual(code, 0)
        json.loads(out)  # poll output stays valid JSON
        self.assertEqual(_pending(), {})
        no_echo = [e for e in _audit_entries()
                   if e.get("result") == "no_echo"]
        self.assertEqual(len(no_echo), 1)
        self.assertEqual(no_echo[0]["client_id"], "c-old")


if __name__ == "__main__":
    unittest.main()
