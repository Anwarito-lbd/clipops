#!/usr/bin/env python3
"""Generate / rotate ClipOps production secrets into .env (never commit the result)."""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def _upsert(env_text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(env_text):
        return pattern.sub(line, env_text)
    if env_text and not env_text.endswith("\n"):
        env_text += "\n"
    return env_text + line + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate ClipOps secrets")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env",
        help="Target .env path (default: repo .env)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Operator password to bcrypt-hash (random if omitted)",
    )
    parser.add_argument(
        "--email",
        default="operator@clipops.local",
        help="Operator email",
    )
    parser.add_argument(
        "--print-password",
        action="store_true",
        help="Print the plaintext password once (store it securely)",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Set CLIPOPS_ENV=production",
    )
    args = parser.parse_args()

    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    password = args.password or secrets.token_urlsafe(18)
    jwt_secret = secrets.token_urlsafe(48)
    password_hash = pwd_context.hash(password)

    env_path: Path = args.env_file
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    example = ROOT / ".env.example"
    if not text and example.exists():
        text = example.read_text(encoding="utf-8")

    text = _upsert(text, "OPERATOR_EMAIL", args.email)
    text = _upsert(text, "OPERATOR_PASSWORD_HASH", password_hash)
    # Clear plaintext password when hash is set
    text = _upsert(text, "OPERATOR_PASSWORD", "")
    text = _upsert(text, "JWT_SECRET", jwt_secret)
    if args.production:
        text = _upsert(text, "CLIPOPS_ENV", "production")
    else:
        text = _upsert(text, "CLIPOPS_ENV", "development")

    env_path.write_text(text, encoding="utf-8")
    print(f"Wrote secrets to {env_path}")
    print("OPERATOR_PASSWORD_HASH set; JWT_SECRET rotated.")
    if args.print_password:
        print(f"ONE-TIME PASSWORD (save now): {password}")
    else:
        print("Re-run with --print-password to display the generated password once.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
