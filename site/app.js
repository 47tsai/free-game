const API="/api";
const AUTH="https://auth.chi.qzz.io";
let accessToken=null;
let accessTokenExpiresAt=0;
let claimEnabled=false;
let authClientId=null;
const $=id=>document.getElementById(id);
function b64url(bytes){return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/g,"")}
function say(message){$("notice").textContent=message||""}
async function digest(value){return b64url(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value)))}
async function login(){
 if(!authClientId){say("Chi Auth 尚未完成應用設定。");return}
 const bytes=crypto.getRandomValues(new Uint8Array(48));
 const verifier=b64url(bytes);
 const state=b64url(crypto.getRandomValues(new Uint8Array(24)));
 sessionStorage.setItem("fg_pkce_verifier",verifier);
 sessionStorage.setItem("fg_oauth_state",state);
 const redirect=location.origin+"/";
 const params=new URLSearchParams({response_type:"code",client_id:authClientId,redirect_uri:redirect,code_challenge:await digest(verifier),code_challenge_method:"S256",state});
 location.href=AUTH+"/api/authorize?"+params.toString();
}
async function finishLogin(){
 const params=new URLSearchParams(location.search);
 const code=params.get("code");
 if(!code)return;
 const state=params.get("state");
 const expected=sessionStorage.getItem("fg_oauth_state");
 const verifier=sessionStorage.getItem("fg_pkce_verifier");
 sessionStorage.removeItem("fg_oauth_state");sessionStorage.removeItem("fg_pkce_verifier");
 if(!state||state!==expected||!verifier){say("登入驗證失敗，請重新登入。");return}
 try{
  const response=await fetch(AUTH+"/api/token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({client_id:authClientId,code,redirect_uri:location.origin+"/",code_verifier:verifier})});
  const data=await response.json();if(!response.ok)throw new Error(data.error||"登入失敗");
  accessToken=data.access_token;accessTokenExpiresAt=Date.now()+Number(data.expires_in||600)*1000;history.replaceState({}, "", location.pathname);$("login").textContent="已登入 Chi Auth";say("登入成功，可以手動標記領取狀態。");
 }catch(error){say(error.message)}
}
function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node}
function safeLink(label,url){if(!url||!/^https:\/\//i.test(url))return null;const a=element("a","chi-button",label);a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a}
async function markClaimed(game,button){
 if(!claimEnabled){say("目前尚未啟用標記功能，請稍後再試。");return}
 if(!accessToken||Date.now()>=accessTokenExpiresAt){
  accessToken=null;accessTokenExpiresAt=0;
  sessionStorage.setItem("fg_pending_claim",game.id);
  say("請先完成 Chi Auth 登入，登入後會自動完成標記。");
  await login();
  return;
 }
 if(button){button.disabled=true;button.textContent="更新中…"}
 try{
  const response=await fetch(API+"/games/"+encodeURIComponent(game.id)+"/claim",{method:"POST",headers:{Authorization:"Bearer "+accessToken}});
  const data=await response.json();
  if(!response.ok){
   const messages={authentication_required:"登入已失效，請重新登入後再試。",github_write_forbidden:"GitHub Token 沒有此儲存庫的寫入權限。",github_write_conflict:"資料剛好有更新，請再按一次。",game_not_found:"找不到這筆遊戲資料。"};
   throw new Error(messages[data.error]||data.error||"更新失敗");
  }
  game.claim_status="claimed";game.claim_source="manual";game.claimed_at=data.game.claimed_at;
  renderGames(window.currentGames);say("已標記為已領取。");
 }catch(error){say(error.message);if(button){button.disabled=false;button.textContent="標記已領取"}}
}
function renderGames(games){
 window.currentGames=games; $("games").replaceChildren();
 $("summary").textContent="共 "+games.length+" 款遊戲 · 已領取 "+games.filter(g=>g.claim_status==="claimed").length+" 款";
 if(!games.length){$("games").append(element("div","empty chi-empty","目前還沒有遊戲資料。"));return}
 for(const game of games){
  const card=element("article","game-card");card.id="game-"+game.id;
  const media=element("div","game-card__media");
  if(game.cover_image_url){const img=element("img","game-card__cover");img.src=game.cover_image_url;img.alt=game.title||"遊戲封面";img.loading="lazy";media.append(img)}
  else media.classList.add("game-card__media--empty");
  const body=element("div","game-card__content");
  const top=element("div","game-card__topline");
  top.append(element("span","game-card__platform",(game.platform||"未知平台").toUpperCase()));
  top.append(element("span","status"+(game.claim_status==="claimed"?" done":""),game.claim_status==="claimed"?"已領取":"尚未領取"));
  body.append(top);
  body.append(element("h2","game-card__title",game.title||"未命名遊戲"));
  if(game.added_at||game.created_at){
   const date=new Date(game.added_at||game.created_at);
   if(!Number.isNaN(date.getTime()))body.append(element("p","game-card__date","加入日期 · "+date.toLocaleDateString("zh-TW",{year:"numeric",month:"short",day:"numeric"})));
  }
  const actions=element("div","game-card__actions");
  const store=safeLink("前往商店",game.store_url);
  const article=safeLink("閱讀文章",game.article_url);
  if(store){store.classList.add("game-card__link");actions.append(store)}
  if(article){article.classList.add("game-card__link");actions.append(article)}
  body.append(actions);
  if(game.claim_status!=="claimed"){
   const button=element("button","chi-button chi-button--primary game-card__claim",accessToken?"標記已領取":"登入並標記已領取");
   button.type="button";button.disabled=!claimEnabled;
   button.addEventListener("click",()=>markClaimed(game,button));body.append(button);
  }else if(game.claim_source){
   body.append(element("p","game-card__claim-note",game.claim_source==="fgc"?"領取狀態由 FGC 自動同步":"由網站手動標記"));
  }
  card.append(media,body);$("games").append(card);
 }
 const focusId=new URLSearchParams(location.search).get("game");
 if(focusId){const target=document.getElementById("game-"+focusId);if(target){target.classList.add("focused");target.scrollIntoView({behavior:"smooth",block:"center"});}}
}
async function init(){
 try{const configResponse=await fetch(API+"/config");if(!configResponse.ok)throw new Error("無法讀取網站設定");const config=await configResponse.json();authClientId=config.auth_client_id;claimEnabled=Boolean(config.claim_enabled);
  if(!authClientId){$("login").disabled=true;$("login").textContent="Chi Auth 尚未設定"}
  const games=await fetch(API+"/games").then(r=>r.json());if(!games.games)throw new Error("無法讀取遊戲資料");
  renderGames(games.games);await finishLogin();
  if(accessToken){
   renderGames(games.games);
   const pendingId=sessionStorage.getItem("fg_pending_claim");
   if(pendingId){
    sessionStorage.removeItem("fg_pending_claim");
    const pendingGame=games.games.find(game=>game.id===pendingId);
    if(pendingGame)await markClaimed(pendingGame,document.querySelector("#game-"+CSS.escape(pendingId)+" .game-card__claim"));
   }
  }
  if(!claimEnabled)say("目前尚未設定 GitHub 寫入權限，手動標記暫時不可用。");
 }catch(error){$("summary").textContent="目前無法載入資料";say(error.message)}
}
$("login").addEventListener("click",login);
init();
