import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from PIL import Image

import wardrobe as w


LEGACY = """ID,Category,Sub-Category,Primary Color,Season,Image_Path,Notes
1,Tops,Oxford Shirt,White,All,closet_images/item_1.png,soft
2,Tops,Turtleneck,Black,Winter,closet_images/item_2.png,
9,Footwear,Loafers,Black,Autumn,None,no photo
"""


class WardrobeTests(unittest.TestCase):
    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            items = w.load_items(Path(tmp) / "wardrobe_db.csv")
            self.assertTrue(items.empty)
            self.assertEqual(list(items.columns), w.ITEM_COLUMNS)

    def test_legacy_none_photo_and_extra_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wardrobe_db.csv"
            path.write_text(LEGACY, encoding="utf-8")
            items = w.load_items(path)
            self.assertEqual(list(items["ID"]), [1, 2, 9])
            loafers = items[items["ID"] == 9].iloc[0]
            self.assertEqual(loafers["Sub-Category"], "Loafers")
            self.assertEqual(loafers["Image_Path"], "")
            self.assertEqual(loafers["Notes"], "no photo")
            self.assertEqual(items.loc[items["ID"] == 1, "Notes"].iloc[0], "soft")
            self.assertEqual(w.clean_path(float("nan")), "")
            self.assertIsNone(w.resolve_image("None", Path(tmp)))

            outfits = w.load_outfits(Path(tmp) / "outfits_db.csv")
            items = w.add_item(
                items,
                outfits,
                category="Tops",
                sub_category="Tee",
                color="White",
                season="Summer",
            )
            w.save_items(items, path)
            again = w.load_items(path)
            self.assertEqual(set(again["Sub-Category"]), {"Oxford Shirt", "Turtleneck", "Loafers", "Tee"})
            self.assertEqual(again.loc[again["ID"] == 1, "Notes"].iloc[0], "soft")
            self.assertEqual(again.loc[again["ID"] == 9, "Image_Path"].iloc[0], "")
            self.assertNotIn("None", again["Image_Path"].tolist())

    def test_float_style_ids_and_blank_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wardrobe_db.csv"
            path.write_text(
                "ID,Category,Sub-Category,Primary Color,Season,Image_Path\n"
                "1.0,Tops,Shirt,White,All,\n"
                ",,,,,\n",
                encoding="utf-8",
            )
            items = w.load_items(path)
            self.assertEqual(list(items["ID"]), [1])
            self.assertEqual(items.iloc[0]["Image_Path"], "")

    def test_corrupt_file_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wardrobe_db.csv"
            original = "this is not a closet\n"
            path.write_text(original, encoding="utf-8")
            with self.assertRaises(w.WardrobeError):
                w.load_items(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_row_without_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wardrobe_db.csv"
            path.write_text(
                "ID,Category,Sub-Category,Primary Color,Season,Image_Path\n"
                ",Tops,Shirt,White,All,\n",
                encoding="utf-8",
            )
            with self.assertRaises(w.WardrobeError):
                w.load_items(path)

    def test_add_requires_a_name_and_does_not_reuse_referenced_ids(self):
        items = w.load_items(Path("missing-closet.csv"))
        outfits = w.add_outfit(
            w.load_outfits(Path("missing-outfits.csv")),
            name="Old look",
            top_id=5,
        )
        with self.assertRaises(w.WardrobeError):
            w.add_item(
                items,
                outfits,
                category="Tops",
                sub_category="   ",
                color="Black",
                season="All",
            )
        items = w.add_item(
            items,
            outfits,
            category="Tops",
            sub_category="  Tee  ",
            color="Black",
            season="All",
        )
        self.assertEqual(int(items.iloc[0]["ID"]), 6)
        self.assertEqual(items.iloc[0]["Sub-Category"], "Tee")

    def test_update_delete_and_outfit_scrub(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = w.load_items(root / "wardrobe_db.csv")
            outfits = w.load_outfits(root / "outfits_db.csv")
            photo = w.store_photo(_png(), 1, root)
            items = w.add_item(
                items,
                outfits,
                category="Tops",
                sub_category="Shirt",
                color="White",
                season="All",
                image_path=photo,
            )
            items = w.add_item(
                items,
                outfits,
                category="Bottoms",
                sub_category="Jeans",
                color="Blue",
                season="All",
            )
            shirt_id = int(items.loc[items["Sub-Category"] == "Shirt", "ID"].iloc[0])
            jeans_id = int(items.loc[items["Sub-Category"] == "Jeans", "ID"].iloc[0])
            outfits = w.add_outfit(
                outfits,
                name="Everyday",
                top_id=shirt_id,
                bottom_id=jeans_id,
                created="2026-10-21",
            )
            items = w.update_item(
                items,
                shirt_id,
                **{"Sub-Category": "Oxford", "Primary Color": "White"},
            )
            self.assertEqual(items.loc[items["ID"] == shirt_id, "Sub-Category"].iloc[0], "Oxford")
            items, outfits = w.delete_item(items, outfits, shirt_id, root)
            self.assertEqual(list(items["Sub-Category"]), ["Jeans"])
            self.assertEqual(outfits.iloc[0]["Top_ID"], "")
            self.assertEqual(outfits.iloc[0]["Bottom_ID"], str(jeans_id))
            self.assertIsNone(w.resolve_image(photo, root))
            self.assertTrue((root / "wardrobe_db.csv").parent.exists())

    def test_filter_sort_and_summary(self):
        items = _sample()
        winter = w.filter_items(items, season="Winter")
        self.assertEqual(
            set(winter["Sub-Category"]),
            {"Oxford Shirt", "Turtleneck", "Jeans (slim)"},
        )
        pink_outer = w.filter_items(items, category="Outerwear", color="Pink")
        self.assertTrue(pink_outer.empty)
        found = w.filter_items(items, query="(slim)")
        self.assertEqual(list(found["Sub-Category"]), ["Jeans (slim)"])
        named = list(w.sort_items(items, "Name")["Sub-Category"])
        self.assertEqual(named[0], "Blouse")
        self.assertLess(named.index("Blouse"), named.index("Turtleneck"))
        self.assertEqual(int(w.sort_items(items, "Recently added").iloc[0]["ID"]), 9)
        summary = w.closet_summary(items)
        self.assertIn("tops", summary)
        self.assertIn("black", summary)
        self.assertIn("Winter", summary)
        self.assertIn("Add a few pieces", w.closet_summary(items.iloc[0:0]))

    def test_photo_roundtrip_and_outside_file_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = w.store_photo(_png(), 4, root)
            self.assertTrue(relative.startswith("closet_images/item_4_"))
            self.assertIsNotNone(w.resolve_image(relative, root))
            outside = root / "note.txt"
            outside.write_text("keep", encoding="utf-8")
            w.remove_stored_photo(str(outside), root)
            self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
            w.remove_stored_photo(relative, root)
            self.assertIsNone(w.resolve_image(relative, root))

    def test_shared_photo_is_not_deleted_while_another_item_uses_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = w.store_photo(_png(), 1, root)
            items = w.load_items(root / "wardrobe_db.csv")
            outfits = w.load_outfits(root / "outfits_db.csv")
            items = w.add_item(
                items, outfits, category="Tops", sub_category="A", color="Black", season="All", image_path=relative
            )
            items = w.add_item(
                items, outfits, category="Tops", sub_category="B", color="Black", season="All", image_path=relative
            )
            first = int(items.iloc[0]["ID"])
            items, _outfits = w.delete_item(items, outfits, first, root)
            self.assertIsNotNone(w.resolve_image(relative, root))

    def test_outfit_needs_a_piece_and_deletes_cleanly(self):
        outfits = w.load_outfits(Path("missing-outfits.csv"))
        with self.assertRaises(w.WardrobeError):
            w.add_outfit(outfits, name="Empty")
        outfits = w.add_outfit(outfits, name="  Dress day  ", full_body_id=3)
        self.assertEqual(outfits.iloc[0]["Name"], "Dress day")
        self.assertEqual(outfits.iloc[0]["FullBody_ID"], "3")
        self.assertTrue(w.delete_outfit(outfits, int(outfits.iloc[0]["ID"])).empty)

    def test_unicode_name_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wardrobe_db.csv"
            items = w.add_item(
                w.load_items(path),
                w.load_outfits(Path(tmp) / "outfits.csv"),
                category="Full Body",
                sub_category="Café dress",
                color="Black",
                season="Summer",
            )
            w.save_items(items, path)
            again = w.load_items(path)
            self.assertEqual(again.iloc[0]["Sub-Category"], "Café dress")


def _png() -> bytes:
    image = Image.new("RGB", (30, 20), "red")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _sample() -> pd.DataFrame:
    rows = [
        (1, "Tops", "Oxford Shirt", "White", "All"),
        (2, "Tops", "Turtleneck", "Black", "Winter"),
        (3, "Bottoms", "Jeans (slim)", "Blue", "All"),
        (4, "Bottoms", "Chinos", "Beige", "Spring"),
        (5, "Outerwear", "Trench Coat", "Green", "Autumn"),
        (6, "Full Body", "Slip Dress", "Black", "Summer"),
        (7, "Footwear", "Sneakers", "White", "Summer"),
        (8, "Tops", "Blouse", "Pink", "Spring"),
        (9, "Footwear", "Loafers", "Black", "Autumn"),
    ]
    frame = pd.DataFrame(rows, columns=["ID", "Category", "Sub-Category", "Primary Color", "Season"])
    frame["Image_Path"] = ""
    return frame


if __name__ == "__main__":
    unittest.main()
