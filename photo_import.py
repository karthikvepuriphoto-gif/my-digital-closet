"""Import a wardrobe from a local folder of photos.

Photos are read and never written. Crops go to a separate folder. Nothing is
added to the closet until a person approves it. Model code lives in
import_models.py and is not imported here, so the rest of the app still runs
if PyTorch is not installed.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageOps, UnidentifiedImageError

import wardrobe as w

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DUPLICATE_SIMILARITY = 0.90
SAME_GARMENT_ACROSS_LABELS = 0.95
DEFAULT_OUTPUT = w.APP_DIR / "imported_wardrobe"
LIBRARY_NAME = "library.json"

# Closet category, output folder, short name, confidence.
LABEL_INFO = {
    "upper-clothes": ("Tops", "tops", "top", 0.8),
    "skirt": ("Bottoms", "bottoms", "skirt", 0.75),
    "pants": ("Bottoms", "bottoms", "pants", 0.85),
    "dress": ("Full Body", "dresses", "dress", 0.75),
    "hat": ("Accessories", "accessories", "hat", 0.7),
    "sunglasses": ("Accessories", "accessories", "sunglasses", 0.7),
    "belt": ("Accessories", "accessories", "belt", 0.45),
    "left-shoe": ("Footwear", "shoes", "shoe", 0.7),
    "right-shoe": ("Footwear", "shoes", "shoe", 0.7),
    "bag": ("Accessories", "accessories", "bag", 0.7),
    "scarf": ("Accessories", "accessories", "scarf", 0.55),
    "coat": ("Outerwear", "outerwear", "coat", 0.85),
    "jacket": ("Outerwear", "outerwear", "jacket", 0.85),
}
GARMENT_LABELS = set(LABEL_INFO)
FOLDER_BY_CATEGORY = {
    "Tops": "tops",
    "Bottoms": "bottoms",
    "Full Body": "dresses",
    "Outerwear": "outerwear",
    "Footwear": "shoes",
    "Accessories": "accessories",
}
COLOR_RGB = {
    "Black": (20, 20, 20),
    "White": (245, 245, 245),
    "Grey": (140, 140, 140),
    "Beige": (210, 190, 160),
    "Brown": (110, 70, 40),
    "Blue": (50, 90, 170),
    "Navy": (20, 35, 80),
    "Green": (40, 110, 60),
    "Red": (180, 40, 40),
    "Pink": (230, 150, 170),
    "Yellow": (230, 200, 60),
    "Orange": (220, 120, 40),
    "Purple": (110, 70, 150),
}
# Long edge before detection. The saved crop is a separate choice.
DETECT_EDGE = 640
PRESETS = {
    "small": {
        "id": "small",
        "label": "Small",
        "edge": 384,
        "quality": 80,
        "detail": "Great for browsing and matching outfits; colors stay accurate, fine detail is softer.",
    },
    "medium": {
        "id": "medium",
        "label": "Medium",
        "edge": 640,
        "quality": 80,
        "detail": "Fabric and edges are easier to see; a good fit if you look closely and still want the closet small.",
    },
    "high": {
        "id": "high",
        "label": "High",
        "edge": 1024,
        "quality": 85,
        "detail": "The closest look when you zoom in; suits a smaller closet, or when you have room to spare.",
    },
}
PRESET_LIST = [PRESETS["small"], PRESETS["medium"], PRESETS["high"]]
CROP_EDGE = PRESETS["small"]["edge"]
WEBP_QUALITY = PRESETS["small"]["quality"]
HIGH_EDGE = PRESETS["high"]["edge"]
PREFS_NAME = "storage_prefs.json"
SAMPLE_DIR = Path(__file__).resolve().parent / "web" / "samples"
# Stride over the detection-sized photo. This is not a tiny thumbnail.
COLOR_SAMPLES = 2500
SKIN_LABELS = {"face", "left-arm", "right-arm", "left-leg", "right-leg"}
_XYZ_FROM_RGB = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float64,
)
_RGB_FROM_XYZ = np.array(
    [
        [3.2404542, -1.5371385, -0.4985314],
        [-0.9692660, 1.8760108, 0.0415560],
        [0.0556434, -0.2040259, 1.0572252],
    ],
    dtype=np.float64,
)
_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)
_LAB_DELTA = 6 / 29
_SRGB_PROFILE: bytes | None = None
_PALETTE_LAB: tuple[list[str], np.ndarray] | None = None


class PhotoImportError(Exception):
    """The import could not continue safely."""


@dataclass
class Region:
    label: str
    category: str
    folder: str
    friendly: str
    crop: Image.Image
    confidence: float
    color: str = ""
    color_hex: str = ""
    crop_box: tuple[float, float, float, float] | None = None


@dataclass
class ScanProgress:
    done: int
    total: int
    waiting: int
    current: str
    found: int
    message: str


@dataclass
class ClothesFinder:
    """Finds garment crops in one image. Tests pass a fake."""

    def find(self, image: Image.Image) -> list[Region]:
        return []


@dataclass
class Embedder:
    def embed(self, image: Image.Image) -> list[float]:
        return []


def privacy_summary() -> str:
    return (
        "Your pictures stay on this computer. The scan only reads them, "
        "and it never uploads them, sends them to a cloud service, or edits them. "
        "The clothing model is downloaded once into a folder next to the app, then runs here. "
        "Telemetry from the model tools is turned off. "
        "Crops are written to a separate folder. "
        "Nothing is added to the closet until you approve it."
    )


def ensure_separate_folders(source: Path, output: Path) -> tuple[Path, Path]:
    """Refuse a crops folder that could let us write into the photo folder."""
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.is_dir():
        raise PhotoImportError(f"That photo folder does not exist: {source}")
    if output == source or _is_relative_to(output, source) or _is_relative_to(source, output):
        raise PhotoImportError(
            "Pick a crops folder that is outside the photo folder. "
            "Original photos are never moved or modified."
        )
    return source, output


def list_images(source: Path, output: Path) -> list[Path]:
    found = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        resolved = path.resolve()
        if _is_relative_to(resolved, output):
            continue
        found.append(resolved)
    return sorted(found, key=lambda item: str(item).lower())


def needs_scan(state: dict, path: Path) -> bool:
    record = state["files"].get(str(path))
    if not record:
        return True
    size, mtime_ns = _signature(path)
    return record.get("size") != size or record.get("mtime_ns") != mtime_ns


def scan_folder(
    source: Path,
    output: Path,
    finder: ClothesFinder,
    embedder: Embedder,
    *,
    limit: int | None = None,
    preset: str | dict | None = "small",
):
    """Scan new or changed photos. Yields progress. Original files are not opened for writing."""
    source, output = ensure_separate_folders(source, output)
    _prepare_output(output)
    state = load_state(output)
    images = list_images(source, output)
    waiting = [path for path in images if needs_scan(state, path)]
    batch = waiting if limit is None else waiting[: max(0, limit)]
    found = 0
    total = len(batch)
    if total == 0:
        yield ScanProgress(
            done=0,
            total=0,
            waiting=0,
            current="",
            found=0,
            message="No new photos to scan. Unchanged pictures are left as they are.",
        )
        return
    for index, path in enumerate(batch, start=1):
        before = path.read_bytes()
        signature = _signature(path)
        error = ""
        regions: list[Region] = []
        try:
            image = _image_from_bytes(before)
            regions = list(finder.find(image))
        except (UnidentifiedImageError, OSError, PhotoImportError) as exc:
            error = str(exc)
        after = path.read_bytes()
        if after != before or _signature(path) != signature:
            raise PhotoImportError(
                f"Stopped because {path.name} changed during the scan. "
                "Original photos are not supposed to be touched."
            )
        new_ids: list[str] = []
        for region in regions:
            garment_id, created = _record_region(state, output, path, region, embedder, preset)
            if garment_id and garment_id not in new_ids:
                new_ids.append(garment_id)
            if created:
                found += 1
        state["files"][str(path)] = {
            "size": signature[0],
            "mtime_ns": signature[1],
            "sha256": hashlib.sha256(before).hexdigest(),
            "error": error,
            "garment_ids": new_ids,
            "scanned_at": _now(),
        }
        save_state(output, state)
        remaining = len(waiting) - index
        detail = error or f"found {len(new_ids)}"
        yield ScanProgress(
            done=index,
            total=total,
            waiting=remaining,
            current=path.name,
            found=found,
            message=f"Scanning {index} of {total} ({remaining} still waiting): {path.name} — {detail}",
        )


def pending_garments(output: Path) -> list[dict]:
    state = load_state(output)
    rows = [dict(row, id=garment_id) for garment_id, row in state["garments"].items() if row.get("status") == "pending"]
    rows.sort(key=lambda row: row.get("created", ""), reverse=True)
    return rows


def import_counts(source: Path | None, output: Path) -> dict[str, int]:
    state = load_state(output) if output.exists() else _empty_state()
    garments = list(state["garments"].values())
    waiting = 0
    if source and source.expanduser().exists():
        try:
            source, output = ensure_separate_folders(source, output)
            waiting = sum(1 for path in list_images(source, output) if needs_scan(state, path))
        except PhotoImportError:
            waiting = 0
    return {
        "waiting": waiting,
        "pending": sum(1 for row in garments if row.get("status") == "pending"),
        "approved": sum(1 for row in garments if row.get("status") == "approved"),
        "rejected": sum(1 for row in garments if row.get("status") == "rejected"),
        "scanned": len(state["files"]),
    }


def approve_garment(
    output: Path,
    garment_id: str,
    items: pd.DataFrame,
    outfits: pd.DataFrame,
    *,
    name: str,
    category: str,
    color: str,
    season: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = output.expanduser().resolve()
    state = load_state(output)
    garment = state["garments"].get(garment_id)
    if garment is None or garment.get("status") != "pending":
        raise PhotoImportError("That detection is no longer waiting for review.")
    if category not in FOLDER_BY_CATEGORY:
        raise PhotoImportError("Pick a category from the closet list.")
    cleaned = name.strip()
    if not cleaned:
        raise PhotoImportError("Enter a name before approving.")
    folder = FOLDER_BY_CATEGORY[category]
    destination = output / folder / Path(garment["crop_path"]).name
    moved = _move_our_file(Path(garment["crop_path"]), destination, output)
    items = w.add_item(
        items,
        outfits,
        category=category,
        sub_category=cleaned,
        color=color,
        season=season,
        image_path=str(moved),
    )
    closet_id = int(items.iloc[-1]["ID"])
    sources = list(garment.get("sources") or [])
    fields = {
        "Source_Photo": sources[0] if sources else "",
        "Source_Photos": "|".join(sources),
    }
    measured = str(garment.get("color") or "").strip()
    measured_hex = str(garment.get("color_hex") or "").strip()
    if measured_hex and color.strip() != measured:
        measured_hex = ""
    if measured_hex:
        fields["Color Hex"] = measured_hex
    items = w.update_item(items, closet_id, **fields)
    garment.update(
        {
            "status": "approved",
            "name": cleaned[:80],
            "category": category,
            "folder": folder,
            "color": color,
            "color_hex": measured_hex,
            "season": season,
            "crop_path": str(moved),
            "closet_id": closet_id,
        }
    )
    save_state(output, state)
    return items, outfits


def reject_garment(output: Path, garment_id: str) -> None:
    output = output.expanduser().resolve()
    state = load_state(output)
    garment = state["garments"].get(garment_id)
    if garment is None or garment.get("status") != "pending":
        raise PhotoImportError("That detection is no longer waiting for review.")
    _delete_our_file(Path(garment.get("crop_path", "")), output)
    garment["status"] = "rejected"
    garment["crop_path"] = ""
    save_state(output, state)


def prepare_photo(image: Image.Image) -> Image.Image:
    """Turn the photo upright and into sRGB. The file on disk is not written."""
    try:
        turned = ImageOps.exif_transpose(image)
    except (OSError, ValueError):
        turned = image
    converted = _to_srgb(turned)
    if converted.mode != "RGB":
        converted = converted.convert("RGB")
    return converted


def downscale(image: Image.Image, edge: int = DETECT_EDGE) -> Image.Image:
    """Shrink the long edge before detection. Smaller photos stay as they are."""
    if max(image.size) <= edge:
        return image
    copy = image.copy()
    copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return copy


def resolve_preset(preset: str | dict | None = None) -> dict:
    if isinstance(preset, dict) and preset.get("id") in PRESETS:
        return PRESETS[str(preset["id"])]
    return PRESETS.get(str(preset or "small"), PRESETS["small"])


def modest_crop(image: Image.Image, edge: int = CROP_EDGE) -> Image.Image:
    """Shrink the long edge. Never enlarge a picture."""
    if max(image.size) <= edge:
        return image
    copy = image.copy()
    copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return copy


def encode_webp(image: Image.Image, preset: str | dict | None = "small") -> bytes:
    """Lossy WebP at the chosen size. Call this only after the color has been measured."""
    spec = resolve_preset(preset)
    prepared = modest_crop(image, int(spec["edge"]))
    if prepared.mode != "RGBA":
        prepared = prepared.convert("RGBA")
    buffer = io.BytesIO()
    prepared.save(buffer, "WEBP", quality=int(spec["quality"]), method=6)
    return buffer.getvalue()


def format_bytes(size: int) -> str:
    amount = max(0, int(size))
    if amount < 1024:
        return f"{amount} B"
    if amount < 1024 * 1024:
        kb = amount / 1024
        return f"{kb:.1f} KB" if kb < 10 else f"{kb:.0f} KB"
    return f"{amount / (1024 * 1024):.1f} MB"


def projection_line(bytes_per_item: int, count: int = 1000) -> str:
    total = max(0, int(bytes_per_item)) * max(0, int(count))
    return f"~{int(count):,} items ≈ {format_bytes(total)}"


def storage_lines(average: int, own: bool) -> list[str]:
    """Average and closet-size examples from measured bytes, not a target band."""
    per_item = max(0, int(average))
    if per_item <= 0:
        return []
    kind = "Your average" if own else "Estimate"
    return [
        f"{kind} · {format_bytes(per_item)} each",
        projection_line(per_item, 100),
        projection_line(per_item, 1000),
    ]


def space_comparison(small_bytes: int, high_bytes: int) -> str:
    small = max(0, int(small_bytes))
    high = max(0, int(high_bytes))
    if small <= 0 or high <= small:
        return ""
    ratio = high / small
    nearest = round(ratio)
    shown = str(nearest) if abs(ratio - nearest) < 0.05 else f"{ratio:.1f}"
    return f"Small uses about {shown}× less space than High."


def prefs_path(root: Path | None = None) -> Path:
    return (root or w.APP_DIR) / PREFS_NAME


def current_preset(root: Path | None = None) -> dict:
    path = prefs_path(root)
    preset_id = "small"
    if path.is_file():
        try:
            preset_id = str(json.loads(path.read_text(encoding="utf-8")).get("crop_quality") or "small")
        except (OSError, json.JSONDecodeError, TypeError):
            preset_id = "small"
    return resolve_preset(preset_id)


def quality_chosen(root: Path | None = None) -> bool:
    path = prefs_path(root)
    if not path.is_file():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("chosen"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def save_preset(preset: str | dict, root: Path | None = None) -> dict:
    spec = resolve_preset(preset)
    path = prefs_path(root)
    path.write_text(json.dumps({"crop_quality": spec["id"], "chosen": True}), encoding="utf-8")
    return spec


def flatten_for_embed(image: Image.Image) -> Image.Image:
    """Plain background for the comparison model. The stored crop stays transparent."""
    if image.mode != "RGBA":
        return image.convert("RGB")
    base = Image.new("RGB", image.size, (246, 241, 234))
    base.paste(image, mask=image.getchannel("A"))
    return base


def nearest_color(image: Image.Image) -> str:
    return dominant_color(image)[0]


def dominant_color(image: Image.Image, mask: np.ndarray | None = None) -> tuple[str, str]:
    """Name and hex for the largest color cluster in CIELAB.

    Pixels come from the garment mask on the detection-sized photo. Background
    and skin stay out of the mask. The sample is a stride across that photo,
    not a tiny thumbnail of the whole crop.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if mask is None:
        chosen = rgb.reshape(-1, 3)
    else:
        selected = np.asarray(mask, dtype=bool)
        if selected.shape != rgb.shape[:2]:
            raise PhotoImportError("The color mask does not match the photo.")
        chosen = rgb[selected]
    if chosen.size == 0:
        return "Grey", "#8C8C8C"
    if len(chosen) > COLOR_SAMPLES:
        step = int(np.ceil(len(chosen) / COLOR_SAMPLES))
        chosen = chosen[::step]
    lab = _rgb_to_lab(chosen.astype(np.float64))
    centers, labels = _kmeans(lab, 3 if len(chosen) >= 24 else 1)
    counts = np.bincount(labels, minlength=len(centers))
    center = _lab_to_rgb(centers[int(np.argmax(counts))])
    return _nearest_name(center), "#{:02X}{:02X}{:02X}".format(int(center[0]), int(center[1]), int(center[2]))


def _label_key(label: str) -> str:
    return label.strip().lower().replace("_", "-").replace(" ", "-")


def classify_label(label: str, box: tuple[int, int, int, int], person_box: tuple[int, int, int, int]) -> tuple[str, str, str, float]:
    """Map a model label to a closet category. Long tops are suggested as outerwear."""
    key = _label_key(label)
    if key not in LABEL_INFO:
        raise PhotoImportError(f"Unknown clothing label: {label}")
    category, folder, friendly, confidence = LABEL_INFO[key]
    if key == "upper-clothes":
        y0, _, y1, _ = box
        py0, _, py1, _ = person_box
        garment_h = max(1, y1 - y0)
        person_h = max(1, py1 - py0)
        ratio = garment_h / person_h
        reaches_low = y1 >= py0 + person_h * 0.72
        # A coat is long on a person, but still shorter than the whole figure.
        # When the garment is the entire foreground, keep the top suggestion.
        if 0.62 <= ratio < 0.92 and reaches_low:
            return "Outerwear", "outerwear", "coat", 0.5
    return category, folder, friendly, confidence


def regions_from_mask(
    mask: np.ndarray,
    original: Image.Image,
    id2label: dict,
    color_image: Image.Image | None = None,
) -> list[Region]:
    """Turn a segmentation mask into garment crops and a measured color."""
    if mask.ndim != 2:
        raise PhotoImportError("The clothing mask has the wrong shape.")
    mask_h, mask_w = mask.shape
    orig_w, orig_h = original.size
    scale_x = orig_w / mask_w
    scale_y = orig_h / mask_h
    labels = {int(key): str(value) for key, value in id2label.items()}
    skin = np.zeros(mask.shape, dtype=bool)
    for label_id, name in labels.items():
        if _label_key(name) in SKIN_LABELS:
            skin |= mask == label_id
    person = mask > 0
    if person.any():
        ys, xs = np.where(person)
        person_box = (int(ys.min()), int(xs.min()), int(ys.max()) + 1, int(xs.max()) + 1)
    else:
        person_box = (0, 0, mask_h, mask_w)
    min_pixels = max(400, int(0.012 * mask_h * mask_w))
    regions: list[Region] = []
    shoes: list[tuple[str, tuple[int, int, int, int], float, np.ndarray]] = []
    for label_id, name in labels.items():
        key = _label_key(name)
        if key not in GARMENT_LABELS:
            continue
        for box, _area, component in _components(mask == label_id, min_pixels):
            if key in {"left-shoe", "right-shoe"}:
                shoes.append((name, box, classify_label(name, box, person_box)[3], component))
                continue
            region = _region_from_component(
                original, name, box, component, skin, scale_x, scale_y, person_box, color_image=color_image
            )
            if region is not None:
                regions.append(region)
    merged = _merge_shoe_boxes(shoes)
    for name, box, _confidence, component in merged:
        region = _region_from_component(
            original,
            name,
            box,
            component,
            skin,
            scale_x,
            scale_y,
            person_box,
            friendly="shoes" if len(merged) == 1 and len(shoes) == 2 else None,
            color_image=color_image,
        )
        if region is not None:
            regions.append(region)
    return regions


def component_boxes(mask: np.ndarray, min_pixels: int) -> list[tuple[tuple[int, int, int, int], int]]:
    """Connected components as (y0, x0, y1, x1), area. y1 and x1 are exclusive."""
    return [(box, area) for box, area, _component in _components(mask, min_pixels)]


def _components(mask: np.ndarray, min_pixels: int) -> list[tuple[tuple[int, int, int, int], int, np.ndarray]]:
    labeled, count = _label_mask(mask.astype(bool))
    found = []
    for label_id in range(1, count + 1):
        component = labeled == label_id
        area = int(component.sum())
        if area < min_pixels:
            continue
        ys, xs = np.where(component)
        box = (int(ys.min()), int(xs.min()), int(ys.max()) + 1, int(xs.max()) + 1)
        found.append((box, area, component))
    return found


def load_state(output: Path) -> dict:
    path = output / LIBRARY_NAME
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhotoImportError(f"Could not read the import notes in {path.name}: {exc}") from exc
    data.setdefault("version", 1)
    data.setdefault("files", {})
    data.setdefault("garments", {})
    return data


def save_state(output: Path, state: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    destination = output / LIBRARY_NAME
    temporary = output / f".{LIBRARY_NAME}.tmp"
    temporary.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)


def suggest_name(color: str, friendly: str) -> str:
    return f"{color} {friendly}".strip()[:80]


def similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    first = np.asarray(left, dtype=np.float32)
    second = np.asarray(right, dtype=np.float32)
    denom = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denom == 0:
        return 0.0
    return float(np.dot(first, second) / denom)


def _record_region(
    state: dict,
    output: Path,
    source: Path,
    region: Region,
    embedder: Embedder,
    preset: str | dict | None = "small",
) -> tuple[str | None, bool]:
    if region.color and region.color_hex:
        color, color_hex = region.color, region.color_hex
    else:
        color, color_hex = dominant_color(region.crop)
    # The comparison signature stays at the small size, so a later picture-size change does not split duplicates.
    embedding = [
        round(float(value), 5)
        for value in embedder.embed(flatten_for_embed(modest_crop(region.crop, CROP_EDGE)))
    ]
    match = _find_duplicate(state, region.category, embedding)
    if match is not None:
        sources = match.setdefault("sources", [])
        source_text = str(source)
        if source_text not in sources:
            sources.append(source_text)
        return match.get("id"), False
    garment_id = uuid.uuid4().hex[:12]
    crop_path = output / "pending" / f"{garment_id}.webp"
    _save_crop(region.crop, crop_path, output, preset)
    state["garments"][garment_id] = {
        "id": garment_id,
        "status": "pending",
        "name": suggest_name(color, region.friendly),
        "category": region.category,
        "folder": region.folder,
        "color": color,
        "color_hex": color_hex,
        "season": "All",
        "label": region.label,
        "friendly": region.friendly,
        "confidence": round(float(region.confidence), 3),
        "crop_path": str(crop_path.resolve()),
        "crop_box": list(region.crop_box) if region.crop_box else None,
        "sources": [str(source)],
        "embedding": embedding,
        "closet_id": None,
        "created": _now(),
    }
    return garment_id, True


def refresh_source_links(items: pd.DataFrame, output: Path) -> pd.DataFrame:
    """Copy newly seen source photos onto closet rows that were already approved."""
    if not output.exists():
        return items
    state = load_state(output)
    updates: list[tuple[int, str, str]] = []
    for garment in state["garments"].values():
        closet_id = garment.get("closet_id")
        if garment.get("status") != "approved" or not closet_id:
            continue
        sources = [str(item) for item in garment.get("sources") or [] if str(item)]
        if not sources:
            continue
        updates.append((int(closet_id), sources[0], "|".join(sources)))
    if not updates:
        return items

    def current(column: str, closet_id: int) -> str | None:
        if column not in items.columns:
            return None
        mask = items["ID"] == closet_id
        if not bool(mask.any()):
            return ""
        return str(items.loc[mask, column].iloc[0])

    needed = False
    for closet_id, first, joined in updates:
        if not bool((items["ID"] == closet_id).any()):
            continue
        if current("Source_Photo", closet_id) != first or current("Source_Photos", closet_id) != joined:
            needed = True
            break
    if not needed:
        return items
    items = items.copy()
    if "Source_Photo" not in items.columns:
        items["Source_Photo"] = ""
    if "Source_Photos" not in items.columns:
        items["Source_Photos"] = ""
    for closet_id, first, joined in updates:
        mask = items["ID"] == closet_id
        if not bool(mask.any()):
            continue
        items.loc[mask, "Source_Photo"] = first
        items.loc[mask, "Source_Photos"] = joined
    return items


def _find_duplicate(state: dict, category: str, embedding: list[float]) -> dict | None:
    best = None
    best_score = 0.0
    for garment in state["garments"].values():
        if garment.get("status") not in {"pending", "approved", "rejected"}:
            continue
        score = similarity(embedding, garment.get("embedding") or [])
        if score < best_score:
            continue
        if not _is_same_item(category, garment.get("category", ""), score):
            continue
        best = garment
        best_score = score
    return best


def _is_same_item(left: str, right: str, score: float) -> bool:
    if score < DUPLICATE_SIMILARITY:
        return False
    if left == right:
        return True
    return {left, right} == {"Tops", "Outerwear"} and score >= SAME_GARMENT_ACROSS_LABELS


def _prepare_output(output: Path) -> None:
    try:
        output.mkdir(parents=True, exist_ok=True)
        (output / "pending").mkdir(exist_ok=True)
        for folder in FOLDER_BY_CATEGORY.values():
            (output / folder).mkdir(exist_ok=True)
    except OSError as exc:
        raise PhotoImportError(f"Could not create the crops folder: {exc}") from exc


def _empty_state() -> dict:
    return {"version": 1, "files": {}, "garments": {}}


def _save_crop(image: Image.Image, path: Path, output: Path, preset: str | dict | None = "small") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_inside(path, output)
    # The color name and hex were stored before this lossy save.
    payload = encode_webp(image, preset)
    temporary = path.with_name(f".{path.name}.tmp")
    _require_inside(temporary, output)
    temporary.write_bytes(payload)
    temporary.replace(path)


def storage_summary(output: Path, items: pd.DataFrame | None = None, root: Path | None = None) -> dict:
    """Bytes used by saved crops and closet photos. Original photo folders are not counted."""
    crops: list[int] = []
    if output.exists() and (output / LIBRARY_NAME).is_file():
        state = load_state(output)
        for garment in state["garments"].values():
            if garment.get("status") == "rejected":
                continue
            path = Path(str(garment.get("crop_path") or ""))
            if path.is_file() and _is_relative_to(path, output):
                crops.append(path.stat().st_size)
    closet: list[int] = []
    if items is not None and root is not None and "Image_Path" in getattr(items, "columns", []):
        folder = root / w.IMAGE_DIR_NAME
        for value in items["Image_Path"].tolist():
            resolved = w.resolve_image(value, root)
            if resolved is not None and _is_relative_to(resolved, folder):
                closet.append(resolved.stat().st_size)

    def average(values: list[int]) -> int:
        return int(round(sum(values) / len(values))) if values else 0

    return {
        "crop_bytes": sum(crops),
        "crop_count": len(crops),
        "crop_average": average(crops),
        "closet_bytes": sum(closet),
        "closet_count": len(closet),
        "closet_average": average(closet),
    }


def reclaim_output(output: Path, preset: str | dict | None = "small") -> dict:
    """Drop extra crop files and shrink ones that are larger than the chosen size. Never enlarge."""
    output = output.expanduser().resolve()
    spec = resolve_preset(preset)
    before = _tree_bytes(output)
    state = load_state(output) if (output / LIBRARY_NAME).is_file() else _empty_state()
    referenced: set[Path] = set()
    for garment in state["garments"].values():
        path = Path(str(garment.get("crop_path") or ""))
        if garment.get("status") == "rejected":
            _delete_our_file(path, output)
            garment["crop_path"] = ""
            continue
        if not path.is_file() or not _is_relative_to(path, output):
            garment["crop_path"] = ""
            continue
        destination = _downscale_file(path, spec, output)
        if destination is None:
            _delete_our_file(path, output)
            garment["crop_path"] = ""
            continue
        garment["crop_path"] = str(destination.resolve())
        referenced.add(destination.resolve())
    removed = _delete_unreferenced_images(output, referenced)
    if (output / LIBRARY_NAME).is_file() or state["garments"]:
        save_state(output, state)
    after = _tree_bytes(output)
    summary = storage_summary(output)
    return {
        "before": before,
        "after": after,
        "freed": max(0, before - after),
        "removed": removed,
        "crop_count": summary["crop_count"],
        "crop_average": summary["crop_average"],
    }


def _long_edge(path: Path) -> int | None:
    try:
        with Image.open(path) as image:
            return max(image.size)
    except (OSError, UnidentifiedImageError):
        return None


def _downscale_file(path: Path, preset: str | dict, output: Path) -> Path | None:
    """Rewrite a crop only when it is larger than the preset or not WebP yet. Never enlarge."""
    spec = resolve_preset(preset)
    edge = int(spec["edge"])
    long_edge = _long_edge(path)
    if long_edge is None:
        return None
    if path.suffix.lower() == ".webp" and long_edge <= edge:
        return path
    try:
        with Image.open(path) as image:
            image.load()
            payload = encode_webp(image, spec)
    except (OSError, UnidentifiedImageError):
        return None
    destination = path.with_suffix(".webp")
    _save_bytes(destination, payload, output)
    if destination.resolve() != path.resolve():
        _delete_our_file(path, output)
    return destination


def _existing_source(sources: list) -> Path | None:
    for value in sources or []:
        path = Path(str(value))
        if path.is_file():
            return path
    return None


def _master_crop(source: Path, box: list | tuple, current: Path | None) -> Image.Image:
    """The garment cut from the original photo, with the saved silhouette if we still have it."""
    image = _image_from_bytes(source.read_bytes())
    width, height = image.size
    try:
        left, upper, right, lower = [float(value) for value in box]
    except (TypeError, ValueError):
        left = upper = 0.0
        right = lower = 1.0
    pixel_box = (
        max(0, int(left * width)),
        max(0, int(upper * height)),
        min(width, int(round(right * width))),
        min(height, int(round(lower * height))),
    )
    if pixel_box[2] - pixel_box[0] < 2 or pixel_box[3] - pixel_box[1] < 2:
        pixel_box = (0, 0, width, height)
    crop = image.crop(pixel_box).convert("RGBA")
    if current is not None and current.is_file():
        try:
            with Image.open(current) as old:
                old.load()
                if "A" in old.getbands():
                    alpha = old.getchannel("A").resize(crop.size, Image.Resampling.BILINEAR)
                    crop.putalpha(alpha)
        except (OSError, UnidentifiedImageError):
            pass
    return modest_crop(crop, HIGH_EDGE)


def _reencode_source(source: Path, box: list | tuple, current: Path | None, preset: str | dict) -> bytes:
    """Cut the same garment out of the original photo and save it at the preset. Never enlarge."""
    return encode_webp(_master_crop(source, box, current), preset)


def master_from_garment(garment: dict) -> Image.Image | None:
    source = _existing_source(garment.get("sources") or [])
    box = garment.get("crop_box")
    current = Path(str(garment.get("crop_path") or ""))
    current = current if current.is_file() else None
    if source is not None and box:
        return _master_crop(source, box, current)
    if current is not None:
        try:
            with Image.open(current) as image:
                image.load()
                return image.copy()
        except (OSError, UnidentifiedImageError):
            return None
    return None


def apply_quality(output: Path, preset: str | dict, root: Path | None = None) -> dict:
    """Save the picture size. Rebuild a crop from its photo when that file is still there."""
    spec = save_preset(preset, root)
    rebuilt = 0
    kept = 0
    shrunk = 0
    output = output.expanduser()
    if output.exists() and (output / LIBRARY_NAME).is_file():
        state = load_state(output)
        for garment in state["garments"].values():
            if garment.get("status") == "rejected":
                continue
            path = Path(str(garment.get("crop_path") or ""))
            if not path.is_file() or not _is_relative_to(path, output):
                continue
            source = _existing_source(garment.get("sources") or [])
            box = garment.get("crop_box")
            if source is not None and box:
                payload = _reencode_source(source, box, path, spec)
                destination = path.with_suffix(".webp")
                _save_bytes(destination, payload, output)
                if destination.resolve() != path.resolve():
                    _delete_our_file(path, output)
                garment["crop_path"] = str(destination.resolve())
                rebuilt += 1
                continue
            before_edge = _long_edge(path)
            updated = _downscale_file(path, spec, output)
            if updated is None:
                garment["crop_path"] = ""
                continue
            after_edge = _long_edge(updated)
            if before_edge and after_edge and after_edge < before_edge:
                shrunk += 1
            else:
                kept += 1
            garment["crop_path"] = str(updated.resolve())
        save_state(output, state)
    return {"preset": spec["id"], "rebuilt": rebuilt, "kept": kept, "shrunk": shrunk}


def sample_outfit() -> list[tuple[str, Image.Image]]:
    pieces = []
    if not SAMPLE_DIR.is_dir():
        return pieces
    for path in sorted(SAMPLE_DIR.glob("*")):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        try:
            with Image.open(path) as image:
                image.load()
                pieces.append((path.stem.replace("-", " ").title(), image.copy()))
        except (OSError, UnidentifiedImageError):
            continue
    return pieces


def preview_rows(images: list[Image.Image]) -> list[dict]:
    """Encode the same pictures at every preset. A small source is not enlarged."""
    rows = []
    for spec in PRESET_LIST:
        payloads = [encode_webp(image, spec) for image in images]
        average = int(round(sum(len(payload) for payload in payloads) / len(payloads))) if payloads else 0
        rows.append({
            "id": spec["id"],
            "label": spec["label"],
            "detail": spec["detail"],
            "edge": spec["edge"],
            "payloads": payloads,
            "sizes": [len(payload) for payload in payloads],
            "average": average,
            "planning": projection_line(average, 1000),
        })
    return rows


def _tree_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _save_bytes(path: Path, payload: bytes, output: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_inside(path, output)
    temporary = path.with_name(f".{path.name}.tmp")
    _require_inside(temporary, output)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _delete_unreferenced_images(output: Path, referenced: set[Path]) -> int:
    removed = 0
    if not output.exists():
        return 0
    for path in output.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.resolve() in referenced:
            continue
        if not _is_relative_to(path, output):
            continue
        path.unlink()
        removed += 1
    return removed


def _move_our_file(source: Path, destination: Path, output: Path) -> Path:
    source = source.expanduser()
    destination = destination.expanduser()
    _require_inside(source, output)
    _require_inside(destination, output)
    if not source.is_file():
        raise PhotoImportError("The crop for that detection is missing.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.resolve() != source.resolve():
        destination = destination.with_name(f"{destination.stem}-{uuid.uuid4().hex[:6]}{destination.suffix}")
        _require_inside(destination, output)
    source.replace(destination)
    return destination.resolve()


def _delete_our_file(path: Path, output: Path) -> None:
    if not str(path):
        return
    try:
        _require_inside(path, output)
    except PhotoImportError:
        return
    if path.is_file():
        path.unlink()


def _require_inside(path: Path, root: Path) -> None:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise PhotoImportError("Refusing to write outside the crops folder.") from exc


def _tight_crop(original: Image.Image, mask: np.ndarray) -> tuple[Image.Image | None, tuple[float, float, float, float] | None]:
    """Cut just around the garment and leave everything else transparent."""
    fitted = _fit_mask(mask, original.size)
    if not fitted.any():
        return None, None
    ys, xs = np.where(fitted)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    pad_y = max(2, int(round((y1 - y0) * 0.02)))
    pad_x = max(2, int(round((x1 - x0) * 0.02)))
    width, height = original.size
    left = max(0, x0 - pad_x)
    upper = max(0, y0 - pad_y)
    right = min(width, x1 + pad_x)
    lower = min(height, y1 + pad_y)
    if right - left < 48 or lower - upper < 48:
        return None, None
    crop = original.crop((left, upper, right, lower)).convert("RGBA")
    alpha = Image.fromarray(np.where(fitted[upper:lower, left:right], np.uint8(255), np.uint8(0)), mode="L")
    crop.putalpha(alpha)
    width, height = original.size
    box = (left / width, upper / height, right / width, lower / height)
    # Keep enough detail to re-save at High. The chosen preset is applied when the file is written.
    return modest_crop(crop, HIGH_EDGE), box


def _crop_original(original: Image.Image, box: tuple[int, int, int, int], scale_x: float, scale_y: float) -> Image.Image | None:
    y0, x0, y1, x1 = box
    left = x0 * scale_x
    upper = y0 * scale_y
    right = x1 * scale_x
    lower = y1 * scale_y
    pad_x = (right - left) * 0.08
    pad_y = (lower - upper) * 0.08
    width, height = original.size
    left = int(max(0, left - pad_x))
    upper = int(max(0, upper - pad_y))
    right = int(min(width, right + pad_x))
    lower = int(min(height, lower + pad_y))
    if right - left < 48 or lower - upper < 48:
        return None
    return original.crop((left, upper, right, lower))


def _merge_shoe_boxes(
    shoes: list[tuple[str, tuple[int, int, int, int], float, np.ndarray]],
) -> list[tuple[str, tuple[int, int, int, int], float, np.ndarray]]:
    left = [item for item in shoes if item[0].lower().startswith("left")]
    right = [item for item in shoes if item[0].lower().startswith("right")]
    if len(left) == 1 and len(right) == 1 and len(shoes) == 2:
        _, first, first_conf, first_mask = left[0]
        _, second, second_conf, second_mask = right[0]
        union = (
            min(first[0], second[0]),
            min(first[1], second[1]),
            max(first[2], second[2]),
            max(first[3], second[3]),
        )
        return [("Right-shoe", union, max(first_conf, second_conf), first_mask | second_mask)]
    return list(shoes)


def _label_mask(mask: np.ndarray) -> tuple[np.ndarray, int]:
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    parent = [0]

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    current = 0
    for y in range(height):
        for x in range(width):
            if not mask[y, x]:
                continue
            left = int(labels[y, x - 1]) if x else 0
            up = int(labels[y - 1, x]) if y else 0
            if left and up and left != up:
                labels[y, x] = left
                parent[find(up)] = find(left)
            elif left or up:
                labels[y, x] = left or up
            else:
                current += 1
                parent.append(current)
                labels[y, x] = current
    roots = {}
    next_id = 0
    for y, x in zip(*np.where(labels > 0)):
        root = find(int(labels[y, x]))
        if root not in roots:
            next_id += 1
            roots[root] = next_id
        labels[y, x] = roots[root]
    return labels, next_id


def _image_from_bytes(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as incoming:
        prepared = prepare_photo(incoming)
        prepared.load()
        return prepared


def _signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _region_from_component(
    original: Image.Image,
    label_name: str,
    box: tuple[int, int, int, int],
    component: np.ndarray,
    skin: np.ndarray,
    scale_x: float,
    scale_y: float,
    person_box: tuple[int, int, int, int],
    friendly: str | None = None,
    color_image: Image.Image | None = None,
) -> Region | None:
    category, folder, guessed, confidence = classify_label(label_name, box, person_box)
    usable = component & ~skin
    if not np.any(usable):
        usable = component
    measured_on = color_image or original
    # Measure the color on the uncompressed mask. The WebP file is written later.
    color, color_hex = dominant_color(measured_on, _fit_mask(usable, measured_on.size))
    crop, crop_box = _tight_crop(original, usable)
    if crop is None:
        return None
    return Region(
        label_name,
        category,
        folder,
        friendly or guessed,
        crop,
        confidence,
        color,
        color_hex,
        crop_box,
    )


def _fit_mask(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    if mask.shape == (height, width):
        return mask.astype(bool)
    image = Image.fromarray(np.where(mask, np.uint8(255), np.uint8(0)), mode="L")
    image = image.resize((width, height), Image.Resampling.NEAREST)
    return np.asarray(image) > 127


def _to_srgb(image: Image.Image) -> Image.Image:
    profile = image.info.get("icc_profile")
    if not profile:
        return image
    try:
        from PIL import ImageCms

        source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
        destination = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(image, source, destination, outputMode="RGB")
    except Exception:
        return image


def _srgb_profile() -> bytes:
    global _SRGB_PROFILE
    if _SRGB_PROFILE is None:
        try:
            from PIL import ImageCms

            _SRGB_PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        except Exception:
            _SRGB_PROFILE = b""
    return _SRGB_PROFILE


def _rgb_to_lab(pixels: np.ndarray) -> np.ndarray:
    linear = np.where(pixels <= 10.31475, pixels / 255.0 / 12.92, ((pixels / 255.0 + 0.055) / 1.055) ** 2.4)
    xyz = linear @ _XYZ_FROM_RGB.T
    scaled = xyz / _WHITE
    curved = np.where(scaled > _LAB_DELTA**3, np.cbrt(scaled), scaled / (3 * _LAB_DELTA**2) + 4 / 29)
    lightness = 116 * curved[:, 1] - 16
    return np.stack(
        [lightness, 500 * (curved[:, 0] - curved[:, 1]), 200 * (curved[:, 1] - curved[:, 2])],
        axis=1,
    )


def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    lightness, green_red, blue_yellow = (float(value) for value in lab)
    fy = (lightness + 16) / 116
    fx = fy + green_red / 500
    fz = fy - blue_yellow / 200
    curved = np.array([fx, fy, fz], dtype=np.float64)
    scaled = np.where(curved > _LAB_DELTA, curved**3, 3 * _LAB_DELTA**2 * (curved - 4 / 29))
    linear = (scaled * _WHITE) @ _RGB_FROM_XYZ.T
    linear = np.clip(linear, 0, None)
    encoded = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * np.power(linear, 1 / 2.4) - 0.055)
    return np.clip(np.rint(encoded * 255.0), 0, 255).astype(np.int64)


def _nearest_name(rgb: np.ndarray) -> str:
    names, palette = _palette_lab()
    lab = _rgb_to_lab(np.array([rgb], dtype=np.float64))[0]
    distances = ((palette - lab) ** 2).sum(axis=1)
    return names[int(np.argmin(distances))]


def _palette_lab() -> tuple[list[str], np.ndarray]:
    global _PALETTE_LAB
    if _PALETTE_LAB is None:
        names = list(COLOR_RGB)
        samples = np.array([COLOR_RGB[name] for name in names], dtype=np.float64)
        _PALETTE_LAB = (names, _rgb_to_lab(samples))
    return _PALETTE_LAB


def _kmeans(points: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    centers = [points[0].copy()]
    while len(centers) < k:
        stacked = np.stack(centers)
        nearest = ((points[:, None, :] - stacked[None, :, :]) ** 2).sum(axis=2).min(axis=1)
        index = int(np.argmax(nearest))
        if float(nearest[index]) <= 1e-6:
            break
        centers.append(points[index].copy())
    centers_array = np.stack(centers)
    labels = np.zeros(len(points), dtype=np.int32)
    for _ in range(12):
        distances = ((points[:, None, :] - centers_array[None, :, :]) ** 2).sum(axis=2)
        labels = distances.argmin(axis=1).astype(np.int32)
        for index in range(len(centers_array)):
            chosen = points[labels == index]
            if len(chosen):
                centers_array[index] = chosen.mean(axis=0)
    return centers_array, labels


def _cli(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Import a wardrobe from local photos.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download-models", help="Download the clothing model once, then run it offline.")
    scan = commands.add_parser("scan", help="Scan a folder of pictures into a separate crops folder.")
    scan.add_argument("--source", required=True, help="Folder of pictures. Files in here are only read.")
    scan.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Crops folder, outside the photo folder.")
    scan.add_argument("--limit", type=int, default=None, help="How many new photos to scan this time.")
    args = parser.parse_args(argv)
    try:
        import import_models

        if args.command == "download-models":
            import_models.download_models()
            print("Models saved on this computer. Later scans can run offline.")
            return 0
        finder, embedder = import_models.load_engines()
        updates = scan_folder(
            Path(args.source),
            Path(args.output),
            finder,
            embedder,
            limit=args.limit,
            preset=current_preset(),
        )
        for update in updates:
            print(update.message, flush=True)
    except PhotoImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
