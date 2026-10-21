/** Play app bridge. In a browser these calls do nothing harmful and report what the browser can see. */

let playPlugin;

function capacitor() {
  if (playPlugin !== undefined) return playPlugin;
  const cap = window.Capacitor;
  if (!cap?.isNativePlatform?.() || !cap.registerPlugin) {
    playPlugin = null;
    return null;
  }
  try {
    playPlugin = cap.registerPlugin("ClosetScan");
  } catch {
    playPlugin = null;
  }
  return playPlugin;
}

export function inPlayApp() {
  return Boolean(capacitor());
}

function emitPower() {
  window.dispatchEvent(new Event("closet-power"));
}

export async function nativeStart(body, done, total) {
  const plugin = capacitor();
  if (!plugin) return { started: false };
  try {
    return await plugin.start({ body, done, total });
  } catch {
    return { started: false };
  }
}

export async function nativeUpdate(body, done, total) {
  const plugin = capacitor();
  if (!plugin) return;
  try {
    await plugin.update({ body, done, total });
  } catch {
    /* The scan still continues in the page. */
  }
}

export async function nativeHoldForCharger(body, done, total) {
  const plugin = capacitor();
  if (!plugin) return;
  try {
    await plugin.holdForCharger({ body, done, total });
  } catch {
    /* Browser waits with the page timer instead. */
  }
}

export async function nativeResumeWork() {
  const plugin = capacitor();
  if (!plugin) return;
  try {
    await plugin.resumeWork();
  } catch {
    /* Keep scanning even if the notification could not be updated. */
  }
}

export async function nativeStop() {
  const plugin = capacitor();
  if (!plugin) return;
  try {
    await plugin.stop();
  } catch {
    /* Already stopped. */
  }
}

export async function powerState() {
  const plugin = capacitor();
  if (plugin) {
    try {
      const status = await plugin.status();
      return {
        known: Boolean(status?.known),
        onPower: Boolean(status?.onPower),
        thermal: status?.thermal || "ok",
      };
    } catch {
      return { known: false, onPower: true, thermal: "ok" };
    }
  }
  if (typeof navigator.getBattery !== "function") return { known: false, onPower: true, thermal: "ok" };
  try {
    const battery = await navigator.getBattery();
    return { known: true, onPower: Boolean(battery.charging), thermal: "ok" };
  } catch {
    return { known: false, onPower: true, thermal: "ok" };
  }
}

export function watchPower(onChange) {
  const plugin = capacitor();
  window.onClosetScan = () => onChange();
  if (plugin?.addListener) {
    plugin.addListener("power", () => onChange()).catch?.(() => {});
  }
  if (typeof navigator.getBattery === "function") {
    navigator.getBattery().then((battery) => {
      battery.addEventListener("chargingchange", onChange);
    }).catch(() => {});
  }
  window.addEventListener("closet-power", onChange);
  return emitPower;
}

export async function requestWakeLock() {
  if (!("wakeLock" in navigator)) return null;
  try {
    return await navigator.wakeLock.request("screen");
  } catch {
    return null;
  }
}

export async function releaseWakeLock(lock) {
  try {
    await lock?.release();
  } catch {
    /* Already released. */
  }
}
