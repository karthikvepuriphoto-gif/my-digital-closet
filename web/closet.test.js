import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyLabel,
  closetSummary,
  componentBoxes,
  fileKey,
  filterItems,
  findDuplicate,
  itemsFromCsv,
  itemsToCsv,
  mergeShoeBoxes,
  dominantColor,
  garmentMask,
  nearestColor,
  outfitsFromCsv,
  regionsFromLabelMasks,
  formatBytes,
  presetById,
  projectionLine,
  spaceComparison,
  storageLines,
  QUALITY_PRESETS,
  scaledCropBox,
  scrubOutfits,
  storageReport,
  sortItems,
  validateOutfit,
} from "./closet.js";

const LEGACY = `ID,Category,Sub-Category,Primary Color,Season,Image_Path,Notes
1,Tops,Oxford Shirt,White,All,closet_images/item_1.png,soft
9,Footwear,Loafers,Black,Autumn,None,no photo
`;

test("legacy none photo and extra column survive a round trip", () => {
  const items = itemsFromCsv(LEGACY);
  assert.equal(items[1].name, "Loafers");
  assert.equal(items[1].imagePath, "");
  assert.equal(items[0].extra.Notes, "soft");
  const again = itemsFromCsv(itemsToCsv(items.map((item) => ({ ...item, imageBlob: item.id === 1 ? new Blob(["x"]) : null }))));
  assert.equal(again[0].imagePath, "closet_images/item_1.png");
  assert.equal(again[1].imagePath, "");
  assert.equal(again[0].extra.Notes, "soft");
});

test("season filter keeps all-season pieces and name sort is alphabetical", () => {
  const items = [
    { id: 2, name: "Turtleneck", category: "Tops", color: "Black", season: "Winter" },
    { id: 1, name: "Oxford Shirt", category: "Tops", color: "White", season: "All" },
    { id: 4, name: "Chinos", category: "Bottoms", color: "Beige", season: "Spring" },
  ];
  const winter = filterItems(items, { season: "Winter" });
  assert.deepEqual(winter.map((item) => item.name).sort(), ["Oxford Shirt", "Turtleneck"]);
  assert.deepEqual(sortItems(items, "Name").map((item) => item.name), ["Chinos", "Oxford Shirt", "Turtleneck"]);
});

test("outfit rules and removal keep the other pieces", () => {
  assert.match(validateOutfit("Separates", { topId: 1, bottomId: null }), /top and a bottom/);
  assert.equal(validateOutfit("One piece", { fullBodyId: 6 }), "");
  const outfits = scrubOutfits([{ id: 1, topId: 2, bottomId: 3, footwearId: 7, outerwearId: null, fullBodyId: null }], 3);
  assert.equal(outfits[0].bottomId, null);
  assert.equal(outfits[0].topId, 2);
});

test("summary mentions the fullest category", () => {
  const text = closetSummary([
    { category: "Tops", color: "White", season: "All" },
    { category: "Tops", color: "White", season: "Winter" },
  ]);
  assert.match(text, /2 pieces/);
  assert.match(text, /tops/);
  assert.match(text, /white/);
  const tied = closetSummary([
    { category: "Tops", color: "White", season: "All" },
    { category: "Bottoms", color: "Blue", season: "All" },
  ]);
  assert.match(tied, /evenly split across bottoms and tops/);
  assert.match(tied, /blue and white are tied/);
});

test("color, outerwear heuristic, shoes, and tiny crops", () => {
  assert.equal(nearestColor(new Uint8Array([50, 90, 170])), "Blue");
  const measured = dominantColor(new Uint8Array([50, 90, 170]));
  assert.equal(measured.name, "Blue");
  assert.match(measured.hex, /^#[0-9A-F]{6}$/);
  const width = 6;
  const height = 6;
  const pixels = new Uint8Array(width * height * 3);
  pixels.fill(245);
  const garment = new Uint8Array(width * height);
  for (let y = 1; y < 5; y += 1) {
    for (let x = 1; x < 5; x += 1) {
      if (y === 1 || y === 4 || x === 1 || x === 4) {
        const index = y * width + x;
        garment[index] = 1;
        pixels[index * 3] = 180;
        pixels[index * 3 + 1] = 40;
        pixels[index * 3 + 2] = 40;
      }
    }
  }
  assert.equal(dominantColor(pixels, garment, 3).name, "Red");
  assert.equal(dominantColor(pixels, null, 3).name, "White");
  const skin = new Uint8Array(garment.length);
  skin[1 * width + 1] = 1;
  skin[1 * width + 2] = 1;
  skin[1 * width + 3] = 1;
  skin[1 * width + 4] = 1;
  const cloth = garmentMask(garment, skin);
  assert.equal(cloth[1 * width + 1], 0);
  assert.equal(dominantColor(pixels, cloth, 3).name, "Red");
  assert.equal(classifyLabel("Upper-clothes", [20, 0, 160, 10], [0, 0, 200, 20]).category, "Outerwear");
  assert.equal(classifyLabel("Upper-clothes", [30, 0, 80, 10], [0, 0, 200, 20]).category, "Tops");
  assert.equal(classifyLabel("Upper-clothes", [0, 0, 200, 20], [0, 0, 200, 20]).category, "Tops");
  const merged = mergeShoeBoxes([
    { label: "Left-shoe", box: [10, 10, 40, 30], confidence: 0.7 },
    { label: "Right-shoe", box: [10, 50, 40, 80], confidence: 0.7 },
  ]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].friendly, "shoes");
  const binary = new Uint8Array(20 * 20);
  for (let y = 2; y < 8; y += 1) for (let x = 2; x < 8; x += 1) binary[y * 20 + x] = 1;
  for (let y = 12; y < 18; y += 1) for (let x = 12; x < 18; x += 1) binary[y * 20 + x] = 1;
  assert.equal(componentBoxes(binary, 20, 20, 10).length, 2);
  assert.equal(scaledCropBox([0, 0, 10, 10], 100, 100, 100, 100), null);
});

test("duplicate signatures collapse a top and a coat, not a shoe", () => {
  const embedding = [1, 0, 0];
  const garments = [{ id: "a", status: "rejected", category: "Tops", embedding, sourceNames: ["one.jpg"] }];
  assert.equal(findDuplicate(garments, "Outerwear", embedding).id, "a");
  assert.equal(findDuplicate(garments, "Footwear", embedding), null);
  const outfits = outfitsFromCsv("ID,Name,Top_ID,Bottom_ID,FullBody_ID,Outerwear_ID,Footwear_ID,Created\n1,Cold walk,2,3,,5,7,2026-10-21\n");
  assert.equal(outfits[0].name, "Cold walk");
  assert.equal(outfits[0].footwearId, 7);
});

test("regions keep a long top as outerwear and merge both shoes", () => {
  const width = 40;
  const height = 80;
  const upper = new Uint8Array(width * height);
  const face = new Uint8Array(width * height);
  const legs = new Uint8Array(width * height);
  const left = new Uint8Array(width * height);
  const right = new Uint8Array(width * height);
  for (let y = 8; y < 60; y += 1) for (let x = 8; x < 32; x += 1) upper[y * width + x] = 1;
  for (let y = 0; y < 8; y += 1) for (let x = 14; x < 26; x += 1) face[y * width + x] = 1;
  for (let y = 60; y < 80; y += 1) for (let x = 10; x < 30; x += 1) legs[y * width + x] = 1;
  for (let y = 64; y < 78; y += 1) for (let x = 4; x < 16; x += 1) left[y * width + x] = 1;
  for (let y = 64; y < 78; y += 1) for (let x = 24; x < 36; x += 1) right[y * width + x] = 1;
  const regions = regionsFromLabelMasks([
    { label: "Face", binary: face, width, height },
    { label: "Upper-clothes", binary: upper, width, height },
    { label: "Left-leg", binary: legs, width, height },
    { label: "Left-shoe", binary: left, width, height },
    { label: "Right-shoe", binary: right, width, height },
  ]);
  assert.equal(regions.filter((region) => region.category === "Outerwear").length, 1);
  const shoes = regions.find((region) => region.friendly === "shoes");
  assert.ok(shoes);
  assert.equal(shoes.binary[70 * width + 8], 1);
  assert.equal(shoes.binary[70 * width + 32], 1);
  assert.equal(shoes.binary[70 * width + 28], 0);
  assert.equal(shoes.binary[70 * width + 20], 0);
  const coat = regions.find((region) => region.category === "Outerwear").binary;
  for (let y = 0; y < 8; y += 1) {
    for (let x = 14; x < 26; x += 1) assert.equal(coat[y * width + x], 0);
  }
});

test("storage counts one photo per piece and leftover originals", () => {
  const report = storageReport({
    items: [{ imageBlob: { size: 20 * 1024 } }, { imageBlob: { size: 40 * 1024 } }, {}],
    garments: [
      { status: "pending", cropBlob: { size: 30 * 1024 } },
      { status: "approved", cropBlob: { size: 12 * 1024 } },
    ],
    inbox: [{ blob: { size: 500 * 1024 } }],
  });
  assert.equal(report.pieceCount, 2);
  assert.equal(report.averageBytes, 30 * 1024);
  assert.equal(report.reviewCount, 1);
  assert.equal(report.extraBytes, 12 * 1024);
  assert.equal(report.originalCount, 1);
  assert.equal(report.totalBytes, 20 * 1024 + 40 * 1024 + 30 * 1024 + 12 * 1024 + 500 * 1024);
  assert.equal(formatBytes(20 * 1024), "20 KB");
  assert.equal(formatBytes(1536), "1.5 KB");
  assert.equal(formatBytes(800), "800 B");
  const csv = itemsToCsv([{ id: 4, name: "Coat", category: "Outerwear", color: "Blue", season: "All", imageBlob: { type: "image/webp" }, extra: {} }]);
  assert.match(csv, /closet_images\/item_4\.webp/);
});

test("picture size defaults to small and projects a closet", () => {
  assert.equal(presetById("missing").id, "small");
  assert.equal(QUALITY_PRESETS[0].edge, 384);
  assert.equal(QUALITY_PRESETS[1].edge, 640);
  assert.equal(QUALITY_PRESETS[2].edge, 1024);
  assert.equal(projectionLine(30 * 1024, 1000), "~1,000 items ≈ 29.3 MB");
  assert.equal(projectionLine(24 * 1024, 12), "~12 items ≈ 288 KB");
  assert.match(QUALITY_PRESETS[0].detail, /browsing and matching/);
  assert.deepEqual(storageLines(16 * 1024, false), [
    "Estimate · 16 KB each",
    "~100 items ≈ 1.6 MB",
    "~1,000 items ≈ 15.6 MB",
  ]);
  assert.equal(storageLines(15 * 1024, true)[0], "Your average · 15 KB each");
  assert.equal(spaceComparison(16 * 1024, 119 * 1024), "Small uses about 7.4× less space than High.");
  assert.equal(spaceComparison(10 * 1024, 70 * 1024), "Small uses about 7× less space than High.");
  assert.equal(spaceComparison(0, 100), "");
});

test("file identity uses the relative path, size, and time", () => {
  const key = fileKey({ webkitRelativePath: "trip/day.jpg", name: "day.jpg", size: 10, lastModified: 5 });
  assert.equal(key, "trip/day.jpg|10|5");
});
