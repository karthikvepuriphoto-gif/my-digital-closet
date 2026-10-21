import {
  CATEGORIES,
  COLORS,
  FOLDER_BY_CATEGORY,
  SEASONS,
  SORTS,
  basename,
  closetSummary,
  countBy,
  fileKey,
  filterItems,
  findDuplicate,
  itemsFromCsv,
  itemsToCsv,
  nextItemId,
  nextOutfitId,
  outfitsFromCsv,
  outfitsToCsv,
  scrubOutfits,
  sortItems,
  suggestLookName,
  swatchColor,
  validateOutfit,
} from "./closet.js";
import { clearStore, deleteRecord, loadCloset, putRecord } from "./db.js";
import { ensureModels, findGarments } from "./vision.js";

const state = {
  items: [],
  outfits: [],
  garments: [],
  scans: [],
  files: [],
  screen: "closet",
  pieceId: null,
  query: "",
  category: "All",
  color: "All",
  season: "All",
  sort: "Recently added",
  outfitMode: "Separates",
  flash: null,
  scanning: false,
  stopScan: false,
  progress: "",
  progressValue: 0,
  removeId: null,
  installEvent: null,
  installDismissed: readInstallDismissed(),
};

const urls = new Map();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

function blobUrl(key, blob) {
  if (!blob) return "";
  const token = `${blob.size}:${blob.type}`;
  const current = urls.get(key);
  if (current?.token === token) return current.url;
  if (current) URL.revokeObjectURL(current.url);
  const url = URL.createObjectURL(blob);
  urls.set(key, { token, url });
  return url;
}

function picture(item, key) {
  const url = blobUrl(key || `item-${item.id}`, item.imageBlob || item.cropBlob);
  if (url) return `<img src="${url}" alt="">`;
  const name = item.name || "Piece";
  return `<div class="swatch" style="background:${swatchColor(item.color)}"><span>${escapeHtml(name)}</span></div>`;
}

function metaLine(item) {
  const season = item.season === "All" ? "All seasons" : item.season;
  const source = basename(item.sourcePhoto);
  return `${item.category} · ${item.color} · ${season}${source ? ` · from ${source}` : ""}`;
}

function options(values, current) {
  return values.map((value) => (
    `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(value)}</option>`
  )).join("");
}

function word(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

function today() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatCreated(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || "");
  if (!match) return value || "";
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    .toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function readInstallDismissed() {
  try {
    return localStorage.getItem("closet-install-dismissed") === "1";
  } catch {
    return false;
  }
}

function standalone() {
  return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
}

function banner() {
  if (!state.flash) return "";
  const [kind, text] = state.flash;
  return `<div class="banner ${kind}" role="status">${escapeHtml(text)}</div>`;
}

function installCard() {
  if (state.screen !== "closet" || standalone() || state.installDismissed) return "";
  const ios = /iPhone|iPad/i.test(navigator.userAgent);
  const button = state.installEvent ? `<button class="primary" data-action="install" type="button">Install</button>` : "";
  const hint = ios
    ? "On iPhone, tap Share, then Add to Home Screen."
    : "Add it from the browser menu, or tap Install when that button is here.";
  return `<section class="install"><p>${hint} No app store.</p><div class="row">${button}<button type="button" data-action="dismiss-install">Not now</button></div></section>`;
}

function renderCloset() {
  const categories = ["All", ...CATEGORIES];
  const filtered = sortItems(filterItems(state.items, state), state.sort);
  const chips = categories.map((category) => (
    `<button type="button" data-action="category" data-value="${escapeHtml(category)}" aria-pressed="${state.category === category}">${escapeHtml(category)}</button>`
  )).join("");
  const cards = filtered.map((item) => `
    <article class="card">
      <a href="#piece/${item.id}">${picture(item)}</a>
      <div class="pad">
        <h3>${escapeHtml(item.name)}</h3>
        <p class="meta">${escapeHtml(metaLine(item))}</p>
      </div>
    </article>`).join("");
  const empty = state.items.length
    ? `<div class="empty"><h2>Nothing matches</h2><p>Try a different name, color, or season.</p><button type="button" data-action="clear-filters">Clear filters</button></div>`
    : `<div class="empty"><h2>Your closet is empty</h2><p>Add a piece, or bring in the closet you already keep on your computer.</p><p><a class="button primary" href="#add">Add a piece</a></p><p><a class="link" href="#import">Bring in a saved closet</a></p></div>`;
  const seasonNote = state.season !== "All" ? `<p class="hint">Includes pieces marked for all seasons.</p>` : "";
  return `
    ${banner()}
    ${state.items.length ? `
      <label>Search<input id="closet-query" type="search" placeholder="Name, color, or category" value="${escapeHtml(state.query)}"></label>
      <div class="chips" role="group" aria-label="Category">${chips}</div>
      <div class="row">
        <label>Color<select id="closet-color">${options(["All", ...COLORS], state.color)}</select></label>
        <label>Season<select id="closet-season">${options(SEASONS, state.season)}</select></label>
      </div>
      <label>Sort<select id="closet-sort">${options(SORTS, state.sort)}</select></label>
      ${seasonNote}
      ${filtered.length ? `<div class="cards">${cards}</div>` : empty}
    ` : empty}
    ${installCard()}`;
}

function renderAdd() {
  return `
    ${banner()}
    <h2>Add a piece</h2>
    <p class="lede">A name is enough. A photo stays on this phone.</p>
    <form class="stack" data-form="add">
      <label>Name<input name="name" maxlength="80" required placeholder="Jeans, sweater, loafers"></label>
      <label>Category<select name="category">${options(CATEGORIES, "Tops")}</select></label>
      <label>Color<select name="color">${options(COLORS, "Black")}</select></label>
      <label>Season<select name="season">${options(SEASONS, "All")}</select></label>
      <label class="file button">Add a photo<input name="photo" type="file" accept="image/*"></label>
      <button class="primary" type="submit">Save piece</button>
    </form>`;
}

function itemById(id) {
  return state.items.find((item) => item.id === Number(id)) || null;
}

function pieceOptions(category, selected, emptyLabel) {
  const rows = state.items.filter((item) => item.category === category).sort((a, b) => a.name.localeCompare(b.name));
  const empty = `<option value="">${escapeHtml(emptyLabel)}</option>`;
  const rest = rows.map((item) => (
    `<option value="${item.id}"${item.id === selected ? " selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.color)}</option>`
  )).join("");
  return empty + rest;
}

function renderOutfits() {
  const separates = state.outfitMode === "Separates";
  const looks = [...state.outfits].sort((a, b) => b.id - a.id).map((outfit) => {
    const pieces = ["topId", "bottomId", "fullBodyId", "outerwearId", "footwearId"]
      .map((field) => itemById(outfit[field]))
      .filter(Boolean);
    const thumbs = pieces.map((item) => picture(item, `look-${outfit.id}-${item.id}`)).join("");
    const names = pieces.map((item) => item.name).join(", ") || "No pieces left";
    return `<article class="card sheet"><div class="cards">${thumbs}</div><h3>${escapeHtml(outfit.name)}</h3><p class="meta">${escapeHtml(names)} · ${escapeHtml(formatCreated(outfit.created))}</p><button type="button" data-action="delete-outfit" data-id="${outfit.id}">Remove look</button></article>`;
  }).join("");
  return `
    ${banner()}
    <h2>Outfits</h2>
    <p class="lede">Start with separates or a one-piece, then add a coat and shoes if you want.</p>
    <div class="chips">
      <button type="button" data-action="outfit-mode" data-value="Separates" aria-pressed="${separates}">Separates</button>
      <button type="button" data-action="outfit-mode" data-value="One piece" aria-pressed="${!separates}">One piece</button>
    </div>
    <form class="stack" data-form="outfit">
      <label>Name<input name="name" maxlength="80" placeholder="Cold walk"></label>
      ${separates ? `
        <label>Top<select name="topId">${pieceOptions("Tops", null, "Choose a top")}</select></label>
        <label>Bottom<select name="bottomId">${pieceOptions("Bottoms", null, "Choose a bottom")}</select></label>
      ` : `<label>One piece<select name="fullBodyId">${pieceOptions("Full Body", null, "Choose a dress or jumpsuit")}</select></label>`}
      <label>Layer<select name="outerwearId">${pieceOptions("Outerwear", null, "None")}</select></label>
      <label>Shoes<select name="footwearId">${pieceOptions("Footwear", null, "None")}</select></label>
      <button class="primary" type="submit">Save look</button>
    </form>
    <div class="stack">${looks || `<div class="empty"><h2>No saved looks yet</h2><p>Build one from the pieces you already own.</p></div>`}</div>`;
}

function chart(title, rows) {
  if (!rows.length) return "";
  const max = Math.max(...rows.map((row) => row.count), 1);
  const bars = rows.map((row) => `
    <div class="bar-row">
      <span>${escapeHtml(row.label)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(row.count / max) * 100}%"></div></div>
      <span>${row.count}</span>
    </div>`).join("");
  return `<h3>${escapeHtml(title)}</h3><div class="bars">${bars}</div><div class="axis"><span>0</span><span>${max}</span></div>`;
}

function renderInsights() {
  if (!state.items.length) {
    return `<h2>Stats</h2><div class="empty"><h2>No numbers yet</h2><p>Add a few pieces and the mix of colors and seasons will show up here.</p></div>`;
  }
  const colors = new Set(state.items.map((item) => item.color).filter(Boolean));
  const seasons = new Set(state.items.map((item) => item.season).filter(Boolean));
  return `
    <h2>Stats</h2>
    <div class="banner ok">${escapeHtml(closetSummary(state.items))}</div>
    <div class="metrics">
      <div class="metric"><b>${state.items.length}</b>Pieces</div>
      <div class="metric"><b>${state.outfits.length}</b>Looks</div>
      <div class="metric"><b>${colors.size}</b>Colors</div>
      <div class="metric"><b>${seasons.size}</b>Seasons tagged</div>
    </div>
    ${chart("By category", countBy(state.items, "category"))}
    ${chart("By color", countBy(state.items, "color"))}
    ${chart("By season", countBy(state.items, "season"))}`;
}

function pendingGarments() {
  return state.garments.filter((garment) => garment.status === "pending")
    .sort((left, right) => String(right.created).localeCompare(String(left.created)));
}

function renderImport() {
  const scanned = new Set(state.scans.map((scan) => scan.key));
  const waiting = state.files.filter((file) => !scanned.has(fileKey(file))).length;
  const pending = pendingGarments();
  const approved = state.garments.filter((garment) => garment.status === "approved").length;
  const failed = state.scans.filter((scan) => scan.error).length;
  const folderButton = "showDirectoryPicker" in window
    ? `<button type="button" data-action="save-folder">Save crops to a folder</button>`
    : `<p class="hint">This browser can download a zip of the crops. Saving straight into a folder is available in Chrome on Android and on a computer.</p>`;
  const cards = pending.map((garment) => `
    <article class="card review" data-garment="${escapeHtml(garment.id)}">
      ${picture(garment, `crop-${garment.id}`)}
      <form class="pad stack">
        <p class="meta">From ${escapeHtml(garment.sourceNames?.map(basename).join(", ") || garment.sourceName || "a photo")}. The original stays where it is.</p>
        ${garment.note ? `<p class="hint">${escapeHtml(garment.note)}</p>` : ""}
        <label>Name<input name="name" maxlength="80" value="${escapeHtml(garment.name)}"></label>
        <label>Category<select name="category">${options(CATEGORIES, garment.category)}</select></label>
        <div class="row">
          <label>Color<select name="color">${options(COLORS, garment.color)}</select></label>
          <label>Season<select name="season">${options(SEASONS, garment.season || "All")}</select></label>
        </div>
        <div class="row">
          <button class="primary" type="button" data-action="approve" data-id="${escapeHtml(garment.id)}">Approve</button>
          <button type="button" data-action="reject" data-id="${escapeHtml(garment.id)}">Reject</button>
        </div>
      </form>
    </article>`).join("");
  return `
    ${banner()}
    <h2>Import from photos</h2>
    <p class="lede">Pick pictures already on this phone. Suggestions stay here until you approve them.</p>
    <div class="banner ok">Your pictures stay on this phone. The scan only reads them. It does not upload them or send them to a cloud service. The clothing model is downloaded once into this browser, then runs here. Nothing is added until you approve it. <a class="link" href="./privacy.html">Privacy</a></div>
    <div class="stack">
      <label class="file button">Choose photos<input id="pick-photos" type="file" accept="image/*" multiple></label>
      <label class="file button">Choose a folder<input id="pick-folder" type="file" accept="image/*" multiple webkitdirectory></label>
      <label class="file button">Take a photo<input id="pick-camera" type="file" accept="image/*" capture="environment"></label>
    </div>
    <p class="hint">${state.files.length} photo${state.files.length === 1 ? "" : "s"} chosen · ${waiting} waiting · ${pending.length} to review · ${approved} approved</p>
    ${failed ? `<p class="hint">${failed} photo${failed === 1 ? "" : "s"} could not be read. The rest can still be scanned.</p>` : ""}
    ${state.progress ? `<p class="hint">${escapeHtml(state.progress)}</p><div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(state.progressValue * 100)}"><span style="width:${state.progressValue * 100}%"></span></div>` : ""}
    <div class="row">
      <button class="primary" type="button" data-action="scan" data-limit="4" ${state.scanning ? "disabled" : ""}>Scan next 4</button>
      <button type="button" data-action="scan" ${state.scanning ? "disabled" : ""}>Scan all remaining</button>
    </div>
    ${state.scanning ? `<button type="button" data-action="stop-scan">Stop after this photo</button>` : ""}
    <h2>Review</h2>
    <p class="lede">Approve a piece to add it. Reject it and only the crop is discarded.</p>
    ${pending.length ? `<button type="button" data-action="approve-all">Approve all as suggested</button>${cards}` : `<div class="empty"><h2>Nothing waiting for review</h2><p>Choose a few photos. The originals are not moved.</p></div>`}
    <h2>Crops and backup</h2>
    <div class="stack">
      <button type="button" data-action="download-crops">Download crops (.zip)</button>
      ${folderButton}
      <button type="button" data-action="download-backup">Download a closet backup</button>
    </div>
    <h2>Bring in a computer closet</h2>
    <p class="lede">From the Python app, choose <code>wardrobe_db.csv</code> and <code>outfits_db.csv</code>. Add the pictures from <code>closet_images</code> if you want the photos too. A backup zip from this app works as well.</p>
    <form class="stack" data-form="migrate">
      <label class="file button">Choose CSV or zip<input name="backup" type="file" accept=".csv,.zip,text/csv,application/zip" multiple></label>
      <label class="file button">Choose photos, optional<input name="images" type="file" accept="image/*" multiple></label>
      <button class="primary" type="submit" data-mode="merge">Add to this closet</button>
      <button type="submit" data-mode="replace">Replace this closet</button>
    </form>`;
}

function renderPiece() {
  const item = itemById(state.pieceId);
  if (!item) return `<div class="empty"><h2>That piece is gone</h2><p><a class="link" href="#closet">Back to the closet</a></p></div>`;
  const confirm = state.removeId === item.id
    ? `<div class="banner err"><p>Remove ${escapeHtml(item.name)}? Saved looks keep their other pieces.</p><div class="row"><button type="button" data-action="confirm-remove" data-id="${item.id}">Remove</button><button type="button" data-action="cancel-remove">Keep it</button></div></div>`
    : `<button type="button" data-action="ask-remove" data-id="${item.id}">Remove</button>`;
  return `
    ${banner()}
    <p><a class="link" href="#closet">Closet</a></p>
    ${picture(item)}
    <form class="stack" data-form="edit" data-id="${item.id}">
      <label>Name<input name="name" maxlength="80" value="${escapeHtml(item.name)}" required></label>
      <label>Category<select name="category">${options(CATEGORIES, item.category)}</select></label>
      <label>Color<select name="color">${options(COLORS.includes(item.color) ? COLORS : [...COLORS, item.color], item.color)}</select></label>
      <label>Season<select name="season">${options(SEASONS.includes(item.season) ? SEASONS : [...SEASONS, item.season], item.season)}</select></label>
      <label class="file button">Replace photo<input name="photo" type="file" accept="image/*"></label>
      <button class="primary" type="submit">Save changes</button>
    </form>
    ${confirm}
    <p class="meta">${escapeHtml(metaLine(item))}</p>`;
}

const views = {
  closet: renderCloset,
  add: renderAdd,
  outfits: renderOutfits,
  insights: renderInsights,
  import: renderImport,
  piece: renderPiece,
};

function render() {
  const active = document.activeElement;
  const activeId = active?.id;
  const caret = active && "selectionStart" in active ? active.selectionStart : null;
  document.querySelector("#counts").textContent = `${word(state.items.length, "piece", "pieces")} · ${word(state.outfits.length, "look", "looks")}`;
  document.querySelector("#screen").innerHTML = (views[state.screen] || renderCloset)();
  for (const link of document.querySelectorAll(".tabbar a")) {
    const on = link.getAttribute("href") === `#${state.screen}`;
    if (on) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (activeId) {
    const next = document.getElementById(activeId);
    if (next) {
      next.focus();
      if (caret != null && next.setSelectionRange) next.setSelectionRange(caret, caret);
    }
  }
}

function readRoute() {
  const [screen, arg] = (location.hash.replace("#", "") || "closet").split("/");
  state.screen = views[screen] ? screen : "closet";
  state.pieceId = screen === "piece" ? Number(arg) : null;
}

async function saveItem(item) {
  await putRecord("items", item);
  const index = state.items.findIndex((row) => row.id === item.id);
  if (index >= 0) state.items[index] = item;
  else state.items.push(item);
}

async function saveOutfit(outfit) {
  await putRecord("outfits", outfit);
  const index = state.outfits.findIndex((row) => row.id === outfit.id);
  if (index >= 0) state.outfits[index] = outfit;
  else state.outfits.push(outfit);
}

async function saveGarment(garment) {
  await putRecord("garments", garment);
  const index = state.garments.findIndex((row) => row.id === garment.id);
  if (index >= 0) state.garments[index] = garment;
  else state.garments.push(garment);
}

let keepFlashOnNextRoute = false;

function flash(kind, text) {
  state.flash = [kind, text];
}

function openCloset() {
  keepFlashOnNextRoute = true;
  if (location.hash === "#closet" || location.hash === "") {
    keepFlashOnNextRoute = false;
    readRoute();
    render();
    return;
  }
  location.hash = "#closet";
}

function optionalId(value) {
  if (!value) return null;
  const number = Number(value);
  return Number.isInteger(number) ? number : null;
}

function imageFile(file) {
  return file && /\.(jpe?g|png|webp|bmp)$/i.test(file.name) && !file.name.startsWith(".");
}

function rememberFiles(list) {
  const seen = new Set(state.files.map(fileKey));
  let added = 0;
  for (const file of list) {
    if (!imageFile(file)) continue;
    const key = fileKey(file);
    if (seen.has(key)) continue;
    seen.add(key);
    state.files.push(file);
    added += 1;
  }
  return added;
}

async function onAdd(form) {
  const data = new FormData(form);
  const name = String(data.get("name") || "").trim();
  if (!name) {
    flash("err", "Enter a name for this piece.");
    render();
    return;
  }
  const photo = data.get("photo");
  const item = {
    id: nextItemId(state.items, state.outfits),
    category: data.get("category"),
    name: name.slice(0, 80),
    color: data.get("color"),
    season: data.get("season"),
    imageBlob: photo && photo.size ? photo : null,
    sourcePhoto: "",
    sourcePhotos: "",
    created: new Date().toISOString(),
    extra: {},
  };
  await saveItem(item);
  flash("ok", `Added ${item.name}.`);
  openCloset();
}

async function onEdit(form) {
  const item = itemById(form.dataset.id);
  if (!item) return;
  const data = new FormData(form);
  const name = String(data.get("name") || "").trim();
  if (!name) {
    flash("err", "Enter a name for this piece.");
    render();
    return;
  }
  const photo = data.get("photo");
  const next = {
    ...item,
    name: name.slice(0, 80),
    category: data.get("category"),
    color: data.get("color"),
    season: data.get("season"),
    imageBlob: photo && photo.size ? photo : item.imageBlob,
  };
  await saveItem(next);
  flash("ok", `Saved ${next.name}.`);
  render();
}

async function onOutfit(form) {
  const data = new FormData(form);
  const picks = {
    topId: state.outfitMode === "Separates" ? optionalId(data.get("topId")) : null,
    bottomId: state.outfitMode === "Separates" ? optionalId(data.get("bottomId")) : null,
    fullBodyId: state.outfitMode === "One piece" ? optionalId(data.get("fullBodyId")) : null,
    outerwearId: optionalId(data.get("outerwearId")),
    footwearId: optionalId(data.get("footwearId")),
  };
  const problem = validateOutfit(state.outfitMode, picks);
  if (problem) {
    flash("err", problem);
    render();
    return;
  }
  const ids = Object.values(picks).filter((id) => id != null);
  const outfit = {
    id: nextOutfitId(state.outfits),
    name: (String(data.get("name") || "").trim() || suggestLookName(state.items, ids)).slice(0, 80),
    created: today(),
    ...picks,
  };
  await saveOutfit(outfit);
  flash("ok", `Saved ${outfit.name}.`);
  render();
}

async function removeItem(id) {
  const item = itemById(id);
  state.items = state.items.filter((row) => row.id !== id);
  state.outfits = scrubOutfits(state.outfits, id);
  await deleteRecord("items", id);
  for (const outfit of state.outfits) await putRecord("outfits", outfit);
  state.removeId = null;
  flash("ok", item ? `Removed ${item.name}.` : "Removed.");
  openCloset();
}

function garmentFields(id) {
  const card = document.querySelector(`[data-garment="${CSS.escape(id)}"]`);
  const garment = state.garments.find((row) => row.id === id);
  if (!card || !garment) return garment;
  const data = new FormData(card.querySelector("form"));
  return {
    ...garment,
    name: String(data.get("name") || garment.name).trim().slice(0, 80),
    category: data.get("category") || garment.category,
    color: data.get("color") || garment.color,
    season: data.get("season") || garment.season,
  };
}

async function approvePrepared(garment) {
  if (!garment || garment.status !== "pending") return;
  if (!garment.name) {
    flash("err", "Enter a name before approving.");
    render();
    return;
  }
  const source = garment.sourceNames?.[0] || garment.sourceName || "";
  const item = {
    id: nextItemId(state.items, state.outfits),
    category: garment.category,
    name: garment.name,
    color: garment.color,
    season: garment.season || "All",
    imageBlob: garment.cropBlob,
    sourcePhoto: source,
    sourcePhotos: (garment.sourceNames || [source]).filter(Boolean).join("|"),
    created: new Date().toISOString(),
    extra: {},
  };
  await saveItem(item);
  await saveGarment({ ...garment, status: "approved", closetId: item.id, cropBlob: garment.cropBlob });
  flash("ok", `Added ${item.name} to the closet.`);
  render();
}

async function approveGarment(id) {
  await approvePrepared(garmentFields(id));
}

async function rejectGarment(id) {
  const garment = state.garments.find((row) => row.id === id);
  if (!garment || garment.status !== "pending") return;
  await saveGarment({ ...garment, status: "rejected", cropBlob: null });
  flash("ok", "Rejected. The original photo was left where it is.");
  render();
}

async function scan(limit) {
  if (state.scanning) return;
  const scanned = new Set(state.scans.map((scan) => scan.key));
  const queue = state.files.filter((file) => !scanned.has(fileKey(file)));
  const batch = limit ? queue.slice(0, limit) : queue;
  if (!batch.length) {
    flash("ok", state.files.length ? "No new photos to scan. Unchanged pictures are left as they are." : "Choose the photos or the folder first.");
    render();
    return;
  }
  state.scanning = true;
  state.stopScan = false;
  state.flash = null;
  state.progress = "Getting the on-device models ready. Photos stay on this phone.";
  state.progressValue = 0;
  render();
  let found = 0;
  try {
    await ensureModels((update) => {
      if (update.status !== "progress") return;
      const ratio = update.total ? update.loaded / update.total : update.progress || 0;
      state.progress = `Downloading the ${update.which || "model"} (${Math.round(ratio * 100)}%). Your photos are not in this download.`;
      state.progressValue = ratio;
      render();
    });
    for (let index = 0; index < batch.length; index += 1) {
      if (state.stopScan) break;
      const file = batch[index];
      const key = fileKey(file);
      state.progress = `Scanning ${index + 1} of ${batch.length}: ${file.name}`;
      state.progressValue = index / batch.length;
      render();
      let error = "";
      const garmentIds = [];
      try {
        const before = `${file.size}:${file.lastModified}`;
        const regions = await findGarments(file);
        if (`${file.size}:${file.lastModified}` !== before) {
          throw new Error(`${file.name} changed while it was being read. Stopped.`);
        }
        for (const region of regions) {
          const match = findDuplicate(state.garments, region.category, region.embedding);
          if (match) {
            const sources = match.sourceNames || [];
            if (!sources.includes(file.name)) sources.push(file.name);
            match.sourceNames = sources;
            await saveGarment(match);
            if (match.closetId) {
              const linked = state.items.find((item) => item.id === match.closetId);
              if (linked) {
                linked.sourcePhoto = sources[0] || linked.sourcePhoto;
                linked.sourcePhotos = sources.join("|");
                await saveItem(linked);
              }
            }
            garmentIds.push(match.id);
          } else {
            const garment = {
              id: crypto.randomUUID(),
              status: "pending",
              sourceName: file.name,
              sourceNames: [file.name],
              created: new Date().toISOString(),
              closetId: null,
              ...region,
            };
            await saveGarment(garment);
            garmentIds.push(garment.id);
            found += 1;
          }
        }
      } catch (err) {
        error = err.message || "That photo could not be read.";
        if (error.includes("changed while")) throw err;
      }
      const record = { key, error, garmentIds, scannedAt: new Date().toISOString() };
      await putRecord("scans", record);
      const scanIndex = state.scans.findIndex((scan) => scan.key === key);
      if (scanIndex >= 0) state.scans[scanIndex] = record;
      else state.scans.push(record);
    }
    flash("ok", `Scan finished. ${word(found, "new piece", "new pieces")} to review.`);
  } catch (error) {
    flash("err", error.message || "The scan stopped.");
  } finally {
    state.scanning = false;
    state.progress = "";
    state.progressValue = 0;
    render();
  }
}

async function zipFiles(files) {
  const { zipSync } = await import("https://cdn.jsdelivr.net/npm/fflate@0.8.2/+esm");
  const zipped = zipSync(files);
  return new Blob([zipped], { type: "application/zip" });
}

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function downloadCrops() {
  const saved = state.items.filter((item) => item.imageBlob);
  if (!saved.length) {
    flash("err", "Approve a piece, or add one with a photo, before downloading crops.");
    render();
    return;
  }
  const files = {};
  for (const item of saved) {
    const folder = FOLDER_BY_CATEGORY[item.category] || "pieces";
    const safe = item.name.replace(/[^\w.-]+/g, "-").slice(0, 40) || "piece";
    files[`${folder}/${safe}-${item.id}.png`] = new Uint8Array(await item.imageBlob.arrayBuffer());
  }
  downloadBlob(await zipFiles(files), "closet-crops.zip");
}

async function saveToFolder() {
  if (!("showDirectoryPicker" in window)) return;
  const saved = state.items.filter((item) => item.imageBlob);
  if (!saved.length) {
    flash("err", "There are no photos to save yet.");
    render();
    return;
  }
  const root = await window.showDirectoryPicker({ mode: "readwrite" });
  for (const item of saved) {
    const folderName = FOLDER_BY_CATEGORY[item.category] || "pieces";
    const folder = await root.getDirectoryHandle(folderName, { create: true });
    const handle = await folder.getFileHandle(`piece-${item.id}.png`, { create: true });
    const writable = await handle.createWritable();
    await writable.write(item.imageBlob);
    await writable.close();
  }
  flash("ok", "Saved the crops into the folder you picked. Your original photos were not moved.");
  render();
}

async function downloadBackup() {
  const files = {
    "wardrobe_db.csv": new TextEncoder().encode(itemsToCsv(state.items)),
    "outfits_db.csv": new TextEncoder().encode(outfitsToCsv(state.outfits)),
  };
  for (const item of state.items) {
    if (!item.imageBlob) continue;
    files[`closet_images/item_${item.id}.png`] = new Uint8Array(await item.imageBlob.arrayBuffer());
  }
  downloadBlob(await zipFiles(files), "closet-backup.zip");
}

async function bytesOf(file) {
  return new Uint8Array(await file.arrayBuffer());
}

async function migrate(form, mode) {
  const data = new FormData(form);
  const backups = [...data.getAll("backup")].filter((file) => file && file.size);
  const images = [...data.getAll("images")].filter((file) => file && file.size);
  if (!backups.length) {
    flash("err", "Choose the CSV files or a backup zip first.");
    render();
    return;
  }
  const texts = [];
  const zippedImages = [];
  for (const file of backups) {
    if (file.name.toLowerCase().endsWith(".zip")) {
      const { unzipSync } = await import("https://cdn.jsdelivr.net/npm/fflate@0.8.2/+esm");
      const entries = unzipSync(await bytesOf(file));
      for (const [name, content] of Object.entries(entries)) {
        const safe = name.split(/[/\\]/).filter((part) => part && part !== "." && part !== "..");
        if (!safe.length) continue;
        const base = safe.at(-1);
        if (base.toLowerCase().endsWith(".csv")) texts.push({ name: base, text: new TextDecoder().decode(content) });
        else if (/\.(jpe?g|png|webp)$/i.test(base)) zippedImages.push(new File([content], base, { type: "image/png" }));
      }
    } else {
      texts.push({ name: file.name, text: await file.text() });
    }
  }
  let items = [];
  let outfits = [];
  try {
    for (const entry of texts) {
      if (entry.text.includes("Sub-Category") || entry.name.toLowerCase().includes("wardrobe")) items = itemsFromCsv(entry.text);
      else if (entry.text.includes("Top_ID") || entry.name.toLowerCase().includes("outfit")) outfits = outfitsFromCsv(entry.text);
      else if (entry.text.includes("Primary Color")) items = itemsFromCsv(entry.text);
    }
  } catch (error) {
    flash("err", error.message);
    render();
    return;
  }
  if (!items.length && !outfits.length) {
    flash("err", "Those files did not look like a closet backup.");
    render();
    return;
  }
  const photos = new Map();
  for (const file of [...images, ...zippedImages]) photos.set(file.name.toLowerCase(), file);
  for (const item of items) {
    const file = photos.get(basename(item.imagePath).toLowerCase());
    if (file) item.imageBlob = file;
  }
  if (mode === "replace") {
    await clearStore("items");
    await clearStore("outfits");
    state.items = [];
    state.outfits = [];
  }
  for (const item of items) {
    const existing = state.items.find((row) => row.id === item.id);
    const merged = existing ? { ...existing, ...item, imageBlob: item.imageBlob || existing.imageBlob } : item;
    await saveItem(merged);
  }
  for (const outfit of outfits) await saveOutfit(outfit);
  flash("ok", mode === "replace"
    ? `Replaced this closet with ${word(items.length, "piece", "pieces")}.`
    : `Brought in ${word(items.length, "piece", "pieces")}.`);
  openCloset();
}

document.body.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  try {
    if (action === "category") {
      state.category = button.dataset.value;
      render();
    } else if (action === "clear-filters") {
      state.query = "";
      state.category = "All";
      state.color = "All";
      state.season = "All";
      render();
    } else if (action === "outfit-mode") {
      state.outfitMode = button.dataset.value;
      render();
    } else if (action === "ask-remove") {
      state.removeId = Number(button.dataset.id);
      render();
    } else if (action === "cancel-remove") {
      state.removeId = null;
      render();
    } else if (action === "confirm-remove") {
      await removeItem(Number(button.dataset.id));
    } else if (action === "delete-outfit") {
      const id = Number(button.dataset.id);
      state.outfits = state.outfits.filter((outfit) => outfit.id !== id);
      await deleteRecord("outfits", id);
      flash("ok", "Removed that look.");
      render();
    } else if (action === "dismiss-install") {
      state.installDismissed = true;
      try { localStorage.setItem("closet-install-dismissed", "1"); } catch { /* private mode */ }
      render();
    } else if (action === "install" && state.installEvent) {
      state.installEvent.prompt();
      await state.installEvent.userChoice;
      state.installEvent = null;
      render();
    } else if (action === "scan") {
      await scan(button.dataset.limit ? Number(button.dataset.limit) : null);
    } else if (action === "stop-scan") {
      state.stopScan = true;
    } else if (action === "approve") {
      await approveGarment(button.dataset.id);
    } else if (action === "reject") {
      await rejectGarment(button.dataset.id);
    } else if (action === "approve-all") {
      const edits = pendingGarments().map((garment) => garmentFields(garment.id));
      for (const garment of edits) await approvePrepared(garment);
    } else if (action === "download-crops") {
      await downloadCrops();
    } else if (action === "save-folder") {
      await saveToFolder();
    } else if (action === "download-backup") {
      await downloadBackup();
    }
  } catch (error) {
    flash("err", error.message || "That could not be saved on this device.");
    render();
  }
});

document.body.addEventListener("submit", async (event) => {
  const form = event.target.closest("form");
  if (!form) return;
  event.preventDefault();
  const submitter = event.submitter;
  try {
    if (form.dataset.form === "add") await onAdd(form);
    else if (form.dataset.form === "edit") await onEdit(form);
    else if (form.dataset.form === "outfit") await onOutfit(form);
    else if (form.dataset.form === "migrate") await migrate(form, submitter?.dataset.mode || "merge");
  } catch (error) {
    flash("err", error.message || "That could not be saved on this device.");
    render();
  }
});

document.body.addEventListener("input", (event) => {
  if (event.target.id === "closet-query") {
    state.query = event.target.value;
    render();
  }
});

document.body.addEventListener("change", (event) => {
  const target = event.target;
  if (target.id === "closet-color") state.color = target.value;
  else if (target.id === "closet-season") state.season = target.value;
  else if (target.id === "closet-sort") state.sort = target.value;
  else if (target.id === "pick-photos" || target.id === "pick-folder" || target.id === "pick-camera") {
    const added = rememberFiles(target.files);
    flash("ok", added ? `Added ${word(added, "photo", "photos")} to the scan list.` : "Those photos were already on the list.");
    target.value = "";
  } else return;
  render();
});

window.addEventListener("hashchange", () => {
  if (!keepFlashOnNextRoute) state.flash = null;
  keepFlashOnNextRoute = false;
  readRoute();
  render();
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  state.installEvent = event;
  render();
});

async function boot() {
  readRoute();
  try {
    const loaded = await loadCloset();
    state.items = loaded.items;
    state.outfits = loaded.outfits;
    state.garments = loaded.garments;
    state.scans = loaded.scans;
  } catch (error) {
    document.querySelector("#screen").innerHTML = `<div class="banner err">This browser could not open private storage, so the closet cannot be saved here. ${escapeHtml(error.message || "")}</div>`;
    return;
  }
  render();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }
}

boot();
