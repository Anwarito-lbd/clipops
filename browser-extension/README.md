# ClipOps Browser Extension (Operator Mode)

Assists your **already logged-in** Content Rewards browser session.

## Install (Chrome / Edge)

1. Start ClipOps API (`http://127.0.0.1:8000`)
2. Open `chrome://extensions` → Enable Developer mode
3. **Load unpacked** → select this `browser-extension` folder
4. Open extension **Options** → Login & save token
5. Open Content Rewards while logged in → use the popup:
   - Scan campaigns → ClipOps
   - Extract brief + assets
   - Highlight Submit / Cash-out

## What it never does

- Auto-click Join, Submit, or Cash-out
- Post to TikTok
- Bypass CAPTCHA
- Run unattended Playwright against Content Rewards

Those final clicks stay yours. An unattended bot should only be considered if Content Rewards gives **written permission**.
