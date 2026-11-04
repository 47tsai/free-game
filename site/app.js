const API="/api";
const AUTH="https://auth.chi.qzz.io";
let accessToken=null,accessTokenExpiresAt=0,claimEnabled=false,authClientId=null;
let allGames=[],page=1,viewMode="grid";
const $=id=>document.getElementById(id);
function b64url(bytes){return btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+","-").replaceAll("/","_").replace(/=+$/g,"")}
function say(message){$("notice").textContent=message||""}
async function digest(value){return b64url(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value)))}
async function login(){
 if(!authClientId){say("Chi Auth 尚未完成應用設定。");return}
 const verifier=b64url(crypto.getRandomValues(new Uint8Array(48))),state=b64url(crypto.getRandomValues(new Uint8Array(24)));
 sessionStorage.setItem("fg_pkce_verifier",verifier);sessionStorage.setItem("fg_oauth_state",state);
 const params=new URLSearchParams({response_type:"code",client_id:authClientId,redirect_uri:location.origin+"/",code_challenge:await digest(verifier),code_challenge_method:"S256",state});
 location.href=AUTH+"/api/authorize?"+params.toString();
}
async function finishLogin(){
 const params=new URLSearchParams(location.search),code=params.get("code");if(!code)return;
 const state=params.get("state"),expected=sessionStorage.getItem("fg_oauth_state"),verifier=sessionStorage.getItem("fg_pkce_verifier");
 sessionStorage.removeItem("fg_oauth_state");sessionStorage.removeItem("fg_pkce_verifier");
 if(!state||state!==expected||!verifier){say("登入驗證失敗，請重新登入。");return}
 try{
  const response=await fetch(AUTH+"/api/token?client_id="+encodeURIComponent(authClientId),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({client_id:authClientId,code,redirect_uri:location.origin+"/",code_verifier:verifier})});
  const data=await response.json();if(!response.ok)throw new Error(data.error||"登入失敗");
  accessToken=data.access_token;accessTokenExpiresAt=Date.now()+Number(data.expires_in||600)*1000;
  history.replaceState({}, "", location.pathname+location.hash);$("login").textContent="已登入 Chi Auth";say("登入成功，可以手動標記領取狀態。");
 }catch(error){say(error.message)}
}
function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node}
function safeLink(label,url){if(!url||!/^https:\/\//i.test(url))return null;const a=element("a","chi-button",label);a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a}
function filteredGames(){
 const keyword=$("search").value.trim().toLocaleLowerCase(),status=$("status-filter").querySelector("[aria-pressed=true]")?.dataset.status||"all",platform=$("platform-filter").querySelector("[aria-pressed=true]")?.dataset.platform||"all";
 return allGames.filter(g=>{
  if(keyword&&!String(g.title||"").toLocaleLowerCase().includes(keyword))return false;
  if(status==="claimed"&&g.claim_status!=="claimed")return false;
  if(status==="unclaimed"&&g.claim_status==="claimed")return false;
  if(platform!=="all"&&String(g.platform||"unknown").toLowerCase()!==platform)return false;
  return true;
 });
}
function renderPagination(total,totalPages){
 const nav=$("pagination");nav.replaceChildren();if(totalPages<=1)return;
 const add=(label,target,disabled=false,active=false)=>{
  const b=element("button","chi-button chi-button--secondary"+(active?" is-active":""),label);b.type="button";b.disabled=disabled;b.setAttribute("aria-label",label==="‹"?"上一頁":label==="›"?"下一頁":"第 "+label+" 頁");if(active)b.setAttribute("aria-current","page");b.addEventListener("click",()=>{page=target;render()} );nav.append(b);
 };
 add("‹",page-1,page===1);
 const start=Math.max(1,Math.min(page-2,totalPages-4)),end=Math.min(totalPages,start+4);
 if(start>1){add("1",1);if(start>2)nav.append(element("span","fg-pagination__info","…"))}
 for(let p=start;p<=end;p++)add(String(p),p,false,p===page);
 if(end<totalPages){if(end<totalPages-1)nav.append(element("span","fg-pagination__info","…"));add(String(totalPages),totalPages)}
 add("›",page+1,page===totalPages);
}
function render(){
 const filtered=filteredGames(),size=$("page-size").value==="all"?filtered.length:Number($("page-size").value),totalPages=Math.max(1,Math.ceil(filtered.length/Math.max(1,size)));
 page=Math.min(page,totalPages);const start=(page-1)*size,visible=$("page-size").value==="all"?filtered:filtered.slice(start,start+size);
 $("summary").textContent="遊戲列表";
 const container=$("games");container.className=viewMode==="list"?"fg-list":"fg-grid";container.replaceChildren();
 if(!visible.length){container.append(element("div","empty chi-empty",allGames.length?"沒有符合條件的遊戲。":"目前還沒有遊戲資料。"))}
 for(const game of visible){
  const card=element("article","game-card");card.id="game-"+game.id;
  const media=element("div","game-card__media");
  if(game.cover_image_url){const img=element("img","game-card__cover");img.src=game.cover_image_url;img.alt=game.title||"遊戲封面";img.loading="lazy";media.append(img)}else media.classList.add("game-card__media--empty");
  const body=element("div","game-card__content"),top=element("div","game-card__topline");
  top.append(element("span","game-card__platform",(game.platform||"未知平台").toUpperCase()));
  top.append(element("span","status"+(game.claim_status==="claimed"?" done":""),game.claim_status==="claimed"?"已領取":"尚未領取"));
  body.append(top,element("h2","game-card__title",game.title||"未命名遊戲"));
  const date=new Date(game.added_at||game.created_at);
  if(!Number.isNaN(date.getTime()))body.append(element("p","game-card__date","加入日期 · "+date.toLocaleDateString("zh-TW",{year:"numeric",month:"short",day:"numeric"})));
  const actions=element("div","game-card__actions"),store=safeLink("前往商店",game.store_url),article=safeLink("閱讀文章",game.article_url);
  if(store){store.classList.add("game-card__link");actions.append(store)}if(article){article.classList.add("game-card__link");actions.append(article)}body.append(actions);
  if(game.claim_status!=="claimed"){const button=element("button","chi-button chi-button--primary game-card__claim",accessToken?"標記已領取":"登入並標記已領取");button.type="button";button.disabled=!claimEnabled;button.addEventListener("click",()=>markClaimed(game,button));body.append(button)}
  else if(game.claim_source)body.append(element("p","game-card__claim-note",game.claim_source==="fgc"?"領取狀態由 FGC 自動同步":"由網站手動標記"));
  card.append(media,body);container.append(card);
 }
 renderPagination(filtered.length,totalPages);
 const focusId=new URLSearchParams(location.search).get("game");
 if(focusId){const target=document.getElementById("game-"+focusId);if(target){target.classList.add("focused");target.scrollIntoView({behavior:"smooth",block:"center"});}}
}
async function markClaimed(game,button){
 if(!claimEnabled){say("目前尚未啟用標記功能，請稍後再試。");return}
 if(!accessToken||Date.now()>=accessTokenExpiresAt){accessToken=null;accessTokenExpiresAt=0;sessionStorage.setItem("fg_pending_claim",game.id);say("請先完成 Chi Auth 登入，登入後會自動完成標記。");await login();return}
 if(button){button.disabled=true;button.textContent="更新中…"}
 try{
  const response=await fetch(API+"/games/"+encodeURIComponent(game.id)+"/claim",{method:"POST",headers:{Authorization:"Bearer "+accessToken}});
  const data=await response.json();if(!response.ok){const messages={authentication_required:"登入已失效，請重新登入後再試。",github_write_forbidden:"GitHub Token 沒有此儲存庫的寫入權限。",github_write_conflict:"資料剛好有更新，請再按一次。",game_not_found:"找不到這筆遊戲資料。"};throw new Error(messages[data.error]||data.error||"更新失敗")}
  game.claim_status="claimed";game.claim_source="manual";game.claimed_at=data.game.claimed_at;render();say("已標記為已領取。");
 }catch(error){say(error.message);if(button){button.disabled=false;button.textContent="標記已領取"}}
}
function populatePlatforms(){
 const group=$("platform-filter"),platforms=[...new Set(allGames.map(g=>String(g.platform||"unknown").toLowerCase()))].sort();
 for(const platform of platforms){const button=element("button","fg-chip",platform==="unknown"?"未知平台":platform.toUpperCase());button.type="button";button.dataset.platform=platform;button.setAttribute("aria-pressed","false");group.append(button)}
}
function setupControls(){
 ["search","page-size"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",()=>{page=1;render()}));
 ["status-filter","platform-filter"].forEach(id=>$(id).addEventListener("click",event=>{const button=event.target.closest("button");if(!button)return;$(id).querySelectorAll("button").forEach(item=>{const active=item===button;item.classList.toggle("is-active",active);item.setAttribute("aria-pressed",String(active))});page=1;render()}));
 $("view-grid").addEventListener("click",()=>setView("grid"));$("view-list").addEventListener("click",()=>setView("list"));
}
function setView(mode){viewMode=mode;$("view-grid").classList.toggle("is-active",mode==="grid");$("view-list").classList.toggle("is-active",mode==="list");$("view-grid").setAttribute("aria-pressed",String(mode==="grid"));$("view-list").setAttribute("aria-pressed",String(mode==="list"));render()}
async function init(){
 try{
  const configResponse=await fetch(API+"/config");if(!configResponse.ok)throw new Error("無法讀取網站設定");const config=await configResponse.json();authClientId=config.auth_client_id;claimEnabled=Boolean(config.claim_enabled);
  if(!authClientId){$("login").disabled=true;$("login").textContent="Chi Auth 尚未設定"}
  const result=await fetch(API+"/games").then(r=>r.json());if(!result.games)throw new Error("無法讀取遊戲資料");
  allGames=result.games;populatePlatforms();setupControls();render();await finishLogin();
  if(accessToken){$("login").textContent="已登入 Chi Auth";const pendingId=sessionStorage.getItem("fg_pending_claim");if(pendingId){sessionStorage.removeItem("fg_pending_claim");const game=allGames.find(item=>item.id===pendingId);if(game)await markClaimed(game,document.querySelector("#game-"+CSS.escape(pendingId)+" .game-card__claim"))}}
  if(!claimEnabled)say("目前尚未設定 GitHub 寫入權限，手動標記暫時不可用。");
 }catch(error){$("summary").textContent="目前無法載入資料";say(error.message)}
}
$("login").addEventListener("click",login);
init();
