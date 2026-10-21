"""Closet data: items, photos, and saved outfits.

The closet file keeps the original columns so wardrobes saved by the first
version of the app still open. Missing photos used to be stored as the word
"None", which pandas reads as NaN and which then crashed the gallery.
"""

from __future__ import annotations

import io
import time
from datetime import date
from pathlib import Path

import pandas as pd
from PIL import Image, UnidentifiedImageError

APP_DIR = Path(__file__).resolve().parent
ITEMS_PATH = APP_DIR / "wardrobe_db.csv"
OUTFITS_PATH = APP_DIR / "outfits_db.csv"
IMAGE_DIR_NAME = "closet_images"

ITEM_COLUMNS = [
    "ID",
    "Category",
    "Sub-Category",
    "Primary Color",
    "Season",
    "Image_Path",
]
OUTFIT_COLUMNS = [
    "ID",
    "Name",
    "Top_ID",
    "Bottom_ID",
    "FullBody_ID",
    "Outerwear_ID",
    "Footwear_ID",
    "Created",
]
PIECE_COLUMNS = [
    "Top_ID",
    "Bottom_ID",
    "FullBody_ID",
    "Outerwear_ID",
    "Footwear_ID",
]

CATEGORIES = ["Tops", "Bottoms", "Full Body", "Outerwear", "Footwear", "Accessories"]
COLORS = [
    "Black",
    "White",
    "Grey",
    "Beige",
    "Brown",
    "Blue",
    "Navy",
    "Green",
    "Red",
    "Pink",
    "Yellow",
    "Orange",
    "Purple",
]
SEASONS = ["All", "Spring", "Summer", "Autumn", "Winter"]
_MISSING_PHOTO = {"", "none", "nan", "null", "n/a", "<na>"}
_SEASON_ORDER = ["Spring", "Summer", "Autumn", "Winter"]
_CATEGORY_WORDS = {
    "Tops": "tops",
    "Bottoms": "bottoms",
    "Full Body": "one-piece clothes",
    "Outerwear": "outerwear",
    "Footwear": "shoes",
    "Accessories": "accessories",
}


class WardrobeError(Exception):
    """A closet file could not be read or a change was not valid."""


def clean_path(value: object) -> str:
    """Return a photo path, or an empty string when there is no photo."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in _MISSING_PHOTO:
        return ""
    return text


def parse_optional_id(value: object) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in _MISSING_PHOTO:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def load_items(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_frame(ITEM_COLUMNS)
    try:
        raw = pd.read_csv(path, keep_default_na=False, dtype=str, encoding="utf-8-sig")
    except Exception as exc:
        raise WardrobeError(f"Could not read the closet file: {exc}") from exc
    if "ID" not in raw.columns:
        raise WardrobeError(
            "The closet file is missing an ID column, so it was left unchanged."
        )
    for column in ITEM_COLUMNS:
        if column not in raw.columns:
            raw[column] = ""
    raw = raw.fillna("")
    blank = raw.apply(
        lambda row: all(str(row[column]).strip() == "" for column in raw.columns),
        axis=1,
    )
    raw = raw.loc[~blank].copy()
    if raw.empty:
        return _empty_frame(list(raw.columns) or ITEM_COLUMNS)

    ids: list[int] = []
    for line, value in enumerate(raw["ID"].tolist(), start=2):
        parsed = parse_optional_id(value)
        if parsed is None:
            raise WardrobeError(
                f"The closet file has a row without a usable ID (line {line}). "
                "It was left unchanged."
            )
        ids.append(parsed)
    raw["ID"] = ids
    for column in ITEM_COLUMNS:
        if column == "ID":
            continue
        raw[column] = raw[column].map(lambda value: "" if value is None else str(value).strip())
    raw["Image_Path"] = raw["Image_Path"].map(clean_path)
    return _ordered(raw, ITEM_COLUMNS).reset_index(drop=True)


def load_outfits(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_frame(OUTFIT_COLUMNS)
    try:
        raw = pd.read_csv(path, keep_default_na=False, dtype=str, encoding="utf-8-sig")
    except Exception as exc:
        raise WardrobeError(f"Could not read saved looks: {exc}") from exc
    if "ID" not in raw.columns:
        raise WardrobeError(
            "The outfits file is missing an ID column, so it was left unchanged."
        )
    for column in OUTFIT_COLUMNS:
        if column not in raw.columns:
            raw[column] = ""
    raw = raw.fillna("")
    blank = raw.apply(
        lambda row: all(str(row[column]).strip() == "" for column in raw.columns),
        axis=1,
    )
    raw = raw.loc[~blank].copy()
    if raw.empty:
        return _empty_frame(OUTFIT_COLUMNS)
    ids: list[int] = []
    for line, value in enumerate(raw["ID"].tolist(), start=2):
        parsed = parse_optional_id(value)
        if parsed is None:
            raise WardrobeError(
                f"Saved looks has a row without a usable ID (line {line}). "
                "It was left unchanged."
            )
        ids.append(parsed)
    raw["ID"] = ids
    raw["Name"] = raw["Name"].map(lambda value: str(value).strip() or "Untitled look")
    raw["Created"] = raw["Created"].map(lambda value: str(value).strip())
    for column in PIECE_COLUMNS:
        raw[column] = raw[column].map(_id_text)
    return _ordered(raw, OUTFIT_COLUMNS).reset_index(drop=True)


def save_items(items: pd.DataFrame, path: Path) -> None:
    _atomic_csv(items, path)


def save_outfits(outfits: pd.DataFrame, path: Path) -> None:
    _atomic_csv(outfits, path)


def add_item(
    items: pd.DataFrame,
    outfits: pd.DataFrame,
    *,
    category: str,
    sub_category: str,
    color: str,
    season: str,
    image_path: str = "",
) -> pd.DataFrame:
    name = sub_category.strip()
    if not name:
        raise WardrobeError("Enter a name for this piece.")
    row = {column: "" for column in items.columns}
    row.update(
        {
            "ID": _next_item_id(items, outfits),
            "Category": category.strip(),
            "Sub-Category": name[:80],
            "Primary Color": color.strip(),
            "Season": season.strip(),
            "Image_Path": clean_path(image_path),
        }
    )
    return _append(items, row)


def update_item(items: pd.DataFrame, item_id: int, **fields: object) -> pd.DataFrame:
    items = items.copy()
    mask = items["ID"] == int(item_id)
    if not mask.any():
        raise WardrobeError("That piece is no longer in the closet.")
    for key, value in fields.items():
        if key not in items.columns:
            items[key] = ""
        if key == "Sub-Category":
            text = str(value).strip()
            if not text:
                raise WardrobeError("Enter a name for this piece.")
            value = text[:80]
        elif key == "Image_Path":
            value = clean_path(value)
        elif key != "ID":
            value = "" if value is None else str(value).strip()
        items.loc[mask, key] = value
    return items


def delete_item(
    items: pd.DataFrame,
    outfits: pd.DataFrame,
    item_id: int,
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    item_id = int(item_id)
    match = items[items["ID"] == item_id]
    if match.empty:
        return items.copy(), outfits.copy()
    photo = match.iloc[0]["Image_Path"]
    kept = items[items["ID"] != item_id].reset_index(drop=True)
    remove_stored_photo(photo, root, kept)
    return kept, scrub_outfits(outfits, item_id)


def add_outfit(
    outfits: pd.DataFrame,
    *,
    name: str,
    top_id: object = None,
    bottom_id: object = None,
    full_body_id: object = None,
    outerwear_id: object = None,
    footwear_id: object = None,
    created: str | None = None,
) -> pd.DataFrame:
    pieces = {
        "Top_ID": top_id,
        "Bottom_ID": bottom_id,
        "FullBody_ID": full_body_id,
        "Outerwear_ID": outerwear_id,
        "Footwear_ID": footwear_id,
    }
    if all(parse_optional_id(value) is None for value in pieces.values()):
        raise WardrobeError("Choose at least one piece.")
    label = name.strip()[:80] or "Untitled look"
    row = {column: "" for column in outfits.columns}
    row.update(
        {
            "ID": _next_outfit_id(outfits),
            "Name": label,
            "Created": created or date.today().isoformat(),
        }
    )
    for column, value in pieces.items():
        row[column] = _id_text(value)
    return _append(outfits, row)


def delete_outfit(outfits: pd.DataFrame, outfit_id: int) -> pd.DataFrame:
    return outfits[outfits["ID"] != int(outfit_id)].reset_index(drop=True)


def scrub_outfits(outfits: pd.DataFrame, item_id: int) -> pd.DataFrame:
    outfits = outfits.copy()
    if outfits.empty:
        return outfits
    for column in PIECE_COLUMNS:
        outfits[column] = outfits[column].map(
            lambda value, item_id=item_id: (
                "" if parse_optional_id(value) == int(item_id) else _id_text(value)
            )
        )
    return outfits


def filter_items(
    items: pd.DataFrame,
    *,
    query: str = "",
    category: str = "All",
    color: str = "All",
    season: str = "All",
) -> pd.DataFrame:
    out = items
    if category and category != "All":
        out = out[out["Category"] == category]
    if color and color != "All":
        out = out[out["Primary Color"] == color]
    if season and season != "All":
        # Pieces tagged "All" are worn in every season.
        out = out[(out["Season"] == season) | (out["Season"] == "All")]
    text = query.strip().lower()
    if text:
        haystack = (
            out["Sub-Category"].astype(str)
            + " "
            + out["Category"].astype(str)
            + " "
            + out["Primary Color"].astype(str)
            + " "
            + out["Season"].astype(str)
        ).str.lower()
        out = out[haystack.str.contains(text, regex=False)]
    return out.reset_index(drop=True)


def sort_items(items: pd.DataFrame, how: str = "Recently added") -> pd.DataFrame:
    if items.empty:
        return items.reset_index(drop=True)
    if how == "Name":
        ordered = items.assign(_name=items["Sub-Category"].astype(str).str.lower())
        ordered = ordered.sort_values(["_name", "ID"], kind="mergesort")
        return ordered.drop(columns="_name").reset_index(drop=True)
    if how == "Color":
        ordered = items.assign(
            _color=items["Primary Color"].astype(str).str.lower(),
            _name=items["Sub-Category"].astype(str).str.lower(),
        )
        ordered = ordered.sort_values(["_color", "_name", "ID"], kind="mergesort")
        return ordered.drop(columns=["_color", "_name"]).reset_index(drop=True)
    return items.sort_values("ID", ascending=False, kind="mergesort").reset_index(drop=True)


def closet_summary(items: pd.DataFrame) -> str:
    if items.empty:
        return "Add a few pieces and this page will show what you own."
    count = len(items)
    piece = "piece" if count == 1 else "pieces"
    top_category = _CATEGORY_WORDS.get(
        str(items["Category"].value_counts().index[0]),
        str(items["Category"].value_counts().index[0]).lower(),
    )
    top_color = str(items["Primary Color"].value_counts().index[0]).lower()
    coverage = {
        season: int(((items["Season"] == season) | (items["Season"] == "All")).sum())
        for season in _SEASON_ORDER
    }
    lowest = min(coverage.values())
    thin = [season for season, total in coverage.items() if total == lowest]
    if len(thin) == len(_SEASON_ORDER):
        season_line = "The four seasons are evenly covered."
    elif len(thin) == 1:
        season_line = (
            f"{thin[0]} is the lightest season, even counting all-season pieces."
        )
    else:
        season_line = (
            f"{_join_names(thin)} are the lightest seasons, "
            "even counting all-season pieces."
        )
    return (
        f"You have {count} {piece}. Most of your closet is {top_category}, "
        f"and {top_color} is the color you own most. {season_line}"
    )


def resolve_image(path: object, root: Path) -> Path | None:
    cleaned = clean_path(path)
    if not cleaned:
        return None
    raw = Path(cleaned)
    candidates = [raw] if raw.is_absolute() else [root / raw, raw]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def store_photo(data: bytes, item_id: int, root: Path) -> str:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise WardrobeError("That photo could not be read. Use a JPG or PNG.") from exc
    if image.mode == "P" and "transparency" in image.info:
        image = image.convert("RGBA")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    image.thumbnail((1400, 1400))
    folder = root / IMAGE_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    # A new filename keeps the browser from showing a replaced photo.
    filename = f"item_{int(item_id)}_{time.time_ns() // 1_000_000}.png"
    destination = folder / filename
    image.save(destination, "PNG")
    return f"{IMAGE_DIR_NAME}/{filename}"


def remove_stored_photo(path: object, root: Path, items: pd.DataFrame | None = None) -> None:
    cleaned = clean_path(path)
    if not cleaned:
        return
    if items is not None and not items.empty:
        still_used = items["Image_Path"].map(clean_path) == cleaned
        if still_used.any():
            return
    resolved = resolve_image(cleaned, root)
    if resolved is None:
        return
    image_root = (root / IMAGE_DIR_NAME).resolve()
    try:
        resolved.relative_to(image_root)
    except ValueError:
        return
    resolved.unlink(missing_ok=True)


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _ordered(frame: pd.DataFrame, required: list[str]) -> pd.DataFrame:
    extras = [column for column in frame.columns if column not in required]
    return frame[list(required) + extras]


def _append(frame: pd.DataFrame, row: dict[str, object]) -> pd.DataFrame:
    addition = pd.DataFrame([{column: row.get(column, "") for column in frame.columns}])
    if frame.empty:
        return addition.reset_index(drop=True)
    return pd.concat([frame, addition], ignore_index=True)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _id_text(value: object) -> str:
    parsed = parse_optional_id(value)
    if parsed is None:
        return ""
    return str(parsed)


def next_item_id(items: pd.DataFrame, outfits: pd.DataFrame) -> int:
    return _next_item_id(items, outfits)


def _next_item_id(items: pd.DataFrame, outfits: pd.DataFrame) -> int:
    ids = [int(value) for value in items["ID"].tolist()] if not items.empty else []
    if not outfits.empty:
        for column in PIECE_COLUMNS:
            for value in outfits[column].tolist():
                parsed = parse_optional_id(value)
                if parsed is not None:
                    ids.append(parsed)
    return (max(ids) if ids else 0) + 1


def _next_outfit_id(outfits: pd.DataFrame) -> int:
    if outfits.empty:
        return 1
    return int(outfits["ID"].max()) + 1


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"
