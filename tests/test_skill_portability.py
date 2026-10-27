import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bookkeeping.skill_settings import BookkeepingSkillStore, BookkeepingSkillError


class SkillPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_saved_local_skill_follows_moved_settings_folder(self):
        old = self.root / "old"
        skill = old / "restored_skills" / "custom.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# custom instruction", encoding="utf-8")
        store = BookkeepingSkillStore(old / "skill.json")
        store.save_path(skill)
        self.assertEqual(json.loads(store.path.read_text())["relative_path"], "restored_skills/custom.md")
        new = self.root / "new"
        shutil.copytree(old, new)
        # The old folder still exists: prefer the new account's local file.
        (new / "restored_skills" / "custom.md").write_text("# moved instruction", encoding="utf-8")
        self.assertEqual(BookkeepingSkillStore(new / "skill.json").load()["content"], "# moved instruction")

    def test_legacy_windows_path_rebases_only_to_managed_local_suffix(self):
        file = self.root / "restored_skills" / "custom.md"
        file.parent.mkdir()
        file.write_text("# local instruction", encoding="utf-8")
        settings = self.root / "skill.json"
        settings.write_text(json.dumps({"version": 1, "path": r"C:\OtherComputer\Account\restored_skills\custom.md"}))
        self.assertEqual(BookkeepingSkillStore(settings, managed_paths=[file]).load()["content"], "# local instruction")
        settings.write_text(json.dumps({"version": 1, "path": r"C:\OtherComputer\unrelated\custom.md"}))
        with self.assertRaises(BookkeepingSkillError):
            BookkeepingSkillStore(settings, managed_paths=[file]).load()

    def test_relative_path_cannot_escape_account_folder(self):
        folder = self.root / "account"
        folder.mkdir()
        secret = self.root / "other.md"
        secret.write_text("# another account", encoding="utf-8")
        settings = folder / "skill.json"
        settings.write_text(json.dumps({"version": 1, "path": str(secret), "relative_path": "../other.md"}))
        with self.assertRaises(BookkeepingSkillError):
            BookkeepingSkillStore(settings).load()

    def test_mobile_selection_cannot_read_another_account_when_local_copy_missing(self):
        folder = self.root / "account"
        folder.mkdir()
        other = self.root / "other.md"
        other.write_text("# other account content", encoding="utf-8")
        settings = folder / "skill.json"
        settings.write_text(json.dumps({"version": 1, "path": str(other)}))
        with self.assertRaises(BookkeepingSkillError):
            BookkeepingSkillStore(settings, managed_paths=[folder / "bookkeeping.md"]).load()

    def test_explicit_unload_does_not_reenable_managed_skill(self):
        file = self.root / "custom.md"
        file.write_text("# custom", encoding="utf-8")
        store = BookkeepingSkillStore(self.root / "skill.json", managed_paths=[file])
        store.clear()
        self.assertIsNone(store.load())
