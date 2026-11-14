// Free Game ç¶²ç«™ â€” å–®é æ‡‰ç”¨ï¼ˆåŸç”Ÿ JSï¼Œç„¡å»ºç½®ï¼‰
// è³‡æ–™ä¾†æºï¼šåŒç«™ Workerï¼ˆ/apiï¼‰ï¼›ç™»å…¥ï¼šChi Authï¼ˆPKCEï¼‰ï¼›æ¨£å¼ï¼šchi-system + fg.cssã€‚
//
// ç›¸å°èˆŠç‰ˆçš„ä¸‰è™•é‚è¼¯ä¿®æ­£ï¼š
//  1. ?game= èšç„¦åªåœ¨åˆæ¬¡æ¸²æŸ“åŸ·è¡Œä¸€æ¬¡ï¼ˆèˆŠç‰ˆæ¯æ¬¡æ¸²æŸ“éƒ½æœƒæ²å›è©²å¡ç‰‡ï¼‰ã€‚
//  2. /api/config è®€ä¸åˆ°ä¸å†æ“‹æ¸…å–®ï¼šåªé—œæ¨™è¨˜åŠŸèƒ½ï¼ŒéŠæˆ²ç…§å¸¸é¡¯ç¤ºã€‚
//  3. ç™»å…¥ token å­˜ sessionStorageï¼ˆåˆ†é å…§æœ‰æ•ˆã€é—œåˆ†é æ¸…é™¤ï¼‰ï¼Œé‡æ–°æ•´ç†ä¸å†æ‰ç™»å…¥ï¼›
//     ç™»å…¥å›ä¾†å¾Œå¤šä¸€æ¬¡ renderï¼Œæ¨™è¨˜æŒ‰éˆ•æ–‡å­—æ‰æœƒå¾ã€Œç™»å…¥ä¸¦æ¨™è¨˜å·²é ˜å–ã€æ›´æ–°éä¾†ã€‚
// å…¶é¤˜ï¼šè«‹æ±‚åŠ  15 ç§’é€¾æ™‚ï¼›è¼‰å…¥ï¼ç©ºï¼éŒ¯èª¤ç‹€æ…‹æ”¹ç”¨ chi-system çš„ .chi-stateï¼›
// éŒ¯èª¤ç‹€æ…‹é™„ã€Œå†è©¦ä¸€æ¬¡ã€æŒ‰éˆ•ï¼›é å°¾ç‰ˆæœ¬ç”± version.jsonï¼ˆCI ç”¢ç”Ÿï¼‰å¡«å…¥ã€‚
// é ˜å–ç‹€æ…‹èˆ‡å°é¢æ”¹è®€ canonical schema æ¬„ä½ claim_status / cover_image_url
// ï¼ˆèˆŠç‰ˆè®€ä¸å­˜åœ¨çš„ claimed / cover_urlï¼Œå°è‡´å…¨éƒ¨é¡¯ç¤ºæœªé ˜å–ã€å°é¢æ°¸é ç©ºç™½ï¼›
//  å·²é ˜å–çš„éŠæˆ²å†æ¨™è¨˜æ™‚ Worker ä¸å¯«å…¥ã€ä¸ç”¢ç”Ÿ commitï¼Œç•«é¢å»é¡¯ç¤ºæˆåŠŸï¼‰ã€‚
// æœ¬ç«™ç¨ç«‹ï¼šheader èˆ‡é å°¾ä¸è¨­è·¨ç«™å°è¦½ï¼›ç™»å…¥æŒ‰éˆ•æ‰‹æ©Ÿç‰ˆåªé¡¯ç¤ºã€Œç™»å…¥ã€ã€‚
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

// ---------- å°å·¥å…· ----------

function $(id) {
  return document.getElementById(id);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function say(message) {
  $("notice").textContent = message || "";
}

// é ˜å–ç‹€æ…‹ä»¥ canonical schema çš„ claim_status ç‚ºæº–ï¼ˆ"unclaimed" / "claimed"ï¼‰ã€‚
function isClaimed(game) {
  return game.claim_status === "claimed";
}

// ç™»å…¥æŒ‰éˆ•æœ‰é•·çŸ­å…©ç¨®æ–‡å­—ï¼ˆæ‰‹æ©Ÿç‰ˆåªé¡¯ç¤ºçŸ­çš„ï¼‰ï¼Œæ”¹æ–‡å­—æ™‚å…©é‚Šä¸€èµ·æ”¹ã€‚
function setLoginLabel(fullLabel, shortLabel) {
  const loginButton = $("login");
  const full = loginButton.querySelector(".fg-login__full");
  const short = loginButton.querySelector(".fg-login__short");
  if (full) full.textContent = fullLabel;
  if (short) short.textContent = shortLabel;
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
      throw new Error((data && data.error) || `è«‹æ±‚å¤±æ•—ï¼ˆ${response.status}ï¼‰`);
    }
    if (data === null) throw new Error("å›æ‡‰æ ¼å¼ä¸æ­£ç¢º");
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("è«‹æ±‚é€¾æ™‚ï¼Œè«‹å†è©¦ä¸€æ¬¡ã€‚");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

// ---------- ç™»å…¥ï¼ˆChi Authï¼ŒPKCEï¼‰ ----------

function saveToken(token, expiresInSeconds) {
  state.accessToken = token;
  state.accessTokenExpiresAt = Date.now() + Number(expiresInSeconds || 600) * 1000;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(TOKEN_EXPIRY_KEY, String(state.accessTokenExpiresAt));
  } catch {
    // sessionStorage ä¸å¯ç”¨æ™‚åªç•™è¨˜æ†¶é«”ï¼Œé‡æ–°æ•´ç†éœ€é‡ç™»
  }
}

function clearToken() {
  state.accessToken = null;
  state.accessTokenExpiresAt = 0;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_EXPIRY_KEY);
  } catch {
    // å¿½ç•¥
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
    // å¿½ç•¥
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
    say("Chi Auth å°šæœªå®Œæˆæ‡‰ç”¨è¨­å®šã€‚");
    return;
  }
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(48)));
  const oauthState = b64url(crypto.getRandomValues(new Uint8Array(24)));
  try {
    sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
    sessionStorage.setItem(OAUTH_STATE_KEY, oauthState);
  } catch {
    say("ç€è¦½å™¨ä¸å…è¨±å„²å­˜ç™»å…¥ç‹€æ…‹ï¼Œè«‹æª¢æŸ¥è¨­å®šå¾Œå†è©¦ã€‚");
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
    // å¿½ç•¥
  }
  if (!oauthState || oauthState !== expectedState || !verifier) {
    say("ç™»å…¥é©—è­‰å¤±æ•—ï¼Œè«‹é‡æ–°ç™»å…¥ã€‚");
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
    setLoginLabel("å·²ç™»å…¥ Chi Auth", "å·²ç™»å…¥");
    say("ç™»å…¥æˆåŠŸï¼Œå¯ä»¥æ‰‹å‹•æ¨™è¨˜é ˜å–ç‹€æ…‹ã€‚");
  } catch (error) {
    say(error.message);
  }
}

// ---------- è³‡æ–™è¼‰å…¥ ----------

async function loadConfig() {
  try {
    const config = await fetchJson(API + "/config");
    state.authClientId = config.auth_client_id;
    state.claimEnabled = Boolean(config.claim_enabled);
    state.configOk = true;
   -¸ÓİÊ×¬¢h­µçVÆÂ“°¢7W'6÷#¢ö–çFW#°¢G&ç6—F–öã¢&6¶w&÷VæBf"‚ÒÖ6†’ÖGW&F–öâ’Â&÷&FW"Ö6öÆ÷"f"‚ÒÖ6†’ÖGW&F–öâ’Â6öÆ÷"f"‚ÒÖ6†’ÖGW&F–öâ“°§Ğ ¢æfrÖ6†—¦fö7W2×f—6–&ÆR°¢÷WFÆ–æS¢f"‚ÒÖ6†’Öfö7W2×v–GF‚’6öÆ–Bf"‚ÒÖ6†’Ö6öÆ÷"Öfö7W2×&–ær“°¢÷WFÆ–æRÖöfg6WC¢f"‚ÒÖ6†’Öfö7W2Ööfg6WB“°§Ğ ¢æfrÖ6†—¦†÷fW"°¢&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"Ö&÷&FW"×7G&öær“°¢6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"×FW‡B×&–Ö'’“°§Ğ ¢ò¢YYşyJhX¾ûÉ¦66VçB˜(®jnûÈ¾ih~ZÙ~ûÈÎˆ8ÎišşyJ‚66VçBRkzˆ›.ûÈxJ66VçBÖ&rFö¶VîûÈÎŠh¾Š‹¾ûÈ’¢ğ¢æfrÖ6†—æ—2Ö7F—fRÀ¢æfr×f–Wr×FövvÆRæ6†’Ö'Fâæ—2Ö7F—fRÀ¢æfr×v–æF–öâæ6†’Ö'Fâæ—2Ö7F—fR°¢&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"Ö66VçB“°¢&6¶w&÷VæC¢6öÆ÷"ÖÖ—‚†–â7&v"Âf"‚ÒÖ6†’Ö6öÆ÷"Ö66VçB’RÂf"‚ÒÖ6†’Ö6öÆ÷"×7W&f6R’“°¢6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"Ö66VçB“°§Ğ ¢æfrÖ6†—æ—2Ö7F—fR°¢föçB×vV–v‡C¢f"‚ÒÖ6†’ÖföçB×vV–v‡BÖÆ&VÂ“°§Ğ ¢æfr×ÆFf÷&ÒÖ6†—2°¢Ö‚Ö†V–v‡C¢sgƒ°¢÷fW&fÆ÷r×“¢WFó°¢Æ–vâÖ6öçFVçC¢fÆW‚×7F'C°¢FF–ær×&–v‡C¢'ƒ°§Ğ ¢ò¢ÒÒÒÒÒÒÒÒÒÒ˜®h‹.XÚx˜rÒÒÒÒÒÒÒÒÒÒ¢ğ¢6vÖW2æfrÖw&–B°¢v–GFƒ¢S°¢F—7Æ“¢w&–C°¢w&–B×FV×ÆFRÖ6öÇVÖç3¢&WVB†WFòÖf–ÆÂÂÖ–æÖ‚†Ö–âƒ#ƒ‚ÂR’Âg"’“°¢Æ–vâÖ—FV×3¢7F'C°¢§W7F–g’Ö6öçFVçC¢7F'C°¢v¢f"‚ÒÖ6†’×76RÓB“°¢FF–ær×F÷¢f"‚ÒÖ6†’×76RÓR“°§Ğ ¢ævÖRÖ6&B°¢v–GFƒ¢S°¢Ö‚×v–GFƒ¢3Cƒ°¢Ö–â×v–GFƒ¢°¢F—7Æ“¢fÆWƒ°¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°¢÷fW&fÆ÷s¢†–FFVã°¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ6†’Ö6öÆ÷"Ö&÷&FW"×7V'FÆR“°¢&÷&FW"×&F—W3¢f"‚ÒÖ6†’×&F—W2ÖÆr“°¢&6¶w&÷VæC¢f"‚ÒÖ6†’Ö6öÆ÷"×7W&f6R“°¢G&ç6—F–öã¢&÷&FW"Ö6öÆ÷"f"‚ÒÖ6†’ÖGW&F–öâ“°§Ğ ¢ævÖRÖ6&C¦†÷fW"°¢&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"Ö&÷&FW"×7G&öær“°§Ğ ¢ævÖRÖ6&Bæfö7W6VB°¢&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"Ö66VçB“°¢÷WFÆ–æS¢f"‚ÒÖ6†’Öfö7W2×v–GF‚’6öÆ–Bf"‚ÒÖ6†’Ö6öÆ÷"Ö66VçB“°¢÷WFÆ–æRÖöfg6WC¢f"‚ÒÖ6†’Öfö7W2Ööfg6WB“°§Ğ ¢ævÖRÖ6&EõöÖVF–°¢F—7Æ“¢&Æö6³°¢v–GFƒ¢S°¢†V–v‡C¢“ƒ°¢fÆWƒ¢“ƒ°¢÷fW&fÆ÷s¢†–FFVã°¢&6¶w&÷VæC¢f"‚ÒÖ6†’Ö6öÆ÷"×7W&f6R×7Væ¶Vâ“°§Ğ ¢ævÖRÖ6&Eõö6÷fW"°¢F—7Æ“¢&Æö6³°¢v–GFƒ¢S°¢†V–v‡C¢S°¢ö&¦V7BÖf—C¢6÷fW#°§Ğ ¢ævÖRÖ6&Eõö6öçFVçB°¢Ö–â×v–GFƒ¢°¢F—7Æ“¢fÆWƒ°¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°¢Æ–vâÖ—FV×3¢7G&WF6ƒ°¢v¢f"‚ÒÖ6†’×76RÓ"“°¢FF–æs¢f"‚ÒÖ6†’×76RÓ2“°§Ğ ¢ævÖRÖ6&Eõ÷F÷Æ–æR°¢F—7Æ“¢fÆWƒ°¢Æ–vâÖ—FV×3¢6VçFW#°¢§W7F–g’Ö6öçFVçC¢76RÖ&WGvVVã°¢v¢f"‚ÒÖ6†’×76RÓ"“°§Ğ ¢ævÖRÖ6&Eõ÷ÆFf÷&Ò°¢6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"×FW‡BÖ×WFVB“°¢föçB×6—¦S¢f"‚ÒÖ6†’ÖföçB×6—¦RÖ6F–öâ“°¢föçB×vV–v‡C¢s°¢ÆWGFW"×76–æs¢ã†VÓ°¢FW‡B×G&ç6f÷&Ó¢WW&66S°§Ğ ¢ævÖRÖ6&Eõ÷F—FÆR°¢Ö&v–ã¢°¢6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"×FW‡B×&–Ö'’“°¢föçB×6—¦S¢f"‚ÒÖ6†’ÖföçB×6—¦RÖ6&B×F—FÆR“°¢föçB×vV–v‡C¢f"‚ÒÖ6†’ÖföçB×vV–v‡BÖ6&B×F—FÆR“°¢Æ–æRÖ†V–v‡C¢f"‚ÒÖ6†’ÖÆ–æRÖ†V–v‡BÖ6&B×F—FÆR“°¢÷fW&fÆ÷r×w&¢ç—v†W&S°§Ğ ¢ævÖRÖ6&EõöFFR°¢Ö&v–ã¢°¢6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"×FW‡BÖ×WFVB“°¢föçB×6—¦S¢f"‚ÒÖ6†’ÖföçB×6—¦RÖ6F–öâ“°§Ğ ¢ævÖRÖ6&Eõö7F–öç2°¢F—7Æ“¢fÆWƒ°¢fÆW‚×w&¢w&°¢v¢f"‚ÒÖ6†’×76RÓ"“°¢Ö&v–â×F÷¢WFó°¢FF–ær×F÷¢f"‚ÒÖ6†’×76RÓ"“°§Ğ ¢ævÖRÖ6&EõöÆ–æ²°¢Ö–âÖ†V–v‡C¢3'ƒ°¢FF–ærÖ–æÆ–æS¢f"‚ÒÖ6†’×76RÓ2“°¢föçB×6—¦S¢f"‚ÒÖ6†’ÖföçB×6—¦RÖ6F–öâ“°§Ğ ¢ævÖRÖ6&Eõö6Æ–Ò°¢v–GFƒ¢S°¢Ö–âÖ†V–v‡C¢3‡ƒ°¢Ö&v–â×F÷¢f"‚ÒÖ6†’×76RÓ“°§Ğ ¢ævÖRÖ6&Eõö6Æ–Ó¦F—6&ÆVB°¢7W'6÷#¢æ÷BÖÆÆ÷vVC°¢÷6—G“¢ãSS°§Ğ ¢ævÖRÖ6&Eõö6Æ–ÒÖæ÷FR°¢Ö&v–ã¢°¢6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"×FW‡BÖ×WFVB“°¢föçB×6—¦S¢f"‚ÒÖ6†’ÖföçB×6—¦RÖ6F–öâ“°§Ğ ¢ò¢ÒÒÒÒÒÒÒÒÒÒkˆ^Yjîjª.ŠibÒÒÒÒÒÒÒÒÒÒ¢ğ¢ò¢h˜¾j™şXJ®XXûÉ®š	ŠŠŞy»NY	Znyh®ûÉ¾jÎ™Ú.Kº^Kˆ®h˜ŞiKjš¾Y	ûÈYJşKˆ™ÈŠhik~›¹îK˜¾‰™^ûÈ8"¢ğ¢6vÖW2æfrÖÆ—7B°¢F—7Æ“¢fÆWƒ°¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°¢v¢f"‚ÒÖ6†’×76RÓ"“°¢FF–ær×F÷¢f"‚ÒÖ6†’×76RÓB“°§Ğ ¢æfrÖÆ—7BævÖRÖ6&B°¢Ö‚×v–GFƒ¢æöæS°§Ğ ¢æfrÖÆ—7BævÖRÖ6&EõöÖVF–°¢†V–v‡C¢ƒƒ°¢fÆW‚Ö&6—3¢ƒƒ°§Ğ ¢ò¢6†’Ö'&V·ö–çC¢6†’Ö'&V·ö–çBÖÖB¢ğ¤ÖVF–†Ö–â×v–GFƒ¢sc‡‚’°¢æfrÖÆ—7BævÖRÖ6&B°¢fÆW‚ÖF—&V7F–öã¢&÷s°¢Æ–vâÖ—FV×3¢7G&WF6ƒ°¢Ö–âÖ†V–v‡C¢'ƒ°¢Ğ ¢æfrÖÆ—7BævÖRÖ6&EõöÖVF–°¢v–GFƒ¢cƒ°¢Ö–â×v–GFƒ¢cƒ°¢†V–v‡C¢WFó°¢Ö–âÖ†V–v‡C¢'ƒ°¢fÆWƒ¢cƒ°¢Ğ ¢æfrÖÆ—7BævÖRÖ6&Eõö6öçFVçB°¢fÆWƒ¢°¢F—7Æ“¢w&–C°¢w&–B×FV×ÆFRÖ6öÇVÖç3¢Ö–æÖ‚ƒÂg"’WFó°¢Æ–vâÖ6öçFVçC¢6VçFW#°¢6öÇVÖâÖv¢f"‚ÒÖ6†’×76RÓB“°¢&÷rÖv¢f"‚ÒÖ6†’×76RÓ"“°¢Ğ ¢æfrÖÆ—7BævÖRÖ6&Eõ÷F÷Æ–æRÀ¢æfrÖÆ—7BævÖRÖ6&Eõ÷F—FÆRÀ¢æfrÖÆ—7BævÖRÖ6&EõöFFRÀ¢æfrÖÆ—7BævÖRÖ6&Eõö6Æ–ÒÖæ÷FR°¢w&–BÖ6öÇVÖã¢°¢Ğ ¢æfrÖÆ—7BævÖRÖ6&Eõö7F–öç2À¢æfrÖÆ—7BævÖRÖ6&Eõö6Æ–Ò°¢w&–BÖ6öÇVÖã¢#°¢w&–B×&÷s¢òS°¢Æ–vâ×6VÆc¢6VçFW#°¢§W7F–g’Ö6öçFVçC¢fÆW‚ÖVæC°¢Ğ ¢æfrÖÆ—7BævÖRÖ6&Eõö6Æ–Ò°¢v–GFƒ¢WFó°¢Ö–â×v–GFƒ¢Sƒ°¢Ö&v–ã¢°¢Ğ§Ğ ¢ò¢ÒÒÒÒÒÒÒÒÒÒXˆnšÒÒÒÒÒÒÒÒÒÒ¢ğ¢æfr×v–æF–öâ°¢F—7Æ“¢fÆWƒ°¢§W7F–g’Ö6öçFVçC¢6VçFW#°¢Æ–vâÖ—FV×3¢6VçFW#°¢fÆW‚×w&¢w&°¢v¢f"‚ÒÖ6†’×76RÓ“°¢FF–ærÖ&Æö6³¢f"‚ÒÖ6†’×76RÓb“°§Ğ ¢æfr×v–æF–öâæ6†’Ö'Fâ°¢Ö–â×v–GFƒ¢3‡ƒ°§Ğ ¢æfr×v–æF–öåõö–æfò°¢FF–ærÖ–æÆ–æS¢f"‚ÒÖ6†’×76RÓ"“°¢6öÆ÷#¢f"‚ÒÖ6†’Ö6öÆ÷"×FW‡BÖ×WFVB“°¢föçB×6—¦S¢f"‚ÒÖ6†’ÖföçB×6—¦RÖ&öG’×6ÖÆÂ“°§Ğ ¢ò¢ÒÒÒÒÒÒÒÒÒÒ‹8~iix¸hX²ÒÒÒÒÒÒÒÒÒÒ¢ğ¢ò¢æ6†’×7FFRYÊ‚w&–BZëYšXZ~Šhjš¾‹zXZ˜:jÈNKØŞ8"¢ğ¢6vÖW2æ6†’×7FFR°¢w&–BÖ6öÇVÖã¢òÓ°§Ğ ¢ò¢ÒÒÒÒÒÒÒÒÒÒÖö&–ÆRvR×F—FÆR76–ærÒÒÒÒÒÒÒÒÒÒ¢ğ¤ÖVF–†Ö‚×v–GFƒ¢scw‚’°¢æfrÖÖ–â°¢FF–ær×F÷¢f"‚ÒÖ6†’×76RÓ2“°¢Ğ ¢æfr×vRÖ†VFW"°¢FF–ærÖ&Æö6³¢f"‚ÒÖ6†’×76RÓ2’f"‚ÒÖ6†’×76RÓ"“°¢Ğ ¢æfrÖ6öçG&öÇ2°¢FF–ær×F÷¢f"‚ÒÖ6†’×76RÓ"“°¢Ğ§Ğ  ¢ò¢ÒÒÒÒÒÒÒÒÒÒÖö&–ÆRvÖRÖ6&Bv–GF‚ÒÒÒÒÒÒÒÒÒÒ¢ğ¤ÖVF–†Ö‚×v–GFƒ¢scw‚’°¢6vÖW2æfrÖw&–B°¢w&–B×FV×ÆFRÖ6öÇVÖç3¢Ö–æÖ‚ƒÂg"“°¢§W7F–g’Ö—FV×3¢7G&WF6ƒ°¢Ğ ¢ævÖRÖ6&B°¢v–GFƒ¢S°¢Ö‚×v–GFƒ¢æöæS°¢&÷‚×6—¦–æs¢&÷&FW"Ö&÷ƒ°¢Ğ§Ğ 