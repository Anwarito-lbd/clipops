/** Campaign scanner — reads campaign cards from the logged-in CR DOM. */

function clipopsScanCampaigns() {
  const campaigns = [];
  const cards = document.querySelectorAll(
    "[data-campaign], .campaign-card, article, [class*='Campaign'], [class*='campaign']"
  );

  const seen = new Set();
  cards.forEach((card, idx) => {
    const text = textOf(card);
    if (!text || text.length < 20) return;
    const nameEl =
      card.querySelector("h1,h2,h3,h4,[class*='title'],[class*='name']") || card;
    const name = textOf(nameEl).split("\n")[0].slice(0, 120);
    if (!name || seen.has(name)) return;
    seen.add(name);

    const link = card.querySelector("a[href]")?.href || location.href;
    const remainingMatch = text.match(/remaining[^0-9%]*(\d{1,3})\s*%/i);
    const utilisedMatch = text.match(/utili[sz]ed[^0-9%]*(\d{1,3})\s*%/i);
    let budgetPct = remainingMatch ? parseFloat(remainingMatch[1]) : null;
    if (budgetPct == null && utilisedMatch) {
      budgetPct = 100 - parseFloat(utilisedMatch[1]);
    }

    campaigns.push({
      external_id: card.getAttribute("data-campaign-id") || `dom-${idx}-${name.slice(0, 24)}`,
      external_url: link,
      name,
      brand: null,
      cpm: cpmMatch ? parseFloat(cpmMatch[1]) : parseMoney(text),
      budget_remaining_pct: budgetPct,
      brief_text: text.slice(0, 4000),
      required_hashtags: Array.from(text.matchAll(/#[A-Za-z0-9_]+/g)).map((m) => m[0]),
      required_tags: Array.from(text.matchAll(/@[A-Za-z0-9._]+/g)).map((m) => m[0]),
      has_rights: !/no rights|unlicensed/i.test(text),
      requires_fake_engagement: /buy followers|fake (views|likes)|bot views/i.test(text),
      misleading_content: /misleading/i.test(text),
      raw: { snippet: text.slice(0, 500) },
    });
  });

  // Fallback: if DOM selectors miss, offer page title as a single candidate
  if (!campaigns.length && /campaign|reward|brief/i.test(document.title + document.body.innerText.slice(0, 200))) {
    campaigns.push({
      external_id: `page-${location.pathname}`,
      external_url: location.href,
      name: document.title || "Current page campaign",
      brief_text: document.body.innerText.slice(0, 4000),
      required_hashtags: Array.from(document.body.innerText.matchAll(/#[A-Za-z0-9_]+/g))
        .slice(0, 20)
        .map((m) => m[0]),
      raw: { source: "page_fallback" },
    });
  }

  return campaigns;
}
