# Official OAuth posting (TikTok + YouTube)

Unofficial cookie/upload bots are out of scope. Use platform OAuth only.

## Status

`GET /api/oauth/status` — shows whether client IDs are configured and Authorize URLs.

## TikTok Content Posting API

1. Create an app at https://developers.tiktok.com/products/content-posting-api
2. Set in `.env`:
   - `TIKTOK_CLIENT_KEY`
   - `TIKTOK_CLIENT_SECRET`
   - `TIKTOK_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/tiktok/callback`
3. `GET /api/oauth/tiktok/start` → open `authorize_url`
4. App **audit** required for public Direct Post; sandbox posts are often SELF_ONLY until approved

## YouTube Data API

1. Google Cloud project → enable YouTube Data API v3 → OAuth client
2. Set `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REDIRECT_URI`
3. `GET /api/oauth/youtube/start` → authorize each of your 3 channels
4. Upload via `videos.insert` (wired in a follow-up once tokens are stored)

## Still manual on Content Rewards

Join / Submit / Cash-out stay human gates even after TikTok/YouTube OAuth upload.
