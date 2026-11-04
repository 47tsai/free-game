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

The static website is in `site/` and is deployed to GitHub Pages at `https://fg.chi.qzz.io`. The API Worker is in `worker/index.js` and handles reads and authenticated manual claim updates through GitHub's Contents API.

The website uses Chi Auth Authorization Code + PKCE. The API Worker checks the short-lived Chi Auth bearer token against `https://auth.chi.qzz.io/api/userinfo` and accepts only the owner subject before updating GitHub JSON. The GitHub token remains in a Cloudflare Worker secret and is never sent to the browser.

Before enabling manual marking:

1. In Chi Auth, register an application named **Free Game**.
2. Set its exact redirect URI to `https://fg.chi.qzz.io/` and allowed origin to `https://fg.chi.qzz.io`.
3. Add these GitHub repository Actions secrets:
   - `CLOUDFLARE_ACCOUNT_ID`
   - `CLOUDFLARE_API_TOKEN`
   - `FREE_GAME_GITHUB_TOKEN` (Contents read/write access to this repository)
   - `CHI_AUTH_CLIENT_ID` (the Client ID issued by Chi Auth)
4. In repository Settings → Pages, select **GitHub Actions** as the build and deployment source. Then run the **Free Game Website** workflow once from the Actions tab.\n5. After the four Worker secrets are configured, pushes affecting `worker/` or `wrangler.toml` deploy the API Worker automatically.

The Discord workflow requires the `DISCORD_WEBHOOK_URL` repository Actions secret.

## Development

Requires Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
free-game ingest --config config/sources.json
free-game fgc-sync
```
