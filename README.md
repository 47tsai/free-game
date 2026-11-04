# Free Game

A 4Gamers RSS collector with FGC claim-state synchronization, Discord notifications, and a small claim-status website.

## Automated schedule

- **4Gamers (UTC+8):** 00:00, 06:00, 12:00, 18:00. Reads the RSS feed, filters free-game articles, extracts the game title, storefront URL, article URL, and Open Graph cover image, then stores the game.
- **FGC (UTC+9):** 00:00, 06:00, 12:00, 18:00. Reads recent messages from `https://ntfy.sh/47tsai-fgc` and applies every `claimed` item to the same game record.

GitHub Actions cron is UTC internally. The workflow files convert the two local schedules to UTC.

## Game state and notifications

Each game is stored in `data/catalog/games.json`. The record includes its title, image, platform, store URL, 4Gamers article URL, discovery time, claim status, claim source, and reminder timestamp.

- A newly discovered game receives one full Discord embed with its image and buttons for the 4Gamers article, storefront, and website.
- If it is already claimed, the first embed displays that state.
- When an already-announced game becomes claimed by FGC or manual marking, the next scheduled run sends a short claimed notice.
- An unclaimed game is reminded every 24 hours from its discovery time until it is claimed.
- Notification records are stored in `data/operations/notifications.json` to prevent duplicate delivery.

4Gamers is trusted as the curated source for free-game information. No storefront promotion API verification is performed.

## Website and manual claim marking

The static website is in `site/` and is configured for GitHub Pages at `https://fg.chi.qzz.io`. The API Worker is in `worker/index.js` and handles reads and authenticated manual claim updates through GitHub's Contents API.

The website uses the existing Chi Auth Authorization Code + PKCE client (`MN7nps4p8bc9oFVHwR1TdZejZyaUmXLt`). The API Worker checks the short-lived Chi Auth bearer token against `https://auth.chi.qzz.io/api/userinfo` and accepts only the owner subject before updating GitHub JSON. The Client ID is public configuration in `wrangler.toml`; it is not a secret. The GitHub token remains in a Cloudflare Worker secret and is never sent to the browser.

### Required configuration

**GitHub repository Actions secrets:**

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `DISCORD_WEBHOOK_URL`

**Cloudflare Worker secret:**

- `GITHUB_TOKEN`: the fine-grained GitHub token with Contents read/write access, restricted to `47tsai/free-game`.

Set `GITHUB_TOKEN` in the Cloudflare dashboard under Workers & Pages → `free-game-api` → Settings → Variables and Secrets. Do not add this token to the repository, source code, or browser configuration.

The existing Chi Auth client redirect URI must include `https://fg.chi.qzz.io/`.

In repository Settings → Pages, select **GitHub Actions** as the build and deployment source. Run the **Free Game Website** workflow once from the Actions tab if the site has not yet been deployed.

After the two Cloudflare Actions secrets are configured, pushes affecting `worker/` or `wrangler.toml` deploy the API Worker automatically. The deploy workflow does not overwrite Worker secrets.

## Development

Requires Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
free-game ingest
free-game fgc-sync
```
