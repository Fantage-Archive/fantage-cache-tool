import os
import shutil
import tempfile
import unittest
import zlib

from src.scanner_utils import (
    classify_directory,
    is_contextual_candidate,
    is_opaque_cache_file,
    is_related,
    normalize_cache_name,
)


class ScannerUtilsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="fa_scanner_test_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_normalize_cache_name_strips_ie_suffixes(self):
        self.assertEqual(normalize_cache_name("worldmap~1.swf"), "worldmap.swf")
        self.assertEqual(normalize_cache_name("fantage_com[2].htm"), "fantage_com.htm")

    def test_related_flash_sharedobject_directory_is_detected(self):
        path = os.path.join(self.temp_dir, "loginserverselect.swf", "UserInfo.sol")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"UserInfo")
        self.assertTrue(is_related(path))

    def test_contextual_pet_asset_name_is_accepted(self):
        self.assertTrue(is_contextual_candidate("springy_blink~1.png"))
        self.assertFalse(is_contextual_candidate("g~1.js"))

    def test_opaque_cache_filename_needs_structure(self):
        self.assertTrue(is_opaque_cache_file("data_1"))
        self.assertTrue(is_opaque_cache_file("f_0000abcd"))
        self.assertFalse(is_contextual_candidate("data_1"))
        self.assertFalse(is_contextual_candidate("f_0000abcd"))
        self.assertFalse(is_contextual_candidate("totally-random"))

    def test_mixed_cache_folder_stays_selective_with_one_related_subtree(self):
        copy_mode = classify_directory(
            os.path.join(self.temp_dir, "mini_pixel cache 2"),
            ["www.fantage.com", "ads.socialvi.be"],
            [
                "mainscreen~1.swf",
                "worldmap~1.swf",
                "cachedassets~1.xml",
                "springy_blink~1.png",
                "global_config~1.xml",
            ],
        )
        self.assertEqual(copy_mode, "files")

    def test_asset_bundle_directory_is_promoted_to_full_copy(self):
        copy_mode = classify_directory(
            os.path.join(self.temp_dir, "renamed cache dump"),
            ["SHRT", "PANT", "HAIR", "FACE"],
            ["global_config.xml", "cachedassets.xml"],
        )
        self.assertEqual(copy_mode, "all")

    def test_hash_prefixed_fantage_dirs_are_promoted_in_cache_dump(self):
        copy_mode = classify_directory(
            os.path.join(self.temp_dir, "ambie cache"),
            ["#play.fantage.com", "#secure.fantage.com"],
            ["data_1"],
        )
        self.assertEqual(copy_mode, "all")

    def test_generic_cache_named_folder_is_not_promoted_without_structure(self):
        copy_mode = classify_directory(
            os.path.join(self.temp_dir, "software cache 2"),
            ["ads.socialvi.be", "cdn.example.com"],
            ["data_1", "ad.js"],
        )
        self.assertIsNone(copy_mode)

    def test_mixed_browser_root_stays_selective(self):
        copy_mode = classify_directory(
            os.path.join(self.temp_dir, "chrome cache root"),
            ["play.fantage.com", "www.fantage.com", "google.com", "cdn.example.com", "facebook.com"],
            ["index", "data_1"],
        )
        self.assertEqual(copy_mode, "files")

    def test_opaque_cache_blob_is_detected_from_decompressed_swf_content(self):
        path = os.path.join(self.temp_dir, "f_000123")
        payload = b"play.fantage.com/r1/worldmap.swf"
        blob = b"CWS\x09\x00\x00\x00\x00" + zlib.compress(payload)
        with open(path, "wb") as handle:
            handle.write(blob)
        self.assertTrue(is_related(path))

    def test_unrelated_file_stays_unmatched(self):
        path = os.path.join(self.temp_dir, "ads.js")
        with open(path, "wb") as handle:
            handle.write(b"console.log('ads only');")
        self.assertFalse(is_related(path))


if __name__ == "__main__":
    unittest.main()
