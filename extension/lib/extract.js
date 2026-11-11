// GENERATED from src/browser/extract_js.py (kept in sync by tests/test_extension.py). Injected into the page; returns the capture.
(() => {
  const root = document.querySelector('main') || document.body;
  const txt = (el) => (el.innerText || '').replace(/\s+/g, ' ').trim();
  const abs = (u) => { try { return new URL(u, location.href).href; } catch (e) { return null; } };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && (r.width > 0 || r.height > 0); };

  // ---- text blocks -> markdown
  const SEL = 'h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,figcaption,td,th,img';
  const all = Array.from(root.querySelectorAll(SEL));
  const blocks = [];
  for (const el of all) {
    if (el.closest('nav,header,footer,script,style,noscript')) continue;
    if (el.tagName !== 'IMG' && !visible(el)) continue;
    if (el.tagName !== 'IMG' && all.some((o) => o !== el && o.tagName !== 'IMG' && el.contains(o))) continue; // keep the innermost block
    if (el.tagName === 'IMG') {
      const src = abs(el.currentSrc || el.src);
      if (src && !src.startsWith('data:')) blocks.push('![' + (el.alt || '').replace(/\]/g, '') + '](' + src + ')');
      continue;
    }
    const t = txt(el);
    if (!t) continue;
    const tag = el.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag)) blocks.push('#'.repeat(+tag[1]) + ' ' + t);
    else if (tag === 'li') blocks.push('- ' + t);
    else if (tag === 'blockquote') blocks.push('> ' + t);
    else if (tag === 'pre') blocks.push('```\n' + (el.innerText || '') + '\n```');
    else blocks.push(t);
  }

  // ---- links
  const links = [], downloads = [];
  let n = 0;
  for (const a of Array.from(document.querySelectorAll('a[href]'))) {
    const href = abs(a.getAttribute('href'));
    if (!href || !/^https?:/.test(href)) continue;
    const text = txt(a).slice(0, 120);
    const label = (text + ' ' + (a.getAttribute('aria-label') || '') + ' ' + (a.getAttribute('title') || '')).toLowerCase();
    const isDl = a.hasAttribute('download') || /download|descargar|telecharger|herunterladen/.test(label);
    links.push({ href, text, download: isDl });
    if (isDl) downloads.push({ href, text });
  }
  // buttons that look like downloads but have no href (only used when --click-downloads)
  const clickable = [];
  for (const b of Array.from(document.querySelectorAll('button,[role=button]'))) {
    const label = (txt(b) + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '')).toLowerCase();
    if (/download|descargar|telecharger|herunterladen/.test(label) && visible(b)) { b.setAttribute('data-fx-dl', String(n)); clickable.push({ idx: n, text: txt(b).slice(0, 80) }); n++; }
  }

  // ---- images (rendered)
  const images = [];
  for (const im of Array.from(document.images)) {
    const src = abs(im.currentSrc || im.src);
    if (src && !src.startsWith('data:') && (im.naturalWidth > 32 || im.naturalHeight > 32)) images.push({ src, alt: im.alt || '', width: im.naturalWidth, height: im.naturalHeight });
  }

  // ---- colour swatches (heuristic: small/medium solid-background boxes + the text around them)
  const swatches = {};
  for (const el of Array.from(root.querySelectorAll('div,span,li,td,figure,button,a'))) {
    const s = getComputedStyle(el);
    const bg = s.backgroundColor;
    if (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 24 || r.width > 600 || r.height > 600) continue;
    let holder = el, label = '';
    for (let i = 0; i < 4 && holder && !label; i++) { holder = holder.parentElement; label = holder ? txt(holder) : ''; if (label.length > 240) label = ''; }
    if (!swatches[bg]) swatches[bg] = { css: bg, label: label || txt(el).slice(0, 120), count: 0 };
    swatches[bg].count++;
  }

  // ---- fonts
  const fam = (sel) => { const e = document.querySelector(sel); return e ? getComputedStyle(e).fontFamily : null; };
  let loaded = [];
  try { loaded = Array.from(document.fonts).filter((f) => f.status === 'loaded').map((f) => ({ family: f.family.replace(/["']/g, ''), weight: f.weight, style: f.style })); } catch (e) {}

  return {
    url: location.href,
    title: (document.querySelector('h1') ? txt(document.querySelector('h1')) : '') || document.title || location.pathname,
    doc_title: document.title,
    markdown: blocks.join('\n\n'),
    text_sample: txt(root).slice(0, 4000),
    links, downloads, clickable, images,
    swatches: Object.values(swatches).slice(0, 80),
    fonts: { heading: fam('h1') || fam('h2'), body: fam('p') || fam('body'), loaded },
  };
})();
