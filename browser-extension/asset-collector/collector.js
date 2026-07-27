/** Asset collector — list downloadable campaign assets (does not auto-join). */

function clipopsCollectAssets() {
  const urls = new Set();
  document.querySelectorAll("a[href], video[src], source[src]").forEach((el) => {
    const href = el.href || el.src;
    if (!href) return;
    if (/\.(mp4|mov|webm|wav|mp3|zip|png|jpe?g)(\?|$)/i.test(href)) {
      urls.add(href);
    }
    if (/download|asset|media|footage/i.test(href) || /download|asset/i.test(el.innerText || "")) {
      urls.add(href);
    }
  });
  return Array.from(urls).slice(0, 50);
}
