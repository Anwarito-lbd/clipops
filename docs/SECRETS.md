# ClipOps secrets

## Rotate (local or prod)

```powershell
cd clipops
.\apps\api\.venv\Scripts\python.exe scripts\rotate_secrets.py --print-password
# For deploy:
.\apps\api\.venv\Scripts\python.exe scripts\rotate_secrets.py --production --print-password
```

This writes to `.env` (gitignored):

- `JWT_SECRET` — random 48-byte URL-safe string  
- `OPERATOR_PASSWORD_HASH` — bcrypt  
- clears `OPERATOR_PASSWORD`  
- sets `CLIPOPS_ENV` (`development` or `production`)

Save the printed password once. Login with `OPERATOR_EMAIL` + that password.

## Production boot gate

With `CLIPOPS_ENV=production`, the API **refuses to start** if:

- `JWT_SECRET` is missing, short, or a known default  
- `OPERATOR_PASSWORD_HASH` is empty  
- plaintext password is still `changeme` / `password` / `admin`

`/health` reports `security_ok`, `security_messages`, and media stack (torch/cuda/whisperx).
