# Deploy Study Harness

The app is one container: the API and the web screen together. It keeps everything (users, chats, memory, credits,
files) in one SQLite file on a **persistent disk**, so pick a host that gives you a disk or volume.

## Before you start (5 minutes)
1. **Rotate your OpenRouter key** (create a new one at openrouter.ai/keys and delete the one pasted in chat). Set a spend limit on it.
2. Choose an admin email and a long admin password.
3. Decide `UNLOCK_ALL`: use **`admin`** on a public site (only your admin login gets every feature).
   **`1` would give every visitor 100,000 free credits on your key.**

## Option A: Render (easiest)
1. Push this repo to GitHub (it is already there).
2. render.com > **New > Blueprint** > pick the repo. It reads `render.yaml`.
3. When asked, fill in `OPENROUTER_API_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`. Everything else is preset (disk, health check, secret).
4. Open the URL Render gives you. Admin console: `/admin.html`.
Cost: the smallest paid instance (a disk needs one).

## Option B: any server with Docker (VPS, Fly.io machine, home server)
```
cp .env.example .env          # fill in OPENROUTER_API_KEY, ADMIN_EMAIL, ADMIN_PASSWORD; set UNLOCK_ALL=admin, DEV_MODE=0
docker compose up -d --build  # serves on port 8000; data in the "study-data" volume
```
Put it behind HTTPS (Caddy, nginx, or your host's proxy). The container already trusts the proxy's headers, so secure cookies work.

## Other hosts (Railway, Fly.io, Koyeb)
Use the `Dockerfile`. Mount a volume at `/data`, set the same environment variables, health check path `/healthz`,
and run **one** instance (SQLite cannot be shared by several copies).

## Environment variables
| Name | Value |
| --- | --- |
| `OPENROUTER_API_KEY` | your key (secret) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | the admin login (created at start; remove the password afterwards if you like) |
| `UNLOCK_ALL` | `admin` on a public site |
| `DEV_MODE` | `0` (never 1 on a public site: it lets anyone act as any user) |
| `PAYMENT_PROVIDER` | `manual` (orders wait for you to mark them paid in the admin console) |
| `APP_SECRET` | long random text (Render generates it) |
| `BRAIN_POLICY` | `cheap` for low cost, `preferred` for the plan's stronger tiers |

## After it is live
- Sign in at `/admin.html`. Check the **Models** tab, press **Sync prices**, and approve the models you want users to see.
- Open **Plans** and set your real prices, credits and benefits.
- **Back up** the database: `docker compose exec app python scripts/backup.py /data/backup.db` (copy the file off the server).
  On Render, use the disk snapshots.
- Updates: push to GitHub; Render redeploys. With Docker: `git pull && docker compose up -d --build`. Data stays on the volume.

## Known limits (be honest with yourself before real customers)
- No payment processor: money is confirmed by hand. Stripe or Toss needs your account and keys.
- One server instance only (SQLite). Fine for hundreds of users, not for thousands.
- No email: there is no "forgot password" email yet (the admin can reset a password with `scripts/create_admin.py`).
