/** Asset collector — find where a campaign's footage actually lives.
 *
 * Campaign pages rarely link raw .mp4 files. They link a "Resources" or
 * "Assets" card pointing at Google Drive, Dropbox or similar. Matching only on
 * media file extensions missed those entirely, which left the operator hunting
 * for footage by hand. Does not download anything — only reports locations.
 */

// Hosts campaigns actually use to hand over footage.
const CLIPOPS_FILE_HOSTS =
  /(?:drive|docs)\.google\.com|dropbox\.com|mega\.(?:nz|io)|wetransfer\.com|we\.tl|1drv\.ms|onedrive\.live\.com|box\.com|icloud\.com|pcloud|mediafire\.com|frame\.io|notion\.(?:so|site)|s3[.-][\w-]*amazonaws\.com|cdn\.|drive\.proton\.me/i;

const CLIPOPS_MEDIA_EXT = /\.(mp4|mov|mkv|webm|m4v|avi|wav|mp3|zip|rar|7z)(\?|#|$)/i;

// Section headings that introduce footage links.
const CLIPOPS_RESOURCE_LABEL =
  /resources?|assets?|files?|footage|media|downloads?|clips?|source material|b[- ]?roll|drive|folder|brief/i;

function clipopsClassifyLink(url, label) {
  if (CLIPOPS_MEDIA_EXT.test(url)) return "direct_media";
  if (CLIPOPS_FILE_HOSTS.test(url)) return "file_host";
  if (CLIPOPS_RESOURCE_LABEL.test(label || "")) return "labelled_resource";
  return "other";
}

/** Nearest preceding heading, so a bare "Resources" card keeps its context. */
function clipopsSectionFor(el) {
  let node = el;
  for (let hops = 0; node && hops < 6; hops++) {
    let sib = node.previousElementSibling;
    while (sib) {
      if (/^H[1-6]$/.test(sib.tagName)) {
        return (sib.innerText || "").trim().slice(0, 60);
      }
      sib = sib.previousElementSibling;
    }
    node = node.parentElement;
  }
  return "";
}

function clipopsCollectAssets() {
  const seen = new Map();

  document.querySelectorAll("a[href], video[src], source[src]").forEach((el) => {
    const url = el.href || el.src;
    if (!url || /^javascript:/i.test(url)) return;

    // Skip navigation back into the platform itself.
    if (/^https?:\/\/(?:www\.)?(?:whop|contentrewards)\.com\/?$/i.test(url)) return;

    const own = (el.innerText || el.getAttribute("aria-label") || "").trim();
    const section = clipopsSectionFor(el);
    const label = [section, own].filter(Boolean).join(" / ").slice(0, 120);
    const kind = clipopsClassifyLink(url, label);

    // "other" links are page furniture unless their section says otherwise.
    if (kind === "other" && !CLIPOPS_RESOURCE_LABEL.test(section)) return;

    if (!seen.has(url)) {
      seen.set(url, { url, kind, label: label || "(unlabelled)" });
    }
  });

  const order = { direct_media: 0, file_host: 1, labelled_resource: 2, other: 3 };
  return Array.from(seen.values())
    .sort((a, b) => order[a.kind] - order[b.kind])
    .slice(0, 50);
}

/** Flat URL list for callers that only want strings. */
function clipopsCollectAssetUrls() {
  return clipopsCollectAssets().map((a) => a.url);
}
