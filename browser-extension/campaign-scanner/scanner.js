/** Campaign scanner — reads campaign cards from the logged-in CR DOM. */

function clipopsScanCampaigns() {
  const campaigns = [];
  const seen = new Set();

  const SELECTORS = [
    "[data-campaign]",
    "[data-campaign-id]",
    "[data-testid*='campaign' i]",
    ".campaign-card",
    "article[class*='campaign' i]",
    "[class*='CampaignCard']",
    "[class*='campaign-card']",
    "[class*='CampaignRow']",
    "main article",
    "main [role='listitem']",
    "[role='article']",
  ];

  let cards = [];
  for (const sel of SELECTORS) {
    try {
      cards = Array.from(document.querySelectorAll(sel));
      if (cards.length) break;
    } catch {
      /* invalid selector in older engines */
    }
  }

  // Broad fallback: large text blocks that look like campaign cards
  if (!cards.length) {
    cards = Array.from(document.querySelectorAll("article, section, li, div")).filter((el) => {
      const t = textOf(el);
      if (!t || t.length < 40 || t.length > 6000) return false;
      return /CPM|budget|reward|hashtag|#\w+/i.test(t);
    });
  }

  cards.forEach((card, idx) => {
    try {
      const text = textOf(card);
      if (!text || text.length < 20) return;
      const nameEl =
        card.querySelector(
          "h1,h2,h3,h4,[class*='title' i],[class*='name' i],[data-testid*='title' i]"
        ) || card;
      const name = textOf(nameEl).split("\n")[0].slice(0, 120);
      if (!name || seen.has(name)) return;
      seen.add(name);

      const linkEl =
        card.querySelector("a[href*='campaign' i], a[href*='reward' i], a[href]") || null;
      const link = linkEl?.href || location.href;

      // When the DOM lumps several campaigns into one node, no figure in it can
      // be attributed to a specific campaign — report none rather than another
      // campaign's rate.
      const merged = looksLikeMultipleCampaigns(text);
      const cpm = merged ? null : extractCpm(text);
      const budget = merged ? { total: null, utilised: null } : extractBudget(text);

      const remainingMatch =
        text.match(/(?:budget\s+)?remaining[^0-9%]*(\d{1,3})\s*%/i) ||
        text.match(/(\d{1,3})\s*%\s*(?:left|remaining)/i);
      const utilisedMatch =
        text.match(/utili[sz]ed[^0-9%]*(\d{1,3})\s*%/i) ||
        text.match(/(\d{1,3})\s*%\s*(?:used|spent|utili[sz]ed)/i);

      let budgetPct = remainingMatch ? parseFloat(remainingMatch[1]) : null;
      if (budgetPct == null && utilisedMatch) {
        budgetPct = 100 - parseFloat(utilisedMatch[1]);
      }
      // Prefer the "$used/$total" progress display when it parsed.
      if (budgetPct == null && budget.total && budget.utilised != null) {
        budgetPct = Math.round((1 - budget.utilised / budget.total) * 1000) / 10;
      }

      const geoMatches = Array.from(
        text.matchAll(/\b(?:US|CA|UK|GB|AU|EU|WW|Worldwide)\b/g)
      ).map((m) => m[0]);

      campaigns.push({
        external_id:
          card.getAttribute("data-campaign-id") ||
          card.getAttribute("data-campaign") ||
          `dom-${idx}-${name.slice(0, 24)}`,
        external_url: link,
        name,
        brand: null,
        cpm,
        total_budget: budget.total,
        budget_utilised: budget.utilised,
        budget_remaining_pct: budgetPct,
        required_geo: [...new Set(geoMatches)],
        brief_text: text.slice(0, 4000),
        required_hashtags: Array.from(text.matchAll(/#[A-Za-z0-9_]+/g)).map((m) => m[0]),
        required_tags: Array.from(text.matchAll(/@[A-Za-z0-9._]+/g)).map((m) => m[0]),
        has_rights: !/no rights|unlicensed|do not use/i.test(text),
        requires_fake_engagement: /buy followers|fake (views|likes)|bot views|engagement farm/i.test(
          text
        ),
        misleading_content: /misleading|false claim|deceptive/i.test(text),
        requires_logo: /logo\s+(required|must)|must\s+include\s+logo/i.test(text),
        requires_cta: /\bCTA\b|call to action|must\s+include\s+(cta|link)/i.test(text),
        unclear_instructions:
          merged || /TBD|see discord|unclear|contact manager/i.test(text),
        raw: {
          snippet: text.slice(0, 500),
          selector_hit: true,
          multiple_campaigns_in_card: merged,
          rates_seen: merged ? distinctRates(text) : undefined,
        },
      });
    } catch (err) {
      console.warn("ClipOps scan card error", err);
    }
  });

  if (
    !campaigns.length &&
    /campaign|reward|brief/i.test(document.title + document.body.innerText.slice(0, 200))
  ) {
    const bodyText = document.body.innerText.slice(0, 4000);
    campaigns.push({
      external_id: `page-${location.pathname}`,
      external_url: location.href,
      name: document.title || "Current page campaign",
      brief_text: bodyText,
      required_hashtags: Array.from(bodyText.matchAll(/#[A-Za-z0-9_]+/g))
        .slice(0, 20)
        .map((m) => m[0]),
      raw: { source: "page_fallback" },
    });
  }

  return campaigns;
}
