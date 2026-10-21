import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

import import_models
import photo_import as pi
import wardrobe as w


def _region(
    color=(180, 40, 40),
    category="Tops",
    folder="tops",
    friendly="top",
    label="Upper-clothes",
    confidence=0.8,
    size=(80, 100),
):
    return pi.Region(
        label,
        category,
        folder,
        friendly,
        Image.new("RGB", size, color),
        confidence,
    )


class ScriptedFinder(pi.ClothesFinder):
    def __init__(self, batches):
        self.batches = [list(batch) for batch in batches]
        self.calls = 0

    def find(self, image):
        self.calls += 1
        if not self.batches:
            return []
        return self.batches.pop(0)


class MeanEmbedder(pi.Embedder):
    def embed(self, image):
        pixels = np.asarray(image.convert("RGB").resize((8, 8)), dtype=np.float32)
        mean = pixels.mean(axis=(0, 1))
        norm = float(np.linalg.norm(mean)) or 1.0
        return (mean / norm).tolist()


class MutatingFinder(pi.ClothesFinder):
    def __init__(self, path: Path):
        self.path = path

    def find(self, image):
        self.path.write_bytes(self.path.read_bytes() + b"\x00")
        return [_region()]


def _photo(folder: Path, name: str, color=(30, 30, 30), size=(48, 64)) -> Path:
    path = folder / name
    Image.new("RGB", size, color).save(path, "PNG")
    return path


def _empty_closet(root: Path):
    return w.load_items(root / "wardrobe_db.csv"), w.load_outfits(root / "outfits_db.csv")


class PhotoImportTests(unittest.TestCase):
    def test_scan_keeps_originals_and_writes_crops_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            photo = _photo(source, "day.png")
            before = photo.read_bytes()
            signature = photo.stat().st_mtime_ns
            finder = ScriptedFinder([[_region()]])
            updates = list(pi.scan_folder(source, output, finder, MeanEmbedder()))
            self.assertEqual(photo.read_bytes(), before)
            self.assertEqual(photo.stat().st_mtime_ns, signature)
            self.assertEqual(updates[-1].found, 1)
            pending = list((output / "pending").glob("*.png"))
            self.assertEqual(len(pending), 1)
            self.assertTrue(pi._is_relative_to(pending[0], output))
            state = pi.load_state(output)
            self.assertEqual(state["files"][str(photo.resolve())]["error"], "")
            self.assertEqual(len(pi.pending_garments(output)), 1)
            items, _outfits = _empty_closet(root)
            self.assertTrue(items.empty)

    def test_approve_adds_a_closet_row_and_reject_cannot_delete_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            photo = _photo(source, "shirt.png", color=(180, 40, 40))
            list(pi.scan_folder(source, output, ScriptedFinder([[_region()]]), MeanEmbedder()))
            pending = pi.pending_garments(output)[0]
            items, outfits = _empty_closet(root)
            items, outfits = pi.approve_garment(
                output,
                pending["id"],
                items,
                outfits,
                name="Red top",
                category="Tops",
                color="Red",
                season="Summer",
            )
            saved = Path(items.iloc[0]["Image_Path"])
            self.assertEqual(saved.parent.name, "tops")
            self.assertTrue(saved.is_file())
            self.assertFalse((output / "pending" / saved.name).exists())
            self.assertEqual(items.iloc[0]["Source_Photo"], str(photo.resolve()))
            self.assertEqual(items.iloc[0]["Sub-Category"], "Red top")
            self.assertTrue(photo.is_file())
            items, outfits = w.delete_item(items, outfits, int(items.iloc[0]["ID"]), root)
            self.assertTrue(saved.is_file())
            self.assertTrue(photo.is_file())

            other = _photo(source, "keep.png")
            before_other = other.read_bytes()
            pi.save_state(
                output,
                {
                    "version": 1,
                    "files": {},
                    "garments": {
                        "danger": {
                            "id": "danger",
                            "status": "pending",
                            "crop_path": str(other),
                        }
                    },
                },
            )
            pi.reject_garment(output, "danger")
            self.assertTrue(other.is_file())
            self.assertEqual(other.read_bytes(), before_other)

    def test_reject_removes_only_the_pending_crop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            photo = _photo(source, "hat.png")
            list(
                pi.scan_folder(
                    source,
                    output,
                    ScriptedFinder([[_region(category="Accessories", folder="accessories", friendly="hat", label="Hat")]]),
                    MeanEmbedder(),
                )
            )
            garment = pi.pending_garments(output)[0]
            crop = Path(garment["crop_path"])
            self.assertTrue(crop.is_file())
            pi.reject_garment(output, garment["id"])
            self.assertFalse(crop.exists())
            self.assertTrue(photo.is_file())
            self.assertEqual(pi.load_state(output)["garments"][garment["id"]]["status"], "rejected")
            self.assertEqual(pi.pending_garments(output), [])

    def test_resume_limit_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            photos = [_photo(source, f"{index}.png") for index in range(3)]
            red = _region(color=(180, 40, 40))
            blue = _region(color=(50, 90, 170))
            finder = ScriptedFinder([[red], [red], [blue]])
            embedder = MeanEmbedder()
            first = list(pi.scan_folder(source, output, finder, embedder, limit=1))
            self.assertEqual(finder.calls, 1)
            self.assertEqual(first[-1].waiting, 2)
            self.assertEqual(pi.import_counts(source, output)["waiting"], 2)
            self.assertEqual(len(pi.pending_garments(output)), 1)
            second = list(pi.scan_folder(source, output, finder, embedder))
            self.assertEqual(finder.calls, 3)
            self.assertEqual(second[-1].found, 1)
            pending = pi.pending_garments(output)
            self.assertEqual(len(pending), 2)
            matched = [row for row in pending if len(row["sources"]) == 2][0]
            self.assertEqual(matched["color"], "Red")
            self.assertCountEqual(matched["sources"], [str(photos[0].resolve()), str(photos[1].resolve())])
            again = list(pi.scan_folder(source, output, finder, embedder))
            self.assertEqual(again[0].total, 0)
            self.assertEqual(finder.calls, 3)

    def test_rejected_duplicate_is_not_added_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            _photo(source, "one.png")
            _photo(source, "two.png")
            finder = ScriptedFinder([[_region()], [_region()]])
            list(pi.scan_folder(source, output, finder, MeanEmbedder(), limit=1))
            garment = pi.pending_garments(output)[0]
            pi.reject_garment(output, garment["id"])
            list(pi.scan_folder(source, output, finder, MeanEmbedder()))
            self.assertEqual(pi.pending_garments(output), [])
            stored = pi.load_state(output)["garments"][garment["id"]]
            self.assertEqual(stored["status"], "rejected")
            self.assertEqual(len(stored["sources"]), 2)

    def test_approved_duplicate_updates_the_closet_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            first = _photo(source, "first.png")
            second = _photo(source, "second.png")
            coat = _region(category="Outerwear", folder="outerwear", friendly="coat", label="Coat")
            finder = ScriptedFinder([[_region()], [coat]])
            list(pi.scan_folder(source, output, finder, MeanEmbedder(), limit=1))
            garment = pi.pending_garments(output)[0]
            items, outfits = _empty_closet(root)
            items, outfits = pi.approve_garment(
                output,
                garment["id"],
                items,
                outfits,
                name="Red top",
                category="Tops",
                color="Red",
                season="All",
            )
            list(pi.scan_folder(source, output, finder, MeanEmbedder()))
            linked = pi.refresh_source_links(items, output)
            self.assertEqual(linked.iloc[0]["Source_Photo"], str(first.resolve()))
            self.assertIn(str(second.resolve()), linked.iloc[0]["Source_Photos"])
            self.assertEqual(len(pi.pending_garments(output)), 0)

    def test_unreadable_photo_does_not_stop_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            bad = source / "notes.jpg"
            bad.write_bytes(b"this is not a photo")
            good = _photo(source, "good.png")
            (source / ".hidden.png").write_bytes(b"skip")
            finder = ScriptedFinder([[_region()]])
            updates = list(pi.scan_folder(source, output, finder, MeanEmbedder()))
            self.assertEqual(finder.calls, 1)
            self.assertEqual(len(updates), 2)
            state = pi.load_state(output)
            self.assertNotEqual(state["files"][str(bad.resolve())]["error"], "")
            self.assertEqual(state["files"][str(good.resolve())]["error"], "")
            self.assertEqual(len(pi.pending_garments(output)), 1)

    def test_crops_folder_cannot_sit_inside_the_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "pictures"
            source.mkdir()
            photo = _photo(source, "day.png")
            before = photo.read_bytes()
            with self.assertRaises(pi.PhotoImportError):
                list(pi.scan_folder(source, source / "crops", ScriptedFinder([[_region()]]), MeanEmbedder()))
            with self.assertRaises(pi.PhotoImportError):
                list(pi.scan_folder(source, source, ScriptedFinder([[]]), MeanEmbedder()))
            self.assertEqual(photo.read_bytes(), before)
            self.assertFalse((source / "crops").exists())

    def test_changed_photo_stops_the_scan_before_a_crop_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pictures"
            output = root / "crops"
            source.mkdir()
            photo = _photo(source, "live.png")
            with self.assertRaises(pi.PhotoImportError):
                list(pi.scan_folder(source, output, MutatingFinder(photo), MeanEmbedder()))
            self.assertEqual(list((output / "pending").glob("*.png")), [])
            self.assertEqual(pi.load_state(output)["files"], {})

    def test_color_components_outerwear_and_shoes(self):
        self.assertEqual(pi.nearest_color(Image.new("RGB", (12, 12), (50, 90, 170))), "Blue")
        mask = np.zeros((30, 40), dtype=bool)
        mask[2:10, 2:10] = True
        mask[16:28, 20:36] = True
        self.assertEqual(len(pi.component_boxes(mask, min_pixels=10)), 2)

        person = (0, 0, 200, 80)
        coat = pi.classify_label("Upper-clothes", (20, 10, 160, 70), person)
        self.assertEqual(coat[0], "Outerwear")
        shirt = pi.classify_label("Upper-clothes", (30, 10, 80, 70), person)
        self.assertEqual(shirt[0], "Tops")
        whole = pi.classify_label("Upper-clothes", person, person)
        self.assertEqual(whole[0], "Tops")

        image = Image.new("RGB", (80, 200), (240, 240, 240))
        labels = np.zeros((200, 80), dtype=np.int32)
        labels[0:30, 20:50] = 11
        labels[30:170, 10:70] = 4
        labels[170:200, 15:65] = 12
        regions = pi.regions_from_mask(labels, image, {4: "Upper-clothes", 11: "Face", 12: "Left-leg"})
        self.assertEqual([region.category for region in regions], ["Outerwear"])

        shoes = np.zeros((200, 200), dtype=np.int32)
        shoes[140:190, 20:70] = 9
        shoes[140:190, 100:150] = 10
        shoe_image = Image.new("RGB", (200, 200), (20, 20, 20))
        found = pi.regions_from_mask(shoes, shoe_image, {9: "Left-shoe", 10: "Right-shoe"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].friendly, "shoes")
        self.assertEqual(found[0].category, "Footwear")

    def test_models_are_not_loaded_until_they_exist_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch.object(import_models, "MARKER", root / "ready.json"),
                mock.patch.object(import_models, "SEGFORMER_DIR", root / "seg"),
                mock.patch.object(import_models, "EMBEDDER_PATH", root / "embed.pth"),
            ):
                self.assertFalse(import_models.models_ready())
                with self.assertRaises(pi.PhotoImportError):
                    import_models.load_engines()
        ready, _message = import_models.packages_ready()
        self.assertIsInstance(ready, bool)


if __name__ == "__main__":
    unittest.main()
