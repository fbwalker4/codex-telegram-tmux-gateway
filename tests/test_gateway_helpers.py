import importlib.util
import os
from pathlib import Path
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

    def test_instance_from_tmux_session_name(self):
        self.assertEqual(self.gateway.instance_from_tmux_session_name("codex"), "")
        self.assertEqual(self.gateway.instance_from_tmux_session_name("codex-tools"), "tools")
        self.assertEqual(self.gateway.instance_from_tmux_session_name("codex-Tools Bot!"), "tools-bot")
        self.assertIsNone(self.gateway.instance_from_tmux_session_name("other"))
        self.assertIsNone(self.gateway.instance_from_tmux_session_name(""))

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
