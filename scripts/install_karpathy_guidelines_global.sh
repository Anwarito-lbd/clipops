#!/usr/bin/env bash
# Install Karpathy guidelines globally for Cursor (all projects), not just this repo.
# https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CURSOR.md
set -euo pipefail
exec "${HOME}/.cursor/install-karpathy-guidelines.sh" 2>/dev/null || {
  curl -fsSL https://raw.githubusercontent.com/multica-ai/andrej-karpathy-skills/main/skills/karpathy-guidelines/SKILL.md >/dev/null
  bash -c "$(cat <<'INNER'
set -euo pipefail
npx --yes skills@latest add multica-ai/andrej-karpathy-skills -g -y -a cursor || true
PLUGIN_ROOT="${HOME}/.cursor/plugins/local/andrej-karpathy-skills"
mkdir -p "${PLUGIN_ROOT}/.cursor-plugin" "${PLUGIN_ROOT}/rules" "${PLUGIN_ROOT}/skills/karpathy-guidelines" \
  "${HOME}/.cursor/rules" "${HOME}/.cursor/skills/karpathy-guidelines" "${HOME}/.agents/skills/karpathy-guidelines"
curl -fsSL https://raw.githubusercontent.com/multica-ai/andrej-karpathy-skills/main/.cursor/rules/karpathy-guidelines.mdc \
  -o "${PLUGIN_ROOT}/rules/karpathy-guidelines.mdc"
curl -fsSL https://raw.githubusercontent.com/multica-ai/andrej-karpathy-skills/main/skills/karpathy-guidelines/SKILL.md \
  -o "${PLUGIN_ROOT}/skills/karpathy-guidelines/SKILL.md"
cp "${PLUGIN_ROOT}/rules/karpathy-guidelines.mdc" "${HOME}/.cursor/rules/karpathy-guidelines.mdc"
cp "${PLUGIN_ROOT}/skills/karpathy-guidelines/SKILL.md" "${HOME}/.cursor/skills/karpathy-guidelines/SKILL.md"
cp "${PLUGIN_ROOT}/skills/karpathy-guidelines/SKILL.md" "${HOME}/.agents/skills/karpathy-guidelines/SKILL.md"
cat > "${PLUGIN_ROOT}/.cursor-plugin/plugin.json" <<'JSON'
{
  "name": "andrej-karpathy-skills",
  "displayName": "Karpathy Guidelines",
  "description": "Always-on Karpathy behavioral guidelines.",
  "version": "1.0.0",
  "license": "MIT",
  "homepage": "https://github.com/multica-ai/andrej-karpathy-skills",
  "rules": "rules",
  "skills": "skills"
}
JSON
# User Rules paste file (true always-on)
python3 - <<'PY'
from pathlib import Path
mdc = Path.home().joinpath(".cursor/rules/karpathy-guidelines.mdc").read_text()
body = mdc.split("---", 2)[2].lstrip("\n") if mdc.startswith("---") else mdc
Path.home().joinpath(".cursor/karpathy-user-rules.md").write_text(
    "# Paste into Cursor → Customize → Rules → User Rules\n"
    "# Source: https://github.com/multica-ai/andrej-karpathy-skills\n\n" + body
)
print("Wrote ~/.cursor/karpathy-user-rules.md")
PY
echo
echo "Global install done."
echo "REQUIRED for always-on in EVERY chat:"
echo "  Cursor → Customize → Rules → User Rules → paste ~/.cursor/karpathy-user-rules.md"
echo "Then: Developer: Reload Window"
INNER
)"
}
