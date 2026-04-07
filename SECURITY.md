# Security Guide

This repository is **public**. Never commit real API keys, tokens, passwords, or OAuth credentials.

---

## Required Environment Variables

Copy `.env.example` to `.env` and fill in your real values:

```bash
cp .env.example .env
# edit .env with your actual keys
```

| Variable | Purpose | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Script generation (Claude) | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | TTS audio generation | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `YOUTUBE_CLIENT_ID` | YouTube upload OAuth2 | [Google Cloud Console](https://console.cloud.google.com/) |
| `YOUTUBE_CLIENT_SECRET` | YouTube upload OAuth2 | [Google Cloud Console](https://console.cloud.google.com/) |
| `YOUTUBE_REFRESH_TOKEN` | YouTube upload OAuth2 | Generated via OAuth2 flow (see below) |
| `ANTHROPIC_MODEL` | *(optional)* Override default model | — |

---

## Setting Up YouTube OAuth2

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Enable the **YouTube Data API v3** under *APIs & Services → Library*.
3. Create **OAuth 2.0 credentials** under *APIs & Services → Credentials*:
   - Application type: **Desktop app**
   - Download the `client_secret_*.json` file.
4. Run the OAuth2 authorization flow (the pipeline will prompt you on first run, or use a standalone script).
5. A `token.json` file is generated locally — this is your refresh token store.
6. Set `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` in `.env`.

> **Reference:** [Google OAuth2 for Installed Apps](https://developers.google.com/identity/protocols/oauth2/native-app)

---

## ⚠️ What Must NOT Be Committed

The following are listed in `.gitignore` and must **never** appear in git:

| Pattern | Reason |
|---|---|
| `.env` / `.env.*` (except `.env.example`) | Contains real secrets |
| `token.json` | OAuth2 token with account access |
| `client_secret*.json` | OAuth2 client credentials |
| `credentials/` | Any credential directory |
| `*.mp3` / `*.mp4` | Generated media, too large for git |
| `episodes/` | Generated episode output |

---

## Running the Security Audit Locally

```bash
bash scripts/security-audit.sh
```

This checks for stray `.env` files, staged media, hardcoded secret patterns, and missing `.gitignore` entries.

---

## Rotating Compromised Keys

If a secret is accidentally committed:

1. **Revoke immediately** — don't wait:
   - Anthropic: [console.anthropic.com](https://console.anthropic.com/) → API Keys → Revoke
   - OpenAI: [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → Revoke
   - Google/YouTube: [console.cloud.google.com](https://console.cloud.google.com/) → Credentials → Delete & recreate
2. **Remove from git history** using `git filter-repo` or BFG Repo-Cleaner:
   ```bash
   # Install: pip install git-filter-repo
   git filter-repo --path-glob '*.env' --invert-paths
   git push --force
   ```
3. **Update your `.env`** with newly generated keys.
4. **Notify** anyone who may have forked or cloned the repo while the secret was exposed.

> **Reference:** [GitHub docs — Removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

---

## Reporting a Security Issue

If you discover a security vulnerability in this project, please open a GitHub Issue or contact the maintainer directly. Do not post actual secret values publicly.
