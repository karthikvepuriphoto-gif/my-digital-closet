/** Closet rules shared by the phone app. No network and no browser storage. */

export const CATEGORIES = ["Tops", "Bottoms", "Full Body", "Outerwear", "Footwear", "Accessories"];
export const COLORS = [
  "Black", "White", "Grey", "Beige", "Brown", "Blue", "Navy",
  "Green", "Red", "Pink", "Yellow", "Orange", "Purple",
];
export const SEASONS = ["All", "Spring", "Summer", "Autumn", "Winter"];
export const SEASON_ORDER = ["Spring", "Summer", "Autumn", "Winter"];
export const SORTS = ["Recently added", "Name", "Color"];
export const FOLDER_BY_CATEGORY = {
  Tops: "tops",
  Bottoms: "bottoms",
  "Full Body": "dresses",
  Outerwear: "outerwear",
  Footwear: "shoes",
  Accessories: "accessories",
};
export const CATEGORY_WORDS = {
  Tops: "tops",
  Bottoms: "bottoms",
  "Full Body": "one-piece clothes",
  Outerwear: "outerwear",
  Footwear: "shoes",
  Accessories: "accessories",
};
export const COLOR_RGB = {
  Black: [20, 20, 20],
  White: [245, 245, 245],
  Grey: [140, 140, 140],
  Beige: [210, 190, 160],
  Brown: [110, 70, 40],
  Blue: [50, 90, 170],
  Navy: [20, 35, 80],
  Green: [40, 110, 60],
  Red: [180, 40, 40],
  Pink: [230, 150, 170],
  Yellow: [230, 200, 60],
  Orange: [220, 120, 40],
  Purple: [110, 70, 150],
};
export const LABEL_INFO = {
  "upper-clothes": ["Tops", "tops", "top", 0.8],
  skirt: ["Bottoms", "bottoms", "skirt", 0.75],
  pants: ["Bottoms", "bottoms", "pants", 0.85],
  dress: ["Full Body", "dresses", "dress", 0.75],
  hat: ["Accessories", "accessories", "hat", 0.7],
  sunglasses: ["Accessories", "accessories", "sunglasses", 0.7],
  belt: ["Accessories", "accessories", "belt", 0.45],
  "left-shoe": ["Footwear", "shoes", "shoe", 0.7],
  "right-shoe": ["Footwear", "shoes", "shoe", 0.7],
  bag: ["Accessories", "accessories", "bag", 0.7],
  scarf: ["Accessories", "accessories", "scarf", 0.55],
  coat: ["Outerwear", "outerwear", "coat", 0.85],
  jacket: ["Outerwear", "outerwear", "jacket", 0.85],
};
export const DUPLICATE_SIMILARITY = 0.9;
export const SAME_GARMENT_ACROSS_LABELS = 0.95;
const MISSING = new Set(["", "none", "nan", "null", "n/a", "<na>"]);
const ITEM_COLUMNS = ["ID", "Category", "Sub-Category", "Primary Color", "Season", "Image_Path"];
const OUTFIT_COLUMNS = ["ID", "Name", "Top_ID", "Bottom_ID", "FullBody_ID", "Outerwear_ID", "Footwear_ID", "Created"];
const PIECE_FIELDS = ["topId", "bottomId", "fullBodyId", "outerwearId", "footwearId"];
const PIECE_COLUMNS = {
  topId: "Top_ID",
  bottomId: "Bottom_ID",
  fullBodyId: "FullBody_ID",
  outerwearId: "Outerwear_ID",
  footwearId: "Footwear_ID",
};

export function labelKey(label) {
  return String(label || "").trim().toLowerCase().replaceAll("_", "-").replaceAll(" ", "-");
}

export function parseCsv(text) {
  const source = String(text || "").replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (quoted) {
      if (char === '"') {
        if (source[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char !== "\r") {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((cells) => cells.some((cell) => String(cell).trim() !== ""));
}

export function cleanPath(value) {
  const text = String(value ?? "").trim();
  return MISSING.has(text.toLowerCase()) ? "" : text;
}

export function parseId(value) {
  const text = String(value ?? "").trim();
  if (MISSING.has(text.toLowerCase())) return null;
  const number = Number(text);
  if (!Number.isInteger(number)) return null;
  return number;
}

function table(text, required) {
  const rows = parseCsv(text);
  if (!rows.length) throw new Error("That file is empty.");
  const header = rows[0].map((cell) => cell.trim());
  if (!header.includes("ID")) throw new Error("That file has no ID column, so it was left unchanged.");
  for (const column of required) {
    if (!header.includes(column)) header.push(column);
  }
  const records = [];
  rows.slice(1).forEach((cells, index) => {
    const blank = cells.every((cell) => String(cell).trim() === "");
    if (blank) return;
    const record = {};
    header.forEach((column, columnIndex) => {
      record[column] = cells[columnIndex] == null ? "" : String(cells[columnIndex]).trim();
    });
    for (const column of required) record[column] = record[column] ?? "";
    const id = parseId(record.ID);
    if (id == null) {
      throw new Error(`That file has a row without a usable ID (line ${index + 2}). It was left unchanged.`);
    }
    record.ID = id;
    records.push(record);
  });
  return records;
}

export function itemsFromCsv(text) {
  return table(text, ITEM_COLUMNS).map((record) => ({
    id: record.ID,
    category: record.Category || "Tops",
    name: (record["Sub-Category"] || "Untitled").slice(0, 80),
    color: record["Primary Color"] || "",
    season: record.Season || "All",
    imagePath: cleanPath(record.Image_Path),
    sourcePhoto: cleanPath(record.Source_Photo),
    sourcePhotos: cleanPath(record.Source_Photos),
    created: record.Created || "",
    extra: Object.fromEntries(Object.entries(record).filter(([key]) => ![
      "ID", "Category", "Sub-Category", "Primary Color", "Season", "Image_Path",
      "Source_Photo", "Source_Photos", "Created",
    ].includes(key))),
  }));
}

export function outfitsFromCsv(text) {
  return table(text, OUTFIT_COLUMNS).map((record) => ({
    id: record.ID,
    name: (record.Name || "Untitled look").slice(0, 80),
    created: record.Created || "",
    topId: parseId(record.Top_ID),
    bottomId: parseId(record.Bottom_ID),
    fullBodyId: parseId(record.FullBody_ID),
    outerwearId: parseId(record.Outerwear_ID),
    footwearId: parseId(record.Footwear_ID),
  }));
}

function csvCell(value) {
  const text = value == null ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function itemsToCsv(items) {
  const extras = [];
  for (const item of items) {
    for (const key of Object.keys(item.extra || {})) {
      if (!extras.includes(key)) extras.push(key);
    }
  }
  const header = [...ITEM_COLUMNS, "Source_Photo", "Source_Photos", ...extras];
  const lines = [header.join(",")];
  for (const item of items) {
    const row = {
      ID: item.id,
      Category: item.category,
      "Sub-Category": item.name,
      "Primary Color": item.color,
      Season: item.season,
      Image_Path: item.imageBlob ? `closet_images/item_${item.id}.png` : "",
      Source_Photo: item.sourcePhoto || "",
      Source_Photos: item.sourcePhotos || "",
      ...(item.extra || {}),
    };
    lines.push(header.map((column) => csvCell(row[column] ?? "")).join(","));
  }
  return `${lines.join("\n")}\n`;
}

export function outfitsToCsv(outfits) {
  const lines = [OUTFIT_COLUMNS.join(",")];
  for (const outfit of outfits) {
    const row = {
      ID: outfit.id,
      Name: outfit.name,
      Created: outfit.created || "",
    };
    for (const [field, column] of Object.entries(PIECE_COLUMNS)) {
      row[column] = outfit[field] == null ? "" : outfit[field];
    }
    lines.push(OUTFIT_COLUMNS.map((column) => csvCell(row[column] ?? "")).join(","));
  }
  return `${lines.join("\n")}\n`;
}

export function basename(path) {
  const text = cleanPath(path);
  if (!text) return "";
  return text.split(/[/\\]/).pop();
}

export function nextItemId(items, outfits) {
  const ids = items.map((item) => item.id);
  for (const outfit of outfits) {
    for (const field of PIECE_FIELDS) {
      if (outfit[field] != null) ids.push(outfit[field]);
    }
  }
  return (ids.length ? Math.max(...ids) : 0) + 1;
}

export function nextOutfitId(outfits) {
  return (outfits.length ? Math.max(...outfits.map((outfit) => outfit.id)) : 0) + 1;
}

export function filterItems(items, { query = "", category = "All", color = "All", season = "All" } = {}) {
  const text = query.trim().toLowerCase();
  return items.filter((item) => {
    if (category !== "All" && item.category !== category) return false;
    if (color !== "All" && item.color !== color) return false;
    if (season !== "All" && item.season !== season && item.season !== "All") return false;
    if (!text) return true;
    const haystack = `${item.name} ${item.category} ${item.color} ${item.season}`.toLowerCase();
    return haystack.includes(text);
  });
}

export function sortItems(items, how = "Recently added") {
  const copy = [...items];
  if (how === "Name") {
    copy.sort((left, right) => left.name.localeCompare(right.name, undefined, { sensitivity: "base" }) || left.id - right.id);
  } else if (how === "Color") {
    copy.sort((left, right) => (
      left.color.localeCompare(right.color, undefined, { sensitivity: "base" })
      || left.name.localeCompare(right.name, undefined, { sensitivity: "base" })
      || left.id - right.id
    ));
  } else {
    copy.sort((left, right) => right.id - left.id);
  }
  return copy;
}

export function scrubOutfits(outfits, itemId) {
  const id = Number(itemId);
  return outfits.map((outfit) => {
    const next = { ...outfit };
    for (const field of PIECE_FIELDS) {
      if (next[field] === id) next[field] = null;
    }
    return next;
  });
}

export function outfitPieces(outfit) {
  return PIECE_FIELDS.map((field) => outfit[field]).filter((id) => id != null);
}

export function validateOutfit(mode, { topId, bottomId, fullBodyId }) {
  if (mode === "One piece") {
    if (fullBodyId == null) return "Add a one-piece, like a dress or jumpsuit, before saving this look.";
    return "";
  }
  if (topId == null || bottomId == null) return "Add a top and a bottom before saving a separates look.";
  return "";
}

export function suggestLookName(items, ids) {
  const names = ids.map((id) => items.find((item) => item.id === id)?.name).filter(Boolean);
  return names.join(" + ") || "Untitled look";
}

function leader(items, field, words) {
  const rows = countBy(items, field);
  const top = rows[0]?.count || 0;
  const names = rows
    .filter((row) => row.count === top)
    .map((row) => words?.[row.label] || row.label.toLowerCase());
  return { tied: names.length > 1, text: joinNames(names) };
}

function joinNames(names) {
  if (names.length <= 1) return names[0] || "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")}, and ${names.at(-1)}`;
}

export function closetSummary(items) {
  if (!items.length) return "Add a few pieces and this page will show what you own.";
  const piece = items.length === 1 ? "piece" : "pieces";
  const categoryLeader = leader(items, "category", CATEGORY_WORDS);
  const colorLeader = leader(items, "color");
  const categoryLine = categoryLeader.tied
    ? `It is evenly split across ${categoryLeader.text}`
    : `Most of your closet is ${categoryLeader.text}`;
  const colorLine = colorLeader.tied
    ? `${colorLeader.text} are tied for the colors you own most`
    : `${colorLeader.text} is the color you own most`;
  const coverage = SEASON_ORDER.map((season) => ({
    season,
    total: items.filter((item) => item.season === season || item.season === "All").length,
  }));
  const lowest = Math.min(...coverage.map((entry) => entry.total));
  const thin = coverage.filter((entry) => entry.total === lowest).map((entry) => entry.season);
  let seasonLine = "The four seasons are evenly covered.";
  if (thin.length === 1) seasonLine = `${thin[0]} is the lightest season, even counting all-season pieces.`;
  else if (thin.length < SEASON_ORDER.length) {
    seasonLine = `${joinNames(thin)} are the lightest seasons, even counting all-season pieces.`;
  }
  return `You have ${items.length} ${piece}. ${categoryLine}, and ${colorLine}. ${seasonLine}`;
}

export function countBy(items, field) {
  const counts = new Map();
  for (const item of items) {
    const label = item[field] || "Unknown";
    counts.set(label, (counts.get(label) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

export function nearestColor(pixels) {
  const totals = Object.fromEntries(Object.keys(COLOR_RGB).map((name) => [name, 0]));
  const step = Math.max(1, Math.floor(pixels.length / 3 / 1200));
  for (let index = 0; index < pixels.length; index += 3 * step) {
    const pixel = [pixels[index], pixels[index + 1], pixels[index + 2]];
    let best = "Grey";
    let bestDistance = Infinity;
    for (const [name, rgb] of Object.entries(COLOR_RGB)) {
      const distance = (pixel[0] - rgb[0]) ** 2 + (pixel[1] - rgb[1]) ** 2 + (pixel[2] - rgb[2]) ** 2;
      if (distance < bestDistance) {
        best = name;
        bestDistance = distance;
      }
    }
    totals[best] += 1;
  }
  return Object.entries(totals).sort((left, right) => right[1] - left[1])[0][0];
}

export function classifyLabel(label, box, personBox) {
  const key = labelKey(label);
  const info = LABEL_INFO[key];
  if (!info) throw new Error(`Unknown clothing label: ${label}`);
  const [category, folder, friendly, confidence] = info;
  if (key === "upper-clothes") {
    const garmentHeight = Math.max(1, box[2] - box[0]);
    const personHeight = Math.max(1, personBox[2] - personBox[0]);
    const ratio = garmentHeight / personHeight;
    const reachesLow = box[2] >= personBox[0] + personHeight * 0.72;
    if (ratio >= 0.62 && ratio < 0.92 && reachesLow) {
      return { category: "Outerwear", folder: "outerwear", friendly: "coat", confidence: 0.5 };
    }
  }
  return { category, folder, friendly, confidence };
}

export function componentBoxes(binary, width, height, minPixels) {
  const labels = new Int32Array(binary.length);
  const parent = [0];
  const find = (value) => {
    let current = value;
    while (parent[current] !== current) {
      parent[current] = parent[parent[current]];
      current = parent[current];
    }
    return current;
  };
  let next = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      if (!binary[index]) continue;
      const left = x ? labels[index - 1] : 0;
      const up = y ? labels[index - width] : 0;
      if (left && up && left !== up) {
        labels[index] = left;
        parent[find(up)] = find(left);
      } else if (left || up) {
        labels[index] = left || up;
      } else {
        next += 1;
        parent.push(next);
        labels[index] = next;
      }
    }
  }
  const boxes = new Map();
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const label = labels[y * width + x];
      if (!label) continue;
      const root = find(label);
      const box = boxes.get(root) || { y0: y, x0: x, y1: y + 1, x1: x + 1, area: 0 };
      box.y0 = Math.min(box.y0, y);
      box.x0 = Math.min(box.x0, x);
      box.y1 = Math.max(box.y1, y + 1);
      box.x1 = Math.max(box.x1, x + 1);
      box.area += 1;
      boxes.set(root, box);
    }
  }
  return [...boxes.values()]
    .filter((box) => box.area >= minPixels)
    .map((box) => [box.y0, box.x0, box.y1, box.x1]);
}

export function boundsOf(binary, width, height) {
  let y0 = height;
  let x0 = width;
  let y1 = 0;
  let x1 = 0;
  let found = false;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!binary[y * width + x]) continue;
      found = true;
      y0 = Math.min(y0, y);
      x0 = Math.min(x0, x);
      y1 = Math.max(y1, y + 1);
      x1 = Math.max(x1, x + 1);
    }
  }
  return found ? [y0, x0, y1, x1] : [0, 0, height, width];
}

export function mergeShoeBoxes(shoes) {
  const left = shoes.filter((shoe) => labelKey(shoe.label).startsWith("left"));
  const right = shoes.filter((shoe) => labelKey(shoe.label).startsWith("right"));
  if (left.length === 1 && right.length === 1 && shoes.length === 2) {
    const first = left[0].box;
    const second = right[0].box;
    return [{
      label: "Right-shoe",
      friendly: "shoes",
      confidence: Math.max(left[0].confidence, right[0].confidence),
      box: [
        Math.min(first[0], second[0]),
        Math.min(first[1], second[1]),
        Math.max(first[2], second[2]),
        Math.max(first[3], second[3]),
      ],
    }];
  }
  return shoes.map((shoe) => ({ ...shoe, friendly: "shoe" }));
}

export function regionsFromLabelMasks(labelMasks) {
  if (!labelMasks.length) return [];
  const { width, height } = labelMasks[0];
  const person = new Uint8Array(width * height);
  for (const mask of labelMasks) {
    if (labelKey(mask.label) === "background") continue;
    for (let index = 0; index < person.length; index += 1) {
      if (mask.binary[index]) person[index] = 1;
    }
  }
  const personBox = boundsOf(person, width, height);
  const minPixels = Math.max(30, Math.round(width * height * 0.008));
  const regions = [];
  const shoes = [];
  for (const mask of labelMasks) {
    const key = labelKey(mask.label);
    if (!LABEL_INFO[key]) continue;
    for (const box of componentBoxes(mask.binary, width, height, minPixels)) {
      const info = classifyLabel(mask.label, box, personBox);
      if (key === "left-shoe" || key === "right-shoe") {
        shoes.push({ label: mask.label, box, confidence: info.confidence });
      } else {
        regions.push({ ...info, label: mask.label, box, maskWidth: width, maskHeight: height });
      }
    }
  }
  for (const shoe of mergeShoeBoxes(shoes)) {
    const info = classifyLabel(shoe.label, shoe.box, personBox);
    regions.push({
      ...info,
      friendly: shoe.friendly || info.friendly,
      label: shoe.label,
      box: shoe.box,
      maskWidth: width,
      maskHeight: height,
    });
  }
  return regions;
}

export function similarity(left, right) {
  if (!left?.length || left.length !== right?.length) return 0;
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (let index = 0; index < left.length; index += 1) {
    dot += left[index] * right[index];
    leftNorm += left[index] ** 2;
    rightNorm += right[index] ** 2;
  }
  const denom = Math.sqrt(leftNorm) * Math.sqrt(rightNorm);
  return denom ? dot / denom : 0;
}

export function isSameItem(left, right, score) {
  if (score < DUPLICATE_SIMILARITY) return false;
  if (left === right) return true;
  return score >= SAME_GARMENT_ACROSS_LABELS && (
    (left === "Tops" && right === "Outerwear") || (left === "Outerwear" && right === "Tops")
  );
}

export function findDuplicate(garments, category, embedding) {
  let best = null;
  let bestScore = 0;
  for (const garment of garments) {
    if (!["pending", "approved", "rejected"].includes(garment.status)) continue;
    const score = similarity(embedding, garment.embedding || []);
    if (score < bestScore || !isSameItem(category, garment.category, score)) continue;
    best = garment;
    bestScore = score;
  }
  return best;
}

export function fileKey(file) {
  const name = file.webkitRelativePath || file.name;
  return `${name}|${file.size}|${file.lastModified}`;
}

export function suggestName(color, friendly) {
  return `${color} ${friendly}`.trim().slice(0, 80);
}

export function scaledCropBox(box, maskWidth, maskHeight, imageWidth, imageHeight) {
  const scaleX = imageWidth / maskWidth;
  const scaleY = imageHeight / maskHeight;
  const [y0, x0, y1, x1] = box;
  let left = x0 * scaleX;
  let top = y0 * scaleY;
  let right = x1 * scaleX;
  let bottom = y1 * scaleY;
  const padX = (right - left) * 0.08;
  const padY = (bottom - top) * 0.08;
  left = Math.max(0, Math.floor(left - padX));
  top = Math.max(0, Math.floor(top - padY));
  right = Math.min(imageWidth, Math.ceil(right + padX));
  bottom = Math.min(imageHeight, Math.ceil(bottom + padY));
  if (right - left < 48 || bottom - top < 48) return null;
  return [left, top, right, bottom];
}

export function swatchColor(color) {
  return {
    Black: "#2a2a2a",
    White: "#f4f1ea",
    Grey: "#c4beb6",
    Beige: "#e0d0b8",
    Brown: "#8a6244",
    Blue: "#3e618f",
    Navy: "#24344f",
    Green: "#3f5c49",
    Red: "#8d3d3d",
    Pink: "#e7b3bf",
    Yellow: "#e4c56a",
    Orange: "#d4843c",
    Purple: "#65547a",
  }[color] || "#d9d0c4";
}
