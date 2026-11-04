const API="/api";
const AUTH="https://auth.chi.qzz.io";
let accessToken=null;
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
  accessToken=data.access_token;history.replaceState({}, "", location.pathname);$("login").textContent="已登入 Chi Auth";say("登入成功，可以手動標記領取狀態。");
 }catch(error){say(error.message)}
}
function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node}
function safeLink(label,url){if(!url||!/^https:\/\//i.test(url))return null;const a=element("a","chi-button",label);a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a}
async function markClaimed(game,button){
 if(!accessToken){say("請先使用 Chi Auth 登入。");return}
 button.disabled=true;
 try{const response=await fetch(API+"/games/"+encodeURIComponent(game.id)+"/claim",{method:"POST",headers:{Authorization:"Bearer "+accessToken}});
 const data=await response.json();if(!response.ok)throw new Error(data.error||"更新失敗");
 game.claim_status="claimed";game.claim_source="manual";game.claimed_at=data.game.claimed_at;renderGames(window.currentGames);say("已標記為已領取。");
 }catch(error){say(error.message);button.disabled=false}
}
function renderGames(games){
 window.currentGames=games;$("games").replaceChildren();
 $("summary").textContent="共 "+games.length+" 款遊戲 · 已領取 "+games.filter(g=>g.claim_status==="claimed").length+" 款";
 if(!games.length){$("games").append(element("div","empty chi-empty","目前還沒有遊戲資料。"));return}
 for(const game of games){
  const card=element("article","card");card.id="game-"+game.id;
  if(game.cover_image_url){const img=element("img","cover");img.src=game.cover_image_url;img.alt=game.title;img.loading="lazy";card.append(img)}
  else card.append(element("div","cover"));
  const body=element("div","body"),row=element("div","title-row"),info=element("div","");
  info.append(element("div","title",game.title||"未命名遊戲"),element("div","platform",game.platform||"未知平台"));
  row.append(info,element("span","status"+(game.claim_status==="claimed"?" done":""),game.claim_status==="claimed"?"已領取":"未領取"));
  body.append(row);
  const links=element("div","links");
  for(const [label,url] of [["商店",game.store_url],["4Gamer 文章",game.article_url]]){const link=safeLink(label,url);if(link)links.append(link)}
  body.append(links);
  if(game.claim_status!=="claimed"){const button=element("button","chi-button chi-button--primary claim",accessToken?"標記已領取":"登入後可手動標記");button.disabled=!accessToken;button.addEventListener("click",()=>markClaimed(game,button));body.append(button)}
  else if(game.claim_source)body.append(element("div","platform",game.claim_source==="fgc"?"由 FGC 自動同步領取":"手動標記領取"));
  card.append(body);$("games").append(card);
 }
 const focusId=new URLSearchParams(location.search).get("game");
 if(focusId){const target=document.getElementById("game-"+focusId);if(target){target.classList.add("focused");target.scrollIntoView({behavior:"smooth",block:"center"});}}
}
async function init(){
 try{const config=await fetch(API+"/config").then(r=>r.json());authClientId=config.auth_client_id;
  if(!authClientId){$("login").disabled=true;$("login").textContent="Chi Auth 尚未設定"}
  const games=await fetch(API+"/games").then(r=>r.json());if(!games.games)throw new Error("無法讀取遊戲資料");
  renderGames(games.games);await finishLogin();if(accessToken)renderGames(games.games);
 }catch(error){$("summary").textContent="目前無法載入資料";say(error.message)}
}
$("login").addEventListener("click",login);
init();
