const OWNER = "47tsai";
const REPO = "free-game";
const BRANCH = "main";
const GAMES_PATH = "data/catalog/games.json";
const AUTH_ORIGIN = "https://auth.chi.qzz.io";
const ALLOWED_ORIGIN = "https://fg.chi.qzz.io";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
      "Vary": "Origin",
    },
  });
}

function decodeContent(encoded) {
  const binary = atob(encoded.replace(/\n/g, ""));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function encodeContent(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

async function githubRequest(env, method = "GET", body) {
  const url = "https://api.github.com/repos/" + OWNER + "/" + REPO + "/contents/" + GAMES_PATH;
  const response = await fetch(url, {
    method,
    headers: {
      Accept: "application/vnd.github+json",
      ...(env.GITHUB_TOKEN ? { Authorization: "Bearer " + env.GITHUB_TOKEN } : {}),
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "FreeGameWebsite",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) throw new Error("github_" + response.status);
  return response.json();
}

async function readGames(env) {
  try {
    const result = await githubRequest(env);
    return { document: JSON.parse(decodeContent(result.content)), sha: result.sha };
  } catch (error) {
    if (String(error.message) === "github_404") {
      return { document: { schema_version: 1, updated_at: new Date().toISOString(), records: [] }, sha: null };
    }
    throw error;
  }
}


async function readPublicGames() {
  const response = await fetch("https://raw.githubusercontent.com/" + OWNER + "/" + REPO + "/" + BRANCH + "/" + GAMES_PATH, {
    headers: { "Cache-Control": "no-cache", "User-Agent": "FreeGameWebsite" },
  });
  if (response.status === 404) return { schema_version: 1, updated_at: new Date().toISOString(), records: [] };
  if (!response.ok) throw new Error("public_games_" + response.status);
  return response.json();
}

async function writeGames(env, document, sha) {
  const body = {
    message: "Update game claim status from fg.chi.qzz.io",
    content: encodeContent(JSON.stringify(document, null, 2) + "\n"),
    branch: BRANCH,
    ...(sha ? { sha } : {}),
  };
  return githubRequest(env, "PUT", body);
}

async function requireOwner(request, env) {
  const authorization = request.headers.get("Authorization") || "";
  if (!/^Bearer [A-Za-z0-9_-]{40,80}$/.test(authorization)) return false;
  const response = await fetch(AUTH_ORIGIN + "/api/userinfo?client_id=" + encodeURIComponent(env.CHI_AUTH_CLIENT_ID), {
    headers: { Authorization: authorization, Origin: ALLOWED_ORIGIN },
  });
  if (!response.ok) return false;
  const user = await response.json();
  return user.sub === "chi-owner" && user.aud === env.CHI_AUTH_CLIENT_ID;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");
    if (origin && origin !== ALLOWED_ORIGIN) return json({ error: "origin_not_allowed" }, 403);
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Authorization, Content-Type",
          "Access-Control-Max-Age": "600",
        },
      });
    }
    if (request.method === "GET" && url.pathname === "/api/config") {
      return json({ auth_client_id: env.CHI_AUTH_CLIENT_ID || null, claim_enabled: Boolean(env.GITHUB_TOKEN) });
    }
    if (request.method === "GET" && url.pathname === "/api/games") {
      try {
        const document = await readPublicGames();
        const games = Array.isArray(document.records) ? document.records : [];
        games.sort((a, b) => String(b.added_at || b.created_at).localeCompare(String(a.added_at || a.created_at)));
        return json({ games: games });
      } catch {
        return json({ error: "games_unavailable" }, 502);
      }
    }
    const match = url.pathname.match(/^\/api\/games\/([^/]+)\/claim$/);
    if (request.method === "POST" && match) {
      if (!(await requireOwner(request, env))) return json({ error: "authentication_required" }, 401);
      if (!env.GITHUB_TOKEN) return json({ error: "github_token_not_configured" }, 503);
      const gameId = decodeURIComponent(match[1]);
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const result = await readGames(env);
          const game = result.document.records.find((item) => item.id === gameId);
          if (!game) return json({ error: "game_not_found" }, 404);
          if (game.claim_status !== "claimed") {
            const now = new Date().toISOString();
            game.claim_status = "claimed";
            game.claimed_at = now;
            game.claim_source = "manual";
            game.claim_notification_pending = true;
            game.updated_at = now;
            result.document.updated_at = now;
            await writeGames(env, result.document, result.sha);
          }
          return json({ ok: true, game: game });
        } catch (error) {
          if (attempt === 0 && String(error.message).includes("github_409")) continue;
          const reason = String(error?.message || "");
          if (reason === "github_401" || reason === "github_403") return json({ error: "github_write_forbidden" }, 503);
          if (reason === "github_409") return json({ error: "github_write_conflict" }, 409);
          return json({ error: "claim_update_failed" }, 502);
        }
      }
      return json({ error: "claim_update_conflict" }, 409);
    }
    return json({ error: "not_found" }, 404);
  },
};
