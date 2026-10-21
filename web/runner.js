/** One-photo-at-a-time scan. Each finished photo is saved before the next one starts. */

import { findDuplicate } from "./closet.js";
import { deleteRecord, getRecord, inboxHas, putRecord, readAll, readInbox, writeInbox } from "./db.js";
import {
  COOLDOWN_MS,
  THERMAL_WAIT_MS,
  describeProgress,
  isImageName,
  markDone,
  markError,
  markNeedsFile,
  markReading,
  needsFileEntry,
  nextEntry,
  queueEntryFromFile,
  shouldAutoResume,
  shouldCoolDown,
  shouldPauseForPower,
  upsertEntry,
} from "./scan-session.js";
import { ensureModels, findGarments } from "./vision.js";
import {
  inPlayApp,
  nativeHoldForCharger,
  nativeResumeWork,
  nativeStart,
  nativeStop,
  nativeUpdate,
  powerState,
  releaseWakeLock,
  requestWakeLock,
  watchPower,
} from "./native-scan.js";

const liveFiles = new Map();

export function bindRunner(ctx) {
  const { state, render, flash, saveItem, saveGarment } = ctx;
  let wakeLock = null;
  let directoryHandle = null;
  let loopPromise = null;

  function stamp() {
    return new Date().toISOString();
  }

  async function saveJob() {
    state.job.updatedAt = stamp();
    await putRecord("prefs", state.job);
  }

  async function saveSettings() {
    await putRecord("prefs", {
      id: "settings",
      onlyWhileCharging: Boolean(state.onlyWhileCharging),
      keepAwake: Boolean(state.keepAwake),
    });
  }

  async function rememberEntry(entry) {
    state.queue = upsertEntry(state.queue, entry);
    await putRecord("queue", entry);
    return entry;
  }

  function progressText(currentName = "") {
    const progress = describeProgress(state.queue, currentName);
    state.progressValue = progress.ratio;
    return progress;
  }

  async function publish(label, mode) {
    state.progress = label;
    const progress = describeProgress(state.queue);
    if (mode === "charger") await nativeHoldForCharger(label, progress.finished, progress.total);
    else if (mode === "work") {
      await nativeResumeWork();
      await nativeUpdate(label, progress.finished, progress.total);
    } else await nativeUpdate(label, progress.finished, progress.total);
    render();
  }

  async function fileFromDirectory(relativePath) {
    if (!directoryHandle || !relativePath) return null;
    try {
      const parts = relativePath.split("/").filter(Boolean);
      let dir = directoryHandle;
      for (let index = 0; index < parts.length - 1; index += 1) {
        dir = await dir.getDirectoryHandle(parts[index]);
      }
      const handle = await dir.getFileHandle(parts[parts.length - 1]);
      return handle.getFile();
    } catch {
      return null;
    }
  }

  async function sourceFile(entry) {
    const stored = await readInbox(entry.key, entry.lastModified);
    if (stored) return stored;
    const live = liveFiles.get(entry.key);
    if (live) return live;
    return fileFromDirectory(entry.relativePath);
  }

  async function scanOne(entry) {
    let source = await sourceFile(entry);
    if (!source) {
      await rememberEntry(markNeedsFile(entry));
      return "halt";
    }
    const before = `${source.size}:${source.lastModified}`;
    if (!(await inboxHas(entry.key))) {
      await writeInbox(entry.key, source);
      if (`${source.size}:${source.lastModified}` !== before) {
        throw new Error(`${entry.name} changed while it was being read. Stopped.`);
      }
      source = await readInbox(entry.key, entry.lastModified);
    }
    await rememberEntry(markReading({ ...entry, stored: true }));
    await publish(progressText(entry.name).label, "work");
    let error = "";
    const garmentIds = [];
    let created = 0;
    try {
      const regions = await findGarments(source);
      for (const region of regions) {
        const match = findDuplicate(state.garments, region.category, region.embedding);
        if (match) {
          const sources = match.sourceNames || [];
          if (!sources.includes(entry.name)) sources.push(entry.name);
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
            sourceName: entry.name,
            sourceNames: [entry.name],
            created: stamp(),
            closetId: null,
            ...region,
          };
          await saveGarment(garment);
          garmentIds.push(garment.id);
          created += 1;
        }
      }
    } catch (err) {
      error = err.message || "That photo could not be read.";
      if (error.includes("changed while") || /model|onnx|wasm|fetch|network/i.test(error)) throw err;
    }
    const finished = error
      ? markError(entry, error, stamp())
      : markDone({ ...entry, stored: true }, garmentIds, stamp());
    await rememberEntry(finished);
    await deleteRecord("inbox", entry.key);
    await putRecord("scans", {
      key: entry.key,
      error,
      garmentIds,
      scannedAt: finished.scannedAt,
    });
    const scanIndex = state.scans.findIndex((scan) => scan.key === entry.key);
    if (scanIndex >= 0) state.scans[scanIndex] = { key: entry.key, error, garmentIds, scannedAt: finished.scannedAt };
    else state.scans.push({ key: entry.key, error, garmentIds, scannedAt: finished.scannedAt });
    return error ? { outcome: "error", created: 0 } : { outcome: "done", created };
  }

  async function holdWake() {
    if (!state.keepAwake || !state.scanning) return;
    wakeLock = await requestWakeLock();
  }

  async function dropWake() {
    await releaseWakeLock(wakeLock);
    wakeLock = null;
  }

  function waitForSignal() {
    return new Promise((resolve) => {
      const timer = setInterval(async () => {
        const power = await powerState();
        if (power.known && power.onPower) finish();
      }, 15000);
      function finish() {
        clearInterval(timer);
        window.removeEventListener("closet-power", finish);
        state.stopPowerWait = null;
        resolve();
      }
      state.stopPowerWait = finish;
      window.addEventListener("closet-power", finish, { once: true });
    });
  }

  async function sweepInbox() {
    const rows = await readAll("inbox");
    const keep = new Set(
      state.queue
        .filter((entry) => entry.status === "queued" || entry.status === "reading" || entry.status === "needs-file")
        .map((entry) => entry.key),
    );
    for (const row of rows) {
      if (!keep.has(row.key)) await deleteRecord("inbox", row.key);
    }
  }

  async function runLoop() {
    if (state.scanning) return loopPromise;
    state.scanning = true;
    state.stopScan = false;
    loopPromise = (async () => {
      let found = 0;
      try {
        state.job.status = "running";
        await saveJob();
        const opening = progressText().label || "Getting the on-device models ready. Photos stay on this phone.";
        state.progress = "Getting the on-device models ready. Photos stay on this phone.";
        render();
        await nativeStart(opening, progressText().finished, progressText().total);
        await holdWake();
        await ensureModels((update) => {
          if (update.status !== "progress") return;
          const ratio = update.total ? update.loaded / update.total : update.progress || 0;
          state.progress = `Downloading the ${update.which || "model"} (${Math.round(ratio * 100)}%). Your photos are not in this download.`;
          state.progressValue = ratio;
          render();
        });
        while (!state.stopScan) {
          const power = await powerState();
          if (shouldPauseForPower(state.onlyWhileCharging, power)) {
            state.job.status = "charging";
            await saveJob();
            await dropWake();
            const label = `${progressText().label}. Waiting for the charger. Finished photos are saved.`;
            await publish(label, "charger");
            await waitForSignal();
            if (state.stopScan) break;
            continue;
          }
          if (shouldCoolDown(power.thermal)) {
            state.job.status = "cooling";
            await saveJob();
            await publish(`${progressText().label}. Paused so the phone can cool down. Finished photos are saved.`, "work");
            await waitOrTimeout(THERMAL_WAIT_MS);
            if (state.stopScan) break;
            continue;
          }
          const entry = nextEntry(state.queue);
          if (!entry) {
            if (needsFileEntry(state.queue)) state.job.status = "needs-file";
            else state.job.status = "done";
            break;
          }
          if (state.job.limit && state.job.processed >= state.job.limit) {
            state.job.status = "stopped";
            break;
          }
          state.job.status = "running";
          await saveJob();
          await holdWake();
          const outcome = await scanOne(entry);
          if (outcome === "halt") {
            state.job.status = "needs-file";
            break;
          }
          found += outcome.created || 0;
          state.job.processed += 1;
          await saveJob();
          await publish(progressText().label, "work");
          await waitOrTimeout(COOLDOWN_MS);
        }
        if (state.stopScan) state.job.status = "stopped";
        await saveJob();
        const progress = progressText();
        if (state.job.status === "needs-file") {
          flash("err", "Choose the same photos to continue. Finished photos stay finished.");
        } else if (state.stopScan) {
          flash("ok", `Stopped after this photo. ${progress.label}. Nothing finished was lost.`);
        } else if (state.job.status === "stopped") {
          flash("ok", `This batch is done. ${progress.label}. The rest stay queued.`);
        } else {
          state.job.status = "done";
          await saveJob();
          flash("ok", `Scan finished. ${found} new ${found === 1 ? "piece" : "pieces"} to review. ${progress.label}.`);
        }
      } catch (error) {
        state.job.status = "stopped";
        await saveJob().catch(() => {});
        flash("err", error.message || "The scan stopped. Finished photos are saved.");
      } finally {
        const stillWaiting = state.job.status === "charging" || state.job.status === "cooling";
        if (!stillWaiting) await nativeStop();
        if (!stillWaiting) await dropWake();
        state.scanning = false;
        if (!stillWaiting) state.progress = "";
        state.progressValue = progressText().ratio;
        render();
      }
    })();
    return loopPromise;
  }

  function waitOrTimeout(ms) {
    return new Promise((resolve) => {
      const timer = setTimeout(finish, ms);
      const onPower = () => finish();
      function finish() {
        clearTimeout(timer);
        window.removeEventListener("closet-power", onPower);
        resolve();
      }
      window.addEventListener("closet-power", onPower);
      state.stopPowerWait = finish;
    });
  }

  async function addFiles(fileList) {
    const files = [...fileList].filter((file) => file && isImageName(file.webkitRelativePath || file.name));
    let added = 0;
    let skipped = 0;
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      const entry = queueEntryFromFile(file);
      const existing = state.queue.find((row) => row.key === entry.key);
      if (existing?.status === "done") {
        skipped += 1;
        continue;
      }
      liveFiles.set(entry.key, file);
      state.progress = `Saving photo ${index + 1} of ${files.length} on this phone so the scan can continue. Originals are untouched.`;
      state.progressValue = files.length ? index / files.length : 0;
      render();
      await new Promise((resolve) => setTimeout(resolve, 0));
      const before = `${file.size}:${file.lastModified}`;
      await writeInbox(entry.key, file);
      if (`${file.size}:${file.lastModified}` !== before) {
        throw new Error(`${file.name} changed while it was being saved. Stopped.`);
      }
      await rememberEntry({
        ...entry,
        status: "queued",
        stored: true,
        error: "",
        garmentIds: existing?.garmentIds || [],
        scannedAt: "",
      });
      added += 1;
    }
    if (!state.scanning) {
      state.progress = "";
      state.progressValue = progressText().ratio;
      render();
    }
    return { added, skipped };
  }

  async function chooseFolder() {
    if (!("showDirectoryPicker" in window)) return;
    const handle = await window.showDirectoryPicker({ mode: "read" });
    directoryHandle = handle;
    try {
      await putRecord("prefs", { id: "folder", handle });
    } catch {
      /* The folder can still be used for this visit. */
    }
    const files = [];
    async function walk(dir, prefix) {
      for await (const [name, child] of dir.entries()) {
        if (name.startsWith(".")) continue;
        const path = prefix ? `${prefix}/${name}` : name;
        if (child.kind === "directory") await walk(child, path);
        else if (isImageName(name)) {
          const file = await child.getFile();
          Object.defineProperty(file, "webkitRelativePath", { value: path });
          files.push(file);
        }
      }
    }
    await walk(handle, "");
    return addFiles(files);
  }

  async function loadFolder() {
    const row = await getRecord("prefs", "folder");
    if (!row?.handle?.queryPermission) return;
    try {
      const permission = await row.handle.queryPermission({ mode: "read" });
      if (permission === "granted") directoryHandle = row.handle;
    } catch {
      directoryHandle = null;
    }
  }

  function ensureJob() {
    if (!state.job) {
      state.job = {
        id: "job",
        status: "idle",
        limit: null,
        processed: 0,
        updatedAt: "",
      };
    }
  }

  return {
    addFiles,
    chooseFolder,
    loadFolder,
    saveSettings,
    async start(limit) {
      if (state.scanning) return;
      ensureJob();
      state.job.limit = limit || null;
      state.job.processed = 0;
      state.job.status = "running";
      if (!nextEntry(state.queue)) {
        flash("ok", state.queue.length ? "No new photos to scan. Unchanged pictures are left as they are." : "Choose the photos or the folder first.");
        state.job.status = state.queue.length ? "done" : "idle";
        await saveJob();
        render();
        return;
      }
      await runLoop();
    },
    async resumeIfNeeded() {
      ensureJob();
      await loadFolder();
      await sweepInbox();
      if (!shouldAutoResume(state.job)) return;
      if (!nextEntry(state.queue)) {
        state.job.status = needsFileEntry(state.queue) ? "needs-file" : "done";
        await saveJob();
        return;
      }
      flash("ok", "Continuing the scan from the last finished photo.");
      await runLoop();
    },
    stopAfterPhoto() {
      state.stopScan = true;
      state.stopPowerWait?.();
    },
    async clearUnfinished() {
      if (state.scanning) return;
      const keep = [];
      for (const entry of state.queue) {
        if (entry.status === "done" || entry.status === "error") {
          keep.push(entry);
          continue;
        }
        await deleteRecord("queue", entry.key);
        await deleteRecord("inbox", entry.key);
        liveFiles.delete(entry.key);
      }
      state.queue = keep;
      ensureJob();
      state.job.status = "idle";
      state.job.processed = 0;
      await saveJob();
      state.progress = "";
      render();
    },
    holdWake,
    notePower: () => window.dispatchEvent(new Event("closet-power")),
    inPlayApp,
    watchPower,
  };
}
