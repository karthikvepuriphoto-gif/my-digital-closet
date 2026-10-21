/** Pure rules for a scan that can stop and continue without losing finished photos. */

import { fileKey } from "./closet.js";

export const COOLDOWN_MS = 2000;
export const THERMAL_WAIT_MS = 30000;

const IMAGE_NAME = /\.(jpe?g|png|webp|bmp)$/i;

export function isImageName(name) {
  const text = String(name || "");
  const base = text.split(/[/\\]/).pop();
  return Boolean(base) && !base.startsWith(".") && IMAGE_NAME.test(base);
}

export function queueEntryFromFile(file) {
  const relativePath = file.webkitRelativePath || file.name;
  return {
    key: fileKey({ name: file.name, webkitRelativePath: relativePath, size: file.size, lastModified: file.lastModified }),
    name: file.name,
    relativePath,
    size: file.size,
    lastModified: file.lastModified,
    status: "queued",
    stored: false,
    error: "",
    garmentIds: [],
    scannedAt: "",
  };
}

export function upsertEntry(entries, entry) {
  const next = entries.slice();
  const index = next.findIndex((row) => row.key === entry.key);
  if (index >= 0) next[index] = entry;
  else next.push(entry);
  return next;
}

export function isFinished(entry) {
  return entry?.status === "done" || entry?.status === "error";
}

export function nextEntry(entries) {
  return entries.find((entry) => entry.status === "queued" || entry.status === "reading") || null;
}

export function needsFileEntry(entries) {
  return entries.find((entry) => entry.status === "needs-file") || null;
}

export function describeProgress(entries, currentName = "") {
  const total = entries.length;
  const finished = entries.filter(isFinished).length;
  const ratio = total ? finished / total : 0;
  let label = "";
  if (total && currentName) label = `Scanning ${Math.min(total, finished + 1)} of ${total}: ${currentName}`;
  else if (total) label = `${finished} of ${total} photos finished`;
  return { finished, total, ratio, label };
}

export function shouldPauseForPower(onlyWhileCharging, power) {
  if (!onlyWhileCharging) return false;
  if (!power?.known) return false;
  return power.onPower !== true;
}

export function shouldCoolDown(thermal) {
  return thermal === "hot";
}

export function shouldAutoResume(job) {
  return job?.status === "running" || job?.status === "charging" || job?.status === "cooling";
}

export function markReading(entry) {
  return { ...entry, status: "reading", error: "" };
}

export function markDone(entry, garmentIds, scannedAt) {
  return {
    ...entry,
    status: "done",
    stored: false,
    error: "",
    garmentIds: garmentIds || [],
    scannedAt: scannedAt || "",
  };
}

export function markError(entry, error, scannedAt) {
  return { ...entry, status: "error", stored: false, error: error || "That photo could not be read.", scannedAt: scannedAt || "" };
}

export function markNeedsFile(entry) {
  return {
    ...entry,
    status: "needs-file",
    error: "Choose this photo again to continue. Finished photos stay finished.",
  };
}
