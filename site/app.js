// Free Game 網站 — 單頁應用（原生 JS，無建置）
// 資料來源：同站 Worker（/api）；登入：Chi Auth（PKCE）；樣式：chi-system + fg.css。
//
// 相對舊版的三處邏輯修正：
//  1. ?game= 聚焦只在初次渲染執行一次（舊版每次渲染都會捲回該卡片）。
//  2. /api/config 讀不到不再擋清單：只關標記功能，遊戲照常顯示。
//  3. 登入 token 存 sessionStorage（分頁內有效、關分頁清除），重新整理不再掉登入；
//     登入回來後多一次 render，標記按鈕文字才會從「登入並標記已領取」更新過來。
// 其餘：請求加 15 秒逾時；載入／空／錯誤狀態改用 chi-system 的 .chi-state；
// 錯誤狀態附「再試一次」按鈕；頁尾版本由 version.json（CI 產生）填入。
"use strict";

const API = "/api";
const AUTH = "https://auth.chi.qzz.io";
const FETCH_TIMEOUT_MS = 15000;
const TOKEN_KEY = "fg_access_token";
const TOKEN_EXPIRY_KEY = "fg_access_token_expires_at";
const PENDING_CLAIM_KEY = "fg_pending_claim";
const PKCE_VERIFIER_KEY = "fg_pkce_verifier";
const OAUTH_STATE_KEY = "fg_oauth_state";

const state = {
  games: [],
  page: 1,
  viewMode: "grid",
  accessToken: null,
  accessTokenExpiresAt: 0,
  claimEnabled: false,
  configOk: false,
  authClientId: null,
  didFocusGame: false,
};

// ---------- 小工具 ----------

function $(id) {
  return document.getElementById(id);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name, className) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "chi-system/icons.svg#" + name);
  svg.append(use);
  return svg;
}

function say(message) {
  $("notice").textContent = message || "";
}

function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/g, "");
}

async function digest(value) {
  return b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

function safeLink(url) {
  return typeof url === "string" && /^https:\/\//.test(url) ? url : null;
}

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs || FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    if (!response.ok) {
      throw new Error((data && data.error) || `請求失敗（${response.status}）`);
    }
    if (data === null) throw new Error("回應格式不正確");
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("請求逾時，請再試一次。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

// ---------- 登入（Chi Auth，PKCE） ----------

function saveToken(token, expiresInSeconds) {
  state.accessToken = token;
  state.accessTokenExpiresAt = Date.now() + Number(expiresInSeconds || 600) * 1000;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(TOKEN_EXPIRY_KEY, String(state.accessTokenExpiresAt));
  } catch {
    // sessionStorage 不可用時只留記憶體，重新整理需重登
  }
}

function clearToken() {
  state.accessToken = null;
  state.accessTokenExpiresAt = 0;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_EXPIRY_KEY);
  } catch {
    // 忽略
  }
}

function restoreToken() {
  try {
    const token = sessionStorage.getItem(TOKEN_KEY);
    const expiresAt = Number(sessionStorage.getItem(TOKEN_EXPIRY_KEY) || 0);
    if (token && expiresAt > Date.now()) {
      state.accessToken = token;
      state.accessTokenExpiresAt = expiresAt;
      return true;
    }
  } catch {
    // 忽略
  }
  clearToken();
  return false;
}

function readPendingClaim() {
  try {
    const pendingId = sessionStorage.getItem(PENDING_CLAIM_KEY);
    if (pendingId) sessionStorage.removeItem(PENDING_CLAIM_KEY);
    return pendingId;
  } catch {
    return null;
  }
}

async function login() {
  if (!state.authClientId) {
    say("Chi Auth 尚未完成應用設定。");
    return;
  }
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(48)));
  const oauthState = b64url(crypto.getRandomValues(new Uint8Array(24)));
  try {
    sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
    sessionStorage.setItem(OAUTH_STATE_KEY, oauthState);
  } catch {
    say("瀏覽器不允許儲存登入狀態，請檢查設定後再試。");
    return;
  }
  const params = new URLSearchParams({
    response_type: "code",
    client_id: state.authClientId,
    redirect_uri: location.origin + "/",
    code_challenge: await digest(verifier),
    code_challenge_method: "S256",
    state: oauthState,
  });
  location.href = AUTH + "/api/authorize?" + params.toString();
}

async function finishLogin() {
  const params = new URLSearchParams(location.search);
  const code = params.get("code");
  if (!code || !state.authClientId) return;
  const oauthState = params.get("state");
  let verifier = null;
  let expectedState = null;
  try {
    verifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
    expectedState = sessionStorage.getItem(OAUTH_STATE_KEY);
    sessionStorage.removeItem(PKCE_VERIFIER_KEY);
    sessionStorage.removeItem(OAUTH_STATE_KEY);
  } catch {
    // 忽略
  }
  if (!oauthState || oauthState !== expectedState || !verifier) {
    say("登入驗證失敗，請重新登入。");
    return;
  }
  try {
    const data = await fetchJson(
      AUTH + "/api/token?client_id=" + encodeURIComponent(state.authClientId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: state.authClientId,
          code,
          redirect_uri: location.origin + "/",
          code_verifier: verifier,
        }),
      }
    );
    saveToken(data.access_token, data.expires_in);
    history.replaceState({}, "", location.pathname + location.hash);
    $("login").textContent = "已登入 Chi Auth";
    say("登入成功，可以手動標記領取狀態。");
  } catch (error) {
    say(error.message);
  }
}

// ---------- 資料載入 ----------

async function loadConfig() {
  try {
    const config = await fetchJson(API + "/config");
    state.authClientId = config.auth_client_id;
    state.claimEnabled = Boolean(config.claim_enabled);
    state.configOk = true;
    if (!state.authClientId) {
      $("login").disabled = true;
      $("login").textContent = "Chi Auth 尚未設定";
    }
  } catch {
    // 設定讀不到不擋清單：只關標記功能，讓使用者至少能看遊戲
    state.claimEnabled = false;
    state.configOk = false;
    $("login").disabled = true;
    say("網站設定讀取失敗，標記功能暫停，遊戲清單仍可瀏覽。");
  }
}

async function loadGames() {
  const gamesEl = $("games");
  gamesEl.replaceChildren(renderState("loading"));
  $("summary").textContent = "正在讀取遊戲資料…";
  try {
    const result = await fetchJson(API + "/games");
    if (!result.games) throw new Error("無法讀取遊戲資料");
    state.games = result.games;
    populatePlatforms();
    render();
  } catch (error) {
    $("summary").textContent = "目前無法載入資料";
    gamesEl.replaceChildren(renderState("error", error.message));
    say(error.message);
  }
}

async function loadVersion() {
  try {
    const data = await fetchJson("version.json", { timeoutMs: 5000 });
    if (data && data.version) {
      $("fg-version").textContent = "版本 v" + data.version;
    }
  } catch {
    // 版本顯示非關鍵，失敗就留預設文字
  }
}

// ---------- 篩選與渲染 ----------

function filteredGames() {
  const keyword = $("search").value.trim().toLowerCase();
  const status = document.querySelector("#status-filter .fg-chip.is-active")?.dataset.status || "all";
  const platform = document.querySelector("#platform-filter .fg-chip.is-active")?.dataset.platform || "all";
  return state.games.filter((game) => {
    if (keyword && !String(game.title || "").toLowerCase().includes(keyword)) return false;
    if (status === "claimed" && !game.claimed) return false;
    if (status === "unclaimed" && game.claimed) return false;
    if (platform !== "all" && game.platform !== platform) return false;
    return true;
  });
}

function claimBadge(game) {
  const badge = element("span", "chi-badge " + (game.claimed ? "chi-badge--success" : "chi-badge--warning"));
  badge.append(element("span", "chi-badge__dot"));
  badge.append(document.createTextNode(game.claimed ? "已領取" : "尚未領取"));
  return badge;
}

function buildCard(game) {
  const card = element("article", "game-card");
  card.id = "game-" + game.id;

  const coverLink = safeLink(game.store_url) || safeLink(game.article_url);
  if (game.cover_url && coverLink) {
    const media = element("a", "game-card__media");
    media.href = coverLink;
    media.target = "_blank";
    media.rel = "noopener";
    media.setAttribute("aria-label", `前往 ${game.title}`);
    const cover = element("img", "game-card__cover");
    cover.src = game.cover_url;
    cover.alt = "";
    cover.loading = "lazy";
    media.append(cover);
    card.append(media);
  } else {
    card.append(element("div", "game-card__media"));
  }

  const content = element("div", "game-card__content");

  const topline = element("div", "game-card__topline");
  topline.append(element("span", "game-card__platform", String(game.platform || "").toUpperCase()));
  topline.append(claimBadge(game));
  content.append(topline);

  content.append(element("h3", "game-card__title", game.title));

  const addedDate = game.added_at ? new Date(game.added_at).toLocaleDateString("zh-TW") : "";
  const offerEnd = game.offer_end_at
    ? new Date(game.offer_end_at).toLocaleString("zh-TW", {
        timeZone: "Asia/Taipei",
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "";
  const dateText = offerEnd
    ? addedDate
      ? `新增 ${addedDate} · 免費截止 ${offerEnd}`
      : `免費截止 ${offerEnd}`
    : addedDate
      ? `新增 ${addedDate}`
      : "";
  if (dateText) content.append(element("p", "game-card__date", dateText));

  const actions = element("div", "game-card__actions");
  const storeLink = safeLink(game.store_url);
  if (storeLink) {
    const link = element("a", "chi-btn chi-btn--secondary game-card__link", "前往商店");
    link.href = storeLink;
    link.target = "_blank";
    link.rel = "noopener";
    actions.append(link);
  }
  const articleLink = safeLink(game.article_url);
  if (articleLink) {
    const link = element("a", "chi-btn chi-btn--secondary game-card__link", "查看介紹");
    link.href = articleLink;
    link.target = "_blank";
    link.rel = "noopener";
    actions.append(link);
  }
  content.append(actions);

  if (game.claimed) {
    const note = game.claim_source === "fgc" ? "FGC 自動同步：已領取" : "已手動標記領取";
    content.append(element("p", "game-card__claim-note", note));
  } else {
    const claimButton = element(
      "button",
      "chi-btn chi-btn--primary game-card__claim",
      state.claimEnabled ? (state.accessToken ? "標記已領取" : "登入並標記已領取") : "標記已領取"
    );
    claimButton.type = "button";
    claimButton.disabled = !state.claimEnabled;
    claimButton.addEventListener("click", () => markClaimed(game, claimButton));
    content.append(claimButton);
  }

  card.append(content);
  return card;
}

function renderPagination(totalPages) {
  const nav = $("pagination");
  nav.replaceChildren();
  if (totalPages <= 1) return;
  const add = (label, target, disabled = false, active = false) => {
    const button = element("button", "chi-btn chi-btn--secondary" + (active ? " is-active" : ""), label);
    button.type = "button";
    button.disabled = disabled;
    button.setAttribute(
      "aria-label",
      label === "‹" ? "上一頁" : label === "›" ? "下一頁" : "第 " + label + " 頁"
    );
    if (active) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => {
      state.page = target;
      render();
    });
    nav.append(button);
  };
  add("‹", state.page - 1, state.page === 1);
  let start = Math.max(1, Math.min(state.page - 2, totalPages - 4));
  let end = Math.min(totalPages, start + 4);
  if (start > 1) {
    add("1", 1, false, state.page === 1);
    if (start > 2) nav.append(element("span", "fg-pagination__info", "…"));
  }
  for (let page = start; page <= end; page++) add(String(page), page, false, page === state.page);
  if (end < totalPages) {
    if (end < totalPages - 1) nav.append(element("span", "fg-pagination__info", "…"));
    add(String(totalPages), totalPages, false, state.page === totalPages);
  }
  add("›", state.page + 1, state.page === totalPages);
}

function renderState(kind, message) {
  const wrap = element("div", "chi-state");
  if (kind === "loading") {
    const spinner = element("div", "chi-spinner");
    spinner.setAttribute("role", "status");
    spinner.setAttribute("aria-label", "載入中");
    spinner.style.margin = "0 auto 16px";
    wrap.append(spinner);
    wrap.append(element("h3", "chi-state__title", "載入中"));
    wrap.append(element("p", "chi-state__desc", "正在取得資料，請稍候。"));
  } else if (kind === "empty") {
    wrap.append(icon("inbox", "chi-state__icon"));
    wrap.append(element("h3", "chi-state__title", "沒有符合條件的遊戲"));
    wrap.append(element("p", "chi-state__desc", message || "調整篩選條件，或等新遊戲上架。"));
  } else if (kind === "error") {
    wrap.append(icon("circle-x", "chi-state__icon"));
    wrap.append(element("h3", "chi-state__title", "載入失敗"));
    wrap.append(element("p", "chi-state__desc", message || "網路發生問題，請檢查連線後再試一次。"));
    const action = element("div", "chi-state__action");
    const retry = element("button", "chi-btn chi-btn--secondary", "再試一次");
    retry.type = "button";
    retry.dataset.fgRetry = "";
    action.append(retry);
    wrap.append(action);
  }
  return wrap;
}

function focusGameOnce() {
  if (state.didFocusGame) return;
  state.didFocusGame = true;
  const focusId = new URLSearchParams(location.search).get("game");
  if (!focusId) return;
  const target = document.getElementById("game-" + focusId);
  if (!target) return;
  target.classList.add("focused");
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

function render() {
  const filtered = filteredGames();
  const pageSizeValue = $("page-size").value;
  const size = pageSizeValue === "all" ? filtered.length : Number(pageSizeValue);
  const totalPages = Math.max(1, Math.ceil(filtered.length / size));
  state.page = Math.min(state.page, totalPages);
  const pageGames = filtered.slice((state.page - 1) * size, state.page * size);
  $("summary").textContent = `共 ${filtered.length} 筆遊戲`;
  const gamesEl = $("games");
  gamesEl.replaceChildren();
  gamesEl.className = state.viewMode === "list" ? "fg-list" : "fg-grid";
  if (!pageGames.length) {
    gamesEl.append(renderState("empty", filtered.length ? "沒有符合條件的遊戲。" : "目前還沒有遊戲資料。"));
  } else {
    pageGames.forEach((game) => gamesEl.append(buildCard(game)));
  }
  renderPagination(totalPages);
  focusGameOnce();
}

function populatePlatforms() {
  const platforms = [...new Set(state.games.map((game) => game.platform).filter(Boolean))].sort();
  const group = $("platform-filter");
  group.querySelectorAll("[data-platform]:not([data-platform='all'])").forEach((chip) => chip.remove());
  platforms.forEach((platform) => {
    const chip = element("button", "fg-chip", platform);
    chip.type = "button";
    chip.dataset.platform = platform;
    chip.setAttribute("aria-pressed", "false");
    group.append(chip);
  });
}

function setView(mode) {
  state.viewMode = mode;
  $("view-grid").classList.toggle("is-active", mode === "grid");
  $("view-grid").setAttribute("aria-pressed", String(mode === "grid"));
  $("view-list").classList.toggle("is-active", mode === "list");
  $("view-list").setAttribute("aria-pressed", String(mode === "list"));
  render();
}

function setupControls() {
  $("search").addEventListener("input", () => {
    state.page = 1;
    render();
  });
  $("page-size").addEventListener("change", () => {
    state.page = 1;
    render();
  });
  const bindChips = (groupId) => {
    $(groupId).addEventListener("click", (event) => {
      const chip = event.target.closest("button");
      if (!chip) return;
      $(groupId).querySelectorAll("button").forEach((button) => {
        button.classList.remove("is-active");
        button.setAttribute("aria-pressed", "false");
      });
      chip.classList.add("is-active");
      chip.setAttribute("aria-pressed", "true");
      state.page = 1;
      render();
    });
  };
  bindChips("status-filter");
  bindChips("platform-filter");
  $("view-grid").addEventListener("click", () => setView("grid"));
  $("view-list").addEventListener("click", () => setView("list"));
  $("login").addEventListener("click", login);
  $("games").addEventListener("click", (event) => {
    if (event.target.closest("[data-fg-retry]")) {
      state.page = 1;
      loadGames();
    }
  });
}

// ---------- 手動標記領取 ----------

async function markClaimed(game, button) {
  if (!state.claimEnabled) {
    say("目前尚未設定 GitHub 寫入權限。");
    return;
  }
  if (!state.accessToken || Date.now() >= state.accessTokenExpiresAt) {
    clearToken();
    try {
      sessionStorage.setItem(PENDING_CLAIM_KEY, game.id);
    } catch {
      // 忽略
    }
    login();
    return;
  }
  try {
    if (button) {
      button.disabled = true;
      button.textContent = "標記中…";
    }
    const data = await fetchJson(API + "/games/" + encodeURIComponent(game.id) + "/claim", {
      method: "POST",
      headers: {
        Authorization: "Bearer " + state.accessToken,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    game.claimed = true;
    game.claimed_at = data.claimed_at;
    game.claim_source = data.claim_source;
    say("已標記為領取。");
    render();
  } catch (error) {
    say(error.message);
    render();
  }
}

// ---------- 啟動 ----------

async function init() {
  setupControls();
  if (restoreToken()) {
    $("login").textContent = "已登入 Chi Auth";
  }
  loadVersion();
  await loadConfig();
  await loadGames();
  await finishLogin();
  if (state.accessToken) {
    render();
    const pendingId = readPendingClaim();
    if (pendingId) {
      const game = state.games.find((item) => item.id === pendingId);
      if (game) await markClaimed(game, null);
    }
  }
  if (state.configOk && !state.claimEnabled) {
    say("目前尚未設定 GitHub 寫入權限，手動標記暫時不可用。");
  }
}

init();
