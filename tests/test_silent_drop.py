#!/usr/bin/env python3
"""Tests for the issue #8 silent-drop fix (2026-11-23).

A code-0 sendmessage reply without message_id is a silent drop: the
server accepted nothing. Text sends (cmd_send, cmd_proactive and the
bind welcome segment) must now require message_id, like media sends
already did — so a drop surfaces as SEND_FAILED / PROACTIVE_FAILED
instead of a false SEND_OK / PROACTIVE_OK, and the send ledger must
not record it as sent.

Run from the repo root:

    python3 -m unittest discover -s tests -v
    # or: python3 tests/test_silent_drop.py
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
DATA_DIR = tempfile.mkdtemp(prefix="ilink-test-silent-drop-")
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
    with open(ilink.SESSION_FILE, "w") as f:
        json.dump({"bot_token": "tok"}, f)
    with open(ilink.CONTACTS_FILE, "w") as f:
        json.dump({"u1": {"context_token": "ctx-1"}}, f)
    for p in (ilink.SEND_AUDIT_FILE, ilink.SEND_LEDGER_FILE,
              ilink.SEND_LEDGER_LOCK_FILE):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def _run(func, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = func(*args, **kwargs)
    return code, buf.getvalue()


def _ledger():
    try:
        with open(ilink.SEND_LEDGER_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _audit_entries():
    try:
        with open(ilink.SEND_AUDIT_FILE) as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


class SendSilentDropTest(unittest.TestCase):
    def setUp(self):
        _pin_paths(self)

    def test_send_code0_without_message_id_fails(self):
        # Issue #8's exact signature: HTTP 200, {"ret": 0}, no
        # message_id. Must not be SEND_OK, must not mark the ledger.
        api = mock.Mock(return_value={"code": 0, "ret": 0})
        with mock.patch.object(ilink, "api", api):
            code, out = _run(ilink.cmd_send, "u1", "ctx-1", "hi",
                             key="sd-1")
        self.assertEqual(code, 1)
        self.assertIn("SEND_FAILED", out)
        self.assertNotIn("SEND_OK", out)
        self.assertEqual(api.call_count, 1)  # app errors do not retry
        self.assertEqual(_ledger()["sd-1"]["status"], "intent")
        self.assertEqual(_audit_entries()[0]["result"], "app_error")

    def test_send_code0_with_message_id_still_ok(self):
        api = mock.Mock(return_value={"code": 0, "message_id": "m"})
        with mock.patch.object(ilink, "api", api):
            code, out = _run(ilink.cmd_send, "u1", "ctx-1", "hi",
                             key="sd-2")
        self.assertEqual(code, 0)
        self.assertIn("SEND_OK", out)
        self.assertEqual(_ledger()["sd-2"]["status"], "sent")


class ProactiveSilentDropTest(unittest.TestCase):
    def setUp(self):
        _pin_paths(self)

    def test_silent_drop_both_attempts_fails(self):
        # First attempt drops silently: the tokenless retry runs (same
        # client_id, server dedupe covers it), the second attempt drops
        # too, and the push must fail loudly instead of PROACTIVE_OK.
        cids = []
        api = mock.Mock(side_effect=lambda *a, **k: (
            cids.append(a[2]["msg"]["client_id"]),
            {"code": 0, "ret": 0},
        )[1])
        with mock.patch.object(ilink, "api", api):
            code, out = _run(ilink.cmd_proactive, "u1", "hello",
                             key="sd-3")
        self.assertEqual(code, 1)
        self.assertIn("RETRY_WITHOUT_TOKEN", out)
        self.assertIn("PROACTIVE_FAILED", out)
        self.assertNotIn("PROACTIVE_OK", out)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(len(set(cids)), 1)  # same client_id, deduped
        self.assertEqual(_ledger()["sd-3"]["status"], "intent")

    def test_silent_drop_then_recovery_ok(self):
        # Drop on the first attempt, message_id on the tokenless retry:
        # the push recovers and is recorded as sent.
        responses = iter([{"code": 0, "ret": 0},
                          {"code": 0, "message_id": "mid-9"}])
        api = mock.Mock(side_effect=lambda *a, **k: next(responses))
        with mock.patch.object(ilink, "api", api):
            code, out = _run(ilink.cmd_proactive, "u1", "hello",
                             key="sd-4")
        self.assertEqual(code, 0)
        self.assertIn("PROACTIVE_OK", out)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(_ledger()["sd-4"]["status"], "sent")


class WelcomeSilentDropTest(unittest.TestCase):
    def setUp(self):
        _pin_paths(self)

    def test_welcome_segment_code0_without_message_id_fails(self):
        # The bind welcome bubbles used to accept code 0 alone, so a
        # silent drop during bind would be recorded as delivered and
        # the owner would never get the welcome.
        with mock.patch.object(ilink, "_send_raw",
                               return_value={"code": 0, "ret": 0}):
            ok, code = ilink._send_welcome_segment(
                "u1", "ctx-1", "hi", "tok", "cid-1")
        self.assertFalse(ok)
        with mock.patch.object(
                ilink, "_send_raw",
                return_value={"code": 0, "message_id": "m"}):
            ok, code = ilink._send_welcome_segment(
                "u1", "ctx-1", "hi", "tok", "cid-2")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
