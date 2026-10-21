/** Closet data stays in IndexedDB on this device. */

const DB_NAME = "my-digital-closet";
const DB_VERSION = 2;
const STORES = ["items", "outfits", "garments", "scans", "queue", "inbox", "prefs"];

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const name of STORES) {
        if (db.objectStoreNames.contains(name)) continue;
        const keyPath = name === "items" || name === "outfits" || name === "garments" ? "id" : name === "prefs" ? "id" : "key";
        db.createObjectStore(name, { keyPath });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore(name, mode, run) {
  const db = await openDb();
  try {
    const tx = db.transaction(name, mode);
    const done = new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("The closet could not be saved on this device."));
    });
    const result = await run(tx.objectStore(name));
    await done;
    return result;
  } finally {
    db.close();
  }
}

export function readAll(name) {
  return withStore(name, "readonly", (store) => requestToPromise(store.getAll()));
}

export function getRecord(name, key) {
  return withStore(name, "readonly", (store) => requestToPromise(store.get(key)));
}

export function putRecord(name, record) {
  return withStore(name, "readwrite", (store) => requestToPromise(store.put(record)));
}

export function deleteRecord(name, id) {
  return withStore(name, "readwrite", (store) => requestToPromise(store.delete(id)));
}

export function clearStore(name) {
  return withStore(name, "readwrite", (store) => requestToPromise(store.clear()));
}

export async function loadCloset() {
  const [items, outfits, garments, scans, queue, prefs] = await Promise.all([
    readAll("items"),
    readAll("outfits"),
    readAll("garments"),
    readAll("scans"),
    readAll("queue"),
    readAll("prefs"),
  ]);
  return { items, outfits, garments, scans, queue, prefs };
}

export async function writeInbox(key, file) {
  const blob = file instanceof Blob ? file : new Blob([await file.arrayBuffer()]);
  await putRecord("inbox", { key, blob, name: file.name || "photo.jpg", type: blob.type || "image/jpeg" });
}

export async function readInbox(key, lastModified = Date.now()) {
  const row = await getRecord("inbox", key);
  if (!row?.blob) return null;
  return new File([row.blob], row.name || "photo.jpg", { type: row.type || "image/jpeg", lastModified });
}

export async function inboxHas(key) {
  const row = await getRecord("inbox", key);
  return Boolean(row?.blob);
}
