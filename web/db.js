/** Closet data stays in IndexedDB on this device. */

const DB_NAME = "my-digital-closet";
const DB_VERSION = 1;

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const name of ["items", "outfits", "garments", "scans"]) {
        if (!db.objectStoreNames.contains(name)) db.createObjectStore(name, { keyPath: name === "scans" ? "key" : "id" });
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
  const [items, outfits, garments, scans] = await Promise.all([
    readAll("items"),
    readAll("outfits"),
    readAll("garments"),
    readAll("scans"),
  ]);
  return { items, outfits, garments, scans };
}
