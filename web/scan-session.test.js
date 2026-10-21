import assert from "node:assert/strict";
import test from "node:test";
import {
  COOLDOWN_MS,
  describeProgress,
  isImageName,
  markDone,
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

test("queue identity follows the path, size, and time", () => {
  const entry = queueEntryFromFile({
    name: "day.jpg",
    webkitRelativePath: "trip/day.jpg",
    size: 10,
    lastModified: 5,
  });
  assert.equal(entry.key, "trip/day.jpg|10|5");
  assert.equal(entry.status, "queued");
  assert.equal(isImageName("trip/day.JPG"), true);
  assert.equal(isImageName(".hidden.jpg"), false);
  assert.equal(isImageName("notes.txt"), false);
});

test("a checkpoint keeps earlier photos finished and retries the one in progress", () => {
  const first = queueEntryFromFile({ name: "a.jpg", size: 1, lastModified: 1 });
  const second = queueEntryFromFile({ name: "b.jpg", size: 2, lastModified: 2 });
  let entries = [first, second];
  entries = upsertEntry(entries, markDone({ ...entries[0], stored: true }, ["garment-1"], "2026-10-21T00:00:00.000Z"));
  entries = upsertEntry(entries, markReading(entries[1]));
  assert.equal(entries[0].status, "done");
  assert.equal(entries[0].stored, false);
  assert.deepEqual(entries[0].garmentIds, ["garment-1"]);
  assert.equal(nextEntry(entries).name, "b.jpg");
  assert.equal(nextEntry(entries).status, "reading");
  const progress = describeProgress(entries, "b.jpg");
  assert.equal(progress.finished, 1);
  assert.equal(progress.total, 2);
  assert.equal(progress.label, "Scanning 2 of 2: b.jpg");
  assert.equal(progress.ratio, 0.5);
});

test("power and heat pauses are optional and unknown power does not block", () => {
  assert.equal(shouldPauseForPower(false, { known: true, onPower: false }), false);
  assert.equal(shouldPauseForPower(true, { known: true, onPower: false }), true);
  assert.equal(shouldPauseForPower(true, { known: true, onPower: true }), false);
  assert.equal(shouldPauseForPower(true, { known: false, onPower: false }), false);
  assert.equal(shouldCoolDown("hot"), true);
  assert.equal(shouldCoolDown("ok"), false);
  assert.ok(COOLDOWN_MS >= 1000);
});

test("only an in-progress scan resumes, and a missing file is not skipped as finished", () => {
  assert.equal(shouldAutoResume({ status: "running" }), true);
  assert.equal(shouldAutoResume({ status: "charging" }), true);
  assert.equal(shouldAutoResume({ status: "cooling" }), true);
  assert.equal(shouldAutoResume({ status: "stopped" }), false);
  assert.equal(shouldAutoResume(null), false);
  const blocked = markNeedsFile(queueEntryFromFile({ name: "c.jpg", size: 3, lastModified: 3 }));
  assert.equal(nextEntry([blocked]), null);
  assert.equal(needsFileEntry([blocked]).name, "c.jpg");
  assert.match(blocked.error, /Finished photos stay finished/);
});
