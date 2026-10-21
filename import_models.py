"""Clothing models that run on this computer.

The files are downloaded once into model_cache/. After that, loading them
turns Hugging Face and Transformers offline so a scan does not call out.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import photo_import as pi
import wardrobe as w

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

CACHE = w.APP_DIR / "model_cache"
SEGFORMER_DIR = CACHE / "segformer_b2_clothes"
EMBEDDER_PATH = CACHE / "mobilenet_v3_small.pth"
MARKER = CACHE / "ready.json"
MODEL_ID = "mattmdjaga/segformer_b2_clothes"
_MEAN = (0.485, 0.456, 0.406)
_STD = (0.229, 0.224, 0.225)

INSTALL_HINT = """pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt"""


def _point_caches() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(CACHE)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(CACHE / "hub")
    os.environ["TORCH_HOME"] = str(CACHE / "torch")


def packages_ready() -> tuple[bool, str]:
    """True when the local libraries are installed. Does not download anything."""
    missing = []
    for name in ("torch", "torchvision", "transformers", "huggingface_hub"):
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if not missing:
        return True, ""
    return False, (
        "Photo import needs PyTorch and Transformers on this computer. "
        "Install the CPU build so the download stays small, then install the rest. "
        "The closet works without them."
    )


def models_ready() -> bool:
    config = SEGFORMER_DIR / "config.json"
    return MARKER.is_file() and config.is_file() and EMBEDDER_PATH.is_file()


def download_models() -> None:
    """Download the segmenter and the embedding network once."""
    if models_ready():
        return
    ready, message = packages_ready()
    if not ready:
        raise pi.PhotoImportError(message)
    _point_caches()
    saved = {key: os.environ.get(key) for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    try:
        _download_files()
    except pi.PhotoImportError:
        raise
    except Exception as exc:
        raise pi.PhotoImportError(
            "The clothing model could not be downloaded. "
            "Check the connection once, then scans stay on this computer. "
            f"({exc})"
        ) from exc
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    if not models_ready():
        raise pi.PhotoImportError("The model download finished without the expected files.")


def load_engines() -> tuple[pi.ClothesFinder, pi.Embedder]:
    """Load models from disk. Refuses to fetch weights."""
    if not models_ready():
        raise pi.PhotoImportError(
            "Download the clothing model once before scanning. "
            "After that it runs on this computer."
        )
    ready, message = packages_ready()
    if not ready:
        raise pi.PhotoImportError(message)
    _point_caches()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    return LocalClothesFinder(), LocalEmbedder()


def _download_files() -> None:
    from huggingface_hub import snapshot_download

    SEGFORMER_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        local_dir=str(SEGFORMER_DIR),
        allow_patterns=["config.json", "preprocessor_config.json", "model.safetensors"],
    )
    import torch
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

    weights = MobileNet_V3_Small_Weights.DEFAULT
    network = mobilenet_v3_small(weights=weights)
    EMBEDDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(network.state_dict(), EMBEDDER_PATH)
    MARKER.write_text(
        json.dumps(
            {
                "segmenter": MODEL_ID,
                "embedder": "mobilenet_v3_small",
                "offline": True,
            }
        ),
        encoding="utf-8",
    )


def _model_views(original):
    """Return the detection-sized photo and the 32-pixel-aligned model input."""
    from PIL import Image

    working = pi.downscale(pi.prepare_photo(original), pi.DETECT_EDGE)
    width, height = working.size
    snapped_w = max(32, (width // 32) * 32)
    snapped_h = max(32, (height // 32) * 32)
    if (snapped_w, snapped_h) == working.size:
        return working, working
    return working, working.resize((snapped_w, snapped_h), Image.Resampling.LANCZOS)


class LocalClothesFinder(pi.ClothesFinder):
    def __init__(self) -> None:
        import torch
        from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor

        torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        self._torch = torch
        self.processor = SegformerImageProcessor.from_pretrained(
            str(SEGFORMER_DIR),
            local_files_only=True,
        )
        self.model = AutoModelForSemanticSegmentation.from_pretrained(
            str(SEGFORMER_DIR),
            local_files_only=True,
        )
        self.model.eval()

    def find(self, image):
        torch = self._torch
        working, model_image = _model_views(image)
        inputs = self.processor(images=model_image.copy(), return_tensors="pt", do_resize=False)
        with torch.inference_mode():
            logits = self.model(**inputs).logits
            sized = torch.nn.functional.interpolate(
                logits,
                size=working.size[::-1],
                mode="bilinear",
                align_corners=False,
            )
            mask = sized.argmax(dim=1)[0].cpu().numpy()
        return pi.regions_from_mask(mask, working, self.model.config.id2label)


class LocalEmbedder(pi.Embedder):
    def __init__(self) -> None:
        import torch
        from torchvision.models import mobilenet_v3_small

        self._torch = torch
        network = mobilenet_v3_small(weights=None)
        state = torch.load(EMBEDDER_PATH, map_location="cpu", weights_only=True)
        network.load_state_dict(state)
        network.eval()
        self.network = network

    def embed(self, image) -> list[float]:
        import numpy as np
        from PIL import Image

        torch = self._torch
        prepared = image.convert("RGB").resize((256, 256), Image.Resampling.BILINEAR)
        side = (256 - 224) // 2
        prepared = prepared.crop((side, side, side + 224, side + 224))
        pixels = np.asarray(prepared, dtype="float32") / 255.0
        mean = np.asarray(_MEAN, dtype="float32")
        std = np.asarray(_STD, dtype="float32")
        pixels = (pixels - mean) / std
        tensor = torch.from_numpy(pixels).permute(2, 0, 1).unsqueeze(0)
        with torch.inference_mode():
            features = self.network.features(tensor)
            pooled = self.network.avgpool(features)
            flat = torch.flatten(pooled, 1)
            norm = torch.linalg.vector_norm(flat, dim=1, keepdim=True).clamp_min(1e-12)
            flat = flat / norm
        return [float(value) for value in flat[0].tolist()]
