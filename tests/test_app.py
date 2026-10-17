import json
from io import BytesIO
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from mutagen.id3 import ID3
from PIL import Image
from tkinterdnd2 import COPY, REFUSE_DROP

import app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.settings_patch = patch.object(app, "SETTINGS", self.folder / "settings.json")
        self.settings_patch.start()
        self.window = app.App()
        self.window.withdraw()
        self.window.url.set("https://youtu.be/test")
        self.destination = self.folder / "저장 폴더"
        self.window.folder.set(str(self.destination))
        self.errors = []
        self.error_patch = patch.object(app.messagebox, "showerror", side_effect=lambda *args, **kwargs: self.errors.append(args))
        self.error_patch.start()
        cover = BytesIO()
        Image.new("RGB", (16, 16), "blue").save(cover, format="JPEG")
        self.cover = cover.getvalue()

        def fixture(url, folder, emit, cancel):
            result = folder / "테스트 음원.mp3"
            result.write_bytes(b"converted mp3 fixture")
            emit("metadata", {"title": "테스트 음원", "thumbnail": self.cover})
            return result

        self.extract_patch = patch.object(app, "extract_mp3", side_effect=fixture)
        self.extract_mock = self.extract_patch.start()

    def tearDown(self):
        self.window.update_idletasks()
        for callback in self.window.tk.call("after", "info"):
            self.window.after_cancel(callback)
        self.window.clear_pending()
        self.window.destroy()
        self.extract_patch.stop()
        self.error_patch.stop()
        self.settings_patch.stop()
        self.temporary.cleanup()

    def wait_for_job(self):
        deadline = time.monotonic() + 5
        while self.window.busy and time.monotonic() < deadline:
            self.window.update()
            time.sleep(.01)
        self.assertFalse(self.window.busy)

    def test_manual_extract_does_not_touch_destination_then_saves(self):
        self.assertFalse(self.window.auto_save.get())
        self.assertTrue(self.window.save_button.cget("state") == "disabled")
        self.window.start()
        self.wait_for_job()
        temporary_result = self.window.pending
        self.assertTrue(temporary_result.is_file())
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.window.save_button.cget("state") == "normal")
        self.window.save()
        self.wait_for_job()
        output = self.destination / "테스트 음원.mp3"
        self.assertEqual(ID3(output)["TIT2"].text, ["테스트 음원"])
        self.assertEqual(ID3(output).getall("APIC")[0].data, self.cover)
        self.assertTrue(output.read_bytes().endswith(b"converted mp3 fixture"))
        self.assertTrue(temporary_result.exists())
        self.assertTrue(self.window.pending_saved)
        self.assertTrue(self.window.save_button.cget("state") == "normal")
        self.window.clear_pending()
        self.assertFalse(temporary_result.exists())

    def test_auto_save_and_settings_are_remembered(self):
        self.window.auto_save_check.toggle()
        self.assertTrue(self.window.auto_save.get())
        self.window.start()
        self.wait_for_job()
        self.assertTrue((self.destination / "테스트 음원.mp3").is_file())
        self.assertTrue(self.window.pending.is_file())
        self.assertTrue(self.window.pending_saved)
        self.assertEqual(self.window.save_button.cget("state"), "normal")
        self.assertEqual(app.load_settings(), {"folder": str(self.destination), "auto_save": True})
        self.window.metadata_editor.fields["artist"].set("수정한 가수")
        second_folder = self.folder / "다른 저장 폴더"
        self.window.folder.set(str(second_folder))
        self.window.save_button.invoke()
        self.wait_for_job()
        self.assertEqual(str(ID3(second_folder / "테스트 음원.mp3")["TPE1"]), "수정한 가수")
        self.assertNotIn("TPE1", ID3(self.destination / "테스트 음원.mp3"))
        self.assertEqual(self.window.save_button.cget("state"), "normal")
        self.assertEqual(self.extract_mock.call_count, 1)

    def test_open_folder_opens_selected_path(self):
        self.destination.mkdir()
        with patch.object(app.os, "startfile") as open_folder:
            self.window.open_folder_button.invoke()
        open_folder.assert_called_once_with(str(self.destination))

    def test_open_missing_folder_does_not_create_it(self):
        with patch.object(app.os, "startfile") as open_folder, patch.object(app.messagebox, "showwarning") as warning:
            self.window.open_folder_button.invoke()
        open_folder.assert_not_called()
        warning.assert_called_once()
        self.assertFalse(self.destination.exists())

    def test_save_failure_keeps_extracted_file_for_retry(self):
        self.window.start()
        self.wait_for_job()
        original = self.window.pending
        blocked = self.folder / "ファイル.txt"
        blocked.write_text("existing", encoding="utf-8")
        self.window.folder.set(str(blocked))
        self.window.save()
        self.wait_for_job()
        self.assertTrue(self.errors)
        self.assertEqual(self.window.pending, original)
        self.assertTrue(original.is_file())
        self.assertTrue(self.window.save_button.cget("state") == "normal")
        self.window.folder.set(str(self.destination))
        self.window.save()
        self.wait_for_job()
        self.assertTrue((self.destination / "테스트 음원.mp3").is_file())

    def test_unsaved_result_is_kept_if_new_extract_is_declined(self):
        self.window.start()
        self.wait_for_job()
        original = self.window.pending
        with patch.object(app.messagebox, "askyesno", return_value=False):
            self.window.start()
        self.assertEqual(self.window.pending, original)
        self.assertTrue(original.is_file())
        self.assertFalse(self.window.busy)

    def test_legacy_settings_default_to_manual_save(self):
        app.SETTINGS.write_text(json.dumps({"folder": str(self.destination)}), encoding="utf-8")
        self.assertEqual(app.load_settings(), {"folder": str(self.destination), "auto_save": False})

    def test_image_drop_supports_spaces_and_korean_and_is_saved(self):
        image = self.folder / "직접 고른 커버 이미지.png"
        Image.new("RGBA", (40, 20), (255, 0, 0, 128)).save(image)
        editor = self.window.metadata_editor
        event = SimpleNamespace(data=self.window.tk.call("list", str(image)))
        # Tcl may return a tuple for list; drop payloads are strings from native TkDnD.
        event.data = self.window.tk.call("format", "%s", event.data)
        self.assertEqual(editor.on_drop(event), COPY)
        self.assertEqual(editor.cover_mode.get(), "file")
        selected_cover = editor.custom_cover
        editor.fields["artist"].set("테스트 가수")
        editor.fields["album"].set("테스트 앨범")
        self.window.start()
        self.wait_for_job()
        self.window.save()
        self.wait_for_job()
        tags = ID3(self.destination / "테스트 음원.mp3")
        self.assertEqual(tags["TPE1"].text, ["테스트 가수"])
        self.assertEqual(tags["TALB"].text, ["테스트 앨범"])
        self.assertEqual(tags.getall("APIC")[0].data, selected_cover)

    def test_drop_is_rejected_while_working(self):
        self.window.set_busy(True)
        editor = self.window.metadata_editor
        self.assertEqual(editor.on_drop(SimpleNamespace(data="bad")), REFUSE_DROP)
        self.assertIsNone(editor.custom_cover)
        self.window.set_busy(False)

    def test_no_cover_option_saves_without_embedded_picture(self):
        self.window.metadata_editor.controls[0].invoke()
        self.window.auto_save.set(True)
        self.window.start()
        self.wait_for_job()
        self.assertEqual(ID3(self.destination / "테스트 음원.mp3").getall("APIC"), [])

    def test_missing_thumbnail_keeps_result_until_cover_is_chosen(self):
        self.window.start()
        self.wait_for_job()
        self.window.metadata_editor.thumbnail = None
        with patch.object(app.messagebox, "showwarning") as warning:
            self.window.save()
        warning.assert_called_once()
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.window.pending.is_file())
        self.window.metadata_editor.cover_mode.set("none")
        self.window.save()
        self.wait_for_job()
        self.assertTrue((self.destination / "테스트 음원.mp3").exists())

    def test_metadata_panel_collapses_without_losing_fields(self):
        self.window.update_idletasks()
        editor = self.window.metadata_editor
        editor.fields["album"].set("앨범 유지")
        self.assertFalse(self.window.metadata_visible.get())
        self.assertFalse(self.window.metadata_panel.winfo_manager())
        self.window.metadata_toggle.toggle()
        self.window.update_idletasks()
        self.window.metadata_toggle.toggle()
        self.assertFalse(self.window.metadata_visible.get())
        self.assertFalse(self.window.metadata_panel.winfo_manager())
        self.assertFalse(self.window.metadata_separator.winfo_manager())
        self.window.update_idletasks()
        self.window.metadata_toggle.toggle()
        self.assertTrue(self.window.metadata_visible.get())
        self.assertEqual(self.window.metadata_panel.winfo_manager(), "grid")
        self.assertEqual(editor.fields["album"].get(), "앨범 유지")

    def test_source_defaults_refresh_without_overwriting_user_edits(self):
        editor = self.window.metadata_editor
        editor.apply_source({"title": "첫 번째 영상", "artist": "원본 가수"})
        editor.fields["artist"].set("직접 입력")
        editor.apply_source({"title": "다음 영상", "artist": "다른 원본 가수"})
        self.assertEqual(editor.fields["title"].get(), "다음 영상")
        self.assertEqual(editor.fields["artist"].get(), "직접 입력")


if __name__ == "__main__":
    unittest.main()
