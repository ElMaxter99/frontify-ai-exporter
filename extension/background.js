// Captures the page of a tab: optional gentle scroll (lazy content) -> extract -> store. Nothing leaves the browser.
import { savePage } from "./lib/store.js";

async function scrollThrough(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, func: async () => {
    const h = document.documentElement.scrollHeight, step = Math.max(400, innerHeight * 0.8);
    for (let y = 0; y < Math.min(h, 20000); y += step) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 250)); }
    scrollTo(0, 0);
  } });
}

export async function capture(tabId, { scroll = true } = {}) {
  const tab = await chrome.tabs.get(tabId);
  if (!/^https?:/.test(tab.url || "")) throw new Error("This tab cannot be captured");
  if (scroll) await scrollThrough(tabId);
  const [{ result }] = await chrome.scripting.executeScript({ target: { tabId }, files: ["lib/extract.js"] });
  if (!result) throw new Error("Nothing extracted");
  await savePage(result);
  return result.title;
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "capture") {
    capture(msg.tabId, { scroll: msg.scroll !== false }).then((title) => reply({ ok: true, title }), (e) => reply({ ok: false, error: String(e.message || e) }));
    return true;
  }
});

// Auto-capture: only for origins the person switched on (and granted) in the popup, only for tabs they open themselves.
chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== "complete" || !tab.url || !/^https?:/.test(tab.url)) return;
  const { autoOrigins = [] } = await chrome.storage.local.get("autoOrigins");
  if (autoOrigins.includes(new URL(tab.url).origin)) {
    await new Promise((r) => setTimeout(r, 1200)); // let the SPA render
    try { await capture(tabId, { scroll: false }); chrome.action.setBadgeText({ tabId, text: "✓" }); } catch (_) { /* ignore */ }
  }
});
