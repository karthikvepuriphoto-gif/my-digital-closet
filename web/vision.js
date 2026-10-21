/**
 * Clothing detection runs in this browser.
 * Model files are downloaded once into the browser cache. Photos are not sent with that request.
 */

import {
  dominantColor,
  labelKey,
  regionsFromLabelMasks,
  scaledCropBox,
  suggestName,
} from "./closet.js";

const DETECT_EDGE = 640;
const CROP_EDGE = 384;
const WEBP_QUALITY = 0.8;

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

function canvasBlob(canvas, type = "image/webp", quality = WEBP_QUALITY) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Could not keep a copy of that crop."))), type, quality);
  });
}

function maskedCrop(working, binary, box) {
  const [left, top, right, bottom] = box;
  const width = right - left;
  const height = bottom - top;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = drawingContext(canvas);
  context.drawImage(working, left, top, width, height, 0, 0, width, height);
  if (!binary) return canvas;
  const image = context.getImageData(0, 0, width, height);
  const frameWidth = working.width;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!binary[(top + y) * frameWidth + (left + x)]) image.data[(y * width + x) * 4 + 3] = 0;
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

export async function shrinkStoredPhoto(file) {
  const decoded = await decodePhoto(file);
  const canvas = canvasSource(decoded, CROP_EDGE);
  decoded.close?.();
  const blob = await canvasBlob(canvas);
  if (file.size && file.type === "image/webp" && blob.size >= file.size) return file;
  return new File([blob], "piece.webp", { type: blob.type || "image/webp" });
}

async function embeddingOf(embedder, canvas) {
  const blob = await canvasBlob(canvas, "image/png");
  const output = await embedder(blob, { pooling: "mean", normalize: true });
  const raw = output?.data ? Array.from(output.data) : [];
  return raw.map((value) => Math.round(Number(value) * 100000) / 100000);
}

export async function findGarments(file, onProgress) {
  const { segmenter, embedder } = await ensureModels(onProgress);
  const decoded = await decodePhoto(file);
  const working = canvasSource(decoded, DETECT_EDGE);
  decoded.close?.();
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
    const cropBox = scaledCropBox(region.box, region.maskWidth, region.maskHeight, working.width, working.height);
    if (!cropBox) continue;
    const aligned = scaleBinary(region.binary, region.maskWidth, region.maskHeight, working.width, working.height);
    const measured = aligned
      ? dominantColor(frame, aligned, 4)
      : dominantColor(frame, null, 4);
    const modest = canvasSource(maskedCrop(working, aligned, cropBox), CROP_EDGE);
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
      cropBlob: await canvasBlob(modest),
      embedding: await embeddingOf(embedder, embedCanvas(modest)),
      note: labelKey(region.label).startsWith("upper") && region.category === "Outerwear"
        ? "Suggested as outerwear because the piece looks long. Change it if it is a shirt."
        : region.confidence < 0.6
          ? "Best guess. Check the category before approving."
          : "",
    });
  }
  return found;
}
