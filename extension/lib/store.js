// Captured pages live in chrome.storage.local, keyed by URL (re-capturing a page replaces it).
const FILE_EXT = /\.(pdf|zip|docx?|xlsx?|pptx?|key|ai|eps|psd|indd|idml|svg|png|jpe?g|gif|webp|tiff?|mp4|mov|webm|mp3|wav|ttf|otf|woff2?|csv|json)(\?|$)/i;

export async function savePage(r) {
  const files = (r.links || []).filter((l) => l.download || FILE_EXT.test(new URL(l.href).pathname + "?")).map((l) => ({ href: l.href, text: l.text }));
  const downloads = [...new Map([...(r.downloads || []), ...files].map((d) => [d.href, d])).values()];
  const page = { url: r.url, title: r.title, markdown: r.markdown, text_sample: r.text_sample, images: r.images, downloads, swatches: r.swatches,
    fonts: r.fonts, link_count: (r.links || []).length, captured_at: new Date().toISOString() };
  const { pages = {} } = await chrome.storage.local.get("pages");
  pages[r.url.split("#")[0]] = page;
  await chrome.storage.local.set({ pages });
}
export async function getPages() { return Object.values((await chrome.storage.local.get("pages")).pages || {}); }
export async function clearPages() { await chrome.storage.local.set({ pages: {} }); }
