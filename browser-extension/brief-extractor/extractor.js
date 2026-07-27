/** Brief extractor — pull requirements from an open campaign page. */

function clipopsExtractBrief() {
  const body = document.body.innerText || "";
  const hashtags = Array.from(body.matchAll(/#[A-Za-z0-9_]+/g)).map((m) => m[0]);
  const tags = Array.from(body.matchAll(/@[A-Za-z0-9._]+/g)).map((m) => m[0]);
  const disclosure =
    body.match(/(?:disclosure|disclose|paid partnership)[^\n]{0,120}/i)?.[0] ||
    "Paid partnership";
  const duration = body.match(/(\d+)\s*[-–to]+\s*(\d+)\s*(?:s|sec|seconds)/i);
  const deadline = body.match(/(?:deadline|due)[^\n]{0,80}/i)?.[0] || null;

  return {
    brief_text: body.slice(0, 8000),
    external_url: location.href,
    required_hashtags: [...new Set(hashtags)].slice(0, 30),
    required_tags: [...new Set(tags)].slice(0, 20),
    required_disclosure: disclosure,
    min_duration_sec: duration ? parseInt(duration[1], 10) : 15,
    max_duration_sec: duration ? parseInt(duration[2], 10) : 60,
    deadline_hint: deadline,
    forbidden_words: [],
    forbidden_claims: [],
  };
}
