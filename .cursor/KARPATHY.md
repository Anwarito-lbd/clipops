# Karpathy guidelines — global + project

Upstream: https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CURSOR.md

## Always-on across ALL Cursor projects (recommended)

1. **User Rules (true always-on):** Cursor → **Customize → Rules → User Rules**  
   Paste `~/.cursor/karpathy-user-rules.md` (from the installer).
2. **Global skill:** `~/.cursor/skills/karpathy-guidelines` (+ `~/.agents/skills/...`)  
   `npx skills add multica-ai/andrej-karpathy-skills -g -y -a cursor`
3. **Local plugin:** `~/.cursor/plugins/local/andrej-karpathy-skills/`  
   Re-run: `./scripts/install_karpathy_guidelines_global.sh` then **Developer: Reload Window**

Project copy (this repo): `.cursor/rules/karpathy-guidelines.mdc` (`alwaysApply: true`).
