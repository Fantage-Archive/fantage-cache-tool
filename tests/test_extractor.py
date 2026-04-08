import os
import shutil
import tempfile
import unittest

from src.extractor import FantageExtractor


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

    def test_should_copy_file_limits_output_extensions(self):
        self.assertTrue(FantageExtractor._should_copy_file("worldmap.swf"))
        self.assertTrue(FantageExtractor._should_copy_file("cachedassets.xml"))
        self.assertTrue(FantageExtractor._should_copy_file("springy.png"))
        self.assertTrue(FantageExtractor._should_copy_file("photo.jpg"))
        self.assertTrue(FantageExtractor._should_copy_file("photo.jpeg"))
        self.assertTrue(FantageExtractor._should_copy_file("username.sol"))
        self.assertFalse(FantageExtractor._should_copy_file("index.html"))
        self.assertFalse(FantageExtractor._should_copy_file("appversion.txt"))
        self.assertFalse(FantageExtractor._should_copy_file("global.js"))

    def test_copy_directory_only_copies_allowed_extensions(self):
        source_root = os.path.join(self.temp_dir, "source")
        output_root = os.path.join(self.temp_dir, "out")
        source_dir = os.path.join(source_root, "play.fantage.com")
        os.makedirs(os.path.join(source_dir, "nested"))

        fixtures = {
            os.path.join(source_dir, "worldmap.swf"): b"swf",
            os.path.join(source_dir, "cachedassets.xml"): b"xml",
            os.path.join(source_dir, "avatar.png"): b"png",
            os.path.join(source_dir, "username.sol"): b"sol",
            os.path.join(source_dir, "index.html"): b"html",
            os.path.join(source_dir, "appversion.txt"): b"txt",
            os.path.join(source_dir, "nested", "topbar.jpg"): b"jpg",
            os.path.join(source_dir, "nested", "global.js"): b"js",
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
            os.path.join(output_root, "play.fantage.com", "username.sol"),
            os.path.join(output_root, "play.fantage.com", "nested", "topbar.jpg"),
        }
        unexpected = {
            os.path.join(output_root, "play.fantage.com", "index.html"),
            os.path.join(output_root, "play.fantage.com", "appversion.txt"),
            os.path.join(output_root, "play.fantage.com", "nested", "global.js"),
        }

        for path in expected:
            self.assertTrue(os.path.exists(path), path)
        for path in unexpected:
            self.assertFalse(os.path.exists(path), path)


if __name__ == "__main__":
    unittest.main()
