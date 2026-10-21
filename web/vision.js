/**
 * Clothing detection runs in this browser.
 * Model files are downloaded once into the browser cache. Photos are not sent with that request.
 */

import {
  dominantColor,
  labelKey,
  presetById,
  regionsFromLabelMasks,
  scaledCropBox,
  suggestName,
} from "./closet.js";

const DETECT_EDGE = 640;
const EMBED_EDGE = 384;

const SEGMENTER_ID = "Xenova/segformer_b0_clothes";
const EMBEDDER_ID = "Xenova/dinov2-small";
const LIBRARY_URL = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.1";

let transformersPromise = null;
let segmenterPromise = null;
let embedderPromise = null;

function library() {
  if (!transformersPromise) {
    transformersPromise = import(LIBRARY_URL).then((module) => {
      module.env.allowLocalModels = false;
      module.env.useBrowserCache = true;
      module.env.backends.onnx.wasm.numThreads = 1;
      module.env.backends.onnx.wasm.proxy = false;
      return module;
    });
  }
  return transformersPromise;
}

async function pipelineFor(task, model, dtype, onProgress) {
  const module = await library();
  return module.pipeline(task, model, {
    dtype,
    device: "wasm",
    progress_callback: onProgress,
  });
}

export function modelsCached() {
  return Boolean(segmenterPromise && embedderPromise);
}

export async function ensureModels(onProgress) {
  if (!segmenterPromise) {
    segmenterPromise = pipelineFor("image-segmentation", SEGMENTER_ID, "q8", (update) => {
      onProgress?.({ ...update, which: "clothing model" });
    }).catch((error) => {
      segmenterPromise = null;
      throw error;
    });
  }
  if (!embedderPromise) {
    embedderPromise = pipelineFor("image-feature-extraction", EMBEDDER_ID, "q4", (update) => {
      onProgress?.({ ...update, which: "comparison model" });
    }).catch((error) => pipelineFor("image-feature-extraction", EMBEDDER_ID, "q8", (update) => {
      onProgress?.({ ...update, which: "comparison model" });
      console.warn("The smaller comparison model did not load. Using the next size.", error);
    })).catch((error) => {
      embedderPromise = null;
      throw error;
    });
  }
  const [segmenter, embedder] = await Promise.all([segmenterPromise, embedderPromise]);
  return { segmenter, embedder };
}

function maskBinary(mask) {
  const width = mask.width;
  const height = mask.height;
  const data = mask.data;
  const channels = mask.channels || Math.max(1, Math.round(data.length / (width * height)));
  const binary = new Uint8Array(width * height);
  for (let index = 0; index < binary.length; index += 1) {
    if (data[index * channels] > 8) binary[index] = 1;
  }
  return { binary, width, height };
}

function drawingContext(canvas) {
  try {
    return canvas.getContext("2d", { willReadFrequently: true, colorSpace: "srgb" })
      || canvas.getContext("2d", { willReadFrequently: true });
  } catch {
    return canvas.getContext("2d", { willReadFrequently: true });
  }
}

function canvasSource(source, maxEdge) {
  const scale = Math.min(1, maxEdge / Math.max(source.width, source.height));
  const width = Math.max(1, Math.round(source.width * scale));
  const height = Math.max(1, Math.round(source.height * scale));
  if (source instanceof HTMLCanvasElement && width === source.width && height === source.height) return source;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  drawingContext(canvas).drawImage(source, 0, 0, width, height);
  return canvas;
}

async function decodePhoto(file) {
  const options = {
    imageOrientation: "from-image",
    colorSpaceConversion: "default",
    premultiplyAlpha: "none",
  };
  try {
    return await createImageBitmap(file, options);
  } catch {
    return await createImageBitmap(file);
  }
}

function scaleBinary(binary, srcWidth, srcHeight, dstWidth, dstHeight) {
  if (!binary) return null;
  if (srcWidth === dstWidth && srcHeight === dstHeight) return binary;
  const out = new Uint8Array(dstWidth * dstHeight);
  for (let y = 0; y < dstHeight; y += 1) {
    const srcY = Math.min(srcHeight - 1, Math.floor((y * srcHeight) / dstHeight));
    for (let x = 0; x < dstWidth; x += 1) {
      const srcX = Math.min(srcWidth - 1, Math.floor((x * srcWidth) / dstWidth));
      out[y * dstWidth + x] = binary[srcY * srcWidth + srcX];
    }
  }
  return out;
}

function canvasBlob(canvas, type = "image/webp", quality = 0.8) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Could not keep a copy of that crop."))), type, quality);
  });
}

function maskedCrop(source, binary, maskWidth, maskHeight, box) {
  const [left, top, right, bottom] = box;
  const width = Math.max(1, right - left);
  const height = Math.max(1, bottom - top);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = drawingContext(canvas);
  context.drawImage(source, left, top, width, height, 0, 0, width, height);
  if (!binary || !maskWidth || !maskHeight) return canvas;
  const image = context.getImageData(0, 0, width, height);
  const frameWidth = source.width;
  const frameHeight = source.height;
  for (let y = 0; y < height; y += 1) {
    const srcY = Math.min(maskHeight - 1, Math.floor(((top + y) * maskHeight) / frameHeight));
    for (let x = 0; x < width; x += 1) {
      const srcX = Math.min(maskWidth - 1, Math.floor(((left + x) * maskWidth) / frameWidth));
      if (!binary[srcY * maskWidth + srcX]) image.data[(y * width + x) * 4 + 3] = 0;
    }
  }
  context.putImageData(image, 0, 0);
  return canvas;
}

function embedCanvas(source) {
  const canvas = document.createElement("canvas");
  canvas.width = source.width;
  canvas.height = source.height;
  const context = drawingContext(canvas);
  context.fillStyle = "#f6f1ea";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source, 0, 0);
  return canvas;
}

function presetEdge(preset, longEdge) {
  return Math.max(1, Math.min(preset.edge, longEdge || preset.edge));
}

export async function shrinkStoredPhoto(file, preset = presetById("small")) {
  const decoded = await decodePhoto(file);
  const longEdge = Math.max(decoded.width, decoded.height);
  const canvas = canvasSource(decoded, presetEdge(preset, longEdge));
  decoded.close?.();
  const blob = await canvasBlob(canvas, "image/webp", preset.quality);
  if (file.size && file.type === "image/webp" && blob.size >= file.size && longEdge <= preset.edge) return file;
  return new File([blob], "piece.webp", { type: blob.type || "image/webp" });
}

export async function downscaleBlob(blob, preset = presetById("small")) {
  if (!blob) return blob;
  const decoded = await decodePhoto(blob);
  const longEdge = Math.max(decoded.width, decoded.height);
  if (longEdge <= preset.edge) {
    decoded.close?.();
    return blob;
  }
  const canvas = canvasSource(decoded, preset.edge);
  decoded.close?.();
  const next = await canvasBlob(canvas, "image/webp", preset.quality);
  return next.size < blob.size ? next : blob;
}

function cropNormalized(decoded, cropBox) {
  const width = decoded.width;
  const height = decoded.height;
  let left = 0;
  let top = 0;
  let right = width;
  let bottom = height;
  if (Array.isArray(cropBox) && cropBox.length === 4) {
    left = Math.max(0, Math.floor(Number(cropBox[0]) * width));
    top = Math.max(0, Math.floor(Number(cropBox[1]) * height));
    right = Math.min(width, Math.ceil(Number(cropBox[2]) * width));
    bottom = Math.min(height, Math.ceil(Number(cropBox[3]) * height));
    if (right - left < 2 || bottom - top < 2) {
      left = 0;
      top = 0;
      right = width;
      bottom = height;
    }
  }
  const canvas = document.createElement("canvas");
  canvas.width = right - left;
  canvas.height = bottom - top;
  drawingContext(canvas).drawImage(decoded, left, top, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height);
  return canvas;
}

async function copyAlpha(canvas, blob) {
  if (!blob) return canvas;
  try {
    const old = await decodePhoto(blob);
    const mask = document.createElement("canvas");
    mask.width = canvas.width;
    mask.height = canvas.height;
    const maskContext = drawingContext(mask);
    maskContext.drawImage(old, 0, 0, mask.width, mask.height);
    old.close?.();
    const context = drawingContext(canvas);
    const cut = context.getImageData(0, 0, canvas.width, canvas.height);
    const alpha = maskContext.getImageData(0, 0, mask.width, mask.height);
    let transparent = false;
    for (let index = 3; index < cut.data.length; index += 4) {
      cut.data[index] = alpha.data[index];
      if (alpha.data[index] < 250) transparent = true;
    }
    if (transparent) context.putImageData(cut, 0, 0);
  } catch {
    // A source photo without a saved silhouette keeps the rectangular crop.
  }
  return canvas;
}

export async function reencodeSource(file, cropBox, currentBlob, preset = presetById("small")) {
  const decoded = await decodePhoto(file);
  const canvas = await copyAlpha(cropNormalized(decoded, cropBox), currentBlob);
  decoded.close?.();
  const longEdge = Math.max(canvas.width, canvas.height);
  const sized = canvasSource(canvas, presetEdge(preset, longEdge));
  return canvasBlob(sized, "image/webp", preset.quality);
}

async function embeddingOf(embedder, canvas) {
  const blob = await canvasBlob(canvas, "image/png");
  const output = await embedder(blob, { pooling: "mean", normalize: true });
  const raw = output?.data ? Array.from(output.data) : [];
  return raw.map((value) => Math.round(Number(value) * 100000) / 100000);
}

export async function findGarments(file, onProgress, preset = presetById("small")) {
  const { segmenter, embedder } = await ensureModels(onProgress);
  const decoded = await decodePhoto(file);
  const working = canvasSource(decoded, DETECT_EDGE);
  const frame = drawingContext(working).getImageData(0, 0, working.width, working.height).data;
  const input = await canvasBlob(working, "image/png");
  const masks = await segmenter(input);
  const labelMasks = masks.map((entry) => ({ label: entry.label, ...maskBinary(entry.mask) }));
  const regions = regionsFromLabelMasks(labelMasks);
  if (!regions.length) {
    const counts = labelMasks.map((mask) => {
      let pixels = 0;
      for (const value of mask.binary) pixels += value;
      return `${mask.label}:${pixels}`;
    }).join(", ");
    console.info(`No clothing regions in ${file.name}. Masks: ${counts || "none"}`);
  }
  const found = [];
  for (const region of regions) {
    const fullBox = scaledCropBox(region.box, region.maskWidth, region.maskHeight, decoded.width, decoded.height);
    if (!fullBox) continue;
    const aligned = scaleBinary(region.binary, region.maskWidth, region.maskHeight, working.width, working.height);
    const measured = aligned
      ? dominantColor(frame, aligned, 4)
      : dominantColor(frame, null, 4);
    const cut = maskedCrop(decoded, region.binary, region.maskWidth, region.maskHeight, fullBox);
    const forEmbed = canvasSource(cut, EMBED_EDGE);
    const stored = canvasSource(cut, presetEdge(preset, Math.max(cut.width, cut.height)));
    const friendly = region.friendly;
    found.push({
      label: region.label,
      category: region.category,
      folder: region.folder,
      friendly,
      confidence: region.confidence,
      color: measured.name,
      colorHex: measured.hex,
      name: suggestName(measured.name, friendly),
      season: "All",
      cropBox: [
        fullBox[0] / decoded.width,
        fullBox[1] / decoded.height,
        fullBox[2] / decoded.width,
        fullBox[3] / decoded.height,
      ],
      cropBlob: await canvasBlob(stored, "image/webp", preset.quality),
      embedding: await embeddingOf(embedder, embedCanvas(forEmbed)),
      note: labelKey(region.label).startsWith("upper") && region.category === "Outerwear"
        ? "Suggested as outerwear because the piece looks long. Change it if it is a shirt."
        : region.confidence < 0.6
          ? "Best guess. Check the category before approving."
          : "",
    });
  }
  decoded.close?.();
  return found;
}
