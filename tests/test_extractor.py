import os
import shutil
import tempfile
import unittest

from src.extractor import FantageExtractor, ScanSource


class ExtractorNamingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="fa_extractor_test_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_next_output_targets_use_base_names_when_free(self):
        folder_path, zip_path = FantageExtractor._next_output_targets(
            self.temp_dir,
            "Fantage_Extraction_User",
            "Fantage_Cache_User",
        )
        self.assertEqual(folder_path, os.path.join(self.temp_dir, "Fantage_Extraction_User"))
        self.assertEqual(zip_path, os.path.join(self.temp_dir, "Fantage_Cache_User.zip"))

    def test_next_output_targets_increment_when_prior_outputs_exist(self):
        os.makedirs(os.path.join(self.temp_dir, "Fantage_Extraction_User"))
        with open(os.path.join(self.temp_dir, "Fantage_Cache_User.zip"), "wb") as handle:
            handle.write(b"zip")

        folder_path, zip_path = FantageExtractor._next_output_targets(
            self.temp_dir,
            "Fantage_Extraction_User",
            "Fantage_Cache_User",
        )
        self.assertEqual(folder_path, os.path.join(self.temp_dir, "Fantage_Extraction_User_2"))
        self.assertEqual(zip_path, os.path.join(self.temp_dir, "Fantage_Cache_User_2.zip"))

    def test_next_output_targets_stay_in_sync_when_only_folder_exists(self):
        os.makedirs(os.path.join(self.temp_dir, "Fantage_Extraction_User"))

        folder_path, zip_path = FantageExtractor._next_output_targets(
            self.temp_dir,
            "Fantage_Extraction_User",
            "Fantage_Cache_User",
        )
        self.assertEqual(folder_path, os.path.join(self.temp_dir, "Fantage_Extraction_User_2"))
        self.assertEqual(zip_path, os.path.join(self.temp_dir, "Fantage_Cache_User_2.zip"))

    def test_should_skip_only_known_os_noise_files(self):
        self.assertTrue(FantageExtractor._should_skip_file(".DS_Store"))
        self.assertTrue(FantageExtractor._should_skip_file("Thumbs.db"))
        self.assertFalse(FantageExtractor._should_skip_file("worldmap.swf"))
        self.assertFalse(FantageExtractor._should_skip_file("global.js"))

    def test_copy_directory_preserves_full_fantage_tree(self):
        source_root = os.path.join(self.temp_dir, "source")
        output_root = os.path.join(self.temp_dir, "out")
        source_dir = os.path.join(source_root, "play.fantage.com")
        os.makedirs(os.path.join(source_dir, "nested"))

        fixtures = {
            os.path.join(source_dir, "worldmap.swf"): b"swf",
            os.path.join(source_dir, "cachedassets.xml"): b"xml",
            os.path.join(source_dir, "avatar.png"): b"png",
            os.path.join(source_dir, "index.html"): b"html",
            os.path.join(source_dir, "appversion.txt"): b"txt",
            os.path.join(source_dir, "nested", "topbar.jpg"): b"jpg",
            os.path.join(source_dir, "nested", "global.js"): b"js",
            os.path.join(source_dir, ".DS_Store"): b"ignore",
        }
        for path, data in fixtures.items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)

        extractor = FantageExtractor(output_root, lambda msg, pct: None)
        os.makedirs(output_root)
        extractor._copy_directory(source_dir, output_root, source_root)

        expected = {
            os.path.join(output_root, "play.fantage.com", "worldmap.swf"),
            os.path.join(output_root, "play.fantage.com", "cachedassets.xml"),
            os.path.join(output_root, "play.fantage.com", "avatar.png"),
            os.path.join(output_root, "play.fantage.com", "index.html"),
            os.path.join(output_root, "play.fantage.com", "appversion.txt"),
            os.path.join(output_root, "play.fantage.com", "nested", "topbar.jpg"),
            os.path.join(output_root, "play.fantage.com", "nested", "global.js"),
        }
        unexpected = {
            os.path.join(output_root, "play.fantage.com", ".DS_Store"),
        }

        for path in expected:
            self.assertTrue(os.path.exists(path), path)
        for path in unexpected:
            self.assertFalse(os.path.exists(path), path)

    def test_browser_scan_groups_output_by_browser_and_profile(self):
        profile_root = os.path.join(self.temp_dir, "profile")
        out_root = os.path.join(self.temp_dir, "out")
        files = {
            os.path.join(profile_root, "play.fantage.com", "login.html"): b"html",
            os.path.join(profile_root, "play.fantage.com", "js", "global.js"): b"js",
            os.path.join(profile_root, "play.fantage.com", "r1", "worldmap.swf"): b"swf",
        }
        for path, data in files.items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)

        extractor = FantageExtractor(out_root, lambda msg, pct: None)
        source = ScanSource(
            label="Google Chrome",
            root=profile_root,
            output_parts=("browser_caches", "Google Chrome", "Default", "Cache"),
            description="Google Chrome / Default / Cache",
        )

        extractor._scan_browser_source(source, out_root)

        expected = os.path.join(
            out_root,
            "browser_caches",
            "Google Chrome",
            "Default",
            "Cache",
            "play.fantage.com",
            "r1",
            "worldmap.swf",
        )
        self.assertTrue(os.path.exists(expected), expected)

    def test_browser_scan_does_not_copy_contextual_garbage_without_fantage_marker(self):
        profile_root = os.path.join(self.temp_dir, "profile")
        out_root = os.path.join(self.temp_dir, "out")
        files = {
            os.path.join(profile_root, "global_config.xml"): b"generic config",
            os.path.join(profile_root, "questlist_config.xml"): b"generic quest list",
            os.path.join(profile_root, "sounddata.xml"): b"generic sound data",
            os.path.join(profile_root, "world_loader.swf"): b"not fantage",
            os.path.join(profile_root, "data_1"): b"opaque but unrelated",
        }
        for path, data in files.items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)

        extractor = FantageExtractor(out_root, lambda msg, pct: None)
        source = ScanSource(
            label="Google Chrome",
            root=profile_root,
            output_parts=("browser_caches", "Google Chrome", "Default", "Cache"),
            description="Google Chrome / Default / Cache",
        )

        extractor._scan_browser_source(source, out_root)

        copied_files = []
        for root, _, filenames in os.walk(out_root):
            for name in filenames:
                copied_files.append(os.path.relpath(os.path.join(root, name), out_root))
        self.assertEqual(copied_files, [])

    def test_browser_scan_keeps_content_confirmed_file_without_path_marker(self):
        profile_root = os.path.join(self.temp_dir, "profile")
        out_root = os.path.join(self.temp_dir, "out")
        confirmed_path = os.path.join(profile_root, "world_loader.swf")
        os.makedirs(os.path.dirname(confirmed_path), exist_ok=True)
        with open(confirmed_path, "wb") as handle:
            handle.write(b"https://play.fantage.com/r1/world_loader.swf")

        extractor = FantageExtractor(out_root, lambda msg, pct: None)
        source = ScanSource(
            label="Google Chrome",
            root=profile_root,
            output_parts=("browser_caches", "Google Chrome", "Default", "Cache"),
            description="Google Chrome / Default / Cache",
        )

        extractor._scan_browser_source(source, out_root)

        expected = os.path.join(
            out_root,
            "browser_caches",
            "Google Chrome",
            "Default",
            "Cache",
            "world_loader.swf",
        )
        self.assertTrue(os.path.exists(expected), expected)

    def test_misc_scan_places_manual_fantage_folders_under_misc(self):
        home_root = os.path.join(self.temp_dir, "home")
        out_root = os.path.join(self.temp_dir, "out")
        path = os.path.join(home_root, "desktop", "manual dump", "play.fantage.com", "register.html")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"register")

        extractor = FantageExtractor(out_root, lambda msg, pct: None)
        source = ScanSource(
            label="Home",
            root=home_root,
            output_parts=("misc", "Home"),
            description="Misc / Home",
        )

        extractor._scan_misc_source(source, out_root, [])

        expected = os.path.join(
            out_root,
            "misc",
            "Home",
            "desktop",
            "manual dump",
            "play.fantage.com",
            "register.html",
        )
        self.assertTrue(os.path.exists(expected), expected)


if __name__ == "__main__":
    unittest.main()
