import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_gateway():
    spec = importlib.util.spec_from_file_location("gateway", ROOT / "COD_telegram_gateway.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GatewayHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gateway = load_gateway()

    def test_normalize_instance_name(self):
        self.assertEqual(self.gateway.normalize_instance_name(None), "")
        self.assertEqual(self.gateway.normalize_instance_name("default"), "")
        self.assertEqual(self.gateway.normalize_instance_name("Tools Bot!"), "tools-bot")

    def test_outbound_requires_explicit_instance_when_named_instances_exist(self):
        self.assertFalse(self.gateway.outbound_requires_explicit_instance("tools", ["tools"]))
        self.assertFalse(self.gateway.outbound_requires_explicit_instance("default", ["tools"]))
        self.assertFalse(self.gateway.outbound_requires_explicit_instance(None, []))
        self.assertTrue(self.gateway.outbound_requires_explicit_instance(None, ["tools"]))
        self.assertTrue(self.gateway.outbound_requires_explicit_instance("", ["tools"]))

    def test_operator_send_enabled(self):
        old_value = os.environ.get("CODEX_TELEGRAM_OPERATOR_SEND")
        try:
            os.environ["CODEX_TELEGRAM_OPERATOR_SEND"] = "1"
            self.assertTrue(self.gateway.operator_send_enabled())
            os.environ["CODEX_TELEGRAM_OPERATOR_SEND"] = "false"
            self.assertFalse(self.gateway.operator_send_enabled())
        finally:
            if old_value is None:
                os.environ.pop("CODEX_TELEGRAM_OPERATOR_SEND", None)
            else:
                os.environ["CODEX_TELEGRAM_OPERATOR_SEND"] = old_value

    def test_instance_from_tmux_session_name(self):
        self.assertEqual(self.gateway.instance_from_tmux_session_name("codex"), "")
        self.assertEqual(self.gateway.instance_from_tmux_session_name("codex-tools"), "tools")
        self.assertEqual(self.gateway.instance_from_tmux_session_name("codex-Tools Bot!"), "tools-bot")
        self.assertIsNone(self.gateway.instance_from_tmux_session_name("other"))
        self.assertIsNone(self.gateway.instance_from_tmux_session_name(""))

    def test_status_rejects_mismatched_env_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env.codex-telegram-tools"
            env_path.write_text(
                "CODEX_TELEGRAM_INSTANCE=other\n"
                "TELEGRAM_BOT_TOKEN=token\n"
                "TELEGRAM_OWNER_CHAT_ID=123\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.pop("TMUX", None)
            env["CODEX_TELEGRAM_INSTANCE"] = "tools"
            env["CODEX_TELEGRAM_ENV"] = str(env_path)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "COD_telegram_gateway.py"), "status"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=10,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Gateway instance mismatch", proc.stderr or proc.stdout)

    def test_sticky_threads_are_disabled_by_default(self):
        old_value = os.environ.get("COD_TELEGRAM_STICKY_THREADS")
        try:
            os.environ.pop("COD_TELEGRAM_STICKY_THREADS", None)
            self.assertIsNone(self.gateway.current_message_thread_id("123"))
        finally:
            if old_value is not None:
                os.environ["COD_TELEGRAM_STICKY_THREADS"] = old_value

    def test_thread_prompt_includes_explicit_reply_command(self):
        prompt = self.gateway.build_codex_prompt(
            {
                "text": "threaded",
                "message_thread_id": 456,
                "attachments": [],
            }
        )
        self.assertIn("[Telegram thread 456]", prompt)
        self.assertIn("message_thread_id: 456", prompt)
        self.assertIn("Reply command:", prompt)
        self.assertIn("User message:", prompt)
        self.assertIn("--message-thread-id 456", prompt)

    def test_active_keepalive_route_preserves_thread(self):
        old_read_state = self.gateway.read_state
        try:
            self.gateway.read_state = lambda: {
                "typing_keepalive": {
                    "chat_id": "123",
                    "message_thread_id": 456,
                    "until": 9999999999,
                }
            }
            self.assertEqual(self.gateway.active_keepalive_route(), ("123", 456))
        finally:
            self.gateway.read_state = old_read_state

    def test_sender_authorized_requires_owner_user_for_groups(self):
        old_chat = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
        old_user = os.environ.get("TELEGRAM_OWNER_USER_ID")
        try:
            os.environ["TELEGRAM_OWNER_CHAT_ID"] = "-100"
            os.environ.pop("TELEGRAM_OWNER_USER_ID", None)
            self.assertTrue(
                self.gateway.sender_authorized({"chat_id": "-100", "chat_type": "private", "from_id": "1"})
            )
            self.assertFalse(
                self.gateway.sender_authorized({"chat_id": "-100", "chat_type": "supergroup", "from_id": "1"})
            )
            os.environ["TELEGRAM_OWNER_USER_ID"] = "1"
            self.assertTrue(
                self.gateway.sender_authorized({"chat_id": "-100", "chat_type": "supergroup", "from_id": "1"})
            )
            self.assertFalse(
                self.gateway.sender_authorized({"chat_id": "-100", "chat_type": "supergroup", "from_id": "2"})
            )
        finally:
            if old_chat is None:
                os.environ.pop("TELEGRAM_OWNER_CHAT_ID", None)
            else:
                os.environ["TELEGRAM_OWNER_CHAT_ID"] = old_chat
            if old_user is None:
                os.environ.pop("TELEGRAM_OWNER_USER_ID", None)
            else:
                os.environ["TELEGRAM_OWNER_USER_ID"] = old_user

    def test_stale_permission_callback_does_not_send_keys(self):
        old_chat = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
        old_user = os.environ.get("TELEGRAM_OWNER_USER_ID")
        old_permission_keys = os.environ.get("COD_TELEGRAM_APPROVE_KEYS")
        old_read_state = self.gateway.read_state
        old_write_state = self.gateway.write_state
        old_answer_callback = self.gateway.answer_callback
        old_run_tmux = self.gateway.run_tmux
        old_capture = self.gateway.capture_tmux_text
        state = {
            "pending_permission": {
                "signature": "oldsig",
                "target": "codex:0.0",
                "status": "sent",
            }
        }
        sent_keys = []
        try:
            os.environ["TELEGRAM_OWNER_CHAT_ID"] = "123"
            os.environ.pop("TELEGRAM_OWNER_USER_ID", None)
            os.environ["COD_TELEGRAM_APPROVE_KEYS"] = "C-m"
            self.gateway.read_state = lambda: state
            self.gateway.write_state = lambda new_state: state.update(new_state)
            self.gateway.answer_callback = lambda *args, **kwargs: None

            def fake_run_tmux(args, input_text=None):
                if args and args[0] == "send-keys":
                    sent_keys.append(args)
                return subprocess.CompletedProcess(args, 0, "", "")

            self.gateway.run_tmux = fake_run_tmux
            self.gateway.capture_tmux_text = lambda target, lines=80: "prompt changed"
            self.gateway.handle_permission_callback(
                {
                    "callback_query_id": "cb",
                    "chat_id": "123",
                    "chat_type": "private",
                    "from_id": "1",
                    "data": "perm:oldsig:approve",
                }
            )
            self.assertEqual(sent_keys, [])
            self.assertEqual(state["pending_permission"]["status"], "sent")
        finally:
            if old_chat is None:
                os.environ.pop("TELEGRAM_OWNER_CHAT_ID", None)
            else:
                os.environ["TELEGRAM_OWNER_CHAT_ID"] = old_chat
            if old_user is None:
                os.environ.pop("TELEGRAM_OWNER_USER_ID", None)
            else:
                os.environ["TELEGRAM_OWNER_USER_ID"] = old_user
            if old_permission_keys is None:
                os.environ.pop("COD_TELEGRAM_APPROVE_KEYS", None)
            else:
                os.environ["COD_TELEGRAM_APPROVE_KEYS"] = old_permission_keys
            self.gateway.read_state = old_read_state
            self.gateway.write_state = old_write_state
            self.gateway.answer_callback = old_answer_callback
            self.gateway.run_tmux = old_run_tmux
            self.gateway.capture_tmux_text = old_capture

    def test_permission_callback_sending_status_does_not_send_keys(self):
        old_chat = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
        old_user = os.environ.get("TELEGRAM_OWNER_USER_ID")
        old_read_state = self.gateway.read_state
        old_answer_callback = self.gateway.answer_callback
        old_run_tmux = self.gateway.run_tmux
        state = {
            "pending_permission": {
                "signature": "oldsig",
                "target": "codex:0.0",
                "status": "sending",
            }
        }
        sent_keys = []
        try:
            os.environ["TELEGRAM_OWNER_CHAT_ID"] = "123"
            os.environ.pop("TELEGRAM_OWNER_USER_ID", None)
            self.gateway.read_state = lambda: state
            self.gateway.answer_callback = lambda *args, **kwargs: None

            def fake_run_tmux(args, input_text=None):
                if args and args[0] == "send-keys":
                    sent_keys.append(args)
                return subprocess.CompletedProcess(args, 0, "", "")

            self.gateway.run_tmux = fake_run_tmux
            self.gateway.handle_permission_callback(
                {
                    "callback_query_id": "cb",
                    "chat_id": "123",
                    "chat_type": "private",
                    "from_id": "1",
                    "data": "perm:oldsig:approve",
                }
            )
            self.assertEqual(sent_keys, [])
        finally:
            if old_chat is None:
                os.environ.pop("TELEGRAM_OWNER_CHAT_ID", None)
            else:
                os.environ["TELEGRAM_OWNER_CHAT_ID"] = old_chat
            if old_user is None:
                os.environ.pop("TELEGRAM_OWNER_USER_ID", None)
            else:
                os.environ["TELEGRAM_OWNER_USER_ID"] = old_user
            self.gateway.read_state = old_read_state
            self.gateway.answer_callback = old_answer_callback
            self.gateway.run_tmux = old_run_tmux

    def test_image_magic_detection(self):
        self.assertEqual(self.gateway.image_extension_from_magic(b"\xff\xd8\xffabc"), ".jpg")
        self.assertEqual(self.gateway.image_extension_from_magic(b"\x89PNG\r\n\x1a\nabc"), ".png")
        self.assertEqual(self.gateway.image_extension_from_magic(b"GIF89abc"), ".gif")
        self.assertEqual(self.gateway.image_extension_from_magic(b"RIFFxxxxWEBPabc"), ".webp")
        self.assertIsNone(self.gateway.image_extension_from_magic(b"not-an-image"))

    def test_attachment_metadata_validation(self):
        ok, reason = self.gateway.validate_attachment_metadata(
            {"kind": "document", "mime_type": "image/png", "file_name": "x.png", "file_size": 10}
        )
        self.assertTrue(ok, reason)

        ok, reason = self.gateway.validate_attachment_metadata(
            {"kind": "document", "mime_type": "text/plain", "file_name": "x.txt", "file_size": 10}
        )
        self.assertFalse(ok)
        self.assertIn("Unsupported", reason)

        old_limit = os.environ.get("COD_TELEGRAM_MAX_IMAGE_BYTES")
        os.environ["COD_TELEGRAM_MAX_IMAGE_BYTES"] = "5"
        try:
            ok, reason = self.gateway.validate_attachment_metadata(
                {"kind": "photo", "file_name": "x.jpg", "file_size": 10}
            )
        finally:
            if old_limit is None:
                os.environ.pop("COD_TELEGRAM_MAX_IMAGE_BYTES", None)
            else:
                os.environ["COD_TELEGRAM_MAX_IMAGE_BYTES"] = old_limit
        self.assertFalse(ok)
        self.assertIn("too large", reason)

    def test_image_prompt_contains_path_and_sanitizes_caption(self):
        prompt = self.gateway.build_codex_prompt(
            {
                "message_id": 123,
                "text": "hello\x00\nworld",
                "attachments": [
                    {
                        "local_path": "/tmp/test.png",
                        "mime_type": "image/png",
                        "width": 10,
                        "height": 20,
                        "saved_bytes": 30,
                    }
                ],
            }
        )
        self.assertIn("[Telegram image message]", prompt)
        self.assertIn("/tmp/test.png", prompt)
        self.assertNotIn("\x00", prompt)
        self.assertIn('"""', prompt)


if __name__ == "__main__":
    unittest.main()
