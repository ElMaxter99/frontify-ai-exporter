# Frontify Brand Capture (Chrome extension)

Open the client's Frontify portal in **your own browser, already logged in**, and capture what you see. No token, no crawler: the extension only reads pages **you** open.

## Install (unpacked, ~1 minute)
1. Chrome → `chrome://extensions` → enable **Developer mode**.
2. **Load unpacked** → select this `extension/` folder.
3. Pin the extension (puzzle icon).

## Use
1. Open a page of the portal and click the extension → **Capturar esta página** (it scrolls gently to load lazy content).
2. Repeat for the pages you need. Or tick **auto-capture** for that site (Chrome asks permission once) and just browse; every page you open is captured while it is on.
3. **Exportar ZIP**. Images/downloadable files linked from captured pages are fetched at that moment, one by one, with a pause (default 1 s) using your session. Untick the box for text-only.

The ZIP has the same layout as the Python exporter: `01_BRAND_GUIDELINES/`, `02_ASSETS/`, `03_DOCUMENTATION/`, `05_METADATA/`, `06_AI_KNOWLEDGE/` (`VISUAL_IDENTITY.md`, `BRAND_GUIDELINES.md`), `README_AI.md`, `EXPORT_REPORT.json`.

## Privacy and footprint
- Everything stays in the browser (`chrome.storage.local`) until you export; nothing is sent anywhere.
- Permissions: `activeTab`, `scripting`, `storage`, `tabs`, `*.frontify.com`; any other site is asked at runtime, only when you enable auto-capture or export files from it.
- Browsing is yours: no extra page loads. Only the optional file fetches at export add requests.

## Limits
Not affiliated with Frontify. Only captured pages are included. Colours/fonts are heuristics from rendered elements; font files and structured metadata (tags, custom fields) are not captured. Originals only where the portal exposes a download link to your user. Tested against a local simulated portal, not yet a real Frontify. Use only on portals you are authorised to export; mind client contracts before sending the content to third-party AI.
