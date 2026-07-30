# Affiliates (MoneyPrinterV2-inspired, ClipOps-safe)

Source ideas: [FujiwaraChoki/MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2)

## What we added

| Feature | In ClipOps |
|---------|------------|
| Amazon affiliate tag + product store | Yes — `/affiliates` + `AMAZON_AFFILIATE_TAG` |
| Bio text with affiliate link | Yes — paste into TikTok / YouTube / X bios |
| Affiliate pitch drafts | Yes — copy → you Post |
| CRON-like promote schedule | Yes — creates **PROMOTE NOW** notifications |
| X/Twitter account row | Yes — seeded `twitter_affiliate` |

## What we will NOT add (from MPV2)

| Feature | Why |
|---------|-----|
| Firefox Twitter browser bot | Violates X ToS; ban risk |
| Browser YouTube Shorts auto-upload | Use official YouTube OAuth stubs instead |
| Amazon scrape bot | Fragile + ToS risk; you paste product URLs |
| Local business scrape + cold email | Spam / CAN-SPAM / platform abuse |

## Workflow

1. Set `AMAZON_AFFILIATE_TAG=yourtag-20` in `.env`
2. Dashboard → **Affiliates** → add Amazon product URL
3. **Build bio** → copy into each account’s profile bio
4. **Draft pitch** → copy → Open X → you press Post
5. **Schedule + fire PROMOTE NOW** → Alerts remind you on a cadence

Optional cron (hourly): `POST /api/affiliates/schedules/run-due` (respects `times_per_day` cooldown). Dashboard button uses `?force=true` for an immediate reminder.

API: `GET /api/affiliates/status` lists implemented vs refused.
