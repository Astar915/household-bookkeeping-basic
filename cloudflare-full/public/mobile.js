"use strict";

// Mobile presentation only; financial rules stay in the shared Python services.
const m = (zh, ja, en) => currentLanguage === "ja-JP" ? ja : currentLanguage === "en-US" ? en : zh;
const e = escapeHtml;
const icons = {
  home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
  chat:'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3v-9a9 9 0 0 1 18-2Z"/><path d="M7 10h10M7 14h6"/>',
  book:'<path d="M5 3h14v18H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M7 3v18M11 8h5M11 12h5"/>',
  investment:'<path d="M3 20h18M5 17l5-5 4 3 6-8"/><path d="M15 7h5v5"/>',
  points:'<circle cx="12" cy="12" r="9"/><path d="m12 6 1.8 3.8 4.2.4-3.1 2.7.9 4.1-3.8-2.1-3.8 2.1.9-4.1L6 10.2l4.2-.4Z"/>',
  wallet:'<rect x="3" y="5" width="18" height="15" rx="4"/><path d="M16 11h5v5h-5a2.5 2.5 0 0 1 0-5ZM4 6l12-3"/>',
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  search:'<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/>',
  arrow:'<path d="m9 5 7 7-7 7"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  eye:'<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  cloud:'<path d="M6 18a5 5 0 0 1-1-10 7 7 0 0 1 13-1 5.5 5.5 0 0 1 0 11Z"/><path d="m9 12 3-3 3 3M12 9v10"/>',
  card:'<rect x="2" y="4" width="20" height="16" rx="4"/><path d="M2 10h20M6 15h4"/>',
  chart:'<path d="M3 3v18h18M7 16v-4M12 16V8M17 16V5"/>',
  food:'<path d="M5 3v6a3 3 0 0 0 6 0V3M8 3v18M19 21V3c-5 2-5 10 0 10"/>',
  settings:'<path d="m10 3 4 0 1 3 3 1 3 3-2 3 0 4-3 1-2 3h-4l-1-3-3-1-3-3 2-3V7l3-1Z"/><circle cx="12" cy="12" r="3"/>',
  repeat:'<path d="m17 2 4 4-4 4M3 11V8a2 2 0 0 1 2-2h16M7 22l-4-4 4-4M21 13v3a2 2 0 0 1-2 2H3"/>',
  asset:'<path d="m3 10 9-7 9 7M5 9v12h14V9M9 21v-7h6v7"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 9h18"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  list:'<path d="M9 6h12M9 12h12M9 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
};
const icon = name => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(icons[name]||icons.book)+'</svg>';
const b = (action, text, id="", cls="button secondary") => {
  const names={privacy:m("显示或隐藏金额","金額表示の切替","Show or hide amounts"),refresh:m("刷新","更新","Refresh"),"hero-mode-toggle":heroProfitMode?m("切换到主要记账货币余额","メイン通貨の残高に切替","Switch to main-currency balance"):m("切换到当期纯利润","当期純利益に切替","Switch to current net profit"),"budget-edit":m("编辑预算","予算編集","Edit budget"),"add-card":m("添加信用卡","カード追加","Add credit card"),"asset-edit":m("登记资产","資産を登録","Register asset"),"investment-add":m("添加投资持仓","投資保有情報を追加","Add investment holding"),"investment-edit":m("修改投资持仓","投資保有情報を編集","Edit investment holding"),"investment-delete":m("删除投资持仓","投資保有情報を削除","Delete investment holding"),"profile-add":m("添加 API 服务","APIを追加","Add API service"),backup:m("创建备份","バックアップ作成","Create backup"),"order-up":m("上移","上へ","Move up"),"order-down":m("下移","下へ","Move down"),"order-remove":m("移除扣款来源","引落元を削除","Remove funding source"),"favorites-edit":m("编辑常用功能","ショートカットを編集","Edit shortcuts"),"favorites-add":m("添加常用功能","ショートカットを追加","Add shortcut"),"favorite-remove":m("移除此常用功能","ショートカットを削除","Remove shortcut")};
  return '<button type="button" class="'+cls+'" data-action="'+action+'" data-id="'+e(id)+'"'+(names[action]?' aria-label="'+e(names[action])+'"':"")+'>'+text+'</button>';
};
const money = (value, currency="JPY", digits=null, accountType="") => hiddenAmounts ? "••••••" : formatMinor(value || "0", currency, digits === null ? currencyMinorDigits(currency, 0) : digits, accountType);
function dateAtTimeZone(instant,timeZone="Asia/Tokyo"){
  const date=new Date(instant);
  if(Number.isNaN(date.getTime()))return "";
  try{
    const parts=new Intl.DateTimeFormat("en-US",{timeZone,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(date);
    const values=Object.fromEntries(parts.map(part=>[part.type,part.value]));
    return values.year&&values.month&&values.day?`${values.year}-${values.month}-${values.day}`:"";
  }catch{return "";}
}
const plainAmount = (minor, digits=0, currency="") => {
  const places=currency?currencyMinorDigits(currency,digits):Number(digits||0);
  const v=BigInt(String(minor || 0)), factor=10n**BigInt(places);
  const a=v<0n?-v:v; return (v<0n?"-":"")+(a/factor).toString()+(places ? "."+(a%factor).toString().padStart(places,"0"):"");
};
function capturePreparedBaseline(preview){
  const workspaceKeys=Object.keys(workspace||{}),base={};
  for(const key of Object.keys(preview||{}))if(!["accounts","transactions"].includes(key)&&workspace&&Object.hasOwn(workspace,key))base[key]=deepCopy(workspace[key]);
  return {workspace:base,workspaceKeys,accounts:deepCopy(cachedBootstrap?.accounts||[])};
}
let workspace = null, workspaceOwner = "", workspaceLoading = null;
const WORKSPACE_CACHE_FORMAT = 2;
let financePieColorNames = [];
let financePieCategoryOrder = [];
let workspaceEpoch = 0;
let ledgerRangeRequest = 0;
let workspaceError = "";
let selectedPage = "home", assetTab = "cash", moreTab = "", reportDate = "", financialTab = "balance", settingsTab = "general", financeTrendMode = "daily", ledgerSearchTimer = null, ledgerRangeRows = null, backupDraft = null, favoritesEditing = false;
let accountViewMode = localStorage.getItem("hh-account-view") === "list" ? "list" : "cards";
let heroProfitMode = true;
let hiddenAmounts = localStorage.getItem("hh-hide-amounts") === "1";
let chatAgent = "ledger_query", chats = {bookkeeping:[], food_health:[], ledger_query:[]}, attachments=[], currentUsageVision=false;
let modelBalances = {}, modelBalanceRequests = {}, modelBalanceCheckedAt = {}, modelBalanceSpend = {};
let investmentQuotes = new Map(), investmentQuoteRequest = 0, mufgFundCatalogPromise = null;
let paymentRulesDraft = null;
let pointRewardsDraft = null;
let activeJob = "", activeJobAgent = "", loadingJob = false, selectedHistory = null, agentSubmitting = false;
let jobRecoveryOwner = "", settingsDraft = null, settingsInlineCapture = null, visibilityRefreshRunning = false;
const sleepMobile = ms => new Promise(resolve => setTimeout(resolve,ms));
const chatSessionLoads = new Map(), chatRestoreLoads = new Map();
const chatSessionKey = owner => "hh-chat-session:"+owner;
const validChatSessionId = value => /^[A-Za-z0-9_-]{6,80}$/.test(String(value||""));
function createChatSessionId(){return crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,"0")).join("");}
function chatCacheKey(owner,agent,sessionId=""){
  if(agent!=="ledger_query")return "chat:"+owner+":"+agent;
  const id=sessionId||localStorage.getItem(chatSessionKey(owner))||"legacy";
  return "chat:"+owner+":"+agent+":"+id;
}
function ensureChatSessionId(owner=currentUser?.id){
  if(!owner)return Promise.resolve("");
  const key=chatSessionKey(owner),stored=localStorage.getItem(key);
  if(validChatSessionId(stored))return Promise.resolve(stored);
  if(chatSessionLoads.has(owner))return chatSessionLoads.get(owner);
  const pending=(async()=>{
    // Preserve visible legacy history only when it exists. An empty transcript
    // means “New chat” was already chosen; old server-side intent must be isolated.
    let legacy=[];try{legacy=await cacheGet("chat:"+owner+":ledger_query")||[];}catch{}
    const id=Array.isArray(legacy)&&legacy.length?"legacy":createChatSessionId();
    localStorage.setItem(key,id);
    if(id==="legacy")try{await cacheSet(chatCacheKey(owner,"ledger_query",id),legacy);}catch{}
    return id;
  })();
  chatSessionLoads.set(owner,pending);
  return pending;
}

function numericUsage(usage,key){const value=Number(usage?.[key]||0);return Number.isFinite(value)&&value>0?Math.floor(value):0;}
function selectedUsageProfile(agent,vision){
  const preferences=workspace?.preferences||{},profileAgent=agent==="ledger_query"?"bookkeeping":agent,profileId=(vision?preferences.visionAgents:preferences.agents)?.[profileAgent];
  return (preferences.profiles||[]).find(profile=>profile.id===profileId)||null;
}
function deepSeekPricePeriod(at=new Date()){
  const parts=new Intl.DateTimeFormat("en-US",{timeZone:"Asia/Shanghai",weekday:"short",hour:"2-digit",hourCycle:"h23"}).formatToParts(at);
  const values=Object.fromEntries(parts.map(part=>[part.type,part.value])),hour=Number(values.hour);
  const weekday=["Mon","Tue","Wed","Thu","Fri"].includes(values.weekday);
  return weekday&&((hour>=9&&hour<12)||(hour>=14&&hour<18))?"peak":"offpeak";
}
function estimateModelUsageCost(usage,profile,at=new Date(),legacy=false){
  if(!usage||!profile)return null;
  let host="";try{host=new URL(String(profile.api_url||"")).hostname.toLowerCase();}catch{return null;}
  if(host!=="api.deepseek.com"&&!host.endsWith(".deepseek.com"))return null;
  const model=String(profile.model||"").trim().toLowerCase();
  const isFlash=["deepseek-flash","deepseek-v4-flash","deepseek-v4-flash-vision-exp"].includes(model);
  const isPro=model==="deepseek-v4-pro";
  if(!isFlash&&!isPro)return null;
  const period=deepSeekPricePeriod(at),peak=period==="peak";
  const rates=isFlash?{hit:peak?0.04:0.02,miss:peak?2:1,output:peak?8:4}:{hit:peak?0.30:0.15,miss:peak?9:4.5,output:peak?27:13.5};
  const perMillion=key=>numericUsage(usage,key)*rates[key==="cache_hit_tokens"?"hit":key==="cache_miss_tokens"?"miss":"output"]/1_000_000;
  return {available:true,currency:"CNY",model:isFlash?"deepseek-flash":"deepseek-v4-pro",period,
    hit_cny:perMillion("cache_hit_tokens"),miss_cny:perMillion("cache_miss_tokens"),output_cny:perMillion("completion_tokens"),estimated:true,legacy:!!legacy};
}
function usagePriceForMessage(usage,agent){
  if(Object.hasOwn(usage||{},"cost_cny"))return usage.cost_cny?.available?usage.cost_cny:null;
  return estimateModelUsageCost(usage,selectedUsageProfile(agent,!!usage?.vision),new Date(),true);
}
function formatRmbCost(value,estimated=true){
  const amount=Number(value);if(!Number.isFinite(amount)||amount<0)return "—";
  const rounded=Number(amount.toFixed(6));
  if(amount>0&&rounded===0)return (estimated?"≈":"")+"<¥0.000001";
  return (estimated?"≈":"")+"¥"+rounded.toLocaleString("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:6});
}
function usageCostLabels(usage,agent){
  const cost=usagePriceForMessage(usage,agent);
  return m("命中","キャッシュ命中","Hit")+" "+formatRmbCost(cost?.hit_cny)+" · "+m("未命中","キャッシュ未命中","Miss")+" "+formatRmbCost(cost?.miss_cny)+" · "+m("输出","出力","Output")+" "+formatRmbCost(cost?.output_cny);
}
function usageTotals(messages){
  return {requests:(messages||[]).reduce((count,message)=>message?.role==="assistant"&&message.usage?count+(numericUsage(message.usage,"requests")||1):count,0)};
}
function renderModelUsagePanel(){
  const panel=$("#modelUsagePanel");if(!panel)return;
  const messages=chats[chatAgent]||[],latest=[...messages].reverse().find(item=>item?.role==="assistant"&&item.usage)?.usage;
  const total=usageTotals(messages),balanceKey=chatAgent+":"+((latest?.vision??(currentUsageVision||attachments.length))?"vision":"text"),balance=modelBalances[balanceKey];
  const metric=(label,value)=>'<div class="usage-metric"><span>'+label+'</span><strong>'+e(value)+'</strong></div>';
  const latestCost=latest?usagePriceForMessage(latest,chatAgent):null;
  const perTurn=latest?metric(m("命中","キャッシュ命中","Hit"),formatRmbCost(latestCost?.hit_cny))+metric(m("未命中","キャッシュ未命中","Miss"),formatRmbCost(latestCost?.miss_cny))+metric(m("输出","出力","Output"),formatRmbCost(latestCost?.output_cny)):'<span class="usage-empty">'+m("发送消息后显示本轮费用","送信後に今回の費用を表示","Cost appears after a reply")+'</span>';
  const balanceText=balance?.available&&balance.balances?.length?balance.balances.map(item=>e(item.currency)+" "+e(item.total)).join(" · "):balance?.reason==="unsupported_provider"?m("当前服务暂不提供余额查询","このサービスの残高照会には未対応です","Balance lookup is not available for this provider"):balance?.reason==="not_configured"?m("先配置并选择 API 服务","APIサービスを設定・選択してください","Configure and select an API service first"):balance?.error?m("余额暂时无法读取","残高を読み取れません","Balance temporarily unavailable"):balance?m("服务商暂未返回余额","サービスから残高が返されませんでした","The provider did not return a balance"):m("正在读取余额…","残高を確認中…","Checking balance…");
  const spend=modelBalanceSpend[balanceKey];
  panel.innerHTML='<div class="usage-panel-head"><strong>'+m("模型费用 · 人民币估算","モデル費用・人民元の概算","Estimated model cost · CNY")+'</strong><span>'+m("本聊天请求","この会話のリクエスト","Chat requests")+' · '+total.requests+'</span></div><div class="usage-panel-current">'+perTurn+'</div><div class="usage-panel-foot"><span>'+m("当前余额","現在の残高","Balance")+'：'+balanceText+'</span><span>'+m("本轮余额变化","今回の残高変化","Balance change")+'：'+(spend?e(spend):m("待更新","更新待ち","Pending update"))+'</span></div>';
}
async function refreshModelBalance(agent=chatAgent,vision=false,{force=false}={}){
  const key=agent+":"+(vision?"vision":"text");
  if(!currentUser||!navigator.onLine||!serverReachable){modelBalances[key]={error:true};if(agent===chatAgent)renderModelUsagePanel();return null;}
  if(modelBalanceRequests[key])return modelBalanceRequests[key];
  if(!force&&modelBalances[key]&&Date.now()-(modelBalanceCheckedAt[key]||0)<60000){if(agent===chatAgent)renderModelUsagePanel();return modelBalances[key];}
  modelBalances[key]={...(modelBalances[key]||{}),loading:true};if(agent===chatAgent)renderModelUsagePanel();
  const owner=currentUser.id;
  modelBalanceRequests[key]=(async()=>{
    try{
      const result=await api('/api/model-balance?agent='+encodeURIComponent(agent)+'&vision='+(vision?'1':'0'));
      if(currentUser?.id!==owner)return null;
      modelBalances[key]=result;modelBalanceCheckedAt[key]=Date.now();
      if(agent===chatAgent){renderModelUsagePanel();}
      return result;
    }catch{
      if(currentUser?.id===owner){modelBalances[key]={error:true};modelBalanceCheckedAt[key]=Date.now();if(agent===chatAgent)renderModelUsagePanel();}
      return null;
    }finally{delete modelBalanceRequests[key];}
  })();
  return modelBalanceRequests[key];
}

function mountMobile() {
  const app=$("#appScreen"), heading=$(".page-heading",app), banner=$("#offlineBanner");
  const accounts=$(".accounts-panel"), entry=$(".entry-panel"), queue=$(".queue-panel"), history=$(".history-panel");
  $(".table-scroll",history).classList.add("legacy-table");
  const legacyNote=$(".privacy-note",app); legacyNote?.remove();
  app.replaceChildren(...[heading,$("#githubBackupWarning"),$("#githubLinkBanner"),banner].filter(Boolean));
  heading.classList.add("mobile-heading");
  heading.querySelector("h1").removeAttribute("data-i18n");
  const tools=document.createElement("div"); tools.className="heading-tools";
  tools.innerHTML=b("privacy",icon("eye"),"","icon-button")+b("refresh",icon("repeat"),"","icon-button");
  heading.append(tools);
  for(const name of ["home","entry","ledger","investment","assets","more"]) {
    const section=document.createElement("section"); section.id="page-"+name; section.className="mobile-page";
    section.dataset.page=name; app.append(section);
  }
  $("#page-entry").innerHTML='<div id="agentPanel" class="panel chat-panel"></div><details class="panel manual-entry"><summary>'+m("手动记一笔","手入力で記帳","Manual entry")+'</summary></details>';
  $("#page-investment").innerHTML='<div id="investmentPanel"></div>';
  $(".manual-entry").append(entry);
  $("#page-assets").innerHTML='<div id="assetTabs" class="mode-pills"></div><div id="creditPanel"></div><div id="fixedPanel"></div>';
  $("#page-assets").append(accounts);
  const accountHeading=$(".accounts-panel .section-heading"),accountViewActions=document.createElement("div");
  accountViewActions.id="accountViewActions";
  accountViewActions.className="account-view-actions";
  accountViewActions.setAttribute("role","group");
  accountViewActions.setAttribute("aria-label",m("账户显示方式","口座の表示方法","Account display"));
  accountViewActions.innerHTML='<button type="button" class="icon-button account-view-toggle" data-action="account-layout" data-id="list" aria-label="'+e(m("横向排布","横並び表示","Row layout"))+'" title="'+e(m("横向排布","横並び表示","Row layout"))+'">'+icon("list")+'</button><button type="button" class="icon-button account-view-toggle" data-action="account-layout" data-id="cards" aria-label="'+e(m("卡片排布","カード表示","Card layout"))+'" title="'+e(m("卡片排布","カード表示","Card layout"))+'">'+icon("grid")+'</button>';
  accountViewActions.append($("#showAccountForm"));
  accountHeading?.append(accountViewActions);
  renderAccountViewControls();
  $("#page-ledger").append(history);
  const filters=document.createElement("div"); filters.id="historyFilters"; filters.className="history-filters";
  filters.innerHTML='<input id="historySearch" type="search" placeholder="'+m("搜索说明、账户或类别","内容・口座・カテゴリを検索","Search entries, accounts or categories")+'" aria-label="'+m("搜索账单","取引を検索","Search transactions")+'"><div class="date-range"><input id="historyStart" type="date" aria-label="'+m("开始日期","開始日","Start date")+'"><span>—</span><input id="historyEnd" type="date" aria-label="'+m("结束日期","終了日","End date")+'"></div>';
  history.insertBefore(filters,$(".table-scroll",history));
  const list=document.createElement("div"); list.id="ledgerList"; list.className="ledger-list"; history.append(list);
  for(const id of ["historySearch","historyStart","historyEnd"]) $("#"+id).addEventListener("input",()=>{renderMobileTransactions();if(id!=="historySearch"){clearTimeout(ledgerSearchTimer);ledgerSearchTimer=setTimeout(()=>guarded(loadLedgerRange),450);}});
  $("#page-more").innerHTML='<div id="moreMenu"></div><section id="modulePanel" class="hidden"></section><section id="backupPage" class="hidden"><div id="cloudControls"></div></section>';
  $("#backupPage").append(queue);
  const nav=document.createElement("nav"); nav.id="bottomNav"; nav.className="glass bottom-nav"; nav.setAttribute("aria-label",m("主导航","メインナビゲーション","Main navigation")); app.append(nav);
  const dlg=document.createElement("dialog"); dlg.id="editorDialog"; dlg.className="editor-sheet";
  dlg.innerHTML='<form id="editorForm" autocomplete="off"><header class="sheet-heading"><button type="button" id="editorCancel" class="text-button"></button><h2 id="editorTitle"></h2><button type="submit" class="text-button accent" id="editorSave"></button></header><div id="editorBody" class="sheet-body"></div><footer id="editorFooter" class="sheet-footer"></footer></form>';
  document.body.append(dlg);
  $("#editorCancel").addEventListener("click",()=>dlg.close());
  dlg.addEventListener("click",event=>{if(event.target===dlg)dlg.close();});
  const device=document.createElement("dialog"); device.id="deviceDialog";device.className="dialog-card";
  device.innerHTML='<h2>GitHub</h2><p id="deviceHelp"></p><div id="deviceCode" class="device-code"></div><div id="deviceLinks"></div><button id="deviceClose" type="button" class="button secondary">'+m("暂时收起","閉じる","Dismiss")+'</button>';
  document.body.append(device);$("#deviceClose").onclick=()=>device.close();
  document.addEventListener("click",handleMobileClick);
  document.addEventListener("change",event=>{if(event.target.id==="reportDate"){reportDate=event.target.value;guarded(()=>loadWorkspace(true));}});
  renderNavigation(); renderAgent();
  window.addEventListener("online",()=>loadWorkspace(true));
  if(window.visualViewport) window.visualViewport.addEventListener("resize",()=>{
    const raised=window.innerHeight-window.visualViewport.height>140;
    document.body.classList.toggle("keyboard-visible",raised);
  });
}

function renderNavigation() {
  const labels={home:m("总览","概要","Today"),entry:m("记账","記帳","Record"),ledger:m("账单","明細","Ledger"),investment:m("投资","投資","Invest"),assets:m("余额","残高","Balances"),more:m("更多","その他","More")};
  const iconsByPage={home:"home",entry:"chat",ledger:"book",investment:"investment",assets:"wallet",more:"more"};
  $("#bottomNav").innerHTML=Object.keys(labels).map(name=>'<button data-action="page" data-id="'+name+'" class="nav-item '+(selectedPage===name?"active":"")+'" aria-current="'+(selectedPage===name?"page":"false")+'">'+icon(iconsByPage[name])+'<span>'+labels[name]+'</span></button>').join("");
  for(const page of $$(".mobile-page"))page.classList.toggle("hidden",page.dataset.page!==selectedPage);
  const pageTitle=$(".page-heading h1"),pageEyebrow=$(".page-heading .eyebrow");
  if(pageTitle)pageTitle.textContent=labels[selectedPage];
  if(pageEyebrow)pageEyebrow.textContent=m("生活，有迹可循","暮らしを、ていねいに","A little more clarity");
}
function renderAccountViewControls() {
  const grid=$("#accountGrid");
  grid?.classList.toggle("is-list",accountViewMode==="list");
  const labels={cards:m("卡片排布","カード表示","Card layout"),list:m("横向排布","横並び表示","Row layout")};
  $$("#accountViewActions [data-action='account-layout']").forEach(button=>{
    const selected=button.dataset.id===accountViewMode;
    button.classList.toggle("selected",selected);
    button.setAttribute("aria-pressed",selected?"true":"false");
    button.setAttribute("aria-label",labels[button.dataset.id]||"");
    button.title=labels[button.dataset.id]||"";
  });
}
function resetMorePageState(){settingsInlineCapture?.();settingsInlineCapture=null;paymentRulesDraft=null;pointRewardsDraft=null;moreTab="";favoritesEditing=false;settingsTab="general";}
function navigate(page) {
  if(selectedPage==="more"&&(page!=="more"||(page==="more"&&moreTab)))resetMorePageState();
  selectedPage=page;renderNavigation();window.scrollTo({top:0,behavior:"instant"});if(page==="more")renderMore();
  if(page==="investment")void refreshInvestmentQuotes();
}
function workspaceLoadError(error) {
  if(error?.status===401)return m("登录已过期，请退出后重新登录。","ログインの有効期限が切れました。再ログインしてください。","Your session expired. Sign out and sign in again.");
  const cloud=typeof runtimeConfig!=="undefined"&&runtimeConfig?.deploymentMode==="cloud";
  if(error?.status)return m(cloud?"云端服务未能读取账本：":"电脑服务未能读取账本：",cloud?"クラウドサービスで台帳を読み込めません：":"PC側で台帳を読み込めません：",cloud?"The cloud service could not read the ledger: ":"The computer could not read the ledger: ")+error.message;
  if(error?.name==="AbortError")return cloud?m("云端账本加载超时，请稍后重试。","クラウド台帳の読み込みがタイムアウトしました。後で再試行してください。","Loading the cloud ledger timed out. Please try again."):m("账本加载超时。请确认电脑服务仍在运行，然后重试。","台帳の読み込みがタイムアウトしました。PC側のサービスを確認して再試行してください。","Ledger loading timed out. Check that the computer service is running, then retry.");
  return cloud?m("暂时无法连接云端服务，请检查网络后重试。","クラウドサービスに接続できません。通信を確認して再試行してください。","Cannot reach the cloud service. Check your connection and try again."):m("暂时连不上电脑。电脑连接本手机热点也可以；请保持热点和电脑记账服务开启，并确认当前访问地址。","PCに接続できません。この端末のテザリングでも利用できます。テザリングとPC側のサービスを有効にし、アクセス先のアドレスを確認してください。","Cannot reach the computer. This phone's hotspot is supported; keep the hotspot and computer service on and check the current address.");
}
async function readLedger(path,options={}) {
  // Retry reads only. A transient Worker/network failure must never resubmit a
  // successful Agent action or a transaction from the offline queue.
  for(let attempt=0;;attempt++){
    try{return await api(path,options);}
    catch(error){
      const retryable=error?.name!=="AbortError"&&(!error.status||[408,429,500,502,503,504].includes(error.status));
      if(attempt>=1||!retryable||options.signal?.aborted)throw error;
      await sleepMobile(400);
    }
  }
}
async function applyPreparedPreview(item, pending=true, render=true) {
  if(!item||item.ownerId!==currentUser?.id||item.type!=="prepared_agent"||!item.preview)return;
  const preview=item.preview;
  if(!workspace||workspaceOwner!==currentUser.id){
    workspace=null;
    if(!cachedBootstrap||workspaceOwner!==currentUser.id)cachedBootstrap={accounts:[],categories:[],transactions:[]};
    workspaceOwner=currentUser.id;
  }
  if(!workspace){
    const rows=new Map((cachedBootstrap.transactions||[]).map(row=>[String(row.id),row]));
    for(const source of preview.transactions||[])rows.set(String(source.id),{...source,pendingSync:Boolean(pending),pendingAgentOpId:item.opId,conflict:Boolean(item.conflict)});
    cachedBootstrap.transactions=[...rows.values()].sort((a,b)=>String(b.occurred_on||"").localeCompare(String(a.occurred_on||""))||Number(b.id||0)-Number(a.id||0)).slice(0,100);
    if(!item.conflict&&Array.isArray(preview.accounts))cachedBootstrap.accounts=deepCopy(preview.accounts);
    await cacheSet("bootstrap:"+currentUser.id,cachedBootstrap).catch(()=>{});
    return;
  }
  if(!item.conflict)for(const [key,value] of Object.entries(preview)){
    if(!["accounts","transactions"].includes(key))workspace[key]=deepCopy(value);
  }
  const rows=new Map((workspace.transactions||[]).map(row=>[String(row.id),row]));
  for(const source of preview.transactions||[]){
    const row={...source,pendingSync:Boolean(pending),pendingAgentOpId:item.opId,conflict:Boolean(item.conflict)};
    rows.set(String(row.id),row);
  }
  workspace.transactions=[...rows.values()].sort((a,b)=>String(b.occurred_on||"").localeCompare(String(a.occurred_on||""))||Number(b.id||0)-Number(a.id||0)).slice(0,2000);
  cachedBootstrap=cachedBootstrap||{accounts:[],categories:[],transactions:[]};
  if(!item.conflict&&Array.isArray(preview.accounts))cachedBootstrap.accounts=deepCopy(preview.accounts);
  const bootstrapRows=new Map((cachedBootstrap.transactions||[]).map(row=>[String(row.id),row]));
  for(const row of preview.transactions||[])bootstrapRows.set(String(row.id),{...row,pendingSync:Boolean(pending),pendingAgentOpId:item.opId,conflict:Boolean(item.conflict)});
  cachedBootstrap.transactions=[...bootstrapRows.values()].sort((a,b)=>String(b.occurred_on||"").localeCompare(String(a.occurred_on||""))||Number(b.id||0)-Number(a.id||0)).slice(0,100);
  await Promise.allSettled([cacheSet("workspace:"+currentUser.id,workspace),cacheSet("bootstrap:"+currentUser.id,cachedBootstrap)]);
  if(render&&currentUser?.id===item.ownerId)renderMobile();
}
function applyQueuedTransaction(item,pending=true){
  if(!item||item.type!=="transaction"||item.ownerId!==currentUser?.id)return;
  if(!workspace||workspaceOwner!==currentUser.id)return;
  const data=item.data||{},accounts=cachedBootstrap?.accounts||[];
  const source=accounts.find(row=>row.name===data.accountName)||{};
  const destination=accounts.find(row=>row.name===data.toAccountName)||{};
  const currency=String(data.currency||source.currency||"JPY");
  const row={id:"pending-"+item.opId,localQueueOpId:item.opId,pendingSync:Boolean(pending),
    occurred_on:String(data.date||""),kind:String(data.kind||"expense"),amount_minor:parseMinorPreview(data.amount,currency),
    currency,description:String(data.description||""),category_name:String(data.categoryName||""),
    account_name:String(data.accountName||""),account_type:source.type||"",currency_minor_digits:source.minorDigits??(["CNY","USD"].includes(currency)?2:0),
    minor_digits:source.minorDigits??(["CNY","USD"].includes(currency)?2:0),to_account_name:String(data.toAccountName||""),
    to_account_type:destination.type||"",to_currency:destination.currency||currency,
    to_amount_minor:data.toAmount?parseMinorPreview(data.toAmount,destination.currency||currency):null,
    to_minor_digits:destination.minorDigits??(["CNY","USD"].includes(destination.currency||currency)?2:0),needs_review:false,balance_effect:"posted"};
  const rows=new Map((workspace.transactions||[]).map(value=>[String(value.localQueueOpId||value.id),value]));
  if(pending)rows.set(item.opId,row);else if(rows.has(item.opId))rows.set(item.opId,{...rows.get(item.opId),pendingSync:false});
  workspace.transactions=[...rows.values()].sort((a,b)=>String(b.occurred_on||"").localeCompare(String(a.occurred_on||""))||((a.pendingSync===b.pendingSync)?Number(b.id||0)-Number(a.id||0):a.pendingSync?-1:1)).slice(0,2000);
  if(cachedBootstrap){
    const bootstrapRows=new Map((cachedBootstrap.transactions||[]).map(value=>[String(value.localQueueOpId||value.id),value]));
    if(pending)bootstrapRows.set(item.opId,row);else if(bootstrapRows.has(item.opId))bootstrapRows.set(item.opId,{...bootstrapRows.get(item.opId),pendingSync:false});
    cachedBootstrap.transactions=[...bootstrapRows.values()].sort((a,b)=>String(b.occurred_on||"").localeCompare(String(a.occurred_on||""))||((a.pendingSync===b.pendingSync)?Number(b.id||0)-Number(a.id||0):a.pendingSync?-1:1)).slice(0,100);
  }
}
const LOCAL_FIRST_ACTIONS=new Set(["settings","onboarding_save","payment_rules","point_rewards","edit_transaction","review_transaction","delete_account","rename_account","reconcile","asset","asset_toggle","delete_asset","recurring","recurring_toggle","delete_recurring","budget","credit_plan","credit_plan_toggle","credit_plan_delete","credit_repay","credit_snapshot","restore_credit","food_purchase","food_eaten","food_group","food_preference","delete_food","category","category_translation","investment_save","run_due"]);
function pendingActionLabel(action,data={}){
  const labels={settings:m("设置更改","設定変更","Settings change"),onboarding_save:m("新手设置","初期設定","Initial setup"),payment_rules:m("支付规则","支払ルール","Payment rules"),point_rewards:m("积分返还规则","ポイント還元ルール","Points reward rules"),edit_transaction:m("修改账目","取引の編集","Edit transaction"),review_transaction:m("核对账目","取引の確認","Review transaction"),delete_account:m("删除账户","口座の削除","Delete account"),rename_account:m("更改账户称呼","口座名の変更","Rename account"),reconcile:m("核对余额","残高の照合","Reconcile balance"),asset:m("固定资产更改","固定資産の変更","Asset change"),asset_toggle:m("固定资产更改","固定資産の変更","Asset change"),delete_asset:m("删除固定资产","固定資産の削除","Delete asset"),recurring:m("定期账目更改","定期取引の変更","Recurring entry change"),recurring_toggle:m("定期账目更改","定期取引の変更","Recurring entry change"),delete_recurring:m("删除定期账目","定期取引の削除","Delete recurring entry"),budget:m("预算更改","予算の変更","Budget change"),credit_plan:m("信用卡计划更改","カード返済予定の変更","Credit plan change"),credit_plan_toggle:m("信用卡计划更改","カード返済予定の変更","Credit plan change"),credit_plan_delete:m("删除信用卡计划","カード返済予定の削除","Delete credit plan"),credit_repay:m("信用卡还款记录","カード返済記録","Credit repayment"),credit_snapshot:m("额度记录","利用枠の記録","Credit snapshot"),restore_credit:m("恢复额度记录","利用枠の復元","Restore credit snapshot"),food_purchase:m("食品采购记录","食品購入記録","Food purchase"),food_eaten:m("饮食记录","食事記録","Meal record"),food_group:m("食品分类更改","食品分類の変更","Food group change"),food_preference:m("饮食设置更改","食生活設定の変更","Food settings change"),delete_food:m("删除食品记录","食品記録の削除","Delete food record"),category_translation:m("类别名称更改","カテゴリ名の変更","Category name change"),investment_save:m("投资持仓更改","投資保有情報の変更","Investment holding change"),run_due:m("处理到期项目","期日の処理","Process due entries"),agent_reset:m("新对话设置","新しい会話","New conversation")};
  const row=action==="edit_transaction"?findTransactionById(data.id):null;
  return action==="delete_account"&&data.name?labels[action]+" · "+data.name:action==="rename_account"&&data.oldName?labels[action]+" · "+data.oldName+" → "+data.name:action==="edit_transaction"&&row?labels[action]+" · "+row.description:labels[action]||m("账本更改","台帳の変更","Ledger change");
}
function safeSettingsPreview(value){
  const cfg=deepCopy(value||{}),old=workspace?.preferences||{};
  cfg.profiles=(cfg.profiles||[]).map(profile=>{const previous=(old.profiles||[]).find(row=>row.id===profile.id)||{};const next={...profile};if(next.api_key){next.keyPresent=true;delete next.api_key;}if(previous.keyPresent)next.keyPresent=true;return next;});
  for(const provider of ["github","gitee"])if(cfg.cloud?.[provider]){const previous=old.cloud?.[provider]||{};for(const key of ["token","refresh_token","client_secret","api_key"])delete cfg.cloud[provider][key];if(previous.connected)cfg.cloud[provider].connected=true;}
  return cfg;
}
function buildPendingActionPreview(action,data,opId){
  let previewData=deepCopy(data||{});const previous={};
  if(action==="investment_save")previous.investments=deepCopy(workspace?.investments||[]);
  if(action==="settings"){previewData=safeSettingsPreview(data);previous.preferences=deepCopy(workspace?.preferences||{});previous.settings=deepCopy(workspace?.settings||{});}
  if(action==="onboarding_save"){previewData.settings=safeSettingsPreview(data.settings||{});previous.preferences=deepCopy(workspace?.preferences||{});previous.settings=deepCopy(workspace?.settings||{});}
  if(["payment_rules","point_rewards","budget","food_preference"].includes(action)){previous.preferences=deepCopy(workspace?.preferences||{});previous.settings=deepCopy(workspace?.settings||{});}
  if(["edit_transaction","review_transaction"].includes(action)){const id=String(data.id);previewData.transactionId=id;previous.transaction=deepCopy((workspace?.transactions||[]).find(row=>String(row.id)===id)||null);previous.bootstrapTransaction=deepCopy((cachedBootstrap?.transactions||[]).find(row=>String(row.id)===id)||null);previous.rangeTransaction=deepCopy((ledgerRangeRows||[]).find(row=>String(row.id)===id)||null);}
  if(["credit_snapshot","credit_repay","credit_plan","credit_plan_toggle","credit_plan_delete","restore_credit"].includes(action)){
    const requestedCardId=String(data.accountId||"");
    const card=(workspace?.cards||[]).find(row=>requestedCardId&&String(row.account_id)===requestedCardId)
      ||(workspace?.cards||[]).find(row=>row.name===String(data.account||data.card||""))||null;
    previewData.cardAccountId=String(card?.account_id||requestedCardId);
    previewData.cardName=String(card?.name||data.account||data.card||"");
    if(card)previous.creditCard=deepCopy(card);
    if(card)previous.creditCardAccount=deepCopy((cachedBootstrap?.accounts||[]).find(row=>String(row.id)===String(card.account_id))||null);
    if(card)previous.creditHistory=deepCopy(workspace?.creditHistory?.[String(card.account_id)]||null);
    if(action==="credit_snapshot"){
      previous.balanceSheet=deepCopy(workspace?.balanceSheet||null);
      previous.reportBalanceSheet=deepCopy(workspace?.reports?.balanceSheet||null);
    }
    if(card)previous.creditRepaymentPlan=deepCopy((workspace?.repaymentPlans||[]).find(row=>String(row.card_account_id)===String(card.account_id))||null);
    if(action==="credit_repay"){
      const sourceName=String(data.source||"");
      previewData.sourceName=sourceName;
      previous.creditSourceAccount=deepCopy((cachedBootstrap?.accounts||[]).find(row=>row.name===sourceName)||null);
      previous.creditSourceCash=deepCopy((workspace?.cash||[]).find(row=>row.account_name===sourceName)||null);
      previewData.localCommitComplete=Boolean(card&&previous.creditSourceAccount&&previous.creditSourceAccount.currency===card.currency);
    }
    const reportCurrency=String(workspace?.settings?.base_currency||workspace?.preferences?.baseCurrency||"JPY").toUpperCase();
    previewData.localCommitComplete=Boolean(card)&&(
      action==="credit_plan"||action==="credit_plan_toggle"||action==="credit_plan_delete"||
      (action==="credit_snapshot"&&!data.includeDifference&&card.debt_estimate_minor!==null&&card.currency===reportCurrency&&String(data.date||workspace.date)===String(workspace.date))||
      (action==="credit_repay"&&card.debt_estimate_minor!==null&&card.currency===reportCurrency&&Boolean(previous.creditSourceAccount&&previous.creditSourceAccount.currency===card.currency))
    );
    if(action==="restore_credit"){
      const history=workspace?.creditHistory?.[previewData.cardAccountId];
      previewData.localCommitComplete=previewData.localCommitComplete&&Boolean((history?.snapshots||[]).some(row=>String(row.id)===String(data.snapshotId)&&String(row.snapshot_type)===String(data.snapshotType)));
    }
  }
  if(action==="category_translation")previous.category=deepCopy((cachedBootstrap?.categories||[]).find(row=>String(row.id)===String(data.id))||null);
  if(["asset","asset_toggle","delete_asset"].includes(action))previous.asset=deepCopy((workspace?.assets||[]).find(row=>String(row.id)===String(data.id))||null);
  if(["recurring","recurring_toggle","delete_recurring"].includes(action))previous.recurring=deepCopy((workspace?.recurring||[]).find(row=>String(row.id)===String(data.id))||null);
  if(action==="delete_food"){const key=data.kind==="purchase"?"food":"eaten";previewData.foodKey=key;previous.food=deepCopy((workspace?.[key]||[]).find(row=>String(row.id)===String(data.id))||null);}
  if(action==="delete_account")previous.account=deepCopy((cachedBootstrap?.accounts||[]).find(row=>String(row.name)===String(data.name))||null);
  if(action==="rename_account")previous.account=deepCopy((cachedBootstrap?.accounts||[]).find(row=>String(row.id)===String(data.accountId))||null);
  if(action==="reconcile")previous.accounts=deepCopy((cachedBootstrap?.accounts||[]).filter(row=>Object.hasOwn(data.amounts||{},row.name)));
  return {action,data:previewData,previous,transactionId:previewData.transactionId||"",opId};
}
function applyRenameAccountPreview(item,pending=true,rollback=false){
  const {data={},previous={}}=item.preview||{},account=previous.account;
  if(!account)return;
  const accountId=String(account.id),oldName=String(data.oldName||account.name||""),newName=rollback?oldName:String(data.name||oldName),fromName=rollback?String(data.name||oldName):oldName;
  const replaceFields=(rows,keys)=>{if(!Array.isArray(rows))return;for(const row of rows){if(!row||typeof row!=="object")continue;for(const key of keys)if(row[key]===fromName)row[key]=newName;}};
  if(cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.map(row=>{if(String(row.id)!==accountId)return row;const copy={...row,name:newName};if(rollback||!pending)delete copy.pendingSync;else copy.pendingSync=true;return copy;});
  for(const rows of [workspace?.cash])replaceFields(rows,["account_name","name"]);
  for(const rows of [workspace?.cards]){if(!Array.isArray(rows))continue;for(const row of rows)if(String(row.account_id)===accountId){row.name=newName;if(rollback||!pending)delete row.pendingSync;else row.pendingSync=true;}}
  for(const rows of [workspace?.transactions,cachedBootstrap?.transactions,ledgerRangeRows])replaceFields(rows,["account_name","to_account_name"]);
  for(const rows of [workspace?.recurring])replaceFields(rows,["account_name"]);
  for(const rows of [workspace?.repaymentPlans])replaceFields(rows,["card_name","source_name","account_name"]);
  for(const report of [workspace?.balanceSheet,workspace?.reports?.balanceSheet])replaceFields(report?.rows?.filter(row=>!String(row.section||"").includes("固定资产")),["name"]);
  const preferenceSets=[workspace?.preferences,workspace?.preferences?.paymentRules,workspace?.preferences?.profiles];
  for(const value of preferenceSets){const profiles=Array.isArray(value)?value:Array.isArray(value?.profiles)?value.profiles:null;if(!profiles)continue;for(const profile of profiles){if(profile.payment_method===fromName)profile.payment_method=newName;if(typeof profile.purpose==="string"&&fromName)profile.purpose=profile.purpose.split(fromName).join(newName);if(Array.isArray(profile.account_order))profile.account_order=profile.account_order.map(name=>name===fromName?newName:name);}}
}
function applyCreditLiabilityPreview(card,oldDebt,newDebt,effectiveDate){
  if(!card||oldDebt===null||oldDebt===undefined||newDebt===null||newDebt===undefined)return false;
  const delta=BigInt(newDebt)-BigInt(oldDebt),currency=String(card.currency||""),digits=Number(card.minor_digits||0);
  for(const balance of [workspace?.balanceSheet,workspace?.reports?.balanceSheet]){
    if(!balance||String(balance.as_of||"")<String(effectiveDate||""))continue;
    const row=(balance.rows||[]).find(value=>String(value.name)===String(card.name));
    if(row){row.amount_minor=String(newDebt);row.amount_text=money(newDebt,currency,digits);row.section=BigInt(newDebt)>0n?"信用卡负债估算":"信用卡";}
    balance.estimated_liabilities=balance.estimated_liabilities||{};
    balance.net_assets=balance.net_assets||{};
    balance.estimated_liabilities[currency]=String(BigInt(balance.estimated_liabilities[currency]||0)+delta);
    balance.net_assets[currency]=String(BigInt(balance.net_assets[currency]||0)-delta);
    if(String(balance.base_equivalent?.currency||"")===currency){
      balance.base_equivalent.estimated_liabilities_minor=String(BigInt(balance.base_equivalent.estimated_liabilities_minor||0)+delta);
      balance.base_equivalent.net_assets_minor=String(BigInt(balance.base_equivalent.net_assets_minor||0)-delta);
    }
  }
  return true;
}
function applyPendingActionPreview(item,pending=true,rollback=false){
  if(!item?.preview||item.ownerId!==currentUser?.id||!workspace||workspaceOwner!==currentUser.id)return;
  const {action,data={},previous={}}=item.preview;
  const previewCardId=String(data.cardAccountId||data.accountId||""),previewCardName=String(data.cardName||data.account||data.card||"");
  if(rollback){
    if(action==="investment_save"&&Array.isArray(previous.investments))workspace.investments=deepCopy(previous.investments);
    if(previous.preferences)workspace.preferences=deepCopy(previous.preferences);
    if(previous.settings)workspace.settings=deepCopy(previous.settings);
    if(["credit_snapshot","credit_repay","credit_plan","credit_plan_toggle","credit_plan_delete","restore_credit"].includes(action)){
      const cardId=previewCardId;
      if(previous.creditCard)workspace.cards=(workspace.cards||[]).map(row=>String(row.account_id)===String(previous.creditCard.account_id)?previous.creditCard:row);
      if(cardId&&workspace.creditHistory){if(previous.creditHistory)workspace.creditHistory[cardId]=deepCopy(previous.creditHistory);else delete workspace.creditHistory[cardId];}
      if(action==="credit_snapshot"){
        if(previous.balanceSheet)workspace.balanceSheet=deepCopy(previous.balanceSheet);
        if(previous.reportBalanceSheet&&workspace.reports)workspace.reports.balanceSheet=deepCopy(previous.reportBalanceSheet);
      }
      if(cardId&&Array.isArray(workspace.repaymentPlans)){
        workspace.repaymentPlans=workspace.repaymentPlans.filter(row=>String(row.card_account_id)!==cardId);
        if(previous.creditRepaymentPlan)workspace.repaymentPlans.push(deepCopy(previous.creditRepaymentPlan));
      }
      if(previous.creditSourceAccount&&cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.map(row=>String(row.id)===String(previous.creditSourceAccount.id)?previous.creditSourceAccount:row);
      if(previous.creditCardAccount&&cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.map(row=>String(row.id)===String(previous.creditCardAccount.id)?previous.creditCardAccount:row);
      if(previous.creditSourceCash&&Array.isArray(workspace.cash))workspace.cash=workspace.cash.map(row=>row.account_name===previous.creditSourceCash.account_name?previous.creditSourceCash:row);
      const pendingId="pending-"+item.opId;
      workspace.transactions=(workspace.transactions||[]).filter(row=>!String(row.id||"").startsWith(pendingId));
      if(cachedBootstrap?.transactions)cachedBootstrap.transactions=cachedBootstrap.transactions.filter(row=>!String(row.id||"").startsWith(pendingId));
      if(Array.isArray(ledgerRangeRows))ledgerRangeRows=ledgerRangeRows.filter(row=>!String(row.id||"").startsWith(pendingId));
    }
    if(["edit_transaction","review_transaction"].includes(action)&&previous.transaction){const id=item.preview.transactionId;const patch=rows=>Array.isArray(rows)?rows.map(row=>String(row.id)===id?{...previous.transaction,pendingSync:false}:row):rows;workspace.transactions=patch(workspace.transactions);if(cachedBootstrap?.transactions)cachedBootstrap.transactions=patch(cachedBootstrap.transactions);if(Array.isArray(ledgerRangeRows))ledgerRangeRows=patch(ledgerRangeRows);}
    if(action==="category_translation"&&previous.category&&cachedBootstrap?.categories)cachedBootstrap.categories=cachedBootstrap.categories.map(row=>String(row.id)===String(data.id)?previous.category:row);
    if(action==="category"&&cachedBootstrap?.categories)cachedBootstrap.categories=cachedBootstrap.categories.filter(row=>String(row.id)!=="pending-"+item.opId);
    if(["asset","asset_toggle","delete_asset"].includes(action)&&previous.asset){const rows=workspace.assets||[];workspace.assets=rows.some(row=>String(row.id)===String(previous.asset.id))?rows.map(row=>String(row.id)===String(previous.asset.id)?previous.asset:row):[...rows,previous.asset];}
    else if(action==="asset")workspace.assets=(workspace.assets||[]).filter(row=>String(row.id)!=="pending-"+item.opId);
    if(["recurring","recurring_toggle","delete_recurring"].includes(action)&&previous.recurring){const rows=workspace.recurring||[];workspace.recurring=rows.some(row=>String(row.id)===String(previous.recurring.id))?rows.map(row=>String(row.id)===String(previous.recurring.id)?previous.recurring:row):[...rows,previous.recurring];}
    else if(action==="recurring")workspace.recurring=(workspace.recurring||[]).filter(row=>String(row.id)!=="pending-"+item.opId);
    if(action==="delete_food"&&previous.food){const rows=workspace[data.foodKey]||[];workspace[data.foodKey]=rows.some(row=>String(row.id)===String(previous.food.id))?rows.map(row=>String(row.id)===String(previous.food.id)?previous.food:row):[previous.food,...rows];}
    if(action==="rename_account")applyRenameAccountPreview(item,false,true);
    if(action==="food_purchase"||action==="food_eaten"){const key=action==="food_purchase"?"food":"eaten";workspace[key]=(workspace[key]||[]).filter(row=>!String(row.id||"").startsWith("pending-"+item.opId));}
    if(action==="delete_account"&&previous.account&&cachedBootstrap?.accounts&&!cachedBootstrap.accounts.some(row=>String(row.id)===String(previous.account.id)))cachedBootstrap.accounts=[...cachedBootstrap.accounts,previous.account];
    if(action==="reconcile"&&cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.map(row=>previous.accounts?.find(old=>String(old.id)===String(row.id))||row);
    if(action==="onboarding_save"&&cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.filter(row=>!String(row.id||"").startsWith("pending-"+item.opId));
    return;
  }
  if(action==="investment_save"){
    investmentQuotes.clear();
    workspace.investments=(data.positions||[]).map(row=>{const currency=String(row.currency||"JPY"),digits=currencyMinorDigits(currency,0);return {...row,currency,fund_code:String(row.fundCode||row.fund_code||""),minor_digits:digits,cost_minor:parseMinorPreview(row.cost,currency,digits),value_minor:parseMinorPreview(row.value??row.cost,currency,digits),updated_on:String(row.updatedOn||workspace.date||""),pendingSync:pending,pendingActionOpId:pending?item.opId:""};});
  }else if(action==="settings"||action==="onboarding_save"){
    const cfg=data.settings||data;workspace.preferences={...(workspace.preferences||{}),...safeSettingsPreview(cfg)};
    if(cfg.timeZone){workspace.preferences.timeZone=cfg.timeZone;workspace.preferences.timeZoneConfigured=true;if(cachedBootstrap)cachedBootstrap.timeZone=cfg.timeZone;}
    workspace.settings={...(workspace.settings||{})};if(cfg.baseCurrency)workspace.settings.base_currency=cfg.baseCurrency;if(cfg.billingCycleStartDay)workspace.settings.billing_cycle_start_day=cfg.billingCycleStartDay;
  }else if(action==="payment_rules")workspace.preferences={...(workspace.preferences||{}),paymentRules:deepCopy(data.profiles||[])};
  else if(action==="point_rewards")workspace.preferences={...(workspace.preferences||{}),pointRewardRules:(data.rules||[]).map(rule=>({payment_account_id:Number(rule.payment_account_id),points_account_id:Number(rule.points_account_id),rate_bps:Number(rule.rate_bps),enabled:true}))};
  else if(action==="budget"){workspace.settings={...(workspace.settings||{}),monthly_jpy_budget_minor:String(data.total||"0"),savings_goal_jpy:String(data.goal||"0"),["savings_plan:"+(workspace.profit?.start||workspace.date||"")]:JSON.stringify({items:data.items||{}})};}
  else if(action==="credit_snapshot"){
    const card=(workspace.cards||[]).find(row=>String(row.account_id)===previewCardId)
      ||(workspace.cards||[]).find(row=>row.name===previewCardName);
    if(card){const digits=Number(card.minor_digits||0),limit=parseMinorPreview(data.limit,card.currency,digits),available=parseMinorPreview(data.available,card.currency,digits),oldDebt=card.debt_estimate_minor,newDebt=(BigInt(limit)-BigInt(available)).toString();applyCreditLiabilityPreview(card,oldDebt,newDebt,data.date||workspace.date);Object.assign(card,{limit_minor:limit,available_minor:available,debt_estimate_minor:newDebt,snapshot_date:data.date||workspace.date,pendingSync:pending,pendingActionOpId:pending?item.opId:""});
      const key=String(card.account_id),history=workspace.creditHistory||(workspace.creditHistory={}),entry=history[key]||(history[key]={snapshots:[],transactions:[]});
      if(!(entry.snapshots||[]).some(row=>String(row.id)==="pending-"+item.opId))entry.snapshots=[{id:"pending-"+item.opId,account_id:card.account_id,snapshot_date:data.date||workspace.date,limit_minor:limit,available_minor:available,note:String(data.note||""),created_at:new Date().toISOString(),transaction_id:null,snapshot_type:"manual",pendingSync:pending},...(entry.snapshots||[])];
    }
  }else if(action==="credit_repay"){
    const card=(workspace.cards||[]).find(row=>String(row.account_id)===previewCardId)
      ||(workspace.cards||[]).find(row=>row.name===previewCardName);
    const sourceName=String(item.preview.sourceName||data.source||""),source=(cachedBootstrap?.accounts||[]).find(row=>row.name===sourceName);
    if(card&&source){
      const amount=BigInt(parseMinorPreview(data.amount,card.currency)),date=String(data.date||workspace.date||""),digits=Number(card.minor_digits||0);
      if(source.currency===card.currency){
        source.balanceMinor=(BigInt(source.balanceMinor||0)-amount).toString();source.pendingSync=pending;source.pendingActionOpId=pending?item.opId:"";
        const cardAccount=(cachedBootstrap?.accounts||[]).find(row=>String(row.id)===String(card.account_id));if(cardAccount){cardAccount.balanceMinor=(BigInt(cardAccount.balanceMinor||0)-amount).toString();cardAccount.pendingSync=pending;cardAccount.pendingActionOpId=pending?item.opId:"";}
        const cash=(workspace.cash||[]).find(row=>row.account_name===sourceName);if(cash){cash.balance_minor=(BigInt(cash.balance_minor||0)-amount).toString();cash.pendingSync=pending;cash.pendingActionOpId=pending?item.opId:"";}
        const oldDebt=card.debt_estimate_minor;
        if(card.available_minor!==null&&card.available_minor!==undefined&&(!card.snapshot_date||date>=String(card.snapshot_date))){
          const limit=BigInt(card.limit_minor||0),available=BigInt(card.available_minor||0),next=available+amount;
          card.available_minor=(next>limit?limit:next).toString();card.debt_estimate_minor=(limit-BigInt(card.available_minor)).toString();
        }
        applyCreditLiabilityPreview(card,oldDebt,card.debt_estimate_minor,date);
        card.pendingSync=pending;card.pendingActionOpId=pending?item.opId:"";
        const tx={id:"pending-"+item.opId,occurred_on:date,kind:"transfer",amount_minor:amount.toString(),currency:card.currency,currency_minor_digits:digits,minor_digits:digits,description:String(data.description||(`${card.name}信用卡还款`)),account_name:sourceName,account_type:source.type||"",to_account_name:card.name,to_account_type:"credit",to_currency:card.currency,to_amount_minor:amount.toString(),to_minor_digits:digits,balance_effect:"posted",needs_review:"0",pendingSync:pending,pendingActionOpId:pending?item.opId:""};
        const upsert=(rows,limit)=>{const values=new Map((rows||[]).map(row=>[String(row.id),row]));values.set(String(tx.id),tx);return [...values.values()].sort((a,b)=>String(b.occurred_on||"").localeCompare(String(a.occurred_on||""))||Number(b.id||0)-Number(a.id||0)).slice(0,limit);};
        workspace.transactions=upsert(workspace.transactions,2000);if(cachedBootstrap)cachedBootstrap.transactions=upsert(cachedBootstrap.transactions,100);if(Array.isArray(ledgerRangeRows))ledgerRangeRows=upsert(ledgerRangeRows,2000);
        const history=workspace.creditHistory||(workspace.creditHistory={}),entry=history[String(card.account_id)]||(history[String(card.account_id)]={snapshots:[],transactions:[]});
        entry.transactions=[{id:tx.id,occurred_on:date,kind:"transfer",description:tx.description,created_at:new Date().toISOString(),card_amount_minor:amount.toString(),direction:"in",pendingSync:pending,pendingActionOpId:pending?item.opId:""},...(entry.transactions||[])].slice(0,100);
      }
    }
  }else if(action==="credit_plan"||action==="credit_plan_toggle"||action==="credit_plan_delete"){
    const card=(workspace.cards||[]).find(row=>String(row.account_id)===previewCardId)
      ||(workspace.cards||[]).find(row=>row.name===previewCardName);
    if(card){
      const current=card.repayment_schedule||{},old=(workspace.repaymentPlans||[]).find(row=>String(row.card_account_id)===String(card.account_id))||{};
      const next=action==="credit_plan"?{...old,...current,id:old.id||"pending-"+item.opId,card_account_id:card.account_id,card_name:card.name,source_name:String(data.source||""),source_account_id:(cachedBootstrap?.accounts||[]).find(row=>row.name===data.source)?.id||old.source_account_id,currency:card.currency,due_day:Number(String(data.date||workspace.date||"").slice(-2))||1,next_due_date:data.date||workspace.date,due_time:String(data.time||old.due_time||"09:00"),enabled:"1",amount_minor:data.amount?parseMinorPreview(data.amount,card.currency):null,amount_status:data.amount?"pending":null,last_status:data.amount?"本期金额已填写，等待还款日":"等待本期金额或还款日",pendingSync:pending,pendingActionOpId:pending?item.opId:""}:action==="credit_plan_delete"?{...old,...current,enabled:"0",amount_minor:null,amount_status:"cancelled",last_status:"计划已删除",pendingSync:pending,pendingActionOpId:pending?item.opId:""}:{...old,...current,enabled:data.enabled?"1":"0",last_status:data.enabled?"等待本期金额或还款日":"已暂停",pendingSync:pending,pendingActionOpId:pending?item.opId:""};
      card.repayment_schedule=next;card.pendingSync=pending;card.pendingActionOpId=pending?item.opId:"";
      const plans=workspace.repaymentPlans||(workspace.repaymentPlans=[]),index=plans.findIndex(row=>String(row.card_account_id)===String(card.account_id));if(index>=0)plans[index]=next;else plans.push(next);
    }
  }else if(action==="restore_credit"){
    const card=(workspace.cards||[]).find(row=>String(row.account_id)===previewCardId)
      ||(workspace.cards||[]).find(row=>row.name===previewCardName),history=workspace.creditHistory?.[previewCardId],snapshots=history?.snapshots||[];
    const selected=snapshots.find(row=>String(row.id)===String(data.snapshotId)&&String(row.snapshot_type)===String(data.snapshotType));
    if(card&&selected){
      const anchorDate=String(selected.snapshot_date||""),anchorCreated=String(selected.created_at||""),anchorTx=Number(selected.transaction_id||0);
      history.snapshots=snapshots.filter(row=>{
        const date=String(row.snapshot_date||""),created=String(row.created_at||""),tx=Number(row.transaction_id||0),rowId=Number(row.id||0);
        return date<anchorDate||(date===anchorDate&&(created<anchorCreated||(created===anchorCreated&&(tx<anchorTx||(tx===anchorTx&&rowId<=Number(selected.id||0))))));
      });
      let available=BigInt(selected.available_minor||0);
      for(const tx of history.transactions||[]){
        const date=String(tx.occurred_on||""),created=String(tx.created_at||""),transactionId=Number(tx.id||0);
        if(date<anchorDate||(date===anchorDate&&(created<anchorCreated||(created===anchorCreated&&transactionId<=anchorTx))))continue;
        const amount=BigInt(tx.card_amount_minor||0);
        if(tx.direction==="in"||tx.kind==="income")available+=amount;else available-=amount;
      }
      const limit=BigInt(selected.limit_minor||0);available=available<0n?0n:available>limit?limit:available;
      Object.assign(card,{limit_minor:limit.toString(),available_minor:available.toString(),debt_estimate_minor:(limit-available).toString(),snapshot_date:anchorDate,pendingSync:pending,pendingActionOpId:pending?item.opId:""});
    }
  }
  else if(action==="category"&&cachedBootstrap?.categories){const id="pending-"+item.opId;if(!cachedBootstrap.categories.some(row=>String(row.id)===id))cachedBootstrap.categories.push({id,name:String(data.name||""),kind:String(data.kind||"expense"),display_name:String(data.name||""),pendingSync:pending});}
  else if(action==="category_translation"&&cachedBootstrap?.categories)cachedBootstrap.categories=cachedBootstrap.categories.map(row=>String(row.id)===String(data.id)?{...row,display_name:String(data.name||row.display_name),pendingSync:pending}:row);
  else if(action==="edit_transaction"||action==="review_transaction"){
    const id=item.preview.transactionId,row=(workspace.transactions||[]).find(value=>String(value.id)===id)||(cachedBootstrap?.transactions||[]).find(value=>String(value.id)===id);
    if(row){const currency=data.currency||row.currency,digits=Number(row.currency_minor_digits??row.minor_digits??(["CNY","USD"].includes(currency)?2:0));const change=action==="edit_transaction"?{occurred_on:data.date||row.occurred_on,kind:data.kind||row.kind,description:data.description??row.description,currency,amount_minor:parseMinorPreview(data.amount,currency,digits),account_name:data.account_name||row.account_name,category_name:data.category_name||row.category_name,to_account_name:data.to_account_name||"",to_amount_minor:data.to_amount?parseMinorPreview(data.to_amount,row.to_currency||currency,Number(row.to_minor_digits??digits)):null,balance_effect:data.memo_only?"memo":"posted",needs_review:data.needs_review?"1":"0"}:{needs_review:"0",...(data.accountName?{account_name:data.accountName}:{}),...(data.account_name?{account_name:data.account_name}:{})};const patch=rows=>Array.isArray(rows)?rows.map(value=>String(value.id)===id?{...value,...change,pendingSync:pending,pendingActionOpId:pending?item.opId:""}:value):rows;workspace.transactions=patch(workspace.transactions);if(cachedBootstrap?.transactions)cachedBootstrap.transactions=patch(cachedBootstrap.transactions);if(Array.isArray(ledgerRangeRows))ledgerRangeRows=patch(ledgerRangeRows);}
  }else if(action==="delete_account"){if(cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.filter(row=>String(row.name)!==String(data.name));if(Array.isArray(workspace.cash))workspace.cash=workspace.cash.filter(row=>String(row.name)!==String(data.name));}
  else if(action==="rename_account")applyRenameAccountPreview(item,pending,false);
  else if(action==="reconcile"&&cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.map(row=>Object.hasOwn(data.amounts||{},row.name)?{...row,balanceMinor:parseMinorPreview(data.amounts[row.name],row.currency,Number(row.minor_digits||0)),pendingSync:pending}:row);
  else if(["asset","asset_toggle","delete_asset"].includes(action)){
    const rows=workspace.assets||(workspace.assets=[]),id=String(data.id||"pending-"+item.opId);
    if(action==="delete_asset")workspace.assets=rows.filter(row=>String(row.id)!==id);
    else if(action==="asset_toggle")workspace.assets=rows.map(row=>String(row.id)===id?{...row,include_in_balance_sheet:data.included?"1":"0",pendingSync:pending}:row);
    else{const currency=data.currency||"JPY",digits=["CNY","USD"].includes(currency)?2:0,row={id:data.id||id,name:data.name||"",currency,cost_minor:parseMinorPreview(data.cost,currency,digits),acquisition_month:data.month||workspace.date?.slice(0,7),useful_life_months:String(data.months||36),include_in_balance_sheet:data.included?"1":"0",disposal_month:data.disposal||"",minor_digits:digits,pendingSync:pending};workspace.assets=rows.some(value=>String(value.id)===id)?rows.map(value=>String(value.id)===id?row:value):[...rows,row];}
  }else if(["recurring","recurring_toggle","delete_recurring"].includes(action)){
    const rows=workspace.recurring||(workspace.recurring=[]),id=String(data.id||"pending-"+item.opId);
    if(action==="delete_recurring")workspace.recurring=rows.filter(row=>String(row.id)!==id);
    else if(action==="recurring_toggle")workspace.recurring=rows.map(row=>String(row.id)===id?{...row,enabled:data.enabled?"1":"0",pendingSync:pending}:row);
    else{const currency=data.currency||"JPY",digits=["CNY","USD"].includes(currency)?2:0,row={id:data.id||id,name:data.name||"",kind:data.kind||"expense",account_name:data.account||"",currency,amount_minor:parseMinorPreview(data.amount,currency,digits),category_name:data.category||"",frequency:data.frequency||"monthly",interval_count:String(data.interval||1),next_due_date:data.date||workspace.date,enabled:"1",minor_digits:digits,pendingSync:pending};workspace.recurring=rows.some(value=>String(value.id)===id)?rows.map(value=>String(value.id)===id?row:value):[...rows,row];}
  }else if(action==="food_purchase"||action==="food_eaten"){
    const key=action==="food_purchase"?"food":"eaten",rows=workspace[key]||(workspace[key]=[]);(data.items||[]).forEach((tuple,index)=>{const name=String(tuple?.[0]||"");if(name)rows.unshift(action==="food_purchase"?{id:"pending-"+item.opId+"-"+index,item_name:name,purchase_date:data.date,quantity_text:String(tuple?.[1]||""),food_group:"other",pendingSync:pending}:{id:"pending-"+item.opId+"-"+index,item_name:name,consumed_on:data.date,meal:data.meal||"",quantity_text:String(tuple?.[1]||""),pendingSync:pending});});
  }else if(action==="food_group"&&workspace.food)workspace.food=workspace.food.map(row=>String(row.id)===String(data.id)?{...row,food_group:data.group,pendingSync:pending}:row);
  else if(action==="food_preference")workspace.settings={...(workspace.settings||{}),food_review_purchases_count_as_eaten:data.enabled?"1":"0"};
  else if(action==="delete_food")workspace[data.foodKey]=(workspace[data.foodKey]||[]).filter(row=>String(row.id)!==String(data.id));
  if(action==="onboarding_save"&&cachedBootstrap?.accounts)for(const account of data.accounts||(data.account?[data.account]:[]))if(account?.name&&!cachedBootstrap.accounts.some(row=>row.name===account.name))cachedBootstrap.accounts.push({id:"pending-"+item.opId+"-"+account.name,name:account.name,type:account.type||"wallet",currency:account.currency||"JPY",minor_digits:["CNY","USD"].includes(account.currency)?2:0,balanceMinor:parseMinorPreview(account.openingBalance||"0",account.currency||"JPY",["CNY","USD"].includes(account.currency)?2:0),pendingSync:pending});
  for(const rows of [workspace.transactions,cachedBootstrap?.transactions,ledgerRangeRows])if(Array.isArray(rows))for(const row of rows)if(row.pendingActionOpId===item.opId){row.pendingActionDispatched=!!item.serverAccepted;row.pendingActionSending=!!item.dispatchStarted;}
}
async function persistPendingActionPreview(){if(!currentUser)return;await Promise.allSettled([workspace&&workspaceOwner===currentUser.id?cacheSet("workspace:"+currentUser.id,workspace):Promise.resolve(),cachedBootstrap?cacheSet("bootstrap:"+currentUser.id,cachedBootstrap):Promise.resolve()]);}
async function applyPendingAgentPreviews(){
  if(!currentUser)return;
  const queue=await outboxAll();
  for(const item of queue){
    if(item.type==="prepared_agent")await applyPreparedPreview(item,true,false);
    else if(item.type==="transaction")applyQueuedTransaction(item,true);
    else if(item.type==="pending_delete")applyPendingDeletePreview(item,true);
    else if(item.type==="pending_action")applyPendingActionPreview(item,true);
  }
  if(workspace&&workspaceOwner===currentUser.id){
    await Promise.allSettled([cacheSet("workspace:"+currentUser.id,workspace),cachedBootstrap?cacheSet("bootstrap:"+currentUser.id,cachedBootstrap):Promise.resolve()]);
  }
}
function applyPendingDeletePreview(item,pending=true,remove=false){
  if(!item?.rowSnapshot||!item.data?.id)return;
  const target=String(item.data.id),owner=item.ownerId;
  if(owner!==currentUser?.id)return;
  const apply=rows=>{
    if(!Array.isArray(rows))return rows;
    let found=false;
    let next=rows.map(row=>{
      if(String(row.id)!==target)return row;
      found=true;
      if(remove)return null;
      const copy={...row};
      if(pending){copy.pendingDelete=true;copy.pendingDeleteOpId=item.opId;copy.pendingDeleteDispatched=!!item.serverAccepted;copy.pendingDeleteSending=!!item.dispatchStarted;copy.pendingDeleteError=item.error||"";}
      else if(copy.pendingDeleteOpId===item.opId){delete copy.pendingDelete;delete copy.pendingDeleteOpId;delete copy.pendingDeleteDispatched;delete copy.pendingDeleteSending;delete copy.pendingDeleteError;}
      return copy;
    }).filter(Boolean);
    if(pending&&!found){
      const copy={...item.rowSnapshot,pendingDelete:true,pendingDeleteOpId:item.opId,pendingDeleteDispatched:!!item.serverAccepted,pendingDeleteSending:!!item.dispatchStarted,pendingDeleteError:item.error||""};
      next=[copy,...next];
    }
    return next;
  };
  if(workspace?.transactions)workspace.transactions=apply(workspace.transactions);
  if(cachedBootstrap?.transactions)cachedBootstrap.transactions=apply(cachedBootstrap.transactions).slice(0,100);
  if(Array.isArray(ledgerRangeRows))ledgerRangeRows=apply(ledgerRangeRows);
}
async function persistPendingDeletePreview(){
  if(!currentUser)return;
  await Promise.allSettled([
    workspace&&workspaceOwner===currentUser.id?cacheSet("workspace:"+currentUser.id,workspace):Promise.resolve(),
    cachedBootstrap?cacheSet("bootstrap:"+currentUser.id,cachedBootstrap):Promise.resolve(),
  ]);
}
window.onPendingDeleteDispatched=async item=>{
  applyPendingDeletePreview(item,true);
  await persistPendingDeletePreview();
  renderMobile();
  await renderOutbox();
};
window.onPendingDeleteFinished=async(item,succeeded)=>{
  applyPendingDeletePreview(item,false,succeeded);
  await persistPendingDeletePreview();
  renderMobile();
  if(!succeeded)await loadWorkspace(true);
};
async function queuePreparedAgent(result, owner){
  if(!result?.prepared||!result.prepareJobId||!result.preview)return null;
  const existing=(await outboxAll()).find(item=>item.opId===result.prepareJobId);
  if(existing){await applyPreparedPreview(existing,true);return existing;}
  const base=newOperation("prepared_agent",{prepareJobId:result.prepareJobId,baseRevision:result.baseRevision||""});
  const item={...base,opId:result.prepareJobId,ownerId:owner,type:"prepared_agent",preview:result.preview,baseline:capturePreparedBaseline(result.preview),
    previewTitle:result.answer||m("Agent 已完成记账","Agent が記帳しました","Agent prepared an entry"),error:"",conflict:false};
  await outboxPut(item);
  await renderOutbox();
  await applyPreparedPreview(item,true);
  return item;
}
window.onPreparedAgentSynced=async(item,revision)=>{
  await applyPreparedPreview(item,false,false);
  if(workspace)for(const row of workspace.transactions||[])if(row.pendingAgentOpId===item.opId){delete row.pendingAgentOpId;delete row.conflict;}
  if(cachedBootstrap)for(const row of cachedBootstrap.transactions||[])if(row.pendingAgentOpId===item.opId){delete row.pendingAgentOpId;delete row.conflict;}
  if(workspace&&revision)workspace.revision=revision;
  if(workspace&&currentUser)await Promise.allSettled([
    cacheSet("workspace:"+currentUser.id,workspace),
    cachedBootstrap?cacheSet("bootstrap:"+currentUser.id,cachedBootstrap):Promise.resolve(),
  ]);
  renderMobile();
};
window.onPreparedAgentConflict=async item=>{
  if(currentUser?.id!==item.ownerId)return;
  const baseline=item.baseline;
  if(baseline){
    if(workspace){for(const key of Object.keys(item.preview||{}))if(!["accounts","transactions"].includes(key)&&!baseline.workspaceKeys?.includes(key))delete workspace[key];Object.assign(workspace,deepCopy(baseline.workspace||{}));}
    if(cachedBootstrap)cachedBootstrap.accounts=deepCopy(baseline.accounts||[]);
    const ids=new Set((item.preview?.transactions||[]).map(row=>String(row.id)));
    if(workspace)workspace.transactions=(workspace.transactions||[]).filter(row=>!ids.has(String(row.id)));
    if(cachedBootstrap)cachedBootstrap.transactions=(cachedBootstrap.transactions||[]).filter(row=>!ids.has(String(row.id)));
  }
  await Promise.allSettled([workspace?cacheSet("workspace:"+item.ownerId,workspace):Promise.resolve(),cachedBootstrap?cacheSet("bootstrap:"+item.ownerId,cachedBootstrap):Promise.resolve()]);
  await loadWorkspace(true);
};
window.onDiscardPreparedAgent=async item=>{
  if(currentUser?.id!==item.ownerId)return;
  const baseline=item.baseline;
  if(baseline){
    if(workspace){for(const key of Object.keys(item.preview||{}))if(!["accounts","transactions"].includes(key)&&!baseline.workspaceKeys?.includes(key))delete workspace[key];Object.assign(workspace,deepCopy(baseline.workspace||{}));}
    if(cachedBootstrap)cachedBootstrap.accounts=deepCopy(baseline.accounts||[]);
  }
  const ids=new Set((item.preview?.transactions||[]).map(row=>String(row.id)));
  if(workspace)workspace.transactions=(workspace.transactions||[]).filter(row=>!ids.has(String(row.id)));
  if(cachedBootstrap)cachedBootstrap.transactions=(cachedBootstrap.transactions||[]).filter(row=>!ids.has(String(row.id)));
  await Promise.allSettled([workspace?cacheSet("workspace:"+item.ownerId,workspace):Promise.resolve(),cachedBootstrap?cacheSet("bootstrap:"+item.ownerId,cachedBootstrap):Promise.resolve()]);
  renderMobile();
};
window.onPendingActionDispatched=async item=>{
  applyPendingActionPreview(item,true);
  await persistPendingActionPreview();
  renderMobile();
  await renderOutbox();
};
window.onPendingActionFinished=async(item,succeeded,message="",result={})=>{
  if(!succeeded)applyPendingActionPreview(item,false,true);
  else{
    if(item.action==="rename_account")applyPendingActionPreview(item,false,false);
    if(item.action==="credit_plan"){
      const card=(workspace?.cards||[]).find(row=>String(row.account_id)===String(item.preview?.data?.cardAccountId||item.preview?.data?.accountId||""));
      if(card?.repayment_schedule){card.repayment_schedule.enabled="1";card.repayment_schedule.last_status=item.preview?.data?.amount?"本期金额已填写，等待还款日":"等待本期金额或还款日";}
      const plan=(workspace?.repaymentPlans||[]).find(row=>String(row.card_account_id)===String(item.preview?.data?.cardAccountId||item.preview?.data?.accountId||""));
      if(plan){plan.enabled="1";plan.last_status=card?.repayment_schedule?.last_status||plan.last_status;}
    }
    const prefix="pending-"+item.opId;
    if(workspace){for(const key of ["food","eaten"])workspace[key]=(workspace[key]||[]).filter(row=>!String(row.id||"").startsWith(prefix));workspace.assets=(workspace.assets||[]).filter(row=>!String(row.id||"").startsWith(prefix));workspace.recurring=(workspace.recurring||[]).filter(row=>!String(row.id||"").startsWith(prefix));}
    if(cachedBootstrap?.accounts)cachedBootstrap.accounts=cachedBootstrap.accounts.filter(row=>!String(row.id||"").startsWith(prefix));
    if(cachedBootstrap?.categories)cachedBootstrap.categories=cachedBootstrap.categories.filter(row=>String(row.id)!==prefix);
    const clearPending=rows=>{for(const row of rows||[])if(row.pendingActionOpId===item.opId){delete row.pendingActionOpId;delete row.pendingActionDispatched;delete row.pendingActionSending;delete row.pendingSync;}};
    if(item.action==="credit_snapshot"){
      const snapshotData=item.preview?.data||{},cardId=String(snapshotData.cardAccountId||""),card=(workspace?.cards||[]).find(row=>String(row.account_id)===cardId)
        ||(workspace?.cards||[]).find(row=>row.name===String(snapshotData.account||item.preview?.cardName||""));
      const confirmed=result?.snapshot;
      if(card){
        if(confirmed?.limit_minor!==undefined&&confirmed?.available_minor!==undefined){
          if(confirmed.estimated_debt_minor!==undefined)applyCreditLiabilityPreview(card,card.debt_estimate_minor,String(confirmed.estimated_debt_minor),confirmed.snapshot_date||snapshotData.date||workspace.date);
          card.limit_minor=String(confirmed.limit_minor);
          card.available_minor=String(confirmed.available_minor);
          if(confirmed.estimated_debt_minor!==undefined)card.debt_estimate_minor=String(confirmed.estimated_debt_minor);
          card.snapshot_date=String(confirmed.snapshot_date||item.preview?.data?.date||workspace.date||"");
        }
        delete card.pendingSync;delete card.pendingActionOpId;
      }
      const history=workspace?.creditHistory?.[cardId],snapshot=(history?.snapshots||[]).find(row=>String(row.id)==="pending-"+item.opId),serverId=result?.snapshot?.snapshot_id;
      if(snapshot&&serverId!==undefined){snapshot.id=serverId;snapshot.pendingSync=false;snapshot.created_at=new Date().toISOString();snapshot.transaction_id=confirmed?.transaction_id??null;if(confirmed){snapshot.limit_minor=String(confirmed.limit_minor);snapshot.available_minor=String(confirmed.available_minor);snapshot.snapshot_date=String(confirmed.snapshot_date||snapshot.snapshot_date);}}
    }
    if(item.action==="credit_repay"&&result?.transaction_id!==undefined){
      const pendingId="pending-"+item.opId,serverId=String(result.transaction_id);
      for(const rows of [workspace?.transactions,cachedBootstrap?.transactions,ledgerRangeRows,workspace?.creditHistory?.[String(item.preview?.data?.cardAccountId)]?.transactions])if(Array.isArray(rows))for(const row of rows)if(String(row.id)===pendingId)row.id=serverId;
    }
    clearPending(workspace?.transactions);clearPending(cachedBootstrap?.transactions);clearPending(ledgerRangeRows);clearPending(workspace?.investments);
    for(const rows of [workspace?.cards,workspace?.cash,workspace?.repaymentPlans,cachedBootstrap?.accounts])for(const row of rows||[])if(row.pendingActionOpId===item.opId){delete row.pendingActionOpId;delete row.pendingSync;}
    for(const entry of Object.values(workspace?.creditHistory||{}))for(const rows of [entry.snapshots,entry.transactions])for(const row of rows||[])if(row.pendingActionOpId===item.opId){delete row.pendingActionOpId;delete row.pendingSync;}
    const targetId=String(item.preview?.data?.id||"");
    for(const row of [...(workspace?.assets||[]),...(workspace?.recurring||[])])if(row.pendingSync&&(String(row.id)===targetId||String(row.id)===prefix))delete row.pendingSync;
  }
  await persistPendingActionPreview();
  renderMobile();
  if(!succeeded&&navigator.onLine&&serverReachable)await loadWorkspace(true);
};
window.onLocalQueueChanged=async item=>{
  if(item?.type==="transaction")applyQueuedTransaction(item,true);
  if(item?.type==="pending_action")applyPendingActionPreview(item,true);
  if(workspace&&currentUser)await cacheSet("workspace:"+currentUser.id,workspace);
  if(item?.type==="pending_action")await persistPendingActionPreview();
  renderMobile();
};
window.onLocalQueueSynced=item=>{
  if(item?.type==="transaction")applyQueuedTransaction(item,false);
  if(workspace&&currentUser)void cacheSet("workspace:"+currentUser.id,workspace);
  renderMobile();
};
async function loadWorkspace(force=false) {
  if(!currentUser||!idb)return;
  const owner=currentUser.id;
  const epoch=workspaceEpoch;
  if(workspaceLoading?.owner===owner&&workspaceLoading.epoch===epoch){
    if(force)workspaceLoading.again=true;
    return workspaceLoading.promise;
  }
  const request={owner,epoch,again:false,promise:null};
  workspaceLoading=request;
  workspaceError="";
  request.promise=(async()=>{
    let cacheMeta=null;
    if(workspaceOwner&&workspaceOwner!==owner){workspace=null;workspaceOwner="";cachedBootstrap=null;}
    if(!workspace||workspaceOwner!==owner||cachedBootstrap?.user?.id!==owner){
      try{
        const [cached,cachedBase,meta]=await Promise.all([
          cacheGet("workspace:"+owner),cacheGet("bootstrap:"+owner),cacheGet("workspace-meta:"+owner),
        ]);
        const valid=Boolean(cached&&cachedBase&&String(cached.revision||"")
          &&cachedBase.user?.id===owner&&Array.isArray(cached.transactions)
          &&Array.isArray(cachedBase.accounts)&&Array.isArray(cachedBase.categories));
        if(currentUser?.id===owner&&workspaceEpoch===epoch&&valid){
          workspace=cached;workspaceOwner=owner;cachedBootstrap=cachedBase;cacheMeta=meta||null;
          await applyPendingAgentPreviews();renderMobile();
        }
      }catch{}
    }else{
      try{cacheMeta=await cacheGet("workspace-meta:"+owner)||null;}catch{}
    }
    do{
      request.again=false;
      const language=currentLanguage,date=reportDate;
      const controller=new AbortController();
      const timeout=setTimeout(()=>controller.abort(),25000);
      try{
        let version=null;
        try{
          version=await readLedger("/api/workspace/revision",{signal:controller.signal});
        }catch(error){
          // During a rolling deploy an older Worker may not have the validator
          // route yet. The full snapshot endpoint remains a safe fallback.
          if(error?.status!==404)throw error;
        }
        if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;
        if(request.again||language!==currentLanguage||date!==reportDate){request.again=true;continue;}
        const cachedTimeZone=cachedBootstrap?.timeZone||workspace?.preferences?.timeZone||"Asia/Tokyo";
        const currentServerDate=version?.serverTime
          ?dateAtTimeZone(version.serverTime,cachedTimeZone)
          :String(version?.serverDate||"");
        const currentConfigRevision=String(version?.configRevision??version?.revision??"");
        const cachedMatches=Boolean(version?.revision&&currentServerDate&&currentConfigRevision
          &&workspace&&workspaceOwner===owner&&cachedBootstrap?.user?.id===owner
          &&String(workspace.revision||"")===String(version.revision)
          &&cacheMeta?.format===WORKSPACE_CACHE_FORMAT
          &&String(cacheMeta.revision||"")===String(version.revision)
          &&String(cacheMeta.configRevision||"")===currentConfigRevision
          &&cacheMeta.serverDate===currentServerDate
          &&cacheMeta.language===language&&cacheMeta.reportDate===date);
        if(cachedMatches){
          workspaceError="";
          await applyPendingAgentPreviews();
          if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;
          await renderAll();
          continue;
        }
        const data=await readLedger("/api/workspace?includeBootstrap=1&lang="+language+(date?"&asOf="+encodeURIComponent(date):""),{signal:controller.signal});
        if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;
        if(request.again||language!==currentLanguage||date!==reportDate){request.again=true;continue;}
        const {bootstrap,...snapshot}=data;
        if(!bootstrap||bootstrap.user?.id!==owner||!snapshot.revision)throw new Error(m("账本响应不完整，请重试刷新。","台帳の応答が不完全です。再度更新してください。","The ledger response is incomplete. Please refresh again."));
        workspace=snapshot;workspaceOwner=owner;cachedBootstrap=bootstrap;workspaceError="";
        cacheMeta={format:WORKSPACE_CACHE_FORMAT,revision:String(snapshot.revision),configRevision:String(version?.configRevision??version?.revision??""),serverDate:String(bootstrap.serverDate||""),language,reportDate:date};
        await applyPendingAgentPreviews();
        await Promise.allSettled([
          cacheSet("workspace:"+owner,snapshot),cacheSet("bootstrap:"+owner,bootstrap),
          cacheSet("workspace-meta:"+owner,cacheMeta),
        ]);
        if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;
        await renderAll();
      }catch(error){
        if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;
        if(request.again)continue;
        // Keep the most recent in-memory view if only the network read failed.
        if(!workspace||workspaceOwner!==owner){
          try{const cached=await cacheGet("workspace:"+owner);if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;workspace=cached||null;workspaceOwner=cached?owner:"";}catch{}
        }
        workspaceError=workspaceLoadError(error);
      }finally{clearTimeout(timeout);}
    }while(request.again);
  if(currentUser?.id===owner&&workspaceEpoch===epoch){
    await applyPendingAgentPreviews();
    await renderOutbox();
    renderMobile();
    resumeJob();
    if(workspace&&workspaceOwner===owner&&!workspaceError&&navigator.onLine)void syncQueue();
    if(selectedPage==="investment")void refreshInvestmentQuotes();
  }
  })().finally(()=>{if(workspaceLoading===request)workspaceLoading=null;});
  return request.promise;
}
async function refreshLedgerViews() {
  const owner=currentUser?.id;if(!owner)return;
  const previousRevision=workspaceOwner===owner?String(workspace?.revision||""):"";
  const previousRange=ledgerRangeRows;
  ledgerRangeRequest++;
  await fetchBootstrap();
  if(currentUser?.id!==owner)return;
  if(!workspaceError&&previousRevision&&String(workspace?.revision||"")===previousRevision){
    ledgerRangeRows=previousRange;
    renderMobileTransactions();
    return;
  }
  ledgerRangeRows=null;
  if($("#historyStart").value||$("#historyEnd").value)await loadLedgerRange();
}
async function loadLedgerRange() {
  if(!currentUser||!serverReachable)return;
  const request=++ledgerRangeRequest,epoch=workspaceEpoch;
  const owner=currentUser.id,start=$("#historyStart").value,end=$("#historyEnd").value;
  const params=new URLSearchParams();if(start)params.set("start",start);if(end)params.set("end",end);
  const rows=await readLedger("/api/transactions?"+params);
  if(currentUser?.id!==owner||workspaceEpoch!==epoch||request!==ledgerRangeRequest||$("#historyStart").value!==start||$("#historyEnd").value!==end)return;
  ledgerRangeRows=rows;renderMobileTransactions();
}
let firstRunSetupBusy=false,firstRunSetupReplay=false,firstRunSetupStep="base",firstRunSetupDraft=null;
const firstRunSetupStages=["base","accounts","api","agents","skills"];
const regionTimeZones=[
  ["Asia/Tokyo",m("日本·东京","日本・東京","Japan · Tokyo")],
  ["Asia/Shanghai",m("中国大陆·上海","中国本土・上海","Mainland China · Shanghai")],
  ["Asia/Hong_Kong",m("中国香港","香港","Hong Kong")],
  ["Asia/Taipei",m("中国台湾·台北","台湾・台北","Taiwan · Taipei")],
  ["Asia/Seoul",m("韩国·首尔","韓国・ソウル","South Korea · Seoul")],
  ["Asia/Singapore",m("新加坡","シンガポール","Singapore")],
  ["Asia/Bangkok",m("泰国·曼谷","タイ・バンコク","Thailand · Bangkok")],
  ["Asia/Dubai",m("阿联酋·迪拜","UAE・ドバイ","UAE · Dubai")],
  ["Europe/London",m("英国·伦敦","英国・ロンドン","UK · London")],
  ["Europe/Paris",m("中欧·巴黎","中央ヨーロッパ・パリ","Central Europe · Paris")],
  ["America/Los_Angeles",m("美国西部·洛杉矶","米国西部・ロサンゼルス","US Pacific · Los Angeles")],
  ["America/Chicago",m("美国中部·芝加哥","米国中部・シカゴ","US Central · Chicago")],
  ["America/New_York",m("美国东部·纽约","米国東部・ニューヨーク","US Eastern · New York")],
  ["Australia/Sydney",m("澳大利亚东部·悉尼","オーストラリア東部・シドニー","Australia Eastern · Sydney")],
  ["Pacific/Auckland",m("新西兰·奥克兰","ニュージーランド・オークランド","New Zealand · Auckland")],
];
function regionTimeZoneOptions(selected,placeholder=false){return (placeholder&&!selected?'<option value="" selected disabled>'+m("请选择所在地区","所在地域を選択","Choose your region")+'</option>':"")+regionTimeZones.map(([value,label])=>'<option value="'+value+'" '+(value===selected?'selected':'')+'>'+label+'</option>').join("");}
let tutorialTour=null,firstRunTourStarted=false,tutorialSpotlightTarget=null;
const tutorialTourSteps=[
  {action:"page",id:"home",selector:'#bottomNav [data-action="page"][data-id="home"]',title:m("总览","概要","Overview"),description:m("查看本期收支、净利润、预算和最近流水。","当期の収支、純利益、予算、最近の取引を確認できます。","See this period's income, expenses, profit, budget, and recent entries."),prompt:m("请点击底部“总览”。","下部の「概要」を押してください。","Tap Overview below.")},
  {action:"page",id:"entry",selector:'#bottomNav [data-action="page"][data-id="entry"]',title:m("记账","記帳","Record"),description:m("用文字或小票图片记账，也可切换饮食助手。","文字やレシート画像で記帳できます。食事アシスタントにも切り替えられます。","Record by text or receipt image, or switch to the food assistant."),prompt:m("请点击底部“记账”。","下部の「記帳」を押してください。","Tap Record below.")},
  {action:"page",id:"ledger",selector:'#bottomNav [data-action="page"][data-id="ledger"]',title:m("账单","明細","Ledger"),description:m("按日期查找流水，可查看、编辑或删除。","日付順に取引を確認し、表示・編集・削除できます。","Find entries by date, then view, edit, or delete them."),prompt:m("请点击底部“账单”。","下部の「明細」を押してください。","Tap Ledger below.")},
  {action:"page",id:"investment",selector:'#bottomNav [data-action="page"][data-id="investment"]',title:m("投资","投資","Investments"),description:m("手动记录基金和股票，按币种查看投入、估值和盈亏；不会影响日常余额。","投資信託や株式を手動で記録し、通貨ごとに投資額・評価額・損益を確認できます。日常の残高には影響しません。","Manually track funds and stocks by currency. Holdings, value, and profit or loss stay separate from everyday balances."),prompt:m("请点击底部“投资”。","下部の「投資」を押してください。","Tap Investments below.")},
  {action:"page",id:"assets",selector:'#bottomNav [data-action="page"][data-id="assets"]',title:m("余额","残高","Balances"),description:m("查看各个账户里有多少钱，也可以添加或修改账户。","口座ごとの残高を確認し、追加・変更できます。","See how much is in each account, and add or update accounts."),prompt:m("请点击底部“余额”。","下部の「残高」を押してください。","Tap Balances below.")},
  {action:"page",id:"more",selector:'#bottomNav [data-action="page"][data-id="more"]',title:m("更多","その他","More"),description:m("报表、预算、定期收支和设置都在这里。","レポート、予算、定期取引、設定はこちらです。","Find reports, budgets, recurring entries, and settings here."),prompt:m("请点击底部“更多”。","下部の「その他」を押してください。","Tap More below.")},
  {action:"module",id:"settings",selector:'#moreMenu .module-row[data-id="settings"]',title:m("打开设置","設定を開く","Open Settings"),description:m("这里管理账本、备份、外观和 Agent。","台帳、バックアップ、外観、Agentを管理します。","Manage the ledger, backups, appearance, and Agents here."),prompt:m("请点击列表中的“设置”。","一覧の「設定」を押してください。","Tap Settings in the list.")},
  {action:"settings-tab",id:"general",selector:'#modulePanel [data-action="settings-tab"][data-id="general"]',title:m("通用设置","一般設定","General settings"),description:m("选择主要记账货币，也可以改外观和语言。","メインの記帳通貨、外観、言語を設定します。","Choose your main bookkeeping currency, appearance, and language."),prompt:m("请点击“通用设置”。","「一般設定」を押してください。","Tap General settings.")},
  {action:"settings-tab",id:"categories",selector:'#modulePanel [data-action="settings-tab"][data-id="categories"]',title:m("记账类别","取引カテゴリ","Categories"),description:m("添加或修改类别，也可以设置每月从几号开始统计。","カテゴリを編集し、毎月何日から集計するかを設定します。","Edit categories and choose which day monthly totals start."),prompt:m("请点击“记账类别”。","「取引カテゴリ」を押してください。","Tap Categories.")},
  {action:"settings-tab",id:"backup",selector:'#modulePanel [data-action="settings-tab"][data-id="backup"]',title:m("备份","バックアップ","Backup"),description:m("连接 GitHub 或 Gitee，管理备份与恢复。","GitHub・Giteeに接続し、バックアップと復元を管理します。","Connect GitHub or Gitee to back up and restore."),prompt:m("请点击“备份”。","「バックアップ」を押してください。","Tap Backup.")},
  {action:"settings-tab",id:"agent",selector:'#modulePanel [data-action="settings-tab"][data-id="agent"]',title:m("Agent 相关","Agent関連","Agent settings"),description:m("设置 API 服务、Agent 分工和 Skill。","API、Agentの役割、Skillを設定します。","Set up API services, Agents, and Skills."),prompt:m("请点击“Agent 相关”。","「Agent関連」を押してください。","Tap Agent settings.")},
  {final:true,title:m("界面导览完成","画面ガイド完了","App tour complete"),description:m("导览完成。之后可从设置旁重新打开。","ガイド完了です。設定の横から再表示できます。","Tour complete. Reopen it beside Settings anytime."),prompt:m("点击完成，开始使用。","完了を押して利用を開始します。","Select Finish to start.")},
];
const requiredSetupTourSteps=[
  {action:"page",id:"more",selector:'#bottomNav [data-action="page"][data-id="more"]',title:m("开始前必需设置","開始前の必須設定","Required setup first"),description:m("先完成必需设置，最后一次保存。","まず必須項目を設定し、最後にまとめて保存します。","Complete setup first. Save everything once at the end."),prompt:m("请点击底部“更多”。","下部の「その他」を押してください。","Tap More below.")},
  {action:"module",id:"settings",selector:'#moreMenu .module-row[data-id="settings"]',title:m("进入设置","設定を開く","Open Settings"),description:m("这里有通用、类别、备份和 Agent 设置。","一般、カテゴリ、バックアップ、Agentの設定があります。","General, Categories, Backup, and Agent settings are here."),prompt:m("请点击列表中的“设置”。","一覧の「設定」を押してください。","Tap Settings in the list.")},
  {action:"settings-tab",id:"general",selector:'#modulePanel [data-action="settings-tab"][data-id="general"]',title:m("打开通用设置","一般設定を開く","Open General settings"),description:m("在这里设置主要记账货币和所在地区。","メインの記帳通貨と所在地域を設定します。","Set your main currency and region here."),prompt:m("请点击“通用设置”。","「一般設定」を押してください。","Tap General settings.")},
  {form:"baseCurrency",selector:"#baseCurrencyForm",title:m("选择主要记账货币","メインの記帳通貨を選択","Choose your main currency"),description:m("选择你平时主要用来记账的货币。其他货币会单独显示。","普段使う通貨を選んでください。他の通貨は別に表示されます。","Choose the currency you use most. Other currencies stay separate."),prompt:m("选好后点击“保存设置”。","選択したら「設定を保存」を押してください。","Choose one, then tap Save settings.")},
  {form:"timeZone",selector:"#regionSettingsForm",title:m("选择所在地区","所在地域を選択","Choose your region"),description:m("还款和定期记账时间会按这里的当地时间执行；夏令时也会自动调整。","返済と定期記帳はこの地域の現地時刻で実行し、夏時間も自動調整します。","Repayments and recurring entries use this local time. Daylight saving time is handled automatically."),prompt:m("选好后点击“保存设置”。","選択したら「設定を保存」を押してください。","Choose one, then tap Save settings.")},
  {action:"settings-tab",id:"agent",selector:'#modulePanel [data-action="settings-tab"][data-id="agent"]',title:m("打开 Agent 相关","Agent関連を開く","Open Agent settings"),description:m("在这里分配 API 服务并检查 Skill。","ここでAPIを割り当て、Skillを確認します。","Assign API services and review Skills here."),prompt:m("请点击“Agent 相关”。","「Agent関連」を押してください。","Tap Agent settings.")},
  {form:"agent-api",guideNext:true,selector:"#apiServiceSettings .section-heading",allowedSelector:"#apiServiceSettings",title:m("配置 API 服务","APIサービスを設定","Configure API services"),description:m("新账号这里是空的，需要自己添加 API；密钥不会从其他账号复制。","新しいアカウントにはAPI設定がありません。自分で追加してください。キーは他のアカウントからコピーされません。","New accounts start with no API service. Add your own; keys are never copied from other accounts."),prompt:m("先点“+”添加服务，再填写接口地址、模型和你自己的 API 密钥。","まず「+」でサービスを追加し、URL・モデル・ご自身のAPIキーを入力してください。","Tap + to add a service, then enter its endpoint, model, and your own API key.")},
  {form:"agent-assignments",guideNext:true,selector:"#agentAssignments",allowedSelector:"#agentAssignments",title:m("分配 API 服务","APIを割り当て","Assign API services"),description:m("为记账和饮食 Agent 分配文字与图片服务。","記帳Agentと食事Agentにテキスト・画像サービスを割り当てます。","Assign text and image services to both Agents."),prompt:m("四项都选好后继续；同一服务可以重复使用。","4項目を選んで続けてください。同じサービスを複数に使えます。","Choose all four services, then continue. You can reuse one service.")},
  {form:"agent-skills",guideNext:true,selector:"#agentSkillSettings",allowedSelector:"#agentSkillSettings",title:m("确认 Skill","Skillを確認","Review Skills"),description:m("新账号已自动载入网页版默认 Skill，可直接使用或编辑。","新しいアカウントにはWeb版の既定Skillを読み込み済みです。そのまま使うか編集できます。","New accounts already have the website's default Skills. Keep or edit them here."),prompt:m("确认两份 Skill 后继续。所有设置最后统一保存。","2つのSkillを確認して続けてください。設定は最後にまとめて保存します。","Review both Skills, then continue. Everything saves together at the end.")},
  {action:"settings-tab",id:"categories",selector:'#modulePanel [data-action="settings-tab"][data-id="categories"]',title:m("打开记账类别","取引カテゴリを開く","Open Categories"),description:m("这里可以修改类别，也能设置每月从哪天开始统计。","カテゴリの編集と、毎月の集計開始日を設定できます。","Edit categories and choose the day monthly totals start."),prompt:m("请点击“记账类别”。","「取引カテゴリ」を押してください。","Tap Categories.")},
  {form:"billingCycleStartDay",selector:"#billingCycleForm",title:m("设置每月统计起始日","毎月の集計開始日を設定","Set the monthly start day"),description:m("选择每月从几号开始统计；总览、报表和预算会跟着更新。","毎月何日から集計するか選びます。概要、レポート、予算も更新されます。","Choose which day monthly totals start. The overview, reports, and budget will update."),prompt:m("选好后点击“保存设置”。","選んだら「設定を保存」を押してください。","Choose a day, then tap Save settings.")},
  {action:"page",id:"assets",selector:'#bottomNav [data-action="page"][data-id="assets"]',title:m("打开余额","残高を開く","Open Balances"),description:m("添加账户，并填写或核对里面的钱。","口座を追加し、残高を入力または確認します。","Add accounts and enter or check their balances."),prompt:m("请点击底部“余额”。","下部の「残高」を押してください。","Tap Balances below.")},
  {form:"accounts",selector:"#showAccountForm",allowedSelector:"#showAccountForm,#accountForm",title:m("设置账户余额","口座残高を設定","Set up account balances"),description:m("第一次使用请添加账户并填写现在有多少钱；已有账户请核对。","初めての場合は口座を追加して今の残高を入力します。既存口座は確認してください。","Add an account and enter how much is in it now, or check existing accounts."),prompt:m("新用户请点右上角“添加账户”；已有账户可点下方确认。","初めての場合は右上の「口座を追加」を押してください。既存口座は下のボタンで確認できます。","New users: tap Add account at the top right. Existing users can confirm below.")},
  {final:true,title:m("必需设置已完成","必須設定が完了","Required setup complete"),description:m("主要记账货币、所在地区、每月统计日期、账户和 Agent 设置会一起保存。","メイン通貨、所在地域、毎月の集計日、口座、Agent設定をまとめて保存します。","Your main currency, region, monthly start day, accounts, and Agent settings will save together."),prompt:m("点击下方按钮保存并开始导览。","下のボタンで保存してガイドを開始します。","Save and start the app tour below.")}
];
function setTutorialPageLocked(locked){
  const nodes=[document.querySelector(".topbar"),$("main"),$("#bottomNav")].filter(Boolean);
  for(const node of nodes){
    if(locked){if(node.dataset.tutorialLocked!=="1"){node.dataset.tutorialPrevInert=node.inert?"1":"0";node.dataset.tutorialLocked="1";}node.inert=true;}
    else if(node.dataset.tutorialLocked==="1"){node.inert=node.dataset.tutorialPrevInert==="1";delete node.dataset.tutorialPrevInert;delete node.dataset.tutorialLocked;}
  }
}
function ensureTutorialDimmer(){
  let dimmer=$("#tutorialDimmer");if(dimmer)return dimmer;
  dimmer=document.createElement("div");dimmer.id="tutorialDimmer";dimmer.className="tutorial-dimmer";dimmer.setAttribute("aria-hidden","true");
  document.body.append(dimmer);return dimmer;
}
function ensureTutorialSpotlightFrame(){
  let frame=$("#tutorialSpotlightFrame");if(frame)return frame;
  frame=document.createElement("div");frame.id="tutorialSpotlightFrame";frame.className="tutorial-spotlight-frame";frame.setAttribute("aria-hidden","true");
  document.body.append(frame);return frame;
}
function updateTutorialSpotlight(){
  const target=tutorialSpotlightTarget,dimmer=$("#tutorialDimmer"),frame=$("#tutorialSpotlightFrame");
  if(!target||!dimmer||!frame||!target.isConnected||!tutorialTour){dimmer?.classList.remove("active");frame?.classList.remove("active");return;}
  const rect=target.getBoundingClientRect(),padding=6;
  const overlayRect=dimmer.getBoundingClientRect();
  if(rect.width<=0||rect.height<=0||overlayRect.width<=0||overlayRect.height<=0){dimmer.classList.remove("active");frame.classList.remove("active");return;}
  const left=Math.max(overlayRect.left,rect.left-padding),top=Math.max(overlayRect.top,rect.top-padding);
  const right=Math.min(overlayRect.right,rect.right+padding),bottom=Math.min(overlayRect.bottom,rect.bottom+padding);
  const width=right-left,height=bottom-top;
  const radius=Math.min(width/2,height/2,Math.max(0,(parseFloat(getComputedStyle(target).borderTopLeftRadius)||12)+padding));
  frame.style.left=left+"px";frame.style.top=top+"px";frame.style.width=width+"px";frame.style.height=height+"px";
  frame.style.borderRadius=radius+"px";
  const vw=overlayRect.width,vh=overlayRect.height,localLeft=left-overlayRect.left,localTop=top-overlayRect.top;
  const maskPath=[
    `M0 0H${vw}V${vh}H0Z`,
    `M${localLeft+radius} ${localTop}H${localLeft+width-radius}A${radius} ${radius} 0 0 1 ${localLeft+width} ${localTop+radius}V${localTop+height-radius}A${radius} ${radius} 0 0 1 ${localLeft+width-radius} ${localTop+height}H${localLeft+radius}A${radius} ${radius} 0 0 1 ${localLeft} ${localTop+height-radius}V${localTop+radius}A${radius} ${radius} 0 0 1 ${localLeft+radius} ${localTop}Z`,
  ].join(" ");
  const maskSvg=`<svg xmlns="http://www.w3.org/2000/svg" width="${vw}" height="${vh}" viewBox="0 0 ${vw} ${vh}"><path d="${maskPath}" fill="white" fill-rule="evenodd"/></svg>`;
  const maskImage=`url("data:image/svg+xml,${encodeURIComponent(maskSvg)}")`;
  dimmer.style.webkitMaskImage=maskImage;dimmer.style.maskImage=maskImage;
  dimmer.style.webkitMaskSize=`${vw}px ${vh}px`;dimmer.style.maskSize=`${vw}px ${vh}px`;
  dimmer.style.webkitMaskPosition="0 0";dimmer.style.maskPosition="0 0";
  dimmer.classList.add("active");frame.classList.add("active");
  positionTutorialGuide($("#firstRunSetupDialog"),target);
}
function positionTutorialGuide(dialog,target){
  if(!dialog?.open)return;
  const margin=14,gap=18,vw=window.innerWidth,vh=window.innerHeight;
  const navRect=$("#bottomNav")?.getBoundingClientRect();
  const bounds={left:margin,top:margin,right:vw-margin,bottom:navRect&&navRect.top<vh?Math.max(margin+1,navRect.top-12):vh-margin};
  const measured=dialog.getBoundingClientRect(),width=Math.min(measured.width,bounds.right-bounds.left),height=Math.min(measured.height,bounds.bottom-bounds.top);
  if(width<=0||height<=0)return;
  const targetRect=target?.isConnected?target.getBoundingClientRect():null;
  const anchor=targetRect||{left:vw*.55,right:vw*.55,top:vh*.45,bottom:vh*.45,width:0,height:0};
  const centerX=(anchor.left+anchor.right)/2,centerY=(anchor.top+anchor.bottom)/2;
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const rightSide=centerX<vw*.48;
  const lowerSide=centerY<vh*.5;
  const preferred=rightSide?"right":lowerSide?"bottom":"left";
  const candidates=[
    {side:"right",x:anchor.right+gap,y:centerY-height/2},
    {side:"left",x:anchor.left-width-gap,y:centerY-height/2},
    {side:"bottom",x:centerX-width/2,y:anchor.bottom+gap},
    {side:"top",x:centerX-width/2,y:anchor.top-height-gap},
    {side:"bottom-right",x:bounds.right-width,y:bounds.bottom-height},
    {side:"top-right",x:bounds.right-width,y:bounds.top},
    {side:"bottom-left",x:bounds.left,y:bounds.bottom-height},
    {side:"top-left",x:bounds.left,y:bounds.top},
  ];
  const excluded=targetRect?{
    left:targetRect.left-10,top:targetRect.top-10,right:targetRect.right+10,bottom:targetRect.bottom+10,
  }:null;
  const textRects=[...document.querySelectorAll("h1,h2,h3,p,label,small,button,a,.module-row,.favorite-tile")]
    .filter(node=>!dialog.contains(node)&&!(target&&target.contains(node))&&!node.closest("#tutorialDimmer,#tutorialSpotlightFrame"))
    .map(node=>node.getBoundingClientRect()).filter(rect=>rect.width>1&&rect.height>1);
  const overlapArea=(a,b)=>Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
  const preference=[preferred,"left","right","bottom","top","bottom-right","top-right","bottom-left","top-left"];
  let best=null;
  for(const candidate of candidates){
    const left=clamp(candidate.x,bounds.left,bounds.right-width),top=clamp(candidate.y,bounds.top,bounds.bottom-height);
    const rect={left,top,right:left+width,bottom:top+height};
    const targetOverlap=excluded?overlapArea(rect,excluded):0;
    let textOverlap=0,textHits=0;
    for(const textRect of textRects){const area=overlapArea(rect,textRect);if(area>0){textHits++;textOverlap+=area;}}
    const rank=preference.indexOf(candidate.side);
    const score=targetOverlap*100000+textHits*10000+textOverlap*10+Math.max(0,rank)*0.01;
    if(!best||score<best.score)best={left,top,score,side:candidate.side};
  }
  if(!best)return;
  dialog.style.left=best.left+"px";dialog.style.top=best.top+"px";
  dialog.style.right="auto";dialog.style.bottom="auto";dialog.dataset.tourPlacement=best.side;
}
function clearTutorialSpotlight(){
  document.querySelectorAll(".tutorial-spotlight,.tutorial-spotlight-host").forEach(node=>node.classList.remove("tutorial-spotlight","tutorial-spotlight-host"));
  tutorialSpotlightTarget=null;$("#tutorialDimmer")?.classList.remove("active");$("#tutorialSpotlightFrame")?.classList.remove("active");
}
function setTutorialSpotlight(target){
  clearTutorialSpotlight();if(!target)return;
  target.classList.add("tutorial-spotlight");
  tutorialSpotlightTarget=target;ensureTutorialDimmer();ensureTutorialSpotlightFrame();requestAnimationFrame(updateTutorialSpotlight);
}
function tutorialExplainSelector(step){
  if(step?.explainSelector)return step.explainSelector;
  if(step?.form)return step.selector;
  if(step?.action==="page")return ({home:"#page-home .hero-balance",entry:"#agentPanel",ledger:".history-panel",assets:".accounts-panel",more:"#moreMenu"})[step.id]||step.selector;
  if(step?.action==="module")return "#settingsPane";
  if(step?.action==="settings-tab")return "#settingsPaneContent";
  return step?.selector||"";
}
window.addEventListener("scroll",updateTutorialSpotlight,{capture:true,passive:true});
window.addEventListener("resize",updateTutorialSpotlight,{passive:true});
function tutorialAllowedClick(event){
  if(!tutorialTour)return;
  const targetNode=event.target instanceof Element?event.target:null;if(!targetNode)return;
  if(targetNode.closest("#firstRunSetupDialog")){
    const button=targetNode.closest("[data-tour-save],[data-tour-skip],[data-tour-skip-cancel],[data-tour-skip-confirm]");
    if(!button)return;
    event.preventDefault();event.stopImmediatePropagation();
    if(button.matches("[data-tour-save]"))void saveTutorialTour();
    else if(button.matches("[data-tour-skip]"))void skipTutorialTour();
    else if(button.matches("[data-tour-skip-cancel]")){tutorialTour.skipConfirm=false;tutorialTour.saveStatus="";tutorialTour.saveStatusError=false;renderTutorialTour();}
    else if(button.matches("[data-tour-skip-confirm]"))void skipTutorialTour(true);
    return;
  }
  if(targetNode.closest("#actionConfirmDialog"))return;
  if(tutorialTour.phase==="explain"){
    event.preventDefault();event.stopImmediatePropagation();return;
  }
  if(tutorialTour.phase==="action"){
    const step=(tutorialTour.mode==="required-setup"?requiredSetupTourSteps:tutorialTourSteps)[tutorialTour.index];
    const target=step?.selector?document.querySelector(step.selector):null;
    if(target&&(target===targetNode||target.contains(targetNode)))return;
    event.preventDefault();event.stopImmediatePropagation();
  }else if(tutorialTour.phase==="form"){
    const step=requiredSetupTourSteps[tutorialTour.index],selector=step?.allowedSelector||step?.selector;
    if(step?.form==="accounts"&&targetNode.closest("#showAccountForm")){
      tutorialTour.focusSelector="#accountForm";
      requestAnimationFrame(()=>{const form=$("#accountForm");if(form&&!form.classList.contains("hidden"))renderTutorialTour();});
      return;
    }
    if(step?.form==="accounts"&&targetNode.closest("#cancelAccount")){
      tutorialTour.focusSelector="#showAccountForm";
      requestAnimationFrame(()=>renderTutorialTour());
      return;
    }
    if(selector&&targetNode.closest(selector))return;
    event.preventDefault();event.stopImmediatePropagation();
  }
}
document.addEventListener("click",tutorialAllowedClick,true);
function closeTutorialTour(){
  const discardDraft=tutorialTour?.batchSave&&tutorialTour.draft?.dirty;
  if(discardDraft){settingsDraft=null;settingsInlineCapture=null;}
  setTutorialPageLocked(false);
  clearTutorialSpotlight();
  tutorialTour=null;const dialog=$("#firstRunSetupDialog");
  clearTutorialSpotlight();
  document.querySelectorAll(".tutorial-draft-status").forEach(node=>node.remove());
  dialog?.classList.remove("tutorial-guide");if(dialog?.open)dialog.close();
  if(discardDraft&&selectedPage==="more"&&moreTab==="settings")renderModule("settings");
}
async function skipTutorialTour(confirmDiscard=false){
  if(!tutorialTour)return;
  const required=tutorialTour.mode==="required-setup",dirty=!!(tutorialTour.batchSave&&tutorialTour.draft?.dirty);
  if(dirty&&!confirmDiscard){
    tutorialTour.skipConfirm=true;
    tutorialTour.saveStatus=m("尚未保存的教程修改会被丢弃；必需设置之后仍可在“更多 → 设置”完成。","未保存の変更は破棄されます。必須設定は後で「その他 → 設定」から行えます。","Unsaved tutorial changes will be discarded. You can finish required setup later under More → Settings.");
    tutorialTour.saveStatusError=false;renderTutorialTour();return;
  }
  closeTutorialTour();
  if(required){
    moreTab="";settingsTab="general";navigate("more");
    if(workspace?.preferences?.onboardingRequired)showToast(m("已跳过导览。首次设置仍需完成；请到“更多 → 设置”手动配置后再开始记账。","ガイドをスキップしました。初期設定は必要です。「その他 → 設定」で設定してから記帳してください。","Tutorial skipped. First-run setup is still required; configure it under More → Settings before recording entries."));
  }
}
function stageGuidedTutorialSettings(changes){
  if(!tutorialTour?.batchSave)return false;
  Object.assign(tutorialTour.draft.settings,changes);tutorialTour.draft.dirty=true;settingsDraft=deepCopy(tutorialTour.draft.settings);
  if(Object.hasOwn(changes,"baseCurrency"))tutorialTour.draft.confirmedSettings.baseCurrency=true;
  if(Object.hasOwn(changes,"billingCycleStartDay"))tutorialTour.draft.confirmedSettings.billingCycleStartDay=true;
  if(Object.hasOwn(changes,"timeZone"))tutorialTour.draft.confirmedSettings.timeZone=true;
  tutorialTour.focusSelector="";
  showToast(m("已暂存在教程中，尚未上传；最后统一保存。","チュートリアル内に一時保存しました。まだ送信されていません。最後にまとめて保存します。","Staged in the tutorial only. Nothing has been uploaded; it will be saved at the end."));
  if(tutorialTour.mode==="required-setup"){
    if(Object.hasOwn(changes,"baseCurrency"))completeRequiredSetupStep("baseCurrency");
    else if(Object.hasOwn(changes,"timeZone"))completeRequiredSetupStep("timeZone");
    else if(Object.hasOwn(changes,"billingCycleStartDay"))completeRequiredSetupStep("billingCycleStartDay");
    return true;
  }
  renderTutorialTour();return true;
}
function completeRequiredSetupStep(formId){
  if(tutorialTour?.mode!=="required-setup")return false;
  const steps=requiredSetupTourSteps,step=steps[tutorialTour.index];
  if(step?.form!==formId)return false;
  if(formId==="accounts"&&!(cachedBootstrap?.accounts||[]).length&&!tutorialTour.draft.accounts.length){
    showToast(m("请先添加至少一个资金账户。","資金口座を1つ以上追加してください。","Add at least one cash account first."),true);return true;
  }
  if(formId==="agent"){
    const issue=tutorialSetupIssue();
    if(issue){showToast(m("请检查 API 服务、文字/图片分配和两个 Skill，确保都已填写。","API、テキスト／画像の割り当てと2つのSkillを確認してください。","Check the API service, text and image assignments, and both Skills."),true);return true;}
  }
  tutorialTour.index++;
  const next=steps[tutorialTour.index];tutorialTour.phase=next?.final?"final":next?.form?"form":"action";tutorialTour.focusSelector="";
  renderTutorialTour();return true;
}
function tutorialAgentSetupIssue(section="all"){
  const settings=tutorialTour?.draft?.settings||{},profiles=(settings.profiles||[]).filter(profile=>
    String(profile.name||"").trim()&&String(profile.api_url||"").trim()&&String(profile.model||"").trim()&&(String(profile.api_key||"").trim()||profile.keyPresent)
  );
  if((section==="api"||section==="all")&&!profiles.length)return "api";
  if(section==="assignments"||section==="all"){
    const hasService=id=>!!id&&profiles.some(profile=>profile.id===id);
    for(const agent of ["bookkeeping","food_health"]){
      if(!hasService(settings.agents?.[agent])||!hasService(settings.visionAgents?.[agent]))return "assignments";
    }
  }
  if((section==="skills"||section==="all")&&["bookkeeping","food_health"].some(agent=>!String(settings.skills?.[agent]||"").trim()))return "skills";
  return "";
}
function advanceRequiredSetupGuide(formId){
  if(tutorialTour?.mode!=="required-setup")return false;
  const steps=requiredSetupTourSteps,step=steps[tutorialTour.index];if(step?.form!==formId||!step.guideNext)return false;
  settingsInlineCapture?.();
  const section=formId==="agent-api"?"api":formId==="agent-assignments"?"assignments":"skills";
  const issue=tutorialAgentSetupIssue(section);
  if(issue){
    const message=issue==="api"?m("请至少填写一个 API 服务的名称、接口地址、模型和密钥。","API名、URL、モデル、キーを設定してください。","Enter an API name, endpoint, model, and key."):issue==="assignments"?m("请为记账和饮食 Agent 都选择文字与图片服务。","記帳Agentと食事Agentのテキスト・画像サービスを選択してください。","Choose text and image services for both Agents."):m("请保留或恢复记账和饮食 Agent 的 Skill。","記帳Agentと食事AgentのSkillを確認してください。","Keep or restore both Agents' Skills.");
    showToast(message,true);return true;
  }
  tutorialTour.index++;const next=steps[tutorialTour.index];tutorialTour.phase=next?.final?"final":next?.form?"form":"action";tutorialTour.focusSelector="";renderTutorialTour();return true;
}
function stageTutorialCategory(action,data){
  if(!tutorialTour?.batchSave)return false;
  tutorialTour.draft.categoryChanges.push({action,data:deepCopy(data)});tutorialTour.draft.dirty=true;
  tutorialTour.focusSelector="";
  showToast(m("类别修改已暂存；教程最后一步统一上传。","カテゴリの変更を一時保存しました。最後にまとめて送信します。","Category change staged; it will upload with the rest at the end."));
  renderTutorialTour();return true;
}
function renderTutorialDraftNotice(){
  document.querySelectorAll(".tutorial-draft-status").forEach(node=>node.remove());
  if(!tutorialTour?.batchSave||selectedPage!=="assets")return;
  const grid=$("#accountGrid"),draft=tutorialTour.draft;if(!grid||(!draft.accounts.length&&!Object.keys(draft.balanceChanges).length))return;
  const notice=document.createElement("div");notice.className="tutorial-draft-status panel";
  const title=document.createElement("strong");title.textContent=m("教程暂存账户","チュートリアルの一時保存口座","Accounts staged in this tutorial");notice.append(title);
  draft.accounts.forEach(account=>{const row=document.createElement("p");row.textContent=account.name+" · "+account.currency;notice.append(row);});
  if(Object.keys(draft.balanceChanges).length){const row=document.createElement("p");row.textContent=m("已暂存 "+Object.keys(draft.balanceChanges).length+" 项余额核对","残高照合を"+Object.keys(draft.balanceChanges).length+"件一時保存","Balance checks staged: "+Object.keys(draft.balanceChanges).length);notice.append(row);}
  const hint=document.createElement("small");hint.textContent=m("尚未上传；教程最后一步统一保存。","まだ送信されていません。最後にまとめて保存します。","Not uploaded yet; everything is saved together at the final step.");notice.append(hint);grid.append(notice);
}
function tutorialSetupIssue(){
  if(!workspace?.preferences?.onboardingRequired&&tutorialTour?.mode!=="required-setup")return "";
  const draft=tutorialTour?.draft;if(!draft)return "baseCurrency";
  if(!draft.confirmedSettings.baseCurrency)return "baseCurrency";
  if(!draft.confirmedSettings.timeZone)return "timeZone";
  if(!draft.confirmedSettings.billingCycleStartDay)return "billingCycleStartDay";
  if(!(cachedBootstrap?.accounts||[]).length&&!draft.accounts.length)return "accounts";
  return tutorialAgentSetupIssue();
}
function tutorialSetupIssueMessage(issue){
  const messages={
    baseCurrency:m("请先选择主要记账货币。","メインの記帳通貨を選択してください。","Choose your main bookkeeping currency first."),
    timeZone:m("请先选择所在地区。","所在地域を選択してください。","Choose your region first."),
    billingCycleStartDay:m("请先选择每月统计起始日。","毎月の集計開始日を選択してください。","Choose the monthly start day first."),
    accounts:m("请先添加并确认至少一个账户。","口座を1つ追加して確認してください。","Add and confirm at least one account first."),
    api:m("请先添加 API 服务，并填写名称、接口地址、模型和自己的密钥。","APIサービスを追加し、名前・URL・モデル・ご自身のキーを入力してください。","Add an API service with its name, endpoint, model, and your own key first."),
    assignments:m("请先为记账和饮食 Agent 选择文字与图片服务。","記帳Agentと食事Agentにテキスト・画像サービスを割り当ててください。","Choose text and image services for both Agents first."),
    skills:m("请先确认记账和饮食 Agent 的 Skill。","記帳Agentと食事AgentのSkillを確認してください。","Review the Skills for both Agents first."),
  };
  return messages[issue]||m("还有必需设置未完成，请按前面的步骤完成后再保存。","未完了の必須設定があります。前の手順を完了してから保存してください。","Some required setup is incomplete. Complete the earlier steps before saving.");
}
async function saveTutorialTour(){
  if(!tutorialTour?.batchSave){closeTutorialTour();return;}
  if(tutorialTour.saving)return;
  const required=tutorialTour.mode==="required-setup";
  if(!required&&!tutorialTour.draft.dirty){closeTutorialTour();return;}
  const missing=tutorialSetupIssue();if(missing){tutorialTour.saveStatus=tutorialSetupIssueMessage(missing);tutorialTour.saveStatusError=true;renderTutorialTour();return;}
  const activeTour=tutorialTour,draft=activeTour.draft;
  activeTour.saving=true;activeTour.saveStatus=m("正在统一保存设置，请稍候，暂时不要关闭页面。","設定をまとめて保存しています。画面を閉じずにお待ちください。","Saving all settings. Please wait and keep this page open.");activeTour.saveStatusError=false;
  renderTutorialTour();
  try{
    const settings=deepCopy(draft.settings);
    settings.baseCurrency=settings.baseCurrency||workspace?.settings?.base_currency||"JPY";
    settings.timeZone=settings.timeZone||"";
    settings.billingCycleStartDay=Number(settings.billingCycleStartDay||workspace?.preferences?.billingCycleStartDay||15);
    if(workspace?.preferences?.onboardingRequired){settings.onboardingStep="skills";settings.completeOnboarding=true;}
    const saveResult=await runAction("onboarding_save",{settings,accounts:draft.accounts,balanceChanges:draft.balanceChanges,categoryChanges:draft.categoryChanges,adjustmentDate:draft.adjustmentDate,confirmBalanceAdjustments:draft.confirmBalanceAdjustments,postDifferences:draft.postDifferences,setupConfirmations:draft.confirmedSettings},()=>{
      if(tutorialTour===activeTour){activeTour.saveStatus=m("服务器正在保存设置，请稍候…","サーバーに設定を保存しています…","Saving settings on the server…");activeTour.saveStatusError=false;renderTutorialTour();}
    },false);
    if(!saveResult?.queued)await loadWorkspace(true);settingsDraft=null;draft.dirty=false;
    if(required){
      activeTour.mode="overview";activeTour.index=0;activeTour.phase="action";activeTour.finalRouted=false;activeTour.focusSelector="";activeTour.saving=false;activeTour.saveStatus="";activeTour.saveStatusError=false;
      selectedPage="home";moreTab="";settingsTab="general";renderNavigation();renderMobile();
      renderTutorialTour();
      showToast(saveResult?.queued?m("设置已先保存在本机，正在后台同步；现在开始界面导览。","設定を端末に保存し、バックグラウンドで同期中です。画面ガイドを開始します。","Setup is saved on this device and syncing in the background. The app tour is starting."):m("必需设置已统一保存，现在开始正式界面导览。","必須設定をまとめて保存しました。画面ガイドを開始します。","Required setup saved. The app tour is starting."));
    }else{closeTutorialTour();if(saveResult?.queued)showToast(m("设置已先保存在本机，正在后台同步云端。","設定を端末に保存しました。クラウドへバックグラウンドで同期中です。","Settings are saved on this device and syncing to the cloud in the background."));}
  }catch(error){
    if(tutorialTour===activeTour){activeTour.saving=false;activeTour.saveStatus=error.message||m("保存失败，草稿仍保留。请检查网络后重试。","保存に失敗しました。下書きは保持されています。通信を確認して再試行してください。","Save failed; your draft is still here. Check your connection and try again.");activeTour.saveStatusError=true;renderTutorialTour();}
  }
}
function currentTutorialSteps(){
  return tutorialTour?.mode==="required-setup"?requiredSetupTourSteps:tutorialTourSteps;
}
function renderTutorialTour(){
  if(!tutorialTour)return;
  const dialog=$("#firstRunSetupDialog"),steps=currentTutorialSteps(),step=steps[tutorialTour.index];
  if(!dialog||!step)return;
  const required=tutorialTour.mode==="required-setup";
  const phase=tutorialTour.phase||(step.final?"final":step.form?"form":"action");
  tutorialTour.phase=phase;
  setTutorialPageLocked(phase==="explain");
  document.querySelectorAll(".tutorial-spotlight").forEach(node=>node.classList.remove("tutorial-spotlight"));
  dialog.classList.add("tutorial-guide");
  const index=tutorialTour.index+1,total=steps.length;
  let actions="",prompt=step.prompt||"";
  if(phase==="explain"){
    prompt=step.action==="settings-tab"&&step.id==="general"
      ?m("这里可以选择总览和报表主要使用的货币，也能改外观和语言。账户里的金额仍按原来的货币显示。","概要とレポートに使う通貨を選びます。口座の金額は元の通貨で表示されます。外観と言語も変更できます。","Choose the main currency for totals and reports. Account amounts stay in their original currency. You can also change appearance and language here.")
      :m("看完后点击“下一步”。","確認したら「次へ」を押してください。","Tap Next when ready.");
    actions='<button type="button" class="button primary" data-tour-next>'+m("下一步","次へ","Next")+'</button>';
  }else if(step.final){
    if(required&&tutorialTour.skipConfirm){
      prompt=m("确认后会退出教程并丢弃尚未保存的设置。","確認するとチュートリアルを終了し、未保存の設定を破棄します。","Confirming exits the tutorial and discards its unsaved settings.");
      actions='<button type="button" class="button danger-text" data-tour-skip-confirm>'+m("确认跳过并退出","スキップして終了","Confirm skip and exit")+'</button>';
    }else if(required){
      actions='<button type="button" class="button primary" data-tour-save '+(tutorialTour.saving?"disabled":"")+'>'+(tutorialTour.saving?m("正在保存设置…","設定を保存中…","Saving settings…"):m("统一保存并开始正式导览","まとめて保存して画面ガイドを開始","Save all and start the app tour"))+'</button>';
      prompt=step.prompt;
    }else{
      actions='<button type="button" class="button primary" data-tour-finish>'+m("完成导览","ガイドを終了","Finish tour")+'</button>';
      prompt=step.prompt;
    }
  }else if(phase==="form"){
    if(step.guideNext){
      actions='<button type="button" class="button primary" data-tour-form-next>'+m("继续","続ける","Continue")+'</button>';
    }else if(step.form==="accounts"&&(cachedBootstrap?.accounts||[]).length){
      prompt=m("新用户请点右上角“添加账户”；已有账户可点下方确认。","初めての場合は右上の「口座を追加」を押してください。既存口座は下のボタンで確認できます。","New users: tap Add account at the top right. Existing users can confirm below.");
      actions='<button type="button" class="button primary" data-tour-confirm-assets>'+m("账户已确认，继续","口座を確認して続ける","Accounts confirmed; continue")+'</button>';
    }
  }else if(!required){
    actions='<button type="button" class="text-button" data-tour-exit>'+m("退出","終了","Exit")+'</button>';
  }
  const number=required?m("必需设置","必須設定","Required setup"):m("界面导览","画面ガイド","App tour");
  const status=tutorialTour.saveStatus?'<p class="tutorial-guide-status'+(tutorialTour.saveStatusError?' is-error':'')+'" role="'+(tutorialTour.saveStatusError?'alert':'status')+'">'+e(tutorialTour.saveStatus)+'</p>':"";
  dialog.innerHTML='<section class="tutorial-guide-card"><div class="spread"><small>'+e(number)+' · '+index+" / "+total+'</small>'+(required?(tutorialTour.skipConfirm?'<button type="button" class="text-button" data-tour-skip-cancel>'+m("返回","戻る","Back")+'</button>':'<button type="button" class="text-button" data-tour-skip '+(tutorialTour.saving?"disabled":"")+'>'+m("跳过导览","ガイドをスキップ","Skip tour")+'</button>'):'<button type="button" class="text-button" data-tour-exit>'+m("退出","終了","Exit")+'</button>')+'</div><h2>'+e(step.title)+'</h2><p>'+e(step.description)+'</p><p class="tutorial-guide-prompt">'+e(prompt)+'</p>'+status+'<div class="tutorial-guide-actions">'+actions+'</div></section>';
  dialog.oncancel=event=>{if(required){event.preventDefault();return;}event.preventDefault();closeTutorialTour();};
  if(!dialog.open)dialog.show();
  const focusSelector=phase==="explain"?tutorialExplainSelector(step):(tutorialTour.focusSelector||step.selector||"");
  const target=document.querySelector(focusSelector);
  if(target){setTutorialSpotlight(target);if(!target.closest("#bottomNav,.topbar"))target.scrollIntoView({behavior:"smooth",block:"center"});}
  dialog.querySelectorAll("[data-tour-exit]").forEach(button=>button.addEventListener("click",closeTutorialTour));
  dialog.querySelector("[data-tour-form-next]")?.addEventListener("click",()=>advanceRequiredSetupGuide(step.form));
  dialog.querySelector("[data-tour-next]")?.addEventListener("click",()=>{
    const next=steps[tutorialTour.index+1];tutorialTour.index++;
    tutorialTour.phase=next?.final?"final":next?.form?"form":"action";tutorialTour.focusSelector="";
    renderTutorialTour();
  });
  dialog.querySelector("[data-tour-confirm-assets]")?.addEventListener("click",()=>completeRequiredSetupStep("accounts"));
  dialog.querySelector("[data-tour-finish]")?.addEventListener("click",closeTutorialTour);
}
function advanceTutorialTour(action,id){
  if(!tutorialTour||tutorialTour.phase!=="action")return;
  tutorialTour.focusSelector="";
  const steps=currentTutorialSteps(),step=steps[tutorialTour.index];
  if(step?.action!==action||step?.id!==id)return;
  if(tutorialTour.mode==="required-setup"){
    tutorialTour.index++;
    const next=steps[tutorialTour.index];tutorialTour.phase=next?.final?"final":next?.form?"form":"action";
    renderTutorialTour();return;
  }
  tutorialTour.phase="explain";renderTutorialTour();
}
function setupBaseSettings(){
  const draft=firstRunSetupReplay?firstRunSetupDraft?.settings:null;
  return {
    baseCurrency:draft?.baseCurrency||workspace?.settings?.base_currency||"JPY",
    billingCycleStartDay:Number(draft?.billingCycleStartDay||workspace?.preferences?.billingCycleStartDay||15),
    timeZone:draft?.timeZone||(workspace?.preferences?.timeZoneConfigured?workspace?.preferences?.timeZone:workspace?.preferences?.onboardingRequired?"":workspace?.preferences?.timeZone)||"",
  };
}
function setupProgress(stage){
  const index=Math.max(0,firstRunSetupStages.indexOf(stage));
  return '<div class="onboarding-progress" aria-label="'+m("新手引导进度","初期設定の進行状況","Setup progress")+'"><div class="onboarding-progress-track"><span style="width:'+Math.round((index+1)*100/firstRunSetupStages.length)+'%"></span></div><small>'+m("第 "+(index+1)+" 步，共 "+firstRunSetupStages.length+" 步","ステップ "+(index+1)+" / "+firstRunSetupStages.length,"Step "+(index+1)+" of "+firstRunSetupStages.length)+'</small></div>';
}
function firstRunStageFromWorkspace(){
  const saved=workspace?.preferences?.onboardingStage||"base";
  if(saved==="assets")return (cachedBootstrap?.accounts||[]).length?"api":"accounts";
  return firstRunSetupStages.includes(saved)?saved:"base";
}
function setupNavigation(stage,submitLabel){
  const index=firstRunSetupStages.indexOf(stage);
  return '<div class="onboarding-actions">'+(index>0?'<button type="button" class="button secondary" data-onboarding-back>'+m("上一步","戻る","Back")+'</button>':"")+'<button class="button primary" type="submit">'+submitLabel+'</button></div>';
}
function captureTutorialDraftForm(form){
  if(!firstRunSetupDraft)return;
  const values={};
  form.querySelectorAll("input,select,textarea").forEach(control=>{
    if(!control.name||control.type==="password")return;
    values[control.name]=control.type==="checkbox"?(control.checked?control.value:""):control.value;
  });
  firstRunSetupDraft.formValues[firstRunSetupStep]=values;
}
function restoreTutorialDraftForm(form){
  const values=firstRunSetupDraft?.formValues?.[firstRunSetupStep];if(!values)return;
  form.querySelectorAll("input,select,textarea").forEach(control=>{
    if(!control.name||control.type==="password"||!Object.hasOwn(values,control.name))return;
    if(control.type==="checkbox")control.checked=values[control.name]===control.value;
    else control.value=values[control.name];
  });
}
function stageFirstRunSetupSettings(form,formData,accounts){
  const draft=firstRunSetupDraft;if(!draft?.settings)throw new Error(m("教程草稿已失效，请重新打开。","チュートリアルの下書きが失効しました。もう一度開いてください。","The tutorial draft expired. Please reopen it."));
  const settings=draft.settings;
  if(firstRunSetupStep==="base"){
    const currency=String(formData.get("baseCurrency")||""),day=Number(formData.get("billingCycleStartDay")),timeZone=String(formData.get("timeZone")||"");
    if(!["JPY","CNY","USD"].includes(currency)||!Number.isInteger(day)||day<1||day>31||!regionTimeZones.some(([value])=>value===timeZone))throw new Error(m("请选择主要记账货币、所在地区和每月统计起始日。","メイン通貨・所在地域・毎月の集計開始日を選択してください。","Choose your main currency, region, and monthly start day."));
    settings.baseCurrency=currency;settings.billingCycleStartDay=day;settings.timeZone=timeZone;
  }else if(firstRunSetupStep==="accounts"){
    const name=String(formData.get("name")||"").trim(),balanceChanges={};
    let newAccount=null;
    if(name){
      newAccount={name,type:String(formData.get("type")||"bank"),currency:String(formData.get("currency")||setupBaseSettings().baseCurrency),openingBalance:String(formData.get("openingBalance")||"0").trim(),openingDate:String(formData.get("openingDate")||workspace?.date||""),completeness:String(formData.get("completeness")||"known"),note:""};
      if(!newAccount.openingDate||!newAccount.openingBalance)throw new Error(m("请补齐新账户的期初余额和日期。","新しい口座の開始残高と日付を入力してください。","Enter the new account's opening balance and date."));
    }
    if(!name&&!accounts.length&&!replay)throw new Error(m("请填写账户名称。","口座名を入力してください。","Enter an account name."));
    if(!hiddenAmounts)for(const account of accounts){
      if(account.pending)continue;
      const value=String(formData.get("balance-"+account.id)||"").trim(),original=plainAmount(account.balanceMinor,account.minorDigits||0,account.currency);
      if(value&&value!==original)balanceChanges[account.name]=value;
    }
    if(Object.keys(balanceChanges).length&&formData.get("confirmBalanceAdjustments")!=="yes")throw new Error(m("请先勾选确认：修改余额会生成调整流水。","残高の変更で調整取引が作成されることを確認してください。","Confirm that changing balances will create adjustment entries."));
    draft.account=newAccount;
    draft.balanceChanges=balanceChanges;draft.adjustmentDate=String(formData.get("adjustmentDate")||workspace?.date||"");draft.confirmBalanceAdjustments=formData.get("confirmBalanceAdjustments")==="yes";
  }else if(firstRunSetupStep==="api"){
    const old=settings.profiles?.[0]||{},apiKey=String(formData.get("apiKey")||"");
    const name=String(formData.get("profileName")||"").trim(),endpoint=String(formData.get("apiUrl")||"").trim(),model=String(formData.get("model")||"").trim();
    if(!name||!endpoint||!model||(!(old.keyPresent||old.api_key)&&!apiKey))throw new Error(m("请填写 API 名称、地址、模型和密钥。","API名、URL、モデル名、キーを入力してください。","Enter the API name, endpoint, model, and key."));
    const profile={...old,id:old.id||crypto.randomUUID(),name,api_url:endpoint,model,api_key:apiKey||old.api_key||"",keyPresent:!!(apiKey||old.keyPresent||old.api_key)};
    settings.profiles=[profile,...(settings.profiles||[]).slice(1)];
  }else if(firstRunSetupStep==="agents"){
    settings.agents={...(settings.agents||{})};settings.visionAgents={...(settings.visionAgents||{})};
    settings.agents.bookkeeping=String(formData.get("text-bookkeeping")||"");settings.visionAgents.bookkeeping=String(formData.get("vision-bookkeeping")||"");settings.agents.food_health=String(formData.get("text-food")||"");settings.visionAgents.food_health=String(formData.get("vision-food")||"");
    if(Object.values(settings.agents).some(value=>!value)||Object.values(settings.visionAgents).some(value=>!value))throw new Error(m("请为两个 Agent 都选择文字和图片服务。","両方のAgentにテキストと画像サービスを選んでください。","Select text and image services for both Agents."));
  }else{
    settings.skills={...(settings.skills||{})};settings.skills.bookkeeping=String(formData.get("skill-bookkeeping")||"");settings.skills.food_health=String(formData.get("skill-food_health")||"");
    if(Object.values(settings.skills).some(value=>!String(value||"").trim()))throw new Error(m("请保留或恢复两个 Agent 的 Skill 文本。","両方のAgentにSkillテキストを設定してください。","Keep or restore skill text for both Agents."));
    settings.completeOnboarding=true;settings.onboardingStep="skills";
  }
  captureTutorialDraftForm(form);
  return firstRunSetupStep==="skills";
}
function renderFirstRunSetupStep(){
  const dialog=$("#firstRunSetupDialog");if(!dialog)return;
  dialog.classList.remove("tutorial-guide");
  const prefs=firstRunSetupReplay&&firstRunSetupDraft?.settings?firstRunSetupDraft.settings:(workspace?.preferences||{}),accounts=cachedBootstrap?.accounts||[],base=setupBaseSettings(),replay=firstRunSetupReplay;
  const labels={
    base:m("账本基础设置","台帳の基本設定","Ledger basics"),
    accounts:m("设置账户和余额","口座と残高を設定","Set up accounts and balances"),
    api:m("配置 API 服务","APIサービスを設定","Configure an API service"),
    agents:m("分配 Agent 服务","Agentサービスを割り当て","Assign Agent services"),
    skills:m("确认 Agent Skill","Agent Skillを確認","Review Agent skills"),
  };
  const stageIndex=firstRunSetupStages.indexOf(firstRunSetupStep);
  const profileChoices=(prefs.profiles||[]).map(profile=>'<option value="'+e(profile.id)+'">'+e(profile.name||profile.model||profile.id)+'</option>').join("");
  let stepBody="",submitLabel=m("保存并继续","保存して続ける","Save and continue");
  if(firstRunSetupStep==="base"){
    const currencies=[["JPY",m("日元","日本円","Japanese yen")],["CNY",m("人民币","人民元","Chinese yuan")],["USD",m("美元","米ドル","US dollar")]];
    const currencyOptions=(replay?"":'<option value="" selected disabled>'+m("请选择主要记账货币","メインの記帳通貨を選択","Choose your main currency")+'</option>')+currencies.map(([code,label])=>'<option value="'+code+'" '+(replay&&base.baseCurrency===code?"selected":"")+'>'+code+' · '+label+'</option>').join("");
    const dayOptions=Array.from({length:31},(_,index)=>'<option value="'+(index+1)+'" '+(replay&&base.billingCycleStartDay===index+1?"selected":"")+'>'+e(m((index+1)+"日",(index+1)+"日",String(index+1)))+'</option>').join("");
    stepBody='<label class="field"><span>'+m("主要记账货币","メインの記帳通貨","Main bookkeeping currency")+'</span><select name="baseCurrency" required>'+currencyOptions+'</select></label><label class="field"><span>'+m("所在地区","所在地域","Region")+'</span><select name="timeZone" required>'+regionTimeZoneOptions(base.timeZone,!base.timeZone)+'</select></label><p class="fineprint">'+m("所在地区会决定当天日期和自动还款等功能使用的当地时间；夏令时会自动调整。","所在地域は今日の日付や自動返済などに使う現地時刻を決めます。夏時間も自動調整します。","Your region sets local dates and times for features such as automatic repayments. Daylight saving time is handled automatically.")+'</p><label class="field"><span>'+m("每月从几号开始统计","毎月何日から集計するか","Which day monthly totals start")+'</span><select name="billingCycleStartDay" required>'+(replay?"":'<option value="" selected disabled>'+m("请选择日期","日付を選択","Choose a day")+'</option>')+dayOptions+'</select></label><p class="fineprint">'+m("每月从你选的日期开始统计，到下个月同一日期的前一天结束。比如选15号，就是每月15号到下月14号。改好后，总览和报表会重新统计，已有记录日期不会改变。","選択した日から翌月の同じ日の前日までを集計します。たとえば15日なら、毎月15日から翌月14日までです。変更後、概要とレポートを再集計します。過去の取引日は変わりません。","Each month starts on your chosen day and ends the day before that day next month. For example, choosing the 15th means the 15th through the 14th. Totals update; existing entry dates do not change.")+'</p>';
  }else if(firstRunSetupStep==="accounts"){
    const accountList=accounts.length?'<div class="onboarding-account-list">'+accounts.map(account=>'<div class="onboarding-account-row"><div><strong>'+e(account.name)+'</strong><span>'+e(t("accountTypes."+account.type)||account.type)+' · '+e(account.currency)+'</span></div>'+(replay&&!hiddenAmounts&&!account.pending?'<label class="field"><span>'+m("当前余额","現在残高","Current balance")+'</span><input name="balance-'+e(account.id)+'" type="text" inputmode="decimal" autocomplete="off" value="'+e(plainAmount(account.balanceMinor,account.minorDigits||0,account.currency))+'"></label>':"")+'</div>').join("")+'</div>':'<p class="fineprint">'+m("当前还没有配置账户。","口座はまだ設定されていません。","No accounts are configured yet.")+'</p>';
    const balanceAdjustmentForm=replay&&accounts.length&&!hiddenAmounts?'<label class="field"><span>'+m("余额核对日期","残高照合日","Balance adjustment date")+'</span><input name="adjustmentDate" type="date" value="'+e(workspace?.date||"")+'" required></label><label class="check-row"><input name="confirmBalanceAdjustments" type="checkbox" value="yes"><span>'+m("确认：修改的余额差额会作为一笔调整流水记入账本","確認：変更した残高の差額を調整取引として台帳に記録します","Confirm: balance differences will be posted as adjustment entries.")+'</span></label>':"";
    const accountForm='<div class="onboarding-account-add"><strong>'+m("添加账户","口座を追加","Add an account")+'</strong><p class="fineprint">'+m("已有账户可以核对现在的余额；填写账户名称也可以添加新账户。所有更改会在最后一步一起保存。","登録済み口座の残高を確認できます。口座名を入力すると新しい口座を追加できます。変更は最後にまとめて保存します。","Check current balances or enter a name to add an account. Changes are saved together at the end.")+'</p><label class="field"><span>'+m("账户名称","口座名","Account name")+'</span><input name="name" '+(replay?"":"required")+' maxlength="80" placeholder="'+e(m("例如：日常银行卡","例：生活費の銀行口座","e.g. Main bank account"))+'"></label><label class="field"><span>'+m("账户类型","口座の種類","Account type")+'</span><select name="type" '+(replay?"":"required")+'><option value="bank">'+t("accountTypes.bank")+'</option><option value="wallet">'+t("accountTypes.wallet")+'</option><option value="prepaid">'+t("accountTypes.prepaid")+'</option><option value="transit">'+t("accountTypes.transit")+'</option><option value="credit">'+t("accountTypes.credit")+'</option></select></label><label class="field"><span>'+m("币种","通貨","Currency")+'</span><select name="currency" '+(replay?"":"required")+'><option value="JPY" '+(base.baseCurrency==="JPY"?"selected":"")+'>JPY</option><option value="CNY" '+(base.baseCurrency==="CNY"?"selected":"")+'>CNY</option><option value="USD" '+(base.baseCurrency==="USD"?"selected":"")+'>USD</option></select></label><label class="field"><span>'+m("当前余额","現在残高","Current balance")+'</span><input name="openingBalance" type="text" inputmode="decimal" autocomplete="off" value="0" '+(replay?"":"required")+'></label><label class="field"><span>'+m("余额日期","残高日","Balance as of")+'</span><input name="openingDate" type="date" value="'+e(workspace?.date||"")+'" '+(replay?"":"required")+'></label><label class="field"><span>'+m("余额确认状态","残高の確認状態","Balance confidence")+'</span><select name="completeness"><option value="known">'+m("已核实","確認済み","Verified")+'</option><option value="partial">'+m("部分核实","一部確認","Partially verified")+'</option><option value="inferred">'+m("估算值","推定","Estimated")+'</option></select></label></div>';
    stepBody=replay?accountList+balanceAdjustmentForm+accountForm:accounts.length?accountList+'<p class="fineprint">'+m("至少一个账户已就绪。其他账户之后可在“账户”页面添加。","口座を1つ以上登録しました。ほかの口座は後から追加できます。","At least one account is ready. Add more later from Accounts.")+'</p>':accountForm;
  }else if(firstRunSetupStep==="api"){
    const existing=prefs.profiles?.[0]||{};
    if(replay){
      const profiles=prefs.profiles||[];
      stepBody=profiles.length?'<div class="onboarding-account-list">'+profiles.map(profile=>'<div><strong>'+e(profile.name||profile.model||profile.id)+'</strong><span>'+e(profile.model||"")+' · '+(profile.keyPresent?m("密钥已配置（隐藏）","キー設定済み（非表示）","Key configured (hidden)"):m("未配置密钥","キー未設定","No key configured"))+'</span></div><p class="fineprint">'+e(profile.api_url||"")+'</p>').join("")+'</div>':'<p class="fineprint">'+m("当前还没有配置 API 服务。","APIサービスはまだ設定されていません。","No API service is configured yet.")+'</p>';
    }else stepBody='<label class="field"><span>'+m("服务名称","サービス名","Service name")+'</span><input name="profileName" required maxlength="80" value="'+e(existing.name||"")+'" placeholder="'+m("例如：我的模型服务","例：利用するAIサービス","e.g. My model provider")+'"></label><label class="field"><span>'+m("API 完整地址","APIエンドポイント","API endpoint URL")+'</span><input name="apiUrl" type="url" required value="'+e(existing.api_url||"")+'" placeholder="https://api.example.com/v1"></label><label class="field"><span>'+m("模型标识","モデルID","Model ID")+'</span><input name="model" required value="'+e(existing.model||"")+'" placeholder="'+m("填写服务商提供的模型名称","サービス提供元のモデル名","Model name from your provider")+'"></label><label class="field"><span>'+m("API 密钥","APIキー","API key")+'</span><input name="apiKey" type="password" autocomplete="new-password" '+(existing.keyPresent?"":"required")+' placeholder="'+e(existing.keyPresent?m("已保存密钥；留空保持不变","保存済みです。変更しない場合は空欄","Saved; leave blank to keep it"):m("粘贴你自己的 API 密钥","自分のAPIキーを貼り付け","Paste your own API key"))+'"></label><p class="fineprint">'+m("密钥会加密保存在这个账号的设置中，不会复制其他人的 API。此步骤只保存配置，不会发送模型请求或消耗 API 额度。","APIキーはこのアカウントの設定に暗号化して保存され、他人のキーはコピーされません。この段階ではモデルを呼び出さず、API利用枠も消費しません。","The key is encrypted in this account's settings. Other users' keys are never copied. This step saves settings only; it does not call the model or use API quota.")+'</p>';
    if(replay)stepBody='<label class="field"><span>'+m("服务名称","サービス名","Service name")+'</span><input name="profileName" required maxlength="80" value="'+e(existing.name||"")+'"></label><label class="field"><span>'+m("API 完整地址","APIエンドポイント","API endpoint URL")+'</span><input name="apiUrl" type="url" required value="'+e(existing.api_url||"")+'"></label><label class="field"><span>'+m("模型标识","モデルID","Model ID")+'</span><input name="model" required value="'+e(existing.model||"")+'"></label><label class="field"><span>'+m("API 密钥","APIキー","API key")+'</span><input name="apiKey" type="password" autocomplete="new-password" '+(existing.keyPresent?"":"required")+' placeholder="'+e(existing.keyPresent?m("已设置，留空则保留原密钥","設定済み。空欄なら現在のキーを保持","Configured; leave blank to keep current key"):m("粘贴你自己的 API 密钥","自分のAPIキーを貼り付け","Paste your own API key"))+'"></label><p class="fineprint">'+m("此步骤只保存配置，不会调用模型。密钥留空会保留当前密钥；填写新密钥才会替换。","この手順では設定のみ保存し、モデルは呼び出しません。キーを空欄にすると現在のキーを維持し、新しいキーを入力すると置き換えます。","This saves configuration only and does not call the model. Leave the key blank to keep it, or enter a new key to replace it.")+'</p>';
  }else if(firstRunSetupStep==="agents"){
    const agentSelect=(name,label,selection)=>'<label class="field"><span>'+label+'</span><select name="'+name+'" required><option value="" selected disabled>'+m("请选择 API 服务","APIサービスを選択","Select an API service")+'</option>'+profileChoices.replace('value="'+e(selection||"")+'"','value="'+e(selection||"")+'" selected')+'</select></label>';
    const firstProfile=prefs.profiles?.[0]?.id||"";
    const assignments=[[m("记账 Agent · 文字服务","記帳Agent・テキスト","Bookkeeping Agent · text"),prefs.agents?.bookkeeping||firstProfile],[m("记账 Agent · 图片服务","記帳Agent・画像","Bookkeeping Agent · images"),prefs.visionAgents?.bookkeeping||firstProfile],[m("饮食 Agent · 文字服务","食事Agent・テキスト","Food Agent · text"),prefs.agents?.food_health||firstProfile],[m("饮食 Agent · 图片服务","食事Agent・画像","Food Agent · images"),prefs.visionAgents?.food_health||firstProfile]];
    stepBody=replay?'<div class="onboarding-account-list">'+assignments.map(([label,id])=>'<div><strong>'+label+'</strong><span>'+e((prefs.profiles||[]).find(profile=>profile.id===id)?.name||(prefs.profiles||[]).find(profile=>profile.id===id)?.model||(id?m("服务未找到","サービスが見つかりません","Service unavailable"):m("未配置","未設定","Not configured")))+'</span></div>').join("")+'</div>':'<p class="fineprint">'+m("为记账和饮食 Agent 分配文字与图片服务。可以先用同一个服务；图片服务需要支持图片输入。","記帳・食事Agentのテキスト用と画像用サービスを選択します。同じサービスを使えます。画像用サービスは画像入力に対応している必要があります。","Choose text and image services for both Agents. You can use the same service; image services must support image input.")+'</p>'+agentSelect("text-bookkeeping",assignments[0][0],assignments[0][1])+agentSelect("vision-bookkeeping",assignments[1][0],assignments[1][1])+agentSelect("text-food",assignments[2][0],assignments[2][1])+agentSelect("vision-food",assignments[3][0],assignments[3][1]);
    if(replay)stepBody='<p class="fineprint">'+m("可在此调整记账和饮食 Agent 使用的文字与图片服务。","ここで記帳・食事Agentのテキスト用と画像用サービスを変更できます。","Change the text and image services used by each Agent here.")+'</p>'+agentSelect("text-bookkeeping",assignments[0][0],assignments[0][1])+agentSelect("vision-bookkeeping",assignments[1][0],assignments[1][1])+agentSelect("text-food",assignments[2][0],assignments[2][1])+agentSelect("vision-food",assignments[3][0],assignments[3][1]);
  }else{
    const skills=prefs.skills||{};
    stepBody='<p class="fineprint">'+m("网站通用 Skill 已自动载入。你可以直接确认使用，也可以编辑文本。Skill 会随请求发送给你自己选择的模型服务。","Web共通のSkillを読み込みました。そのまま使うか、内容を編集できます。Skillは選択したご自身のモデルサービスに送信されます。","The website's shared skills are loaded. Keep them as they are or edit them. Skills are sent only to the model service you selected.")+'</p>'+["bookkeeping","food_health"].map(agent=>'<section class="onboarding-skill"><div class="spread"><strong>'+ (agent==="bookkeeping"?m("记账 Agent Skill","記帳Agent Skill","Bookkeeping Agent skill"):m("饮食 Agent Skill","食事Agent Skill","Food Agent skill"))+'</strong>'+(replay?"":'<button type="button" class="text-button accent" data-onboarding-default="'+agent+'">'+m("恢复网站默认","Webの初期値に戻す","Restore website default")+'</button>')+'</div><textarea name="skill-'+agent+'" rows="8" '+(replay?'readonly':'required')+' spellcheck="false" aria-label="'+(agent==="bookkeeping"?"Bookkeeping Agent Skill":"Food Agent Skill")+'">'+e(skills[agent]||"")+'</textarea></section>').join("");
    if(replay)stepBody=stepBody.replace(' readonly',' required');
    submitLabel=m("确认 Skill 并完成","Skillを確認して完了","Confirm skills and finish");
  }
  const back=stageIndex>0?'<button type="button" class="button secondary" data-onboarding-back>'+m("上一步","戻る","Back")+'</button>':"";
  if(replay)submitLabel=stageIndex===firstRunSetupStages.length-1?m("全部保存并完成","すべて保存して完了","Save all and finish"):m("暂存并继续","下書き保存して続ける","Save draft and continue");
  const navigation='<div class="onboarding-actions">'+back+'<button class="button primary" type="submit">'+submitLabel+'</button></div>';
  const descriptions={
    base:m("选择你平时主要用来记账的货币，并选好每月从几号开始统计。","普段使う通貨と、毎月何日から集計するかを選びます。","Choose your main currency and the day monthly totals should start."),
    accounts:m("添加一个账户，填上现在有多少钱。","口座を追加して、今いくらあるか入力します。","Add an account and enter how much is in it now."),
    api:m("使用你自己的模型服务凭据。","ご自身のモデルサービスを設定します。","Connect your own model service."),
    agents:m("选择各 Agent 使用的文字和图片服务。","各Agentのテキスト・画像サービスを選択します。","Choose text and image services for each Agent."),
    skills:m("检查随请求发送给模型的操作说明。","モデルに送信する指示内容を確認します。","Review the instructions sent to your model."),
  };
  dialog.innerHTML='<form id="firstRunSetupForm" class="first-run-setup-form" autocomplete="off">'+(replay?'<button type="button" class="button secondary onboarding-close" data-onboarding-close>'+m("退出教程","チュートリアルを終了","Exit tutorial")+'</button>':"")+'<div class="assistant-orb">'+icon("settings")+'</div>'+setupProgress(firstRunSetupStep)+'<h2 id="firstRunSetupTitle">'+labels[firstRunSetupStep]+'</h2><p class="muted onboarding-description">'+descriptions[firstRunSetupStep]+'</p>'+(replay?'<p class="fineprint onboarding-save-note">'+m("每一步只暂存在当前页面，不会更新云端。最后一步才统一提交；刷新或关闭页面会丢弃草稿。","各ステップはこのページ内に一時保存され、クラウドは更新されません。最後にまとめて送信します。更新・終了すると下書きは破棄されます。","Each step stays temporarily on this page; nothing is sent to the cloud until the final step. Refreshing or closing the page discards this draft.")+'</p>':"")+stepBody+'<p id="firstRunSetupError" class="first-run-setup-error hidden" role="alert"></p>'+navigation+'</form>';
  dialog.oncancel=event=>{if(!firstRunSetupReplay)event.preventDefault();else{firstRunSetupReplay=false;firstRunSetupDraft=null;}};
  const form=$("#firstRunSetupForm",dialog),errorBox=$("#firstRunSetupError",dialog);
  if(replay)restoreTutorialDraftForm(form);
  form.querySelector("[data-onboarding-close]")?.addEventListener("click",()=>{firstRunSetupReplay=false;firstRunSetupDraft=null;dialog.close();});
  form.querySelector("[data-onboarding-back]")?.addEventListener("click",()=>{
     if(firstRunSetupReplay){try{stageFirstRunSetupSettings(form,new FormData(form),accounts);}catch{captureTutorialDraftForm(form);}}
    firstRunSetupStep=firstRunSetupStages[stageIndex-1];renderFirstRunSetupStep();
  });
  form.querySelectorAll("[data-onboarding-default]").forEach(button=>button.addEventListener("click",async()=>{
    try{const defaults=await api("/api/default-skills");const target=form.querySelector('[name="skill-'+button.dataset.onboardingDefault+'"]');if(target)target.value=defaults[button.dataset.onboardingDefault]||"";}
    catch(error){errorBox.textContent=error.message||m("默认 Skill 暂时无法载入。","初期Skillを読み込めません。","Could not load the default skill.");errorBox.classList.remove("hidden");}
  }));
  form.onsubmit=async event=>{
    event.preventDefault();if(firstRunSetupBusy)return;
    const button=form.querySelector('button[type="submit"]'),formData=new FormData(form),baseSettings=setupBaseSettings();
    if(firstRunSetupReplay){
      try{
        errorBox.classList.add("hidden");
        const finished=stageFirstRunSetupSettings(form,formData,accounts);
        if(!finished){firstRunSetupStep=firstRunSetupStages[stageIndex+1];renderFirstRunSetupStep();return;}
        firstRunSetupBusy=true;form.querySelectorAll("button,input,select,textarea").forEach(control=>control.disabled=true);button.textContent=m("正在统一提交到云端…","まとめてクラウドに保存中…","Submitting all changes to cloud…");
        const draft=firstRunSetupDraft;
        const result=await runAction("onboarding_save",{settings:draft.settings,account:draft.account,adjustments:draft.balanceChanges,adjustmentDate:draft.adjustmentDate,confirmBalanceAdjustments:draft.confirmBalanceAdjustments},null,false);
        if(!result?.queued)await loadWorkspace(true);
        firstRunSetupReplay=false;firstRunSetupDraft=null;dialog.close();showToast(result?.queued?m("设置已先保存在本机，正在后台同步云端。","設定を端末に保存しました。クラウドへバックグラウンドで同期中です。","Settings are saved on this device and syncing to the cloud in the background."):m("所有设置已统一保存。","すべての設定をまとめて保存しました。","All settings were saved together."));
      }catch(error){errorBox.textContent=error.message||m("统一保存失败，设置草稿仍保留，请检查后重试。","一括保存に失敗しました。下書きは保持されています。確認して再試行してください。","Could not save the changes. Your draft is still here; review it and try again.");errorBox.classList.remove("hidden");}
      finally{if(firstRunSetupBusy){firstRunSetupBusy=false;if(dialog.open){form.querySelectorAll("button,input,select,textarea").forEach(control=>control.disabled=false);const currentButton=form.querySelector('button[type="submit"]');if(currentButton)currentButton.textContent=m("全部保存并完成","すべて保存して完了","Save all and finish");}}}
      return;
    }
    firstRunSetupBusy=true;form.querySelectorAll("button,input,select,textarea").forEach(control=>control.disabled=true);errorBox.classList.add("hidden");button.textContent=m("正在保存…","保存中…","Saving…");
    try{
      if(firstRunSetupStep==="base"){
        const baseCurrency=String(formData.get("baseCurrency")||""),billingCycleStartDay=Number(formData.get("billingCycleStartDay")),timeZone=String(formData.get("timeZone")||"");
        if(!["JPY","CNY","USD"].includes(baseCurrency)||!Number.isInteger(billingCycleStartDay)||billingCycleStartDay<1||billingCycleStartDay>31||!regionTimeZones.some(([value])=>value===timeZone))throw new Error(m("请选择主要记账货币、所在地区和每月统计起始日。","メイン通貨・所在地域・毎月の集計開始日を選択してください。","Choose your main currency, region, and monthly start day."));
        const cfg=deepCopy(prefs);cfg.baseCurrency=baseCurrency;cfg.billingCycleStartDay=billingCycleStartDay;cfg.timeZone=timeZone;cfg.onboardingStep="base";
        const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);firstRunSetupStep="accounts";
      }else if(firstRunSetupStep==="accounts"){
        const name=String(formData.get("name")||"").trim();
        const changedBalances={};
        if(firstRunSetupReplay&&!hiddenAmounts)for(const account of accounts){
          if(account.pending)continue;
          const value=String(formData.get("balance-"+account.id)||"").trim(),original=plainAmount(account.balanceMinor,account.minorDigits||0,account.currency);
          if(value&&value!==original)changedBalances[account.name]=value;
        }
        if(Object.keys(changedBalances).length&&formData.get("confirmBalanceAdjustments")!=="yes")throw new Error(m("请先勾选确认：修改余额会生成调整流水。","残高の変更で調整取引が作成されることを確認してください。","Confirm that changing balances will create adjustment entries."));
        if(name&&Object.keys(changedBalances).length)throw new Error(m("请分两次保存：先调整已有账户余额，或清空余额修改后添加新账户。","既存口座の残高調整と新規口座の追加は、別々に保存してください。","Save in two steps: adjust existing balances first, or clear those edits before adding an account."));
        if(Object.keys(changedBalances).length){
          const date=String(formData.get("adjustmentDate")||"");if(!date)throw new Error(m("请选择余额核对日期。","残高照合日を選択してください。","Choose a balance adjustment date."));
          const result=await runAction("reconcile",{date,postDifferences:true,amounts:changedBalances},null,false);if(!result?.queued)await loadWorkspace(true);
        }
        if(name){
          await api("/api/accounts",{method:"POST",body:JSON.stringify({name,type:String(formData.get("type")||"bank"),currency:String(formData.get("currency")||baseSettings.baseCurrency),openingBalance:String(formData.get("openingBalance")||"0"),openingDate:String(formData.get("openingDate")||workspace?.date||""),completeness:String(formData.get("completeness")||"known"),note:"",onboardingStep:"accounts"})});
          await loadWorkspace(true);
        }else if(!accounts.length&&!firstRunSetupReplay)throw new Error(m("请填写账户名称。","口座名を入力してください。","Enter an account name."));
        firstRunSetupStep="api";
      }else if(firstRunSetupStep==="api"){
        const cfg=deepCopy(prefs),old=cfg.profiles?.[0]||{},apiKey=String(formData.get("apiKey")||"");
        if(!String(formData.get("profileName")||"").trim()||!String(formData.get("apiUrl")||"").trim()||!String(formData.get("model")||"").trim()||(!old.keyPresent&&!apiKey))throw new Error(m("请填写 API 名称、地址、模型和密钥。","API名、URL、モデル名、キーを入力してください。","Enter the API name, endpoint, model, and key."));
        const profile={...old,id:old.id||crypto.randomUUID(),name:String(formData.get("profileName")).trim(),api_url:String(formData.get("apiUrl")).trim(),model:String(formData.get("model")).trim(),api_key:apiKey};
        cfg.profiles=[profile,...(cfg.profiles||[]).slice(1)];cfg.baseCurrency=baseSettings.baseCurrency;cfg.billingCycleStartDay=baseSettings.billingCycleStartDay;cfg.timeZone=baseSettings.timeZone;cfg.onboardingStep="api";
        const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);firstRunSetupStep="agents";
      }else if(firstRunSetupStep==="agents"){
        const cfg=deepCopy(prefs);cfg.agents={...(cfg.agents||{})};cfg.visionAgents={...(cfg.visionAgents||{})};
        cfg.agents.bookkeeping=String(formData.get("text-bookkeeping")||"");cfg.visionAgents.bookkeeping=String(formData.get("vision-bookkeeping")||"");cfg.agents.food_health=String(formData.get("text-food")||"");cfg.visionAgents.food_health=String(formData.get("vision-food")||"");
        if(Object.values(cfg.agents).some(value=>!value)||Object.values(cfg.visionAgents).some(value=>!value))throw new Error(m("请为两个 Agent 都选择文字和图片服务。","両方のAgentにテキストと画像サービスを選んでください。","Select text and image services for both Agents."));
        cfg.baseCurrency=baseSettings.baseCurrency;cfg.billingCycleStartDay=baseSettings.billingCycleStartDay;cfg.timeZone=baseSettings.timeZone;cfg.onboardingStep="agents";
        const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);firstRunSetupStep="skills";
      }else{
        const cfg=deepCopy(prefs);cfg.skills={...(cfg.skills||{})};
        cfg.skills.bookkeeping=String(formData.get("skill-bookkeeping")||"");cfg.skills.food_health=String(formData.get("skill-food_health")||"");
        if(Object.values(cfg.skills).some(value=>!String(value||"").trim()))throw new Error(m("请保留或恢复两个 Agent 的 Skill 文本。","両方のAgentにSkillテキストを設定してください。","Keep or restore skill text for both Agents."));
        cfg.baseCurrency=baseSettings.baseCurrency;cfg.billingCycleStartDay=baseSettings.billingCycleStartDay;cfg.timeZone=baseSettings.timeZone;cfg.onboardingStep="skills";cfg.completeOnboarding=true;
        const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);
        if(!workspace?.preferences?.onboardingRequired){
          if(firstRunSetupReplay){firstRunSetupReplay=false;dialog.close();showToast(m("设置已保存，新手教程完成。","設定を保存し、チュートリアルを終了しました。","Settings saved. Tutorial complete."));return;}
          showToast(m("新手设置完成，可以开始记账了。","初期設定が完了しました。記帳を開始できます。","Setup complete. You can start bookkeeping."));return;
        }
      }
      renderFirstRunSetupStep();
    }catch(error){errorBox.textContent=error.message||m("保存失败，请检查填写内容后重试。","保存できませんでした。入力内容を確認してください。","Could not save. Review the information and try again.");errorBox.classList.remove("hidden");}
    finally{firstRunSetupBusy=false;if(dialog.open){form.querySelectorAll("button,input,select,textarea").forEach(control=>control.disabled=false);const currentButton=form.querySelector('button[type="submit"]');if(currentButton){currentButton.textContent=firstRunSetupReplay?(firstRunSetupStep==="skills"?m("保存并完成","保存して完了","Save and finish"):m("保存并继续","保存して続ける","Save and continue")):(firstRunSetupStep==="skills"?m("确认 Skill 并完成","Skillを確認して完了","Confirm skills and finish"):m("保存并继续","保存して続ける","Save and continue"));}}}
  };
}
function startGuidedTutorial(){
  const dialog=$("#firstRunSetupDialog");if(!dialog)return;
  settingsInlineCapture?.();settingsInlineCapture=null;settingsDraft=null;firstRunSetupReplay=false;firstRunSetupDraft=null;moreTab="";settingsTab="general";
  if(dialog.open)dialog.close();
  const settings=deepCopy(workspace?.preferences||{});
  settings.baseCurrency=settings.baseCurrency||workspace?.settings?.base_currency||"JPY";
  settings.billingCycleStartDay=Number(settings.billingCycleStartDay||15);
  settings.timeZone=settings.timeZone||"";
  tutorialTour={mode:"required-setup",index:0,phase:"action",batchSave:true,finalRouted:false,draft:{settings,accounts:[],balanceChanges:{},categoryChanges:[],confirmedSettings:{baseCurrency:false,timeZone:false,billingCycleStartDay:false},adjustmentDate:workspace?.date||"",confirmBalanceAdjustments:false,postDifferences:false,dirty:false}};
  firstRunTourStarted=true;
  navigate("home");
  renderTutorialTour();
}
function syncFirstRunSetup(){
  const dialog=$("#firstRunSetupDialog");if(!dialog)return;
  if(tutorialTour)return;
  const required=!!(currentUser&&workspace&&workspace.preferences?.onboardingRequired);
  if(!required){if(dialog.open&&!firstRunSetupReplay)dialog.close();return;}
  if(firstRunTourStarted)return;
  firstRunTourStarted=true;startGuidedTutorial();
}
async function openFirstRunTutorial(){
  const dialog=$("#firstRunSetupDialog");if(!dialog||!currentUser)return;
  if(!workspace||workspaceOwner!==currentUser.id)await loadWorkspace(true);
  if(!workspace||workspaceOwner!==currentUser.id){showToast(workspaceError||m("账本尚未载入，请稍后重试。","台帳を読み込めません。もう一度お試しください。","The ledger is not loaded yet. Please try again."),true);return;}
  startGuidedTutorial();
}
$("#tutorialButton")?.addEventListener("click",()=>void openFirstRunTutorial());
$("#accountForm")?.addEventListener("submit",event=>{
  if(!workspace?.preferences?.onboardingRequired&&!tutorialTour?.batchSave)return;
  event.preventDefault();event.stopImmediatePropagation();
  const form=event.currentTarget,values=new FormData(form),submit=form.querySelector('button[type="submit"]');
  if(form.dataset.onboardingSaving)return;form.dataset.onboardingSaving="1";if(submit)submit.disabled=true;
  void guarded(async()=>{
    const data={name:String(values.get("name")||"").trim(),type:String(values.get("type")||"bank"),currency:String(values.get("currency")||"JPY"),openingBalance:String(values.get("openingBalance")||"0").trim(),openingDate:String(values.get("openingDate")||workspace.date||""),completeness:String(values.get("completeness")||"known"),note:"",onboardingStep:"accounts"};
    if(tutorialTour?.batchSave){const {onboardingStep,...account}=data;tutorialTour.draft.accounts.push(account);tutorialTour.draft.dirty=true;form.reset();form.querySelector('[name="openingDate"]').value=workspace.date||"";form.classList.add("hidden");renderTutorialDraftNotice();showToast(m("账户已暂存，尚未上传；最后会和其他设置一起保存。","口座を一時保存しました。まだ送信されず、最後に他の設定と一緒に保存します。","Account staged locally; it will be saved with the other settings at the end."));if(tutorialTour.mode==="required-setup")completeRequiredSetupStep("accounts");else renderTutorialTour();return;}
    await api("/api/accounts",{method:"POST",body:JSON.stringify(data)});form.reset();form.querySelector('[name="openingDate"]').value=workspace.date||"";form.classList.add("hidden");await loadWorkspace(true);showToast(m("账户已保存，可以继续设置。","口座を保存しました。設定を続けてください。","Account saved. Continue with setup."));
  }).finally(()=>{delete form.dataset.onboardingSaving;if(submit)submit.disabled=false;});
},true);
function renderMobile() {
  renderNavigation();renderDashboard();renderBackupWarning();renderAssetTabs();renderCredits();renderAssets();renderInvestment();renderMore();renderCloud();renderMobileTransactions();
  const editorDialog=$("#editorDialog"),editorCancel=$("#editorCancel"),editorSave=$("#editorSave");
  if(editorDialog&&!editorDialog.open){if(editorCancel)editorCancel.textContent=t("cancel");if(editorSave)editorSave.textContent=m("保存","保存","Save");}
  syncFirstRunSetup();if(tutorialTour){renderTutorialTour();renderTutorialDraftNotice();}
}
function renderBackupWarning() {
  const root=$("#githubBackupWarning");if(!root)return;
  root.replaceChildren();
  const preferences=workspace?.preferences||{};
  const status=String(preferences.autoStatus||"").trim();
  let kind=String(preferences.autoStatusKind||"");
  if(!kind&&status){
    if(/授权需要重新连接|授权已失效|授权需要更新|重新连接 GitHub|重新授权/.test(status))kind="reauthorize";
    else if(/内部错误|联系管理员/.test(status))kind="internal_error";
    else if(/备份未完成|上传失败|上传暂时失败|同步失败/.test(status))kind="provider_error";
  }
  if(!status||!["reauthorize","internal_error","conflict","provider_error","temporary"].includes(kind)){
    root.classList.add("hidden");return;
  }
  const message=document.createElement("span");message.className="github-backup-warning-message";message.textContent=status;root.append(message);
  if(kind==="reauthorize"){
    const action=document.createElement("button");action.type="button";action.className="text-button";action.dataset.action="backup-warning-reauthorize";
    action.textContent=m("重新授权","再認証","Reauthorize");root.append(action);
  }
  root.classList.remove("hidden");
}
function metric(label,value,extra="",cls="") {
  return '<article class="metric '+cls+'"><span>'+label+'</span><strong>'+value+'</strong>'+(extra?'<small>'+extra+'</small>':"")+'</article>';
}
function renderDashboard() {
  const root=$("#page-home");
  if(!workspace){root.innerHTML=workspaceError?'<div class="panel workspace-error" role="alert"><p>'+e(workspaceError)+'</p>'+b("workspace-retry",m("重试","再試行","Retry"),"","button primary")+'</div>':'<div class="panel empty-state">'+m("正在载入你的账本…","台帳を読み込み中…","Loading your ledger…")+'</div>';return;}
  const settings=workspace.settings||{},baseCurrency=settings.base_currency||"JPY";
  const p=workspace.profit||{},currencies=p.currencies||{},j=p.jpy_equivalent||{},base=p.base_equivalent||j,bal=workspace.balanceSheet||{};
  const currencyNet=Object.entries(currencies).filter(([,row])=>BigInt(row.net_minor||0)!==0n).map(([code,row])=>money(row.net_minor,code,row.minor_digits)).join(" · ")||money("0",baseCurrency);
  const currencyOrder=code=>({JPY:0,CNY:1,USD:2}[code]??3);
  const foreignNetAssets=Object.entries(bal.net_assets||{}).filter(([code,value])=>code!==baseCurrency&&BigInt(value||0)!==0n).sort(([a],[b])=>currencyOrder(a)-currencyOrder(b)||a.localeCompare(b)).map(([code,value])=>money(value,code)).join(" · ");
  const heroTitle=heroProfitMode?m("当期纯利润 · ","当期純利益 · ","Current net profit · ")+baseCurrency:m("主要记账货币余额 · ","メイン通貨の残高 · ","Main-currency balance · ")+baseCurrency;
  const heroAmount=heroProfitMode?money(base.net_minor||"0",baseCurrency):money(bal.net_assets?.[baseCurrency]||"0",baseCurrency);
  let heroSubtitle,heroCombined="";
  if(heroProfitMode){
    heroSubtitle=m("按记账当天的汇率换算","記帳日の為替レートで換算","Converted using the exchange rate on the entry date");
    const missingRates=Number(base.missing_conversion_count||0)>0;
    heroCombined=m("原币净利润","元通貨別の純利益","Native-currency net profit")+" · "+currencyNet+(missingRates?"（"+m("部分汇率缺失，合计不完整","一部の為替が未登録のため合計は不完全です","incomplete: some exchange rates are missing")+"）":"");
  }else{
    heroSubtitle=m("只显示这种货币的金额；其他货币不换算。","この通貨の金額だけを表示します。他の通貨は換算しません。","Only this currency is shown here. Other currencies are not converted.");
    if(foreignNetAssets)heroCombined=m("其他货币余额","その他の通貨の残高","Other-currency balances")+" · "+foreignNetAssets;
  }
  const total=settings.monthly_jpy_budget_minor||"0";
  const remaining=BigInt(total)-BigInt(j.expense_minor);
  const percent=BigInt(total)>0n?Math.min(100,Math.max(0,Number(BigInt(j.expense_minor)*100n/BigInt(total)))):0;
  root.innerHTML='<section class="hero-balance glass"><div class="hero-top"><span>'+heroTitle+'</span><span class="live-badge">'+m("我的账本","マイ台帳","My ledger")+'</span></div><div class="hero-value">'+heroAmount+'</div><p>'+heroSubtitle+'</p>'+(heroCombined?'<p class="hero-combined-profit">'+heroCombined+'</p>':"")+'<div class="hero-footer">'+b("hero-mode-toggle",icon("repeat")+m("切换","切替","Switch"),"","button hero-secondary hero-mode-toggle")+'<div class="hero-actions">'+b("page",icon("plus")+" "+m("记一笔","記帳する","Record"),"entry","button hero-primary")+b("page",m("查看账户","口座を見る","Accounts"),"assets","button hero-secondary")+'</div></div></section>'+
    '<div class="metrics-grid">'+metric(m("本期支出","今期の支出","Period spending"),money(base.expense_minor,baseCurrency),p.start+" — "+p.through,"expense-metric")+metric(m("本期收入","今期の収入","Period income"),money(base.income_minor,baseCurrency),m("按记账当天的汇率换算","記帳日の為替レートで換算","Converted using the exchange rate on the entry date"),"income-metric")+'</div>'+
    '<section class="panel budget-card"><div class="section-heading"><h2>'+m("预算，还剩","予算の残り","Room in your budget")+'</h2>'+b("module",icon("arrow"),"budget","icon-button")+'</div><strong class="budget-value">'+money(remaining)+'</strong><div class="budget-track"><progress max="100" value="'+percent+'"></progress></div><div class="spread muted"><span>'+m("已用","使用済み","Used")+' '+percent+'%</span><span>'+m("预算","予算","Budget")+' '+money(total)+'</span></div></section>'+
    '<section class="panel"><div class="section-heading"><h2>'+m("钱花在哪里","支出の内訳","Where it went")+'</h2>'+b("module",m("报表","レポート","Reports"),"reports","text-button accent")+'</div>'+categoryBars(base.categories,baseCurrency)+'</section>'+
    '<section class="panel"><div class="section-heading"><h2>'+m("最近记录","最近の記録","Latest activity")+'</h2>'+b("page",m("全部","すべて","See all"),"ledger","text-button accent")+'</div>'+(workspace.transactions.slice(0,4).map(txCard).join("")||empty(m("从第一笔开始记录生活","最初の記帳から始めましょう","Start with your first entry")))+'</section>'+
    (Number(base.missing_conversion_count||0)>0?'<p class="fineprint">'+m("有些以前的记录没有汇率，所以没算进主要记账货币合计。","過去の記録の一部に為替レートがなく、メイン通貨の合計に含まれていません。","Some past entries have no exchange rate, so they are not included in the main-currency total.")+'</p>':"");
}
function empty(text){return '<div class="empty-state">'+text+'</div>';}
function categoryBars(categories={},currency="JPY") {
  const entries=Object.entries(categories).sort((a,b)=>BigInt(b[1])>BigInt(a[1])?1:-1).slice(0,8);
  const max=entries.reduce((x,item)=>BigInt(item[1])>x?BigInt(item[1]):x,1n);
  return entries.map(([name,amount],index)=>'<div class="category-bar"><div class="spread"><span>'+e(name)+'</span><strong>'+money(amount,currency)+'</strong></div><svg viewBox="0 0 300 7" preserveAspectRatio="none" class="spark-bar color-'+index+'"><rect width="300" height="7" rx="3.5" class="bar-track"/><rect width="'+Number(BigInt(amount)*300n/max)+'" height="7" rx="3.5" class="bar-fill"/></svg></div>').join("")||empty(m("记录后会在这里呈现","記帳するとここに表示されます","Your spending will appear here"));
}
function transactionDisplayDescription(row){
  const description=String(row?.description||"");
  const legacy=description.match(/^信用卡欠款调整：[\s\S]*?欠款\s*([\d,]+(?:\.\d+)?)\s*(JPY|CNY|USD)[\s\S]*?本次快照估算欠款\s*([\d,]+(?:\.\d+)?)\s*(JPY|CNY|USD)/i);
  if(!legacy)return description;
  const currency=legacy[2].toUpperCase();
  if(currency!==String(row.currency||"").toUpperCase())return description;
  const card=(workspace?.cards||[]).find(value=>value.name===row.account_name&&String(value.currency||"").toUpperCase()===currency);
  if(!card)return description;
  const snapshots=workspace?.creditHistory?.[String(card.account_id)]?.snapshots||[];
  const current=snapshots.filter(value=>String(value.snapshot_date)===String(row.occurred_on)&&String(value.snapshot_type)==="manual")
    .sort((left,right)=>String(right.created_at||"").localeCompare(String(left.created_at||"")))[0];
  if(!current||current.limit_minor===null||current.limit_minor===undefined||current.available_minor===null||current.available_minor===undefined)return description;
  const createdAt=String(row.created_at||"");
  const prior=snapshots.filter(value=>value.limit_minor!==null&&value.limit_minor!==undefined&&createdAt&&String(value.created_at||"")<createdAt)
    .sort((left,right)=>String(right.created_at||"").localeCompare(String(left.created_at||"")))[0];
  const baselineLimit=prior?.limit_minor??current.limit_minor;
  const previousDebt=parseMinorPreview(legacy[1].replace(/,/g,""),currency);
  const previousAvailable=(BigInt(baselineLimit)-BigInt(previousDebt)).toString();
  const digits=Number(card.minor_digits||0),previousText=money(previousAvailable,currency,digits).replace(new RegExp("\\s*"+currency+"$"),"");
  return "信用卡额度盘点调整：可用额度 "+previousText+" → "+money(current.available_minor,currency,digits);
}
function txCard(row) {
  const arrow=row.kind==="income"?"↙":row.kind==="transfer"?"⇄":"↗";
  const account=row.kind==="transfer"?(row.account_name||"")+" → "+(row.to_account_name||""):row.account_name||m("备查","メモ","Memo");
  const sign=row.kind==="income"?"+":row.kind==="expense"?"−":"";
  const syncLabel=row.pendingDelete?(row.pendingDeleteDispatched?m("云端删除处理中","クラウドで削除中","Deletion processing in cloud"):row.pendingDeleteSending?m("正在确认云端接收状态","クラウドの受付状態を確認中","Checking whether the cloud accepted it"):m("待删除 · 可撤销","削除待ち・取り消し可能","Pending deletion · undo available")):row.pendingSync?(row.conflict?m("同步冲突，待核对","同期競合・確認待ち","Sync conflict"):m("云端同步中","クラウド同期中","Syncing to cloud")):"";
  return '<button class="transaction-card'+(row.pendingDelete?' pending-delete':'')+'" data-action="tx-detail" data-id="'+e(row.id)+'"><span class="transaction-icon kind-'+e(row.kind)+'">'+arrow+'</span><span class="transaction-description"><strong>'+e(transactionDisplayDescription(row))+'</strong><small>'+e(row.category_name||t(row.kind))+' · '+e(account)+'</small><time>'+e(row.occurred_on)+(row.needs_review&&row.needs_review!=="0"?" · "+t("review"):"")+(syncLabel?" · "+syncLabel:"")+'</time></span><span class="transaction-amount kind-'+e(row.kind)+'">'+sign+money(row.amount_minor,row.currency,row.currency_minor_digits||row.minor_digits)+'</span></button>';
}
function findTransactionById(id) {
  for (const rows of [workspace?.transactions, ledgerRangeRows, cachedBootstrap?.transactions]) {
    if (!Array.isArray(rows)) continue;
    const row = rows.find(item => String(item.id) === String(id));
    if (row) return row;
  }
  return null;
}
function renderMobileTransactions() {
  const node=$("#ledgerList");if(!node)return;
  let rows=(ledgerRangeRows&&($("#historyStart").value||$("#historyEnd").value)?ledgerRangeRows:null)||workspace?.transactions||cachedBootstrap?.transactions||[];
  const query=$("#historySearch").value.trim().toLocaleLowerCase(),start=$("#historyStart").value,end=$("#historyEnd").value;
  rows=rows.filter(row=>(!start||row.occurred_on>=start)&&(!end||row.occurred_on<=end)&&(!query||[row.description,row.account_name,row.to_account_name,row.category_name,row.amount_minor].join(" ").toLocaleLowerCase().includes(query)));
  const transactionCount=$("#transactionCount");if(transactionCount)transactionCount.textContent=rows.length+"";
  node.innerHTML=rows.map(txCard).join("")||empty(t("noTransactions"));
  const historyHint=$(".history-panel .section-heading p");
  if(historyHint){historyHint.removeAttribute("data-i18n");historyHint.textContent=m("按日期、账户或说明查找最近2000条记录","最近2000件を日付・口座・内容で検索","Search the latest 2,000 entries by date, account or description");}
}
function renderAssetTabs() {
  $("#assetTabs").innerHTML=[["cash",m("账户余额","口座残高","Account balances")],["credit",m("信用卡","カード","Credit")],["fixed",m("固定资产","固定資産","Property")]].map(([id,label])=>b("asset-tab",label,id,"pill "+(assetTab===id?"selected":""))).join("");
  $(".accounts-panel").classList.toggle("hidden",assetTab!=="cash");
  $("#creditPanel").classList.toggle("hidden",assetTab!=="credit");
  $("#fixedPanel").classList.toggle("hidden",assetTab!=="fixed");
}
function renderCredits() {
  const cards=workspace?.cards||[];
  $("#creditPanel").innerHTML='<div class="section-heading"><h2>'+m("信用卡管理","カード管理","Credit cards")+'</h2>'+b("add-card",icon("plus"),"","icon-button")+'</div>'+
    '<p class="fineprint">'+m("欠款为额度差额估算，不代表当月账单。还款仅记录转账，不操作银行。","債務は利用枠の差による目安です。返済は台帳内の振替のみです。","Debt is an estimate from credit availability. Repayments only record ledger transfers.")+'</p>'+
    (cards.map((card,i)=>'<article class="credit-card credit-'+i%3+'"><div class="spread"><h3>'+e(card.name)+'</h3>'+icon("card")+'</div><span>'+m("当前可用额度","利用可能額","Available credit")+'</span><strong>'+ (card.available_minor===null?"—":money(card.available_minor,card.currency,card.minor_digits))+'</strong><div class="credit-details"><span>'+m("总额度","利用限度額","Total limit")+'<b>'+(card.limit_minor===null?"—":money(card.limit_minor,card.currency,card.minor_digits))+'</b></span><span>'+m("欠款估算","債務の目安","Estimated debt")+'<b>'+(card.debt_estimate_minor===null?"—":money(card.debt_estimate_minor,card.currency,card.minor_digits))+'</b></span></div><p>'+m("快照","スナップショット","Snapshot")+' '+e(hiddenAmounts?"••••":card.snapshot_date||"—")+'</p>'+(card.pendingSync?'<p class="fineprint" role="status">'+m("已先在本机更新，正在后台同步云端。","端末に先に反映しました。クラウドへ同期中です。","Updated on this device first; syncing to cloud in the background.")+'</p>':'')+'<div class="button-row">'+b("account-rename",m("更改称呼","口座名を変更","Rename"),card.account_id)+b("credit-snapshot",m("录入快照","枠を入力","Snapshot"),card.account_id)+b("credit-repay",m("还款","返済","Repay"),card.account_id)+b("credit-history",m("恢复额度快照","枠履歴を復元","Restore snapshot"),card.account_id)+b("credit-plan",m("应还计划","返済予定","Due plan"),card.account_id)+(card.repayment_schedule&&card.repayment_schedule.last_status!=="计划已删除"?b("credit-plan-delete",m("删除计划","予定を削除","Delete plan"),card.account_id,"button danger-text"):"")+'</div></article>').join("")||empty(m("先登记一张信用卡","カードを追加してください","Add your first credit card")));
  const inactivePlanIds=new Set(cards.filter(card=>card.repayment_schedule&&card.repayment_schedule.enabled!=="1").map(card=>String(card.account_id)));
  if(inactivePlanIds.size)for(const button of $("#creditPanel").querySelectorAll('[data-action="credit-plan"]'))if(inactivePlanIds.has(String(button.dataset.id)))button.remove();
  for(const button of $("#creditPanel").querySelectorAll('[data-action="credit-plan-delete"]')){
    const card=cards.find(row=>String(row.account_id)===String(button.dataset.id));
    if(!card?.repayment_schedule||card.repayment_schedule.enabled!=="1")button.remove();
  }
}
function renderAssets() {
  const balanceRows=workspace?.balanceSheet?.rows||[];
  $("#fixedPanel").innerHTML='<div class="section-heading"><h2>'+m("固定资产","固定資産","Fixed assets")+'</h2>'+b("asset-edit",icon("plus"),"","icon-button")+'</div>'+
    (workspace?.assets||[]).map(asset=>{const row=balanceRows.find(item=>String(item.asset_id)===String(asset.id));const original=row?.original_cost_minor??asset.cost_minor;const depreciation=BigInt(row?.accumulated_depreciation_minor||"0");return '<article class="panel asset-card"><div class="spread"><h3>'+e(asset.name)+'</h3>'+b("asset-edit",m("编辑","編集","Edit"),asset.id,"text-button accent")+'</div><strong class="asset-price">'+money(original,asset.currency)+'</strong><p class="muted asset-depreciation">'+m("累计折旧","累計減価償却","Accumulated depreciation")+' <strong>'+(depreciation>0n?"−":"")+money(depreciation.toString(),asset.currency)+'</strong></p><div class="button-row">'+b("asset-toggle",asset.include_in_balance_sheet==="1"?m("已计入报表","集計対象","Included"):m("未计入报表","集計対象外","Excluded"),asset.id)+b("asset-delete",m("删除","削除","Delete"),asset.id,"button danger-text")+'</div></article>';}).join("");
}
const MUFG_FUND_API="https://developer.am.mufg.jp";
async function getMufgFundQuote(fundCode,quantity){
  const code=String(fundCode||"").trim();
  if(!/^\d{6}$/.test(code))throw new Error("unsupported_fund_code");
  const quantityText=String(quantity||"").trim(),match=quantityText.match(/^(\d{1,16})(?:\.(\d{1,8}))?$/);
  if(!match)throw new Error("invalid_fund_quantity");
  const whole=BigInt(match[1]),fraction=BigInt((match[2]||"").padEnd(8,"0")||"0"),quantityAtoms=whole*100000000n+fraction;
  if(quantityAtoms<=0n)throw new Error("invalid_fund_quantity");
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),9000);
  try{
    const response=await fetch(MUFG_FUND_API+"/fund_information_latest/fund_cd/"+code,{method:"GET",mode:"cors",credentials:"omit",cache:"no-cache",headers:{Accept:"application/json"},signal:controller.signal});
    if(!response.ok)throw new Error("quote_unavailable");
    const payload=await response.json(),item=payload?.datasets?.[0],nav=String(item?.nav||""),baseDate=String(item?.base_date||"");
    if(Number(payload?.result?.status)!==200||String(item?.fund_cd||"")!==code||!/^\d+$/.test(nav)||BigInt(nav)<=0n||!/^\d{8}$/.test(baseDate))throw new Error("quote_unavailable");
    // Japanese public NAVs are quoted per 10,000 units. Use integer arithmetic
    // and round down to whole yen, matching the displayed indicative value.
    const valueMinor=(BigInt(nav)*quantityAtoms)/(10000n*100000000n);
    return {fundCode:code,fundName:String(item.fund_name||""),nav,baseDate:baseDate.slice(0,4)+"-"+baseDate.slice(4,6)+"-"+baseDate.slice(6),valueMinor:valueMinor.toString()};
  }finally{clearTimeout(timer);}
}
async function refreshInvestmentQuotes(){
  if(!workspace||workspaceOwner!==currentUser?.id)return;
  const request=++investmentQuoteRequest,owner=currentUser?.id;
  const positions=(workspace.investments||[]).filter(row=>row.kind==="fund"&&/^\d{6}$/.test(String(row.fund_code||""))&&String(row.quantity||"").trim());
  investmentQuotes=new Map(positions.map(row=>[String(row.id),{status:"loading"}]));
  if(selectedPage==="investment")renderInvestment();
  let index=0;
  const workers=Array.from({length:Math.min(4,positions.length)},async()=>{
    while(index<positions.length){
      const row=positions[index++];
      try{const quote=await getMufgFundQuote(row.fund_code,row.quantity);if(request===investmentQuoteRequest)investmentQuotes.set(String(row.id),{status:"ready",...quote});}
      catch{if(request===investmentQuoteRequest)investmentQuotes.set(String(row.id),{status:"error"});}
    }
  });
  await Promise.all(workers);
  if(request===investmentQuoteRequest&&owner===currentUser?.id&&selectedPage==="investment")renderInvestment();
}
async function loadMufgFundCatalog(){
  if(!mufgFundCatalogPromise){
    mufgFundCatalogPromise=(async()=>{
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),9000);
      try{
        const response=await fetch(MUFG_FUND_API+"/fund_information_all_latest",{method:"GET",mode:"cors",credentials:"omit",cache:"default",headers:{Accept:"application/json"},signal:controller.signal});
        if(!response.ok)throw new Error("catalog_unavailable");
        const text=await response.text();if(new Blob([text]).size>2*1024*1024)throw new Error("catalog_too_large");
        const payload=JSON.parse(text),rows=payload?.datasets;
        if(Number(payload?.result?.status)!==200||!Array.isArray(rows)||rows.length>2000)throw new Error("catalog_unavailable");
        return rows.filter(row=>/^\d{6}$/.test(String(row?.fund_cd||""))&&String(row?.fund_name||"").trim()).map(row=>({fundCode:String(row.fund_cd),name:String(row.fund_name),nav:String(row.nav||""),baseDate:String(row.base_date||"")}));
      }finally{clearTimeout(timer);}
    })().catch(error=>{mufgFundCatalogPromise=null;throw error;});
  }
  return mufgFundCatalogPromise;
}
function installFundNameSearch(){
  const nameInput=$("#edit-name"),kindInput=$("#edit-kind"),currencyInput=$("#edit-currency"),codeInput=$("#edit-fundCode");
  if(!nameInput||!kindInput||!currencyInput||!codeInput)return;
  const fieldLabel=nameInput.closest(".field"),codeLabel=codeInput.closest(".field"),results=document.createElement("div");
  results.className="investment-fund-results";results.setAttribute("role","listbox");results.hidden=true;fieldLabel?.after(results);
  let timer=0,sequence=0;
  const updateVisibility=()=>{const isFund=kindInput.value==="fund";if(codeLabel)codeLabel.hidden=!isFund;if(!isFund){results.hidden=true;results.replaceChildren();}};
  const search=async()=>{
    const query=String(nameInput.value||"").trim().normalize("NFKC").toLocaleLowerCase();
    const current=++sequence;
    if(kindInput.value!=="fund"||query.length<2){results.hidden=true;results.replaceChildren();return;}
    results.hidden=false;results.innerHTML='<p class="investment-fund-search-status">'+m("正在查找三菱UFJ基金…","三菱UFJの投資信託を検索中…","Searching MUFG funds…")+'</p>';
    try{
      const catalog=await loadMufgFundCatalog();if(current!==sequence)return;
      const matches=catalog.filter(item=>(item.name+" "+item.fundCode).normalize("NFKC").toLocaleLowerCase().includes(query)).slice(0,8);
      if(!matches.length){results.innerHTML='<p class="investment-fund-search-status">'+m("没有找到该公司管理的基金；仍可手动填写估值。","該当する三菱UFJの投資信託がありません。評価額は手入力できます。","No matching MUFG fund. You can still enter the value manually.")+'</p>';return;}
      results.innerHTML=matches.map(item=>'<button type="button" class="investment-fund-option" data-fund-code="'+e(item.fundCode)+'"><strong>'+e(item.name)+'</strong><span>'+m("基金代码 ","ファンドコード ","Code ")+e(item.fundCode)+(item.nav?" · NAV "+e(item.nav):"")+'</span></button>').join("");
      results.querySelectorAll("[data-fund-code]").forEach(button=>button.addEventListener("click",()=>{
        const fund=catalog.find(item=>item.fundCode===button.dataset.fundCode);if(!fund)return;
        nameInput.value=fund.name;codeInput.value=fund.fundCode;currencyInput.value="JPY";kindInput.value="fund";results.hidden=true;results.replaceChildren();
      }));
    }catch{
      if(current===sequence)results.innerHTML='<p class="investment-fund-search-status">'+m("暂时无法读取基金目录，请稍后重试；也可以手动填写。","ファンド一覧を取得できません。後で再試行するか、手入力してください。","Fund list unavailable. Try later or enter the details manually.")+'</p>';
    }
  };
  nameInput.addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(()=>void search(),280);});
  kindInput.addEventListener("change",updateVisibility);updateVisibility();
}
function renderInvestment(){
  const root=$("#investmentPanel");if(!root)return;
  if(!workspace){root.innerHTML=workspaceError?'<div class="panel workspace-error" role="alert"><p>'+e(workspaceError)+'</p>'+b("workspace-retry",m("重试","再試行","Retry"),"","button primary")+'</div>':'<div class="panel empty-state">'+m("正在载入你的投资持仓…","投資の保有状況を読み込み中…","Loading investment holdings…")+'</div>';return;}
  const rows=Array.isArray(workspace?.investments)?workspace.investments:[];
  const currentValue=row=>investmentQuotes.get(String(row.id))?.status==="ready"?investmentQuotes.get(String(row.id)).valueMinor:String(row.value_minor||"0");
  const totals=new Map();
  for(const row of rows){
    const currency=String(row.currency||"JPY"),digits=Number(row.minor_digits??currencyMinorDigits(currency,0));
    const total=totals.get(currency)||{cost:0n,value:0n,digits};
    total.cost+=BigInt(String(row.cost_minor||0));total.value+=BigInt(currentValue(row));totals.set(currency,total);
  }
  if(!totals.size){const currency=String(workspace?.settings?.base_currency||"JPY");totals.set(currency,{cost:0n,value:0n,digits:currencyMinorDigits(currency,0)});}
  const summary=[...totals].map(([currency,total])=>{
    const profit=total.value-total.cost,cls=profit<0n?"negative":profit>0n?"positive":"";
    return '<article class="investment-total"><span>'+e(currency)+'</span><div><small>'+m("投入","投入額","Invested")+'</small><strong>'+money(total.cost.toString(),currency,total.digits)+'</strong></div><div><small>'+m("当前估值","現在の評価額","Current value")+'</small><strong>'+money(total.value.toString(),currency,total.digits)+'</strong></div><div><small>'+m("浮动盈亏","評価損益","Unrealized P/L")+'</small><strong class="'+cls+'">'+(profit>0n?"+":"")+money(profit.toString(),currency,total.digits)+'</strong></div></article>';
  }).join("");
  const kinds={fund:m("基金 / 投信","投資信託","Fund"),jp_stock:m("日本股票","日本株","Japan stock"),us_stock:m("美国股票","米国株","US stock"),other:m("其他","その他","Other")};
  const intro=m("按币种统计，不计入日常余额、收支或预算。三菱UFJ资管基金可搜索产品名并自动估值；打开本页时读取一次最新净值。其他产品可手动填写。","通貨別に集計し、日常の残高・収支・予算には含めません。三菱UFJアセットマネジメントの投信は商品名で検索して自動評価できます。本ページを開くと最新基準価額を1回取得します。その他の商品は手入力できます。","Totals stay separate from daily balances, income, spending, and budgets. Search MUFG Asset Management funds by name for automatic valuation; opening this page fetches the latest NAV once. Enter other products manually.");
  root.innerHTML='<section class="panel investment-overview"><div class="section-heading"><div><h2>'+m("投资持仓","投資の保有状況","Investment holdings")+'</h2><p class="muted">'+intro+'</p></div>'+b("investment-add",icon("plus"),"","icon-button")+'</div><div class="investment-totals">'+summary+'</div></section>'+
    (rows.length?'<section class="investment-list">'+rows.map(row=>{const currency=String(row.currency||"JPY"),digits=Number(row.minor_digits??currencyMinorDigits(currency,0)),quote=investmentQuotes.get(String(row.id)),value=BigInt(currentValue(row)),profit=value-BigInt(String(row.cost_minor||0)),cls=profit<0n?"negative":profit>0n?"positive":"";let updated=row.updated_on||"";if(quote?.status==="loading")updated=m("正在更新基金净值…","基準価額を更新中…","Updating fund NAV…");else if(quote?.status==="ready")updated=m("净值日期 ","基準価額日 ","NAV date ")+quote.baseDate;else if(quote?.status==="error")updated=m("自动估值暂不可用，显示手动估值","自動評価を取得できず、手入力の評価額を表示","Auto valuation unavailable; showing the manual value");else if(row.kind==="fund"&&row.fund_code)updated=m("打开投资页时自动更新","投資ページを開くと自動更新","Refreshes when Investments opens");return '<article class="panel investment-position"><div class="investment-position-heading"><div><h3>'+e(row.name)+'</h3><small>'+e(kinds[row.kind]||kinds.other)+' · '+e(currency)+(row.quantity?" · "+e(row.quantity)+" "+(row.kind==="fund"?m("口","口","units"):m("份","株","shares")):"")+(row.kind==="fund"&&row.fund_code?" · "+m("基金代码 ","コード ","Code ")+e(row.fund_code):"")+'</small></div><span class="investment-updated">'+e(updated)+(row.pendingSync?" · "+m("待同步","同期待ち","Pending sync"):"")+'</span></div><div class="investment-position-values"><div><small>'+m("投入","投入額","Invested")+'</small><strong>'+money(row.cost_minor,currency,digits)+'</strong></div><div><small>'+m("当前估值","現在の評価額","Current value")+'</small><strong>'+money(value.toString(),currency,digits)+'</strong></div><div><small>'+m("浮动盈亏","評価損益","Unrealized P/L")+'</small><strong class="'+cls+'">'+(profit>0n?"+":"")+money(profit.toString(),currency,digits)+'</strong></div></div><div class="investment-position-actions">'+b("investment-edit",m("修改持仓","保有情報を編集","Edit holding"),row.id,"text-button accent")+b("investment-delete",m("删除","削除","Delete"),row.id,"text-button danger-text")+'</div></article>';}).join("")+'</section>':'<section class="panel investment-empty"><span class="module-icon">'+icon("investment")+'</span><h3>'+m("投资资产：0","投資資産：0","Investment assets: 0")+'</h3><p>'+m("买入后点右上角“+”录入产品、投入金额和当前估值。基金可搜索三菱UFJ资管产品并填入口数自动估值；其他产品可手动录入。","購入後、右上の「+」から商品・投資額・評価額を登録します。投信は三菱UFJアセットマネジメントの商品を検索し、口数を入力すると自動評価できます。その他は手入力できます。","After buying, tap + to enter the product and invested amount. MUFG Asset Management funds can be searched and valued from your unit count; enter other products manually.")+'</p></section>');
}
const modules=()=>[
  ["rules","card",m("付款方式与扣款顺序","支払ルールと優先順位","Payment rules"),m("用途匹配，按账户顺序扣款","用途と口座優先順位","Scenarios and account priorities")],
  ["points","points",m("积分管理","ポイント管理","Points"),m("查看积分余额，设置消费自动返还","ポイント残高と自動還元を管理","Track points and set automatic rewards")],
  ["recurring","repeat",m("定期付款与收入","定期支払・収入","Recurring entries"),m("周期、账单币种与到期处理","周期・請求通貨・期日処理","Schedules, currencies and due dates")],
  ["finance","chart",m("财务报表和预算","財務レポートと予算","Financial reports & budget"),m("账户余额、收支和预算管理","口座残高・収支・予算の管理","Account balances, income, spending, and budgets")],
  ["food","food",m("食材与饮食健康","食材と食生活","Food & wellbeing"),m("采购、食用记录与回顾","購入・食事記録・振り返り","Purchases, meals and reviews")],
  ["backup","cloud",m("备份与多设备恢复","バックアップと復元","Backup & restore"),m("GitHub、Gitee 与本机快照","GitHub・Gitee・ローカル","GitHub, Gitee and local snapshots")],
  ["categories","book",m("记账类别","取引カテゴリ","Categories"),m("收入、支出与三种显示语言","収入・支出・表示名","Income, expense and display names")],
  ["settings","settings",m("设置","設定","Settings"),m("通用设置、记账类别、备份与 Agent 相关","一般設定、取引カテゴリ、バックアップ、Agent関連","General settings, categories, backup and Agent settings")],
  ["install","plus",m("安装到 iPhone","iPhoneにインストール","Install on iPhone"),m("添加到主屏幕与离线使用","ホーム画面・オフライン","Home Screen and offline access")],
];
function renderMore() {
  const catalog=favoriteCatalog(),saved=getFavorites(),editing=favoritesEditing;
  const favorites='<section class="mobile-favorites"><div class="section-heading"><h2>'+m("常用功能","よく使う機能","Quick access")+'</h2><div class="favorite-tools">'+b("favorites-edit",editing?m("完成","完了","Done"):m("编辑","編集","Edit"),"","text-button accent")+b("favorites-add",icon("plus"),"","icon-button")+'</div></div>'+
    (saved.length?'<div class="favorite-grid">'+saved.map(id=>{const item=catalog.find(row=>row.id===id);return item?'<div class="favorite-item">'+b("favorite",'<span class="module-icon">'+icon(item.icon)+'</span><strong>'+item.title+'</strong>',id,"favorite-tile")+(editing?b("favorite-remove","×",id,"favorite-remove"):'')+'</div>':"";}).join("")+'</div>':'<p class="muted">'+m("点击 + 添加常用功能。","＋から機能を追加できます。","Tap + to add shortcuts.")+'</p>')+
    (editing?'<div class="favorite-picker"><p>'+m("添加常用功能","機能を追加","Add a shortcut")+'</p><div class="favorite-options">'+catalog.filter(item=>!saved.includes(item.id)).map(item=>b("favorite-add",icon(item.icon)+" "+item.title,item.id,"text-button")).join("")+'</div></div>':"")+'</section>';
  $("#moreMenu").innerHTML=favorites+modules().filter(([id])=>!["backup","categories"].includes(id)).map(([id,ico,title,subtitle])=>'<button class="module-row" data-action="module" data-id="'+id+'"><span class="module-icon">'+icon(ico)+'</span><span><strong>'+title+'</strong><small>'+subtitle+'</small></span>'+icon("arrow")+'</button>').join("");
  $("#moreMenu").classList.toggle("hidden",!!moreTab);
  $("#modulePanel").classList.toggle("hidden",!moreTab);
  $("#backupPage").classList.add("hidden");
  if(moreTab){
    if(moreTab==="backup"||moreTab==="categories"){settingsTab=moreTab;moreTab="settings";}
    renderModule(moreTab);
  }
}
window.addEventListener("household-language-changed",()=>{
  if(selectedPage==="more"&&["settings","rules","points"].includes(moreTab)){if(moreTab==="points")capturePointRewardsDraft();renderModule(moreTab);}
});
function favoriteCatalog(){return [
  {id:"home",icon:"home",title:m("总览","概要","Overview")},
  {id:"entry",icon:"chat",title:m("记账","記帳","Record")},
  {id:"ledger",icon:"book",title:m("账单记录","取引一覧","Ledger")},
  {id:"investment",icon:"investment",title:m("投资","投資","Investments")},
  {id:"assets",icon:"wallet",title:m("余额","残高","Balances")},
  ...modules().filter(([id])=>!["backup","categories"].includes(id)).map(([id,ico,title])=>({id,icon:ico,title}))
];}
function getFavorites(){const key="hh-mobile-favorites:"+(currentUser?.id||"guest");const defaults=["ledger","assets","finance"];try{const stored=localStorage.getItem(key);const values=stored===null?defaults:JSON.parse(stored);const allowed=new Set(favoriteCatalog().map(item=>item.id));return Array.isArray(values)?[...new Set(values.map(id=>["budget","reports"].includes(id)?"finance":["backup","categories"].includes(id)?"settings":id).filter(id=>allowed.has(id)))].slice(0,8):defaults;}catch{return defaults;}}
function saveFavorites(values){localStorage.setItem("hh-mobile-favorites:"+(currentUser?.id||"guest"),JSON.stringify(values));}
function openFavorite(id){if(["home","entry","ledger","investment","assets"].includes(id)){navigate(id);return;}navigate("more");if(id==="rules")paymentRulesDraft=deepCopy(workspace?.preferences?.paymentRules||[]);if(id==="points")pointRewardsDraft=deepCopy(workspace?.preferences?.pointRewardRules||[]);if(["backup","categories","settings"].includes(id)){settingsTab=id==="backup"?"backup":id==="categories"?"categories":"general";moreTab="settings";}else moreTab=id;renderMore();}
function moduleHeader(id) {
  const item=modules().find(row=>row[0]===id);
  return '<div class="module-header">'+b("module-back",m("‹ 更多","‹ その他","‹ More"),"","text-button accent")+'<h2>'+e(item?.[2]||"")+'</h2></div>';
}
function financeTable(headers,rows,label,variant="") {
  const head=headers.map(value=>'<th scope="col">'+e(value)+'</th>').join("");
  const body=rows.length?rows.map((row,index)=>'<tr class="'+(row.kind||"")+(index%2?" finance-stripe-alt":"")+'">'+row.cells.map((cell,column)=>'<td class="finance-col-'+column+'">'+cell+'</td>').join("")+'</tr>').join(""):'<tr><td class="finance-empty" colspan="'+headers.length+'">'+m("暂无报表数据","レポートデータがありません","No report data")+'</td></tr>';
  return '<div class="finance-table-scroll" role="region" tabindex="0" aria-label="'+e(label)+'"><table class="finance-table '+variant+'"><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
}
function billingCycleSettingsHtml(){
  const cycleStartDay=Number((tutorialTour?.batchSave?tutorialTour.draft.settings.billingCycleStartDay:workspace?.preferences?.billingCycleStartDay)||15);
  const cycleOptions=Array.from({length:31},(_,index)=>index+1).map(day=>'<option value="'+day+'" '+(cycleStartDay===day?'selected':'')+'>'+day+' '+m("号","日","day")+'</option>').join("");
  return '<form id="billingCycleForm" class="profile-editor billing-cycle-settings"><h3>'+m("每月统计周期","毎月の集計期間","Monthly totals period")+'</h3><label class="field"><span>'+m("每月从几号开始统计","毎月何日から集計するか","Which day monthly totals start")+'</span><select id="settings-billing-cycle-day">'+cycleOptions+'</select></label><p class="fineprint">'+m("选择每月从几号开始统计。比如选15号，就是每月15号到下月14号。如果某个月没有这一天，就从当月最后一天开始。改好后，总览、报表和预算会重新统计，已有记录日期不会变。","毎月何日から集計するか選びます。たとえば15日なら、毎月15日から翌月14日までです。その日がない月は月末から始めます。変更後、概要・レポート・予算を再集計します。取引日は変わりません。","Choose which day monthly totals start. For example, the 15th means the 15th through the 14th of the next month. If a month has no such day, the period starts on its last day. Totals update; existing entry dates stay the same.")+'</p><div class="button-row"><button class="button primary" type="submit">'+m("保存设置","設定を保存","Save settings")+'</button></div></form>';
}
function categoriesPanelContent(){
  return billingCycleSettingsHtml()+'<div class="settings-category-area"><div class="button-row settings-category-actions">'+b("category-add",icon("plus")+" "+m("添加类别","カテゴリを追加","Add category"))+ '</div><section class="panel settings-category-list">'+(cachedBootstrap?.categories||[]).map((row,index)=>'<div class="settings-category-row"><div class="settings-category-copy"><strong>'+e(row.display_name)+'</strong><small>'+e(t(row.kind))+" · "+e(row.name)+'</small></div>'+b("category-edit",m("翻译","表示名","Translate"),index,"text-button accent")+'</div>').join("")+'</section></div>';
}
function generalSettingsContent(){
  const currentMode=window.HouseholdAppearance.mode,languageOptions=[["zh-CN","简体中文"],["ja-JP","日本語"],["en-US","English"]];
  const languagePanel='<section class="profile-editor"><h3>'+m("语言","言語","Language")+'</h3><label class="field"><span>'+m("界面语言","表示言語","Interface language")+'</span><select id="languageSelect">'+languageOptions.map(([value,label])=>'<option value="'+value+'" '+(currentLanguage===value?'selected':'')+'>'+label+'</option>').join("")+'</select></label><p class="fineprint">'+m("语言只保存在当前浏览器，不会同步到其他设备。切换时会先确认；确认后清空 Agent 对话和未发送内容。","言語設定はこのブラウザーだけに保存され、他の端末には同期されません。変更前に確認し、確定後はAgentの会話と未送信内容を消去します。","Language is saved in this browser only and is not synced to other devices. Switching asks for confirmation and then clears Agent chats and unsent content.")+'</p></section>';
  const baseCurrency=(tutorialTour?.batchSave?tutorialTour.draft.settings.baseCurrency:"")||workspace?.settings?.base_currency||"JPY";
  const currencyPanel='<form id="baseCurrencyForm" class="profile-editor"><h3>'+m("主要记账货币","メインの記帳通貨","Main bookkeeping currency")+'</h3><label class="field"><span>'+m("总览和报表显示的货币","概要とレポートに表示する通貨","Currency shown in overview and reports")+'</span><select id="baseCurrencySelect">'+[["JPY","JPY · 日元"],["CNY","CNY · 人民币"],["USD","USD · 美元"]].map(([value,label])=>'<option value="'+value+'" '+(baseCurrency===value?'selected':'')+'>'+label+'</option>').join("")+'</select></label><p class="fineprint">'+m("这里选择总览和报表主要使用的货币。账户余额和以前的记录会保留原来的货币；其他货币需要合计时，软件会按汇率换算。现在的预算仍按日元计算。","概要とレポートに使う通貨を選びます。口座残高と過去の記録は元の通貨のままです。他の通貨を合計する場合は為替レートで換算します。予算は引き続き日本円で計算します。","Choose the main currency shown in the overview and reports. Account balances and past entries keep their original currency. Other currencies are converted when a total is needed. Budgets are still calculated in JPY.")+'</p><div class="button-row"><button class="button primary" type="submit">'+m("保存设置","設定を保存","Save settings")+'</button></div></form>';
  const settings=tutorialTour?.batchSave?tutorialTour.draft.settings:(workspace?.preferences||{}),configured=Boolean(settings.timeZoneConfigured||!workspace?.preferences?.onboardingRequired),timeZone=configured?(settings.timeZone||"Asia/Tokyo"):"";
  const regionPanel='<form id="regionSettingsForm" class="profile-editor"><h3>'+m("所在地区","所在地域","Region")+'</h3><label class="field"><span>'+m("当地日期和时间","現地の日付と時刻","Local date and time")+'</span><select id="regionTimeZoneSelect" required>'+regionTimeZoneOptions(timeZone,!timeZone)+'</select></label><p class="fineprint">'+m("用于账单日期、自动还款和“今天/昨天”等日期判断。按该地区实际时间运行，夏令时会自动调整。更改地区不会修改已记账日期。","明細の日付、自動返済、「今日／昨日」などの判定に使います。選択した地域の時刻で動作し、夏時間も自動調整します。過去の取引日は変更しません。","Used for entry dates, automatic repayments, and words like today or yesterday. Schedules use this region's local clock and adjust for daylight saving time. Existing entry dates will not change.")+'</p><div class="button-row"><button class="button primary" type="submit">'+m("保存设置","設定を保存","Save settings")+'</button></div></form>';
  return '<div class="settings-general-grid">'+appearanceSettingsHtml(currentMode)+languagePanel+currencyPanel+regionPanel+'</div>';
}
function renderModule(id) {
  if(id==="budget"||id==="reports"){
    financialTab=id==="budget"?"budget":"balance";
    id="finance";
  }
  const root=$("#modulePanel"), w=workspace;if(!w){root.innerHTML=moduleHeader(id)+'<div class="panel workspace-error" role="alert"><p>'+e(workspaceError||m("账本尚未载入。","台帳を読み込み中です。","The ledger has not loaded yet."))+'</p>'+b("workspace-retry",m("重试","再試行","Retry"),"","button primary")+'</div>';return;}
  let content=moduleHeader(id);
  if(id==="settings"){
    const queuePanel=document.querySelector(".queue-panel");if(queuePanel&&!$("#backupPage").contains(queuePanel))$("#backupPage").append(queuePanel);
    const tabs=[["general",m("通用设置","一般設定","General settings")],["categories",m("记账类别","取引カテゴリ","Categories")],["backup",m("备份","バックアップ","Backup")],["agent",m("Agent 相关","Agent関連","Agent settings")]];
    content+='<div class="mode-pills settings-tabs" role="tablist" aria-label="'+m("设置功能","設定機能","Settings sections")+'">'+tabs.map(([key,label])=>b("settings-tab",label,key,"pill "+(settingsTab===key?"selected":""))).join("")+'</div><div id="settingsPane" class="settings-pane"><div id="settingsPaneContent"></div><div id="settingsQueue"></div></div>';
    root.innerHTML=content;
    const pane=$("#settingsPaneContent");
    if(settingsTab==="general"){
      pane.innerHTML=generalSettingsContent();
      pane.querySelector("#settings-appearance")?.addEventListener("change",event=>{
        const previous=window.HouseholdAppearance.mode;
        try{window.HouseholdAppearance.save(event.target.value);showToast(m("外观已保存","外観を保存しました","Appearance saved"));}
        catch{event.target.value=previous;showToast(m("无法保存外观，请检查浏览器存储权限。","外観を保存できません。ブラウザーのストレージ設定を確認してください。","Could not save appearance. Check browser storage permissions."),true);}
      });
      pane.querySelector("#baseCurrencyForm")?.addEventListener("submit",async event=>{
        event.preventDefault();
        const previous=(tutorialTour?.batchSave?tutorialTour.draft.settings.baseCurrency:"")||workspace?.settings?.base_currency||"JPY";
        const baseCurrency=event.currentTarget.querySelector("#baseCurrencySelect").value;
        if(baseCurrency===previous){if(tutorialTour?.batchSave&&(workspace?.preferences?.onboardingRequired||tutorialTour.mode==="required-setup")){stageGuidedTutorialSettings({baseCurrency});return;}return;}
        const confirmed=await confirmOnce(m("更改主要记账货币","メインの記帳通貨を変更","Change main currency"),m("总览和报表里的合计金额会重新计算。账户余额和以前的记录不会改变；现有预算仍按日元计算。要继续吗？","概要とレポートの合計を再計算します。口座残高と過去の記録は変わりません。今の予算は日本円のままです。続けますか？","Totals in the overview and reports will be recalculated. Account balances and past entries will not change. Existing budgets stay in JPY. Continue?"));
        if(!confirmed){event.currentTarget.querySelector("#baseCurrencySelect").value=previous;return;}
        if(stageGuidedTutorialSettings({baseCurrency}))return;
        const cfg=deepCopy(workspace.preferences||{});cfg.baseCurrency=baseCurrency;if(workspace.preferences?.onboardingRequired)cfg.onboardingStep="base";
        await guarded(async()=>{const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);renderModule("settings");if(!result?.queued)showToast(m("主要记账货币已保存","メインの記帳通貨を保存しました","Main currency saved"));});
      });
      pane.querySelector("#regionSettingsForm")?.addEventListener("submit",async event=>{
        event.preventDefault();
        const timeZone=String(event.currentTarget.querySelector("#regionTimeZoneSelect").value||"");
        if(!regionTimeZones.some(([value])=>value===timeZone)){showToast(m("请选择所在地区。","所在地域を選択してください。","Choose a region."),true);return;}
        const previous=(tutorialTour?.batchSave?tutorialTour.draft.settings.timeZone:"")||workspace?.preferences?.timeZone||"Asia/Tokyo";
        if(timeZone===previous&&workspace?.preferences?.timeZoneConfigured){if(tutorialTour?.batchSave&&(workspace?.preferences?.onboardingRequired||tutorialTour.mode==="required-setup")){stageGuidedTutorialSettings({timeZone});return;}return;}
        if(stageGuidedTutorialSettings({timeZone}))return;
        const cfg=deepCopy(workspace?.preferences||{});cfg.timeZone=timeZone;
        if(workspace?.preferences?.onboardingRequired)cfg.onboardingStep="base";
        await guarded(async()=>{const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);renderModule("settings");if(!result?.queued)showToast(m("所在地区已保存，后续日期和定时操作将使用当地时间。","所在地域を保存しました。今後の日付と予定は現地時刻を使います。","Region saved. Future dates and scheduled actions will use local time."));});
      });
    }
    else if(settingsTab==="categories"){
      pane.innerHTML=categoriesPanelContent();
      pane.querySelector("#billingCycleForm")?.addEventListener("submit",async event=>{
        event.preventDefault();
        const cfg=deepCopy(workspace.preferences);
        cfg.billingCycleStartDay=Number(event.currentTarget.querySelector("#settings-billing-cycle-day").value);if(workspace.preferences?.onboardingRequired){cfg.baseCurrency=workspace.settings?.base_currency||"JPY";cfg.onboardingStep="base";}
        if(stageGuidedTutorialSettings({billingCycleStartDay:cfg.billingCycleStartDay}))return;
        await guarded(async()=>{const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);renderModule("settings");if(!result?.queued)showToast(m("每月统计设置已保存","毎月の集計設定を保存しました","Monthly totals settings saved"));});
      });
    }
    else if(settingsTab==="backup"){renderCloud(pane,false);$("#settingsQueue").append(queuePanel);}
    else void editSettings(true);
    return;
  }
  if(id==="recurring")content+='<div class="button-row">'+b("recurring-edit",icon("plus")+" "+m("新增规则","予定を追加","New schedule"))+b("run-due",m("处理到期项目","期日を処理","Process due entries"))+'</div>'+
    w.recurring.map(row=>'<article class="panel"><div class="spread"><h3>'+e(row.name)+'</h3><strong>'+money(row.amount_minor,row.currency,row.minor_digits)+'</strong></div><p>'+e(row.account_name)+" · "+e(row.category_name)+'</p><p class="muted">'+e(row.next_due_date)+" · "+e({daily:m("每天","毎日","Daily"),weekly:m("每周","毎週","Weekly"),monthly:m("每月","毎月","Monthly"),yearly:m("每年","毎年","Yearly")}[row.frequency])+'</p><div class="button-row">'+b("recurring-edit",m("编辑","編集","Edit"),row.id)+b("recurring-toggle",row.enabled==="1"?m("暂停","停止","Pause"):m("启用","有効化","Enable"),row.id)+b("recurring-delete",m("删除","削除","Delete"),row.id,"button danger-text")+'</div></article>').join("");
  if(id==="rules"){
    const rules=paymentRulesDraft||(paymentRulesDraft=deepCopy(w.preferences?.paymentRules||[])),accounts=fieldsAccount();
    content+='<p class="fineprint payment-rules-intro">'+m("用途说明什么时候使用这条规则；扣款顺序决定优先从哪个账户付款。","用途はルールを使う場面、引落順は優先する口座を表します。","Purpose tells when to use a rule; the order sets which account pays first.")+'</p><div class="button-row payment-rules-tools">'+b("rule-add",icon("plus")+" "+m("添加规则","ルールを追加","Add rule"))+b("payment-rules-save",m("保存","保存","Save"),"","button primary")+'</div>';
    const cards=rules.map((rule,index)=>'<section class="rule-editor" data-rule="'+index+'"><div class="spread"><strong>'+m("规则","ルール","Rule")+' '+(index+1)+'</strong>'+b("rule-remove",m("删除规则","ルールを削除","Delete rule"),index,"text-button danger-text")+'</div><label class="field"><span>'+m("支付账户","支払口座","Payment account")+'</span><select data-rule-key="payment_method">'+accounts.map(([name,label])=>'<option value="'+e(name)+'" '+(rule.payment_method===name?"selected":"")+'>'+e(label)+'</option>').join("")+'</select></label><label class="field"><span>'+t("currency")+'</span><select data-rule-key="currency">'+[["",m("不限","指定なし","Any")],["JPY","JPY"],["CNY","CNY"],["USD","USD"]].map(([value,label])=>'<option value="'+value+'" '+(rule.currency===value?"selected":"")+'>'+label+'</option>').join("")+'</select></label><label class="field"><span>'+m("用途提示","適用する用途","Purpose / scenario")+'</span><textarea data-rule-key="purpose" rows="2">'+e(rule.purpose||"")+'</textarea></label><p class="fineprint">'+m("从上到下依次扣款","上から順に引き落とし","Funding priority, top to bottom")+'</p><div class="funding-order">'+(rule.account_order||[rule.payment_method]).map((name,position)=>'<div class="order-row"><span>'+(position+1)+'</span><select data-order="'+position+'">'+(cachedBootstrap?.accounts||[]).map(account=>'<option value="'+e(account.name)+'" '+(account.name===name?"selected":"")+'>'+e(account.name)+" · "+e(account.currency)+'</option>').join("")+'</select>'+b("order-up","↑",index+":"+position,"icon-button")+b("order-down","↓",index+":"+position,"icon-button")+b("order-remove","×",index+":"+position,"icon-button")+'</div>').join("")+'</div>'+b("order-add",m("添加扣款来源","引落元を追加","Add funding source"),index)+'</section>').join("");
    content+='<div class="payment-rules-list">'+(cards.length?cards:'<section class="panel payment-rules-empty"><p>'+m("还没有付款规则，添加一条后就能按用途和顺序选择账户。","支払ルールがありません。追加すると用途と優先順位で口座を選べます。","No payment rules yet. Add one to choose accounts by purpose and priority.")+'</p>'+b("rule-add",icon("plus")+" "+m("添加规则","ルールを追加","Add rule"))+'</section>')+'</div>';
  }
  if(id==="points"){
    const rules=pointRewardsDraft||(pointRewardsDraft=deepCopy(w.preferences?.pointRewardRules||[]));
    const pointAccounts=(cachedBootstrap?.accounts||[]).filter(account=>account.type==="points"&&account.currency==="JPY");
    const paymentAccounts=(cachedBootstrap?.accounts||[]).filter(account=>account.type!=="points");
    const balances=(w.cash||[]).filter(account=>account.account_type==="points");
    const recent=(w.transactions||[]).filter(row=>String(row.source||"").startsWith("auto_point_reward:")).slice(0,12);
    const selectOptions=(items,selected,emptyLabel)=>items.length?items.map(account=>'<option value="'+e(String(account.id))+'" '+(String(selected)===String(account.id)?"selected":"")+'>'+e(account.name)+" · "+e(account.currency)+'</option>').join(''):'<option value="">'+e(emptyLabel)+'</option>';
    const cards=rules.map((rule,index)=>'<section class="point-rule" data-point-rule="'+index+'"><div class="point-rule-head"><strong>'+m("返还规则","還元ルール","Reward rule")+' '+(index+1)+'</strong>'+b("point-rule-remove",m("删除","削除","Remove"),index,"text-button danger-text")+'</div><div class="point-rule-fields"><label class="field"><span>'+m("付款账户","支払口座","Payment account")+'</span><select data-point-rule-key="payment_account_id">'+selectOptions(paymentAccounts,rule.payment_account_id,m("没有可用账户","利用できる口座がありません","No eligible accounts"))+'</select></label><label class="field"><span>'+m("积分存入","還元先ポイント口座","Points account")+'</span><select data-point-rule-key="points_account_id">'+selectOptions(pointAccounts,rule.points_account_id,m("请先创建积分账户","先にポイント口座を作成してください","Create a points account first"))+'</select></label><label class="field point-rate-field"><span>'+m("返还比例（%）","還元率（%）","Reward rate (%)")+'</span><div class="point-rate-input"><input type="number" inputmode="decimal" min="0.01" max="100" step="0.01" data-point-rule-key="rate_percent" value="'+e((Number(rule.rate_bps||0)/100).toFixed(2))+'"><span>%</span></div></label></div></section>').join("");
    const balanceCards=balances.length?balances.map(account=>'<article class="point-balance-card"><span>'+e(account.account_name)+'</span><strong>'+money(account.balance_minor,"JPY",account.minor_digits,"points")+'</strong></article>').join(""):'<p class="fineprint">'+m("还没有积分账户。请先到“余额”添加账户，并将类型设为“积分”。","ポイント口座がありません。「残高」で口座を追加し、種類を「ポイント」に設定してください。","No points account yet. Add one under Balances and set its type to Points.")+'</p>';
    const recentRows=recent.length?recent.map(row=>'<div class="point-history-row"><div><strong>'+e(row.description||m("自动返积分","自動ポイント還元","Automatic points reward"))+'</strong><small>'+e(row.occurred_on||"")+" · "+e(row.account_name||"")+'</small></div><strong>+'+money(row.amount_minor,row.currency||"JPY",row.currency_minor_digits??0,"points")+'</strong></div>').join(""):'<p class="fineprint">'+m("设置规则后，新消费产生的积分会显示在这里。","ルール設定後、新しい利用で獲得したポイントがここに表示されます。","Rewards from future purchases will appear here after you set a rule.")+'</p>';
    content+='<section class="panel point-overview"><div class="section-heading"><div><h3>'+m("积分余额","ポイント残高","Points balances")+'</h3><p class="fineprint">'+m("每1点按1日元等值记录，积分单独展示，不计入日常账户资产。","1ポイントを1円相当で記録します。日常の口座資産とは分けて表示します。","One point is recorded as ¥1 equivalent and shown separately from cash assets.")+'</p></div></div><div class="point-balance-grid">'+balanceCards+'</div></section>'+
      '<section class="panel point-rules-panel"><div class="section-heading"><div><h3>'+m("消费自动返积分","利用時の自動ポイント還元","Automatic rewards on purchases")+'</h3><p class="fineprint">'+m("按付款账户设置返还比例。确认入账后的消费会自动记一笔积分收入；改删原消费时会同步调整。按日元等值金额计算，舍去不足1点的部分。规则只应用于保存后新增或修改的消费，不追溯旧账。","支払口座ごとに還元率を設定します。確定済みの利用にポイント収入を自動記録し、元の取引を編集・削除すると連動して更新します。円換算額から計算し、1ポイント未満は切り捨てます。保存後の新規・編集取引に適用し、過去分には遡及しません。","Set a rate for each payment account. Confirmed purchases create a points income entry; editing or deleting the purchase updates the linked reward. Rewards use the JPY-equivalent spend and round down to whole points. Rules apply to purchases entered or edited after saving; past entries are not backfilled.")+'</p></div></div><div class="point-rules-toolbar">'+b("point-rule-add",icon("plus")+" "+m("添加规则","ルールを追加","Add rule"))+b("point-rewards-save",m("保存","保存","Save"),"","button primary")+'</div><div class="point-rules-list">'+(cards||'<p class="fineprint">'+m("还没有返还规则，添加一条即可开始自动累计。","還元ルールはまだありません。追加すると自動で貯まります。","No reward rules yet. Add one to start tracking rewards automatically.")+'</p>')+'</div></section>'+
      '<section class="panel point-history-panel"><h3>'+m("最近自动返还","最近の自動還元","Recent automatic rewards")+'</h3>'+recentRows+'</section>';
  }
  if(id==="finance") {
    const finance=workspace.reports||workspace;
    const financeTabs=[["balance",m("余额和欠款","残高と借入","Balances and debt")],["profit",m("本期利润表","本期損益","Period profit")],["budget",m("预算管理","予算管理","Budget")]];
    content+='<div class="mode-pills finance-tabs" aria-label="'+m("财务报表和预算","財務レポートと予算","Financial reports and budget")+'">'+financeTabs.map(([key,label])=>b("finance-tab",label,key,"pill "+(financialTab===key?"selected":""))).join("")+'</div>';
    if(financialTab==="balance") {
      const balance=finance.balanceSheet,rows=balance.rows||[],currencyOrder=code=>({JPY:0,CNY:1,USD:2}[code]??3);
      const assetSections=[m("货币资产","貨幣資産","Monetary assets"),m("资产（信用卡贷余）","資産（カード利用可能枠）","Assets (available credit)"),m("固定资产","固定資産","Fixed assets")];
      const liabilitySections=[m("信用卡负债估算","クレジットカード負債の推定","Estimated credit card liabilities"),m("已登记的欠款","登録済みの借入","Recorded debt"),m("负债（待录入额度）","負債（利用枠未入力）","Liabilities (credit limit not entered)"),m("信用卡","クレジットカード","Credit card")];
      const uncertainSections=[m("负余额（待核对）","マイナス残高（要確認）","Negative balance (review required)"),m("积分负数（待核对）","ポイント残高がマイナス（要確認）","Negative points balance (review required)"),m("非货币负数（待核对）","非貨幣残高がマイナス（要確認）","Negative non-monetary balance (review required)")];
      const assetRows=rows.filter(row=>assetSections.includes(row.section)),liabilityRows=rows.filter(row=>liabilitySections.includes(row.section));
      const pointsRows=rows.filter(row=>row.section===m("积分（不计入资产）","ポイント（資産に含まない）","Points (excluded from assets)"));
      const otherAssetRows=rows.filter(row=>row.section===m("非货币资产","非貨幣資産","Non-monetary assets"));
      const uncertainRows=rows.filter(row=>uncertainSections.includes(row.section));
      const futureRows=rows.filter(row=>row.section===m("未生效账户","未適用の口座","Inactive account"));
      const classified=new Set([...assetRows,...liabilityRows,...pointsRows,...otherAssetRows,...uncertainRows,...futureRows]);
      const otherRows=rows.filter(row=>!classified.has(row)),tableRows=[];
      const addRow=(cells,kind="")=>tableRows.push({cells,kind});
      const addEntry=(row,kind="")=>{
        const included=Boolean(row.include_in_balance_sheet),assetId=row.asset_id;
        const check=assetId?'<button type="button" class="finance-check" data-action="asset-toggle" data-id="'+e(String(assetId))+'" aria-pressed="'+(included?"true":"false")+'" aria-label="'+e((included?m("不计入余额总额","残高合計に含めない","Leave out of the balance total"):m("计入余额总额","残高合計に含める","Include in the balance total"))+" · "+row.name)+'">'+(included?"☑":"☐")+'</button>':"";
        const status=row.status?'<small>'+e(row.status)+'</small>':"";
        addRow([check,'<span class="finance-item-name">'+e(row.name)+'</span>'+status,'<span class="finance-amount">'+e(row.amount_text||money(row.amount_minor,row.currency))+'</span>'],kind);
      };
      const grouped=values=>Object.entries(values||{}).sort(([a],[b])=>currencyOrder(a)-currencyOrder(b)||a.localeCompare(b)).map(([code,value])=>money(value,code)).join(" · ")||money("0","JPY");
      const codes=Object.keys(balance.assets||{}).sort((a,b)=>currencyOrder(a)-currencyOrder(b)||a.localeCompare(b));
      for(const code of codes){
        const digits=["CNY","USD"].includes(code)?2:0,assets=BigInt(balance.assets?.[code]||0),liabilities=BigInt(balance.known_liabilities?.[code]||0)+BigInt(balance.estimated_liabilities?.[code]||0);
        addRow(["",e(code+"资产负债"),""],"finance-section");
        addRow(["",e(code+"资产"),""],"finance-group");
        for(const row of assetRows.filter(item=>item.currency===code))addEntry(row,row.section===m("固定资产","固定資産","Fixed assets")&&!row.include_in_balance_sheet?"finance-excluded":"");
        addRow(["",e("　"+code+"资产合计"),'<span class="finance-amount">'+money(String(assets),code,digits)+'</span>'],"finance-total");
        addRow(["",e(code+"负债"),""],"finance-group");
        for(const row of liabilityRows.filter(item=>item.currency===code))addEntry(row);
        const liabilityLabel=balance.unknown_liability_count?"　"+code+m("负债小计","負債小計"," liabilities subtotal"):"　"+code+m("负债合计","負債合計"," liabilities total");
        addRow(["",e(liabilityLabel),'<span class="finance-amount">'+money(String(liabilities),code,digits)+'</span>'],"finance-total");
        addRow(["",e("　"+code+m("扣除欠款后还剩","借入を差し引いた残り","remaining after debt")),'<span class="finance-amount">'+money(balance.net_assets?.[code]||"0",code,digits)+'</span>'],"finance-total");
        if(code==="JPY"){
          addRow(["",e(m("积分（单独展示，不计入资产）","ポイント（別表示・資産に含めない）","Points (shown separately, excluded from assets)")),""],"finance-section");
          for(const row of pointsRows)addEntry(row);
          for(const row of uncertainRows.filter(item=>item.section===m("积分负数（待核对）","ポイント残高がマイナス（要確認）","Negative points balance (review required)")))addEntry(row,"finance-warning");
        }
      }
      if(otherAssetRows.length){addRow(["",e(m("其他非货币资产","その他の非貨幣資産","Other non-monetary assets")),""],"finance-group");for(const row of otherAssetRows)addEntry(row);}
      const otherUncertain=uncertainRows.filter(row=>row.section!==m("积分负数（待核对）","ポイント残高がマイナス（要確認）","Negative points balance (review required)"));
      if(otherUncertain.length){addRow(["",e(m("待核对负余额（未计入资产合计）","要確認のマイナス残高（資産合計に含めない）","Negative balances to review (excluded from assets)")),""],"finance-group");for(const row of otherUncertain)addEntry(row,"finance-warning");}
      if(balance.unknown_liability_count)addRow(["",e(m("未估算信用卡负债","未推定のカード負債","Unestimated credit card liabilities")),'<span class="finance-amount">'+e(String(balance.unknown_liability_count)+m("张（未计入负债小计）","件（負債小計に含めない）"," card(s), excluded from subtotal"))+'</span>'],"finance-warning");
      if(futureRows.length||otherRows.length){addRow(["",e(m("其他 / 尚未生效项目","その他 / 未適用の項目","Other / inactive items")),""],"finance-group");for(const row of [...futureRows,...otherRows])addEntry(row,"finance-warning");}
      const baseBalance=balance.base_equivalent||{},baseCode=baseBalance.currency||"JPY";
      const summary=m("银行账户余额","銀行口座の残高","Bank account balances")+"："+grouped(balance.bank_deposits)+"　·　"+m("账户余额合计","口座残高の合計","Total account balances")+"："+grouped(balance.assets)+"　·　"+m("信用卡欠款估算","カード負債の推定","Estimated card debt")+"："+grouped(balance.estimated_liabilities)+"　·　"+m("已登记的欠款","登録済みの借入","Recorded debt")+"："+grouped(balance.known_liabilities)+"　·　"+m("主要记账货币余额","メイン通貨の残高","Main-currency balance")+"："+money(baseBalance.net_assets_minor||"0",baseCode)+(Number(baseBalance.missing_conversion_count||0)?"（"+m("部分记录没有汇率","為替レートがない記録あり","some entries have no rate")+"）":"");
      content+='<div class="finance-report-controls"><label class="finance-date"><span>'+m("截至日期","基準日","As of")+'</span><input id="reportDate" type="date" value="'+e(reportDate||balance.as_of||workspace.date)+'"></label><div class="finance-report-summary">'+e(m("账户余额和欠款汇总","口座残高と借入のまとめ","Account balances and debt summary"))+" · "+e(balance.as_of||workspace.date)+"<small>"+e(summary)+'</small></div></div>'+financeTable([m("计入余额总额","残高合計に含める","In balance total"),m("项目","項目","Item"),m("金额","金額","Amount")],tableRows,m("账户和欠款明细","口座と借入の明細","Account and debt details"),"balance-table")+'<p class="fineprint finance-footnote">'+m("信用卡负债为额度差额估算；积分单独列示；负数和待核对项目会单独标出。","カード負債は利用枠からの推定です。ポイントは別表示し、要確認項目は区分して表示します。","Credit card liabilities are estimated from credit limits. Points and items needing review are shown separately.")+'</p>';
    }
    if(financialTab==="profit") {
      const profit=finance.profit,jpy=profit.jpy_equivalent,base=profit.base_equivalent||jpy,baseCode=base.currency||"JPY",tableRows=[],moneyFor=(value,code,digits)=>money(String(value),code,digits);
      const addProfit=(currency,item,amount,note,kind="")=>tableRows.push({kind,cells:[e(currency),e(item),'<span class="finance-amount">'+e(amount)+'</span>',e(note)]});
      const currencyRows=Object.entries(profit.currencies||{}).sort(([a],[b])=>({JPY:0,CNY:1,USD:2}[a]??3)-({JPY:0,CNY:1,USD:2}[b]??3)||a.localeCompare(b));
      for(const [code,values] of currencyRows){
        const digits=Number(values.minor_digits||0);
        addProfit(code,m("收入合计","収入合計","Total income"),moneyFor(values.income_minor,code,digits),m("已记录收入","記録済み収入","Recorded income"),"finance-income");
        addProfit(code,m("消费合计","支出合計","Total spending"),moneyFor(-BigInt(values.expense_minor||0),code,digits),m("包含已入账与备查支出","記帳済み・メモ支出を含む","Posted and memo expenses"),"finance-expense");
        addProfit(code,m("其中：已入账消费","内訳：記帳済み支出","Of which: posted spending"),moneyFor(-BigInt(values.posted_expense_minor||0),code,digits),m("会影响账户余额","口座残高に反映","Affects account balances"),"finance-expense");
        if(BigInt(values.memo_expense_minor||0))addProfit(code,m("其中：仅备查消费","内訳：メモ支出","Of which: memo spending"),moneyFor(-BigInt(values.memo_expense_minor),code,digits),m("不影响账户余额","口座残高に反映しない","Does not affect balances"),"finance-expense");
        if(BigInt(values.needs_review_expense_minor||0))addProfit(code,m("待核对消费","要確認の支出","Spending to review"),moneyFor(-BigInt(values.needs_review_expense_minor),code,digits),m("包含在消费合计中","支出合計に含む","Included in spending total"),"finance-warning");
        for(const [name,value] of Object.entries(values.categories||{}).sort(([,a],[,b])=>BigInt(b)>BigInt(a)?1:BigInt(b)<BigInt(a)?-1:0))addProfit(code,m("支出分类：","支出カテゴリ：","Spending category: ")+name,moneyFor(-BigInt(value),code,digits),m("按账本分类汇总","台帳カテゴリ別","Grouped by ledger category"),"finance-expense");
        addProfit(code,m("本期合计","当期合計","Period net"),moneyFor(values.net_minor,code,digits),m("收入减消费","収入 − 支出","Income minus spending"),BigInt(values.net_minor||0)>=0n?"finance-income finance-total":"finance-expense finance-total");
      }
      addProfit(m("换算后合计","換算後の合計","Converted total"),m("收入合计","収入合計","Total income"),moneyFor(base.income_minor,baseCode,Number(base.minor_digits||0)),m("按记账当天的汇率换算","記帳日の為替レートで換算","Converted using the exchange rate on the entry date"),"finance-income");
      addProfit(m("换算后合计","換算後の合計","Converted total"),m("消费合计","支出合計","Total spending"),moneyFor(-BigInt(base.expense_minor||0),baseCode,Number(base.minor_digits||0)),m("包含已入账与备查支出","記帳済み・メモ支出を含む","Posted and memo expenses"),"finance-expense");
      for(const [name,value] of Object.entries(base.categories||{}).sort(([,a],[,b])=>BigInt(b)>BigInt(a)?1:BigInt(b)<BigInt(a)?-1:0))addProfit(m("换算后合计","換算後の合計","Converted total"),m("支出分类：","支出カテゴリ：","Spending category: ")+name,moneyFor(-BigInt(value),baseCode,Number(base.minor_digits||0)),m("按每笔记账当天的汇率换算","記帳日の為替レートで換算","Converted using the exchange rate on each entry date"),"finance-expense");
      addProfit(m("换算后合计","換算後の合計","Converted total"),m("本期合计","当期合計","Period net"),moneyFor(base.net_minor,baseCode,Number(base.minor_digits||0)),m("收入减消费","収入 − 支出","Income minus spending"),BigInt(base.net_minor||0)>=0n?"finance-income finance-total":"finance-expense finance-total");
      if(Number(base.missing_conversion_count||0))addProfit(m("待补汇率","為替未登録","FX rate missing"),m("未折算流水","未換算の取引","Unconverted entries"),String(base.missing_conversion_count)+m(" 笔"," 件"," entries"),m("没有汇率，未计入合计","為替レートがなく、合計に含まれていません","Not included because the exchange rate is missing"),"finance-warning");
      const summary=m("统计截至","集計基準日","Through")+" "+profit.through+"　·　"+m("当前银行存款","現在の銀行預金","Current bank deposits")+"："+Object.entries(finance.balanceSheet.bank_deposits||{}).map(([code,value])=>money(value,code)).join(" · ");
      content+='<div class="finance-report-controls"><label class="finance-date"><span>'+m("截至日期","基準日","As of")+'</span><input id="reportDate" type="date" value="'+e(reportDate||profit.through||workspace.date)+'"></label><div class="finance-period-summary"><strong>'+e(profit.start)+" — "+e(profit.through)+'</strong><span>'+e(summary)+'</span></div></div>'+financeTable([m("币种 / 单位","通貨 / 単位","Currency / unit"),m("项目","項目","Item"),m("金额","金額","Amount"),m("说明","説明","Notes")],tableRows,m("本期利润明细","当期損益の明細","Period profit details"),"profit-table")+'<p class="fineprint finance-footnote">'+m("其他货币的记录会按记账当天的汇率换算，原来的金额也会保留。余额按报表日期的汇率换算；转账和还信用卡不算消费。","他の通貨の記録は記帳日の為替レートで換算し、元の金額も表示します。残高はレポート日のレートで換算します。口座間の移動とカード返済は支出に含みません。","Other currencies are converted using the exchange rate on the entry date, and original amounts remain visible. Balances use the report date's rate. Transfers and card repayments are not counted as spending.")+'</p>';
    }
    if(financialTab==="budget") {
      const settings=workspace.settings||finance.settings||{},total=settings.monthly_jpy_budget_minor||"0",analytics=budgetAnalytics(finance.profit.start,finance.profit.through),remaining=BigInt(total)-analytics.totalSpent;
      let plan={};try{plan=JSON.parse(settings["savings_plan:"+finance.profit.start]||settings["savings_plan:monthly_template"]||"{}").items||{};}catch{}
      const budgetRows=Object.entries(plan).sort(([a],[b])=>a.localeCompare(b)).map(([name,value])=>({cells:[e(name),'<span class="finance-amount">'+e(money(analytics.actualByCategory[name]||"0"))+'</span>','<span class="finance-amount">'+e(money(value))+'</span>','<span class="finance-amount">'+e(money((BigInt(value||0)-BigInt(analytics.actualByCategory[name]||0)).toString()))+'</span>']}));
      const period=finance.profit.start+" — "+finance.profit.through;
      const allocation=Object.values(plan).reduce((sum,value)=>sum+BigInt(value||0),0n);
      financePieColorNames=[...(cachedBootstrap?.categories||[]).map(row=>String(row.name||row.display_name||"")),...Object.keys(analytics.actualByCategory),...Object.keys(plan),m("其他","その他","Other")].filter(Boolean);
      financePieCategoryOrder=Object.entries(plan).sort(([,left],[,right])=>BigInt(left||0)>BigInt(right||0)?-1:BigInt(left||0)<BigInt(right||0)?1:0).map(([name])=>name);
      const spendingSummary='<div class="finance-spending-summary"><strong>'+e(period)+'</strong><span>'+m("本期已入账支出","今期の記帳済み支出","Posted spending this period")+' <b>'+money(analytics.totalSpent.toString())+'</b></span>'+(analytics.missingFxCount?'<small>'+m("缺少汇率的人民币流水：","為替未登録の人民元取引：","CNY entries missing exchange rates: ")+analytics.missingFxCount+m("笔，未计入图表。","件。グラフには含まれません。"," entries; excluded from charts.")+'</small>':"")+'</div>';
      const trendPanel='<section class="finance-chart-panel"><div class="finance-chart-heading"><h3>'+m("支出趋势","支出の推移","Spending trend")+'</h3><div class="finance-chart-modes">'+b("budget-trend-mode",m("日度","日別","Daily"),"daily","pill "+(financeTrendMode==="daily"?"selected":""))+b("budget-trend-mode",m("月度","月別","Monthly"),"monthly","pill "+(financeTrendMode==="monthly"?"selected":""))+'</div></div><p class="finance-chart-hint">'+m("日度显示本期；月度显示近12个月。将鼠标移到折线上的圆点查看日期和金额。","日別は今期、月別は直近12か月です。折れ線の点にカーソルを合わせると日付と金額を表示します。","Daily shows this period; monthly shows the last 12 months. Hover over a point on the line for its date and amount.")+'</p>'+trendChart(analytics,financeTrendMode)+'</section>';
      const spendingPie='<section class="finance-chart-panel"><h3>'+m("本期消费类别","今期の支出カテゴリ","Spending categories this period")+'</h3>'+financePieChart(Object.entries(analytics.actualByCategory),m("本期暂无已入账分类支出。","今期の記帳済みカテゴリ支出はありません。","No posted category spending this period."))+'</section>';
      const budgetHead='<div class="finance-budget-head"><div><strong>'+e(period)+'</strong><p>'+m("总预算","予算合計","Total budget")+'：<b>'+money(total)+'</b>　·　'+m("分类分配","カテゴリ配分","Category allocation")+'：<b>'+money(allocation.toString())+'</b><br>'+m("已使用","使用済み","Spent")+'：<b>'+money(analytics.totalSpent.toString())+'</b>　·　'+m("剩余","残額","Remaining")+'：<b>'+money(remaining.toString())+'</b></p></div>'+b("budget-edit",m("编辑预算","予算編集","Edit budget"),"","button secondary finance-budget-edit")+'</div>';
      const budgetTable=(budgetRows.length?"":'<p class="fineprint finance-footnote">'+m("尚未设置分类预算。点击“编辑预算”设置。","カテゴリ予算は未設定です。「予算編集」から設定できます。","No category budgets yet. Select Edit budget to set them.")+'</p>')+financeTable([m("类别","カテゴリ","Category"),m("已使用","使用額","Spent"),m("预算","予算","Budget"),m("剩余","残額","Remaining")],budgetRows,m("本期分类预算","今期カテゴリ予算","Period category budget"),"budget-table");
      const budgetPie='<section class="finance-chart-panel"><h3>'+m("预算分配","予算配分","Budget allocation")+'</h3>'+financePieChart(Object.entries(plan),m("添加类别预算后显示预算分配。","カテゴリ予算を追加すると配分を表示します。","Add category budgets to see the allocation."))+'</section>';
      content+='<div class="finance-budget-layout"><div class="finance-budget-side finance-spending-side">'+spendingSummary+trendPanel+'</div><div class="finance-budget-side finance-budget-main">'+budgetHead+budgetTable+'</div><div class="finance-pie-row">'+spendingPie+budgetPie+'</div></div>';
    }
  }
  if(id==="food") {
    content+='<div class="button-row">'+b("food-purchase",m("添加采购","購入を追加","Add purchase"))+b("food-eaten",m("记录饮食","食事を記録","Log meal"))+b("food-preference",m("采购计入偏好","購入の計上設定","Purchase preference"))+'</div><section class="panel"><h3>'+m("饮食回顾","食生活の振り返り","Food review")+'</h3><p class="prewrap">'+e(w.foodReview)+'</p></section><h3>'+m("采购食品","購入した食品","Food purchases")+'</h3>'+
      w.food.map(row=>'<div class="panel food-row"><div><strong>'+e(row.item_name)+'</strong><small>'+e(row.purchase_date)+" · "+e(row.quantity_text||"")+" · "+e(w.foodGroups[row.food_group]||row.food_group)+'</small></div>'+b("food-group",m("分类","分類","Group"),row.id,"text-button accent")+b("food-delete",m("删除","削除","Delete"),"purchase:"+row.id,"text-button danger-text")+'</div>').join("")+
      '<h3>'+m("食用记录","食事記録","Meals")+'</h3>'+w.eaten.map(row=>'<div class="panel food-row"><div><strong>'+e(row.item_name)+'</strong><small>'+e(row.consumed_on)+" · "+e(row.meal)+" · "+e(row.quantity_text)+'</small></div>'+b("food-delete",m("删除","削除","Delete"),"eaten:"+row.id,"text-button danger-text")+'</div>').join("");
  }
  if(id==="categories")content+=categoriesPanelContent();
  if(id==="install"){
    const cloud=typeof runtimeConfig!=="undefined"&&runtimeConfig?.deploymentMode==="cloud";
    const installHelp=cloud
      ?m("添加后可从主屏幕快速打开。手动账目可离线暂存，重新联网后同步；Agent 和云备份需要网络。","ホーム画面からすぐ開けます。手動記録はオフラインで一時保存でき、再接続後に同期します。Agent とクラウドバックアップには通信が必要です。","Open it quickly from your Home Screen. Manual entries can queue offline and sync when reconnected; Agents and cloud backups need a connection.")
      :m("同 Wi-Fi 测试时，电脑需保持开机并运行服务。离线可暂存手动账目；Agent 和云备份需要连接服务。","同じWi-FiでのテストはPCとサービスの起動が必要です。オフラインでは手動取引を保存できます。","For Wi-Fi testing, keep the computer and service running. Manual entries can be queued offline; Agents and cloud backups need a connection.");
    content+='<section class="panel installation"><div class="install-symbol">'+icon("plus")+'</div><h3>'+m("让记账住进你的主屏幕","ホーム画面に家計簿を","A place on your Home Screen")+'</h3><ol><li>'+m("在 iPhone Safari 打开当前 HTTPS 地址。","iPhoneのSafariでこのHTTPSアドレスを開きます。","Open this HTTPS address in Safari on iPhone.")+'</li><li>'+m("点“分享”，选择“添加到主屏幕”。","共有から「ホーム画面に追加」を選択。","Tap Share, then Add to Home Screen.")+'</li><li>'+m("开启“作为网页 App 打开”（如有），再点“添加”。","表示される場合はWebアプリとして開くを有効にし「追加」。","Enable Open as Web App if shown, then tap Add.")+'</li></ol><p>'+installHelp+'</p><p class="address-display">'+e(location.origin)+'</p>'+(cloud?"":'<a class="button secondary" href="/test-ca.cer">'+m("下载本机测试证书","テスト証明書を取得","Download test certificate")+'</a>')+'</section>';
  }
  root.innerHTML=content;
  if(id==="finance"&&financialTab==="budget"){
    const chart=root.querySelector(".trend-chart"),wrap=root.querySelector(".finance-chart-wrap"),tooltip=root.querySelector(".finance-chart-tooltip");
    chart?.addEventListener("pointermove",event=>{
      const point=event.target instanceof Element?event.target.closest(".trend-point"):null;
      if(!point){tooltip?.classList.add("hidden");return;}
      if(!tooltip||!wrap)return;
      tooltip.textContent=point.dataset.tip||"";
      tooltip.classList.remove("hidden");
      const bounds=wrap.getBoundingClientRect(),left=event.clientX-bounds.left+12,top=event.clientY-bounds.top-tooltip.offsetHeight-10;
      tooltip.style.left=Math.max(5,Math.min(left,bounds.width-tooltip.offsetWidth-5))+"px";
      tooltip.style.top=Math.max(4,Math.min(top,bounds.height-tooltip.offsetHeight-4))+"px";
    });
    chart?.addEventListener("pointerleave",()=>tooltip?.classList.add("hidden"));
    root.querySelectorAll(".finance-pie").forEach(pie=>{
      const pieWrap=pie.closest(".finance-pie-wrap"),pieTooltip=pieWrap?.querySelector(".finance-chart-tooltip");
      pie.addEventListener("pointermove",event=>{
        const slice=event.target instanceof Element?event.target.closest("[data-tip]"):null;
        if(!slice){if(!pie.dataset.tapTip)pieTooltip?.classList.add("hidden");return;}
        if(!pieTooltip||!pieWrap)return;
        pieTooltip.textContent=slice.dataset.tip||"";
        pieTooltip.classList.remove("hidden");
        const bounds=pieWrap.getBoundingClientRect(),left=event.clientX-bounds.left+12,top=event.clientY-bounds.top-pieTooltip.offsetHeight-10;
        pieTooltip.style.left=Math.max(4,Math.min(left,bounds.width-pieTooltip.offsetWidth-4))+"px";
        pieTooltip.style.top=Math.max(4,Math.min(top,bounds.height-pieTooltip.offsetHeight-4))+"px";
      });
      pie.addEventListener("pointerleave",event=>{if(event.pointerType!=="touch"&&!pie.dataset.tapTip)pieTooltip?.classList.add("hidden");});
      pie.addEventListener("click",event=>{
        const slice=event.target instanceof Element?event.target.closest("[data-tip]"):null;
        if(!slice){if(!pie.dataset.tapTip)pieTooltip?.classList.add("hidden");return;}
        if(!pieTooltip||!pieWrap)return;
        if(pie.dataset.tapTip===slice.dataset.tip){delete pie.dataset.tapTip;pieTooltip.classList.add("hidden");return;}
        pie.dataset.tapTip=slice.dataset.tip||"";
        pieTooltip.textContent=pie.dataset.tapTip;
        pieTooltip.classList.remove("hidden");
        const bounds=pieWrap.getBoundingClientRect(),left=event.clientX-bounds.left+10,top=event.clientY-bounds.top-pieTooltip.offsetHeight-9;
        pieTooltip.style.left=Math.max(4,Math.min(left,bounds.width-pieTooltip.offsetWidth-4))+"px";
        pieTooltip.style.top=Math.max(4,Math.min(top,bounds.height-pieTooltip.offsetHeight-4))+"px";
      });
    });
  }
}
function budgetAnalytics(start,through) {
  const dateKey=date=>date.toISOString().slice(0,10),monthKey=date=>dateKey(date).slice(0,7);
  const startDate=new Date((start||workspace.date)+"T12:00:00"),throughDate=new Date((through||workspace.date)+"T12:00:00");
  const dailyMap=new Map(),cursor=new Date(startDate);
  for(let count=0;cursor<=throughDate&&count<40;count++){const key=dateKey(cursor);dailyMap.set(key,0n);cursor.setDate(cursor.getDate()+1);}
  const firstMonth=new Date(throughDate.getFullYear(),throughDate.getMonth()-11,1,12),monthlyMap=new Map();
  for(let index=0;index<12;index++){const date=new Date(firstMonth.getFullYear(),firstMonth.getMonth()+index,1,12),key=monthKey(date);monthlyMap.set(key,{date:key,label:key,value:0n});}
  const actualByCategory={};let missingFxCount=0;
  for(const row of workspace.transactions||[]){
    if(row.kind!=="expense"||row.balance_effect!=="posted")continue;
    const day=String(row.occurred_on||""),month=day.slice(0,7),inDaily=dailyMap.has(day),inMonthly=monthlyMap.has(month);
    if(!inDaily&&!inMonthly)continue;
    const raw=row.currency==="JPY"?row.amount_minor:row.jpy_equiv_minor;
    if(raw===null||raw===undefined){missingFxCount++;continue;}
    const amount=BigInt(raw);if(amount<=0n)continue;
    if(inMonthly)monthlyMap.get(month).value+=amount;
    if(inDaily){dailyMap.set(day,dailyMap.get(day)+amount);const category=row.category_name||"未分类";actualByCategory[category]=(BigInt(actualByCategory[category]||0)+amount).toString();}
  }
  const daily=[...dailyMap].map(([date,value])=>({date,label:date.slice(5).replace("-","/"),value}));
  const monthly=[...monthlyMap.values()];
  const totalSpent=Object.values(actualByCategory).reduce((sum,value)=>sum+BigInt(value),0n);
  return {daily,monthly,actualByCategory,totalSpent,missingFxCount};
}
function financePieChart(entries,emptyMessage) {
  const preferred=new Map(financePieCategoryOrder.map((name,index)=>[name,index]));
  const ranked=(entries||[]).map(([name,value])=>[String(name),BigInt(value||0)]).filter(([,value])=>value>0n).sort((a,b)=>{
    const left=preferred.get(a[0]),right=preferred.get(b[0]);
    if(left!==undefined||right!==undefined){if(left===undefined)return 1;if(right===undefined)return -1;return left-right;}
    return a[1]>b[1]?-1:a[1]<b[1]?1:a[0].localeCompare(b[0]);
  });
  if(!ranked.length)return '<p class="finance-pie-empty">'+e(emptyMessage)+'</p>';
  const visible=ranked.length>8?[...ranked.slice(0,7),[m("其他","その他","Other"),ranked.slice(7).reduce((sum,row)=>sum+row[1],0n)]]:ranked;
  const total=visible.reduce((sum,row)=>sum+row[1],0n);
  const categoryOrder=[...new Set([...financePieColorNames,...visible.map(([name])=>name)])].sort((a,b)=>a.localeCompare(b));
  const categoryColor=name=>"hsl("+((categoryOrder.indexOf(name)*137.508+216)%360).toFixed(1)+" 70% 48%)";
  const cx=82,cy=82,radius=78;let angle=-90;
  const slices=visible.map(([name,value])=>{
    const fraction=Number(value*1_000_000n/total)/1_000_000,end=angle+fraction*360,color=categoryColor(name);
    const percent=Number(value*10_000n/total)/100,tip=name+" · "+percent.toFixed(percent%1?1:0)+"% · "+(hiddenAmounts?m("金额已隐藏","金額を非表示","Amount hidden"):money(value.toString()));
    let shape;
    if(visible.length===1)shape='<circle data-tip="'+e(tip)+'" cx="'+cx+'" cy="'+cy+'" r="'+radius+'" fill="'+color+'"><title>'+e(tip)+'</title></circle>';
    else{const radians=degree=>degree*Math.PI/180,x1=cx+radius*Math.cos(radians(angle)),y1=cy+radius*Math.sin(radians(angle)),x2=cx+radius*Math.cos(radians(end)),y2=cy+radius*Math.sin(radians(end)),large=end-angle>180?1:0;shape='<path data-tip="'+e(tip)+'" d="M '+cx+' '+cy+' L '+x1.toFixed(2)+' '+y1.toFixed(2)+' A '+radius+' '+radius+' 0 '+large+' 1 '+x2.toFixed(2)+' '+y2.toFixed(2)+' Z" fill="'+color+'"><title>'+e(tip)+'</title></path>';}
    angle=end;
    return {name,value,color,percent,shape};
  });
  return '<div class="finance-pie-content"><div class="finance-pie-wrap"><svg class="finance-pie" viewBox="0 0 164 164" role="img" aria-label="'+e(m("按类别分布","カテゴリ別内訳","Category breakdown"))+'">'+slices.map(item=>item.shape).join("")+'</svg><div class="finance-chart-tooltip hidden" role="tooltip"></div></div><ul class="finance-pie-legend">'+slices.map(item=>'<li><span class="finance-pie-swatch" style="--slice-color:'+item.color+'"></span><span class="finance-pie-name" title="'+e(item.name)+'">'+e(item.name)+'</span><strong>'+item.percent.toFixed(item.percent%1?1:0)+'% · '+money(item.value.toString())+'</strong></li>').join("")+'</ul></div>';
}
function trendChart(analytics,mode="daily") {
  const points=mode==="monthly"?analytics.monthly:analytics.daily,max=points.reduce((largest,item)=>item.value>largest?item.value:largest,1n);
  const width=760,height=360,left=22,right=748,top=12,bottom=310,plotHeight=bottom-top,slot=points.length?(right-left)/points.length:0;
  const pointX=index=>left+slot*index+slot/2;
  const pointY=value=>{
    if(hiddenAmounts)return bottom-6;
    if(value<=0n)return bottom;
    const height=Math.max(3,Math.min(plotHeight,Number(value*BigInt(plotHeight)/max)));
    return bottom-height;
  };
  const grid=[0,1,2,3,4].map(index=>{const y=bottom-plotHeight*index/4;return '<line class="trend-gridline" x1="'+left+'" y1="'+y.toFixed(1)+'" x2="'+right+'" y2="'+y.toFixed(1)+'"/>';}).join("");
  const coordinates=points.map((point,index)=>({point,x:pointX(index),y:pointY(point.value)}));
  const line=coordinates.length>1?'<polyline class="trend-line" points="'+coordinates.map(({x,y})=>x.toFixed(1)+','+y.toFixed(1)).join(" ")+'"></polyline>':"";
  const markers=coordinates.map(({point,x,y})=>{
    const tip=point.date+" · "+(hiddenAmounts?m("金额已隐藏","金額を非表示","Amount hidden"):money(point.value.toString()));
    return '<circle class="trend-point" data-tip="'+e(tip)+'" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="5"><title>'+e(tip)+'</title></circle>';
  }).join("");
  const labelCount=Math.min(6,points.length),labels=Array.from({length:labelCount},(_,tick)=>{
    const index=Math.round((points.length-1)*tick/Math.max(1,labelCount-1)),x=pointX(index);
    return '<text class="trend-axis-label" x="'+x.toFixed(1)+'" y="346" text-anchor="middle">'+e(points[index]?.label||"")+'</text>';
  }).join("");
  const chartLabel=mode==="monthly"?m("近12个月支出趋势","過去12か月の支出推移","Spending over the last 12 months"):m("本期日度支出趋势","今期の日別支出推移","Daily spending this period");
  return '<div class="finance-chart-wrap"><svg class="trend-chart" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+e(chartLabel)+'"><g class="trend-plot">'+grid+line+'</g><g class="trend-markers">'+markers+'</g>'+labels+'</svg><div class="finance-chart-tooltip hidden" role="tooltip"></div></div>';
}

function renderCloud(target=$("#cloudControls"),includeHeader=true) {
  const root=target,header=includeHeader?moduleHeader("backup"):"";
  const cfg=workspace?.preferences;if(!cfg){root.innerHTML=header+'<div class="panel workspace-error" role="alert"><p>'+e(workspaceError||m("账本尚未载入。","台帳を読み込み中です。","The ledger has not loaded yet."))+'</p>'+b("workspace-retry",m("重试","再試行","Retry"),"","button primary")+'</div>';return;}
  const selected=backupDraft||cfg;
  const scopes={settings:m("设置与自定义 Skill","設定・カスタムSkill","Settings & skills"),bills:m("账单与小票","取引・レシート","Entries & receipts"),payment_methods:m("付款方式","支払ルール","Payment rules"),recurring_payments:m("定期付款","定期支払","Recurring entries"),bank_accounts:m("银行与资金账户","銀行・資金口座","Cash accounts"),credit_cards:m("信用卡","カード","Credit cards"),assets:m("资产管理","固定資産","Assets")};
  root.innerHTML=header+
    '<section class="panel"><div class="section-heading"><h3>'+m("备份范围","バックアップ範囲","Backup scope")+'</h3>'+b("scope-all",m("全选 / 取消全选","全選択 / 解除","Select / clear all"),"","text-button accent")+'</div><form id="scopeForm"><div class="scope-grid">'+Object.entries(scopes).map(([key,name])=>'<label class="check-row"><input type="checkbox" name="'+key+'" '+(selected.scope[key]?"checked":"")+'><span>'+name+'</span></label>').join("")+'</div><label class="check-row"><input type="checkbox" name="autoSync" '+(selected.autoSync?"checked":"")+'><span>'+m("记账后自动云备份","記帳後に自動バックアップ","Back up after recording")+'</span></label><button class="button primary" type="submit">'+m("应用备份设置","設定を適用","Apply backup settings")+'</button>'+b("scope-cancel",t("cancel"))+ '</form><p class="fineprint">'+m("API 密钥与 GitHub/Gitee 授权不包含在备份中。恢复会替换账本，恢复前自动保留完整副本。","APIキーやGitHub/Gitee認証は含めません。復元前に現在の完全コピーを保存します。","API keys and GitHub/Gitee authorization are excluded. Restoring replaces the ledger after making a full safety copy.")+'</p></section>'+
    ["github","gitee"].map(provider=>{const cloud=cfg.cloud[provider]||{};return '<section class="panel cloud-card"><div class="spread"><h3>'+provider.toUpperCase()+'</h3><span class="status-dot '+(cloud.connected?"connected":"")+'">'+(cloud.connected?m("已连接","接続済み","Connected"):m("未连接","未接続","Not connected"))+'</span></div><p class="muted">'+e(cloud.repository||m("使用你自己账号下的独立私有仓库","自分のアカウントの非公開リポジトリ","A private repository in your own account"))+'</p><div class="button-row">'+b("cloud-connect",m("连接 / 重新授权","接続・再認証","Connect / authorize"),provider)+(cloud.connected?b("cloud-upload",m("上传备份","アップロード","Upload"),provider)+b("cloud-restore",m("从云端恢复","復元","Restore"),provider)+b("cloud-disconnect",m("断开","切断","Disconnect"),provider,"button danger-text"):"")+'</div></section>';}).join("")+
    '<p class="fineprint">'+e(cfg.autoStatus)+'</p><section class="panel"><div class="section-heading"><h3>'+m("本机备份历史","ローカル履歴","Local backup history")+'</h3>'+b("backup",icon("plus"))+'</div>'+
    (workspace.backups||[]).map(row=>'<div class="backup-row"><div><strong>'+e(row.name)+'</strong><small>'+e(new Date(row.date).toLocaleString())+" · "+Math.ceil(Number(row.size)/1024)+" KB"+'</small></div><a class="text-button accent" href="/api/backup?name='+encodeURIComponent(row.name)+'">'+m("下载","保存","Download")+'</a>'+b("local-restore",m("恢复","復元","Restore"),row.name,"text-button")+'</div>').join("")+
    '<label class="button secondary file-button">'+m("导入完整备份包","バックアップを取り込む","Restore a backup file")+'<input id="bundleFile" type="file" accept=".zip,application/zip"></label></section>';
  const scopeForm=root.querySelector("#scopeForm");
  scopeForm.onsubmit=async event=>{event.preventDefault();const form=new FormData(event.currentTarget);const draft=deepCopy(cfg);for(const key in scopes)draft.scope[key]=form.has(key);draft.autoSync=form.has("autoSync");await guarded(async()=>{await runAction("settings",draft);backupDraft=null;renderCloud(root,includeHeader);});};
  scopeForm.onchange=()=>{const form=new FormData(scopeForm);backupDraft={scope:Object.fromEntries(Object.keys(scopes).map(key=>[key,form.has(key)])),autoSync:form.has("autoSync")};};
  root.querySelector("#bundleFile").onchange=event=>guarded(()=>restoreFile(event.target.files?.[0]));
}
const deepCopy=value=>JSON.parse(JSON.stringify(value));
function fieldsAccount(type="all") {
  return (cachedBootstrap?.accounts||[]).filter(row=>type==="all"?row.type!=="points":type==="cash"?row.type!=="credit"&&row.type!=="points":row.type===type).map(row=>[row.name,row.name+" · "+row.currency]);
}
const fieldsCategories=kind=>(cachedBootstrap?.categories||[]).filter(row=>row.kind===kind).map(row=>[row.name,row.display_name]);
const field=(name,label,type="text",value="",options=[])=>({name,label,type,value,options});
async function openForm(title, fields, submit, options={}) {
  $("#editorSave").classList.remove("hidden");
  $("#editorTitle").textContent=title;$("#editorSave").textContent=m("保存","保存","Save");$("#editorCancel").textContent=t("cancel");
  $("#editorFooter").replaceChildren();
  $("#editorBody").className="sheet-body"+(options.bodyClass?" "+options.bodyClass:"");
  $("#editorBody").innerHTML=(options.note?'<p class="fineprint">'+e(options.note)+'</p>':"")+fields.map(item=>{
    const id="edit-"+item.name;
    let control;
    if(item.type==="select")control='<select id="'+id+'" name="'+item.name+'" '+(item.optional?"":"required")+'>'+item.options.map(option=>'<option value="'+e(option[0])+'" '+(String(option[0])===String(item.value)?"selected":"")+'>'+e(option[1])+'</option>').join("")+'</select>';
    else if(item.type==="textarea")control='<textarea id="'+id+'" name="'+item.name+'" rows="'+(item.rows||5)+'" '+(item.optional?"":"required")+'>'+e(item.value)+'</textarea>';
    else if(item.type==="checkbox")control='<input id="'+id+'" name="'+item.name+'" type="checkbox" '+(item.value?"checked":"")+'>';
    else control='<input id="'+id+'" name="'+item.name+'" type="'+(["decimal","integer"].includes(item.type)?"text":item.type)+'" '+(item.type==="decimal"?'inputmode="decimal" autocomplete="off"':item.type==="integer"?'inputmode="numeric"':"")+' value="'+e(item.value)+'" '+(item.optional?"":"required")+' '+(item.readonly?'readonly aria-readonly="true"':"")+' '+(item.type==="password"?'autocomplete="new-password"':"")+'>';
    return '<label class="'+(item.type==="checkbox"?"check-row":"field")+(item.className?" "+e(item.className):"")+'"><span>'+e(item.label)+'</span>'+control+'</label>';
  }).join("");
  const dialog=$("#editorDialog");
  if(options.bodyClass)dialog.addEventListener("close",()=>{$("#editorBody").className="sheet-body";},{once:true});
  if(!dialog.open)dialog.showModal();
  $("#editorForm").onsubmit=async event=>{
    event.preventDefault();if(event.currentTarget.dataset.busy)return;
    const data=Object.fromEntries(new FormData(event.currentTarget));for(const item of fields)if(item.type==="checkbox")data[item.name]=!!$("#edit-"+item.name).checked;
    event.currentTarget.dataset.busy="1";$("#editorSave").disabled=true;
    try{await submit(data);dialog.close();}catch(error){showToast(error.message,true);}
    finally{delete $("#editorForm").dataset.busy;$("#editorSave").disabled=false;}
  };
  options.onReady?.();
}
async function guarded(callback){try{return await callback();}catch(error){showToast(error.message,true);}}
async function confirmOnce(target,impact,labels={}) {
  const dialog=$("#actionConfirmDialog");
  if(!dialog||dialog.open)return false;
  const title=$("#actionConfirmTitle"),copy=$("#actionConfirmImpact"),cancel=$("#actionConfirmCancel"),accept=$("#actionConfirmAccept");
  title.textContent=target;copy.textContent=impact;
  cancel.textContent=labels.cancel||m("取消","キャンセル","Cancel");
  accept.textContent=labels.accept||m("确认","確認","Confirm");
  return new Promise(resolve=>{
    let settled=false;
    const finish=value=>{
      if(settled)return;settled=true;
      cancel.onclick=null;accept.onclick=null;dialog.onclick=null;
      dialog.removeEventListener("cancel",onCancel);dialog.removeEventListener("close",onClose);
      if(dialog.open)dialog.close();
      resolve(value);
    };
    const onCancel=event=>{event.preventDefault();finish(false);};
    const onClose=()=>finish(false);
    cancel.onclick=()=>finish(false);accept.onclick=()=>finish(true);
    dialog.onclick=event=>{if(event.target===dialog)finish(false);};
    dialog.addEventListener("cancel",onCancel);dialog.addEventListener("close",onClose);
    try{if(typeof dialog.showModal==="function")dialog.showModal();else dialog.setAttribute("open","");}
    catch{dialog.setAttribute("open","");}
    cancel.focus();
  });
}
window.confirmBeforeQueuedOperation=async()=>{
  const queue=await outboxAll();
  if(!queue.some(item=>!item.serverAccepted))return true;
  return confirmOnce(
    m("上一项还没传到云端","前の変更はまだクラウドに届いていません","The previous change is not in the cloud yet"),
    m("这项更改会先保存在本机，并按顺序上传。继续后，云端接收前仍可撤销最新一项。","この変更はまず端末に保存され、順番にアップロードされます。続行後も、クラウド受付前なら最後の変更を取り消せます。","This change will be saved on this device and uploaded in order. You can still undo the latest change before the cloud accepts it."),
    {accept:m("继续","続ける","Continue")}
  );
};
function showActionProgress(action,state="running",error="") {
  const isAgent=action==="agent"||action==="agent_prepare";
  const copies={
    settings:[m("正在保存设置到服务器…","設定をサーバーに保存中…","Saving settings to the server…"),m("正在更新 API 与账本设置，请勿重复点击。","APIと台帳の設定を更新しています。重複して操作しないでください。","Updating API and ledger settings. Please do not click again.")],
    onboarding_save:[m("正在统一保存新手教程设置…","初期設定をまとめて保存中…","Saving tutorial changes together…"),m("正在一起保存主要记账货币、每月统计日期、账户、API、Agent 和 Skill 设置，请勿重复提交。","主要通貨、毎月の集計日、口座、API、Agent、Skillをまとめて保存しています。続けて送信しないでください。","Your main currency, monthly start day, accounts, API, Agent, and Skill settings are being saved together. Please do not submit again.")],
    cloud_connect:[m("正在保存云端连接…","クラウド接続を保存中…","Saving cloud connection…"),m("正在安全保存授权信息，请稍候。","認証情報を安全に保存しています。","Saving authorization securely. Please wait.")],
    payment_rules:[m("正在保存支付规则…","支払ルールを保存中…","Saving payment rules…"),m("正在提交更改并刷新账本。请勿重复点击。","変更を送信して台帳を更新しています。重複して操作しないでください。","Submitting changes and refreshing the ledger. Please do not click again.")],
    agent:[m("正在处理你的请求…","リクエストを処理中…","Processing your request…"),m("记账可能需要一点时间；你可以继续查看其他页面，也可以在这里中断。","処理に時間がかかる場合があります。ほかの画面を確認するか、ここで中断できます。","This may take a little while. You can view other pages or stop the task here.")],
    agent_prepare:[m("正在处理你的请求…","リクエストを処理中…","Processing your request…"),m("模型正在识别内容；完成后会先在本机更新，再后台同步云端。","モデルが内容を確認しています。完了後、まず端末に反映し、バックグラウンドで同期します。","The model is preparing your entry. It will appear here first, then sync to the cloud in the background.")],
  };
  let [title,detail]=copies[action]||[m("正在保存到账本服务器…","台帳サーバーに保存中…","Saving to the ledger server…"),m("正在提交更改并刷新账本。请勿重复点击或关闭页面。","変更を送信して台帳を更新しています。重複操作やページを閉じる操作はお控えください。","Submitting changes and refreshing the ledger. Please do not click again or close the page.")];
  if(state==="done"){title=m("操作已完成","処理が完了しました","Operation complete");detail=m("账本已更新。","台帳を更新しました。","Your ledger is up to date.");}
  if(state==="failed"){title=m("操作未完成","処理を完了できませんでした","Operation did not complete");detail=error||m("未能完成此次操作，请根据页面提示处理后重试。","処理を完了できませんでした。画面の案内を確認して再試行してください。","The operation could not be completed. Follow the page message and try again.");}
  showCloudProgress(title,detail,{modal:!isAgent});
  const spinner=$("#cloudProgressDialog .cloud-progress-spinner");
  if(spinner)spinner.dataset.state=state;
  const cancel=$("#cloudProgressCancel");
  if(cancel){
    cancel.classList.toggle("hidden",!isAgent||state!=="running");
    cancel.disabled=isAgent&&!activeJob;
    cancel.textContent=m("取消任务","タスクを中断","Stop task");
    cancel.onclick=isAgent&&state==="running"?async()=>{
      if(!activeJob||cancel.disabled)return;
      const jobId=activeJob;cancel.disabled=true;
      $("#cloudProgressTitle").textContent=m("正在请求中断…","中断を要求中…","Requesting cancellation…");
      $("#cloudProgressDetail").textContent=m("请稍候，服务器正在安全停止任务。","安全に処理を停止しています。","The server is stopping the task safely.");
      try{await api("/api/cancel-job",{method:"POST",body:JSON.stringify({id:jobId})});}
      catch(cancelError){cancel.disabled=false;showToast(cancelError.message,true);}
    }:null;
  }
}
async function runAction(action,data={},progress=null,refresh=true) {
  const owner=currentUser?.id;if(!owner)throw new Error(t("login"));
  if(LOCAL_FIRST_ACTIONS.has(action)){
    if(activeJob)throw new Error(m("记账仍在处理中，请等待当前请求完成后再修改账本。","記帳を処理中です。完了後に台帳を変更してください。","Bookkeeping is still processing. Wait for it to finish before changing the ledger."));
    if(window.confirmBeforeQueuedOperation&&!await window.confirmBeforeQueuedOperation())throw new Error(m("已取消本次操作。","今回の操作を取り消しました。","This operation was cancelled."));
    const operation=newOperation("pending_action",data),preview=buildPendingActionPreview(action,data,operation.opId);
    const item={...operation,type:"pending_action",action,preview,displayLabel:pendingActionLabel(action,data),notBefore:0,error:"",conflict:false};
    await outboxPut(item);
    if(action==="onboarding_save"){
      // The saved outbox row is the durable local commit. Do not hold the
      // tutorial on secondary cache/UI work; those can finish in the background.
      applyPendingActionPreview(item,true);
      renderMobile();
      void Promise.allSettled([persistPendingActionPreview(),renderOutbox()]);
    }else{
      await window.onLocalQueueChanged?.(item);
      await renderOutbox();
    }
    showToast(m("已先保存在本机，正在等待云端接收…","端末に保存しました。クラウドの受付を待っています…","Saved on this device. Waiting for cloud acceptance…"));
    if(navigator.onLine&&serverReachable)void syncQueue();
    return {queued:true,opId:item.opId};
  }
  if(!navigator.onLine||!serverReachable)throw new Error(m("此操作需要连接服务；内容还在当前编辑页。","この操作にはサービスへの接続が必要です。入力は編集画面に残っています。","This action needs a connection. Your input remains in the editor."));
  const queuedBeforeDirectAction=await outboxAll();
  if(queuedBeforeDirectAction.length){
    if(window.confirmBeforeQueuedOperation&&!await window.confirmBeforeQueuedOperation())throw new Error(m("已取消本次操作。","今回の操作を取り消しました。","This operation was cancelled."));
    void syncQueue();
    throw new Error(m("本机还有更改正在等待云端接收。为避免顺序冲突，请等顶部状态恢复后再继续。","端末にクラウド受付待ちの変更があります。順序の競合を防ぐため、上部の状態が戻ってから続けてください。","A local change is still waiting for cloud acceptance. Wait for the status above to clear before continuing."));
  }
  if(activeJob&&action!=="agent"&&action!=="agent_prepare")throw new Error(m("记账仍在处理中，你可以查看其他页面；完成后再修改账本。","記帳を処理中です。ほかの画面は確認できますが、台帳の変更は完了後に行ってください。","Bookkeeping is still processing. You can view other pages; wait until it finishes before changing the ledger."));
  const opId=crypto.randomUUID();
  const isAgentAction=action==="agent"||action==="agent_prepare";
  activeJobAgent=isAgentAction?String(data.agent||chatAgent):"";
  const ownsProgress=!progress;
  if(ownsProgress)showActionProgress(action);
  try{
    let job=await api("/api/action",{method:"POST",body:JSON.stringify({action,data,opId})});
    if(currentUser?.id!==owner)throw new Error(t("logout"));
    localStorage.setItem("hh-active-job:"+owner,job.id);
    if(isAgentAction){localStorage.setItem("hh-active-job-agent:"+owner,String(data.agent||chatAgent));localStorage.setItem("hh-active-job-conversation:"+owner,String(data.conversationId||""));}
    activeJob=job.id;window.cloudJobActive=true;updateConnection();
    if(action==="agent"||action==="agent_prepare"){renderAgent();if(ownsProgress)showActionProgress(action);}
    let pollFailures=0;
    while(job.state==="running"){
      if(progress)progress(job);
      await sleepMobile(pollFailures?Math.min(1000*2**Math.min(pollFailures-1,3),8000):1000);
      if(currentUser?.id!==owner)throw new Error(t("logout"));
      try{job=await api("/api/job?id="+encodeURIComponent(job.id));pollFailures=0;}
      catch(error){
        const retryable=!error.status||error.status===408||error.status===429||error.status>=500;
        if(!retryable){activeJob="";if(!isAgentAction)activeJobAgent="";window.cloudJobActive=false;updateConnection();renderAgent();throw error;}
        pollFailures++;
      }
    }
    if(currentUser?.id!==owner)throw new Error(t("logout"));
    localStorage.removeItem("hh-active-job:"+owner);localStorage.removeItem("hh-active-job-agent:"+owner);localStorage.removeItem("hh-active-job-conversation:"+owner);activeJob="";if(!isAgentAction)activeJobAgent="";window.cloudJobActive=false;updateConnection();
    if(job.state!=="done")throw new Error(localizeServerError(job.result?.error||job.message||m("操作未完成","操作未完了","Action did not complete")));
    if(job.cloudSnapshotSaved===false)showToast(m("操作已完成，但云端快照未能保存。请保持服务运行并稍后重试备份。","操作は完了しましたが、クラウドスナップショットを保存できませんでした。サービスを終了せず、後でバックアップを再試行してください。","The action completed, but its cloud snapshot was not saved. Keep the service running and retry the backup later."),true);
    if(!job.result?.readOnly&&!['agent_prepare','cloud_upload','cloud_restore','cloud_connect','cloud_disconnect','github_auth','startup_pull','agent_reset','backup','restore_local'].includes(action)){
    }
    if(refresh){
      try{await refreshLedgerViews();}
      catch(error){
        showToast(m("操作已完成，但账本页面暂时未能刷新。请稍后点击“刷新”核对，先不要重复提交。","操作は完了しましたが、台帳画面を更新できませんでした。後で「更新」を押して確認し、重複して送信しないでください。","The action completed, but the ledger view could not refresh. Click Refresh later to verify it; do not submit it again."),true);
      }
    }
    if(ownsProgress){showActionProgress(action,"done");await sleepMobile(450);}
    return job.result;
  }catch(error){
    if(activeJob===opId){activeJob="";if(!isAgentAction)activeJobAgent="";window.cloudJobActive=false;updateConnection();}
    if(isAgentAction&&!localStorage.getItem("hh-active-job:"+owner))localStorage.removeItem("hh-active-job-conversation:"+owner);
    else if(!activeJob&&!isAgentAction)activeJobAgent="";
    if(action==="cloud_upload")void loadWorkspace(true).catch(()=>{});
    if(ownsProgress){showActionProgress(action,"failed",error.message);await sleepMobile(action==="agent"||action==="agent_prepare"?1800:700);}
    throw error;
  }finally{if(ownsProgress)hideCloudProgress();}
}
function cloudProgressCopy(action,provider,stage,state="running",error="") {
  const providerName=provider==="gitee"?"Gitee":"GitHub";
  const copies={
    backup:{title:m("正在创建本地备份","ローカルバックアップを作成中","Creating local backup"),detail:m("正在整理账本并保存备份，请稍候。","台帳をまとめて保存しています。しばらくお待ちください。","Preparing and saving your ledger backup. Please wait.")},
    cloud_upload:{title:m("正在上传备份到 "+providerName,providerName+" にバックアップをアップロード中","Uploading backup to "+providerName),detail:m("正在准备账本快照，请稍候。","台帳スナップショットを準備しています。","Preparing a ledger snapshot.")},
    cloud_restore:{title:m("正在从 "+providerName+" 恢复",providerName+" から復元中","Restoring from "+providerName),detail:m("云端数据下载后，会先备份当前账本再恢复。","ダウンロード後、現在の台帳をバックアップしてから復元します。","The current ledger is backed up before the downloaded data is restored.")},
    restore_local:{title:m("正在恢复本地备份","ローカルバックアップを復元中","Restoring local backup"),detail:m("恢复前会先备份当前账本，请稍候。","復元前に現在の台帳をバックアップします。","The current ledger is backed up before restoring.")},
  };
  const stages={
    backup_create:[m("正在创建本地备份…","ローカルバックアップを作成中…","Creating local backup…"),m("正在整理账本数据并保存备份文件。","台帳データをまとめてバックアップを保存しています。","Packaging ledger data and saving the backup file.")],
    cloud_prepare:[m("正在检查备份服务…","バックアップサービスを確認中…","Checking backup service…"),m("正在确认连接和仓库状态。","接続とリポジトリを確認しています。","Checking the connection and repository.")],
    cloud_snapshot:[m("正在生成账本快照…","台帳スナップショットを作成中…","Creating ledger snapshot…"),m("正在整理所选备份内容并生成快照。","選択したバックアップ内容をまとめています。","Preparing the selected backup contents.")],
    cloud_upload:[m("正在上传到 "+providerName+"…",providerName+" にアップロード中…","Uploading to "+providerName+"…"),m("快照已生成，正在传输到你的私有仓库。","スナップショットを非公開リポジトリに転送しています。","The snapshot is being sent to your private repository.")],
    cloud_download:[m("正在从 "+providerName+" 下载…",providerName+" からダウンロード中…","Downloading from "+providerName+"…"),m("正在获取云端账本数据。","クラウド台帳を取得しています。","Fetching the cloud ledger.")],
    cloud_restore:[m("正在检查并恢复账本…","台帳を検証して復元中…","Validating and restoring ledger…"),m("当前账本已先行备份，正在应用云端数据。","現在の台帳をバックアップし、クラウドデータを適用しています。","The current ledger is backed up; cloud data is being applied.")],
    cloud_finish:[m("正在确认备份状态…","バックアップ状態を確認中…","Confirming backup status…"),m("正在保存同步记录并核对仓库状态。","同期状態を保存しています。","Saving sync status and confirming the repository state.")],
    local_restore:[m("正在恢复本地账本…","ローカル台帳を復元中…","Restoring local ledger…"),m("正在应用备份数据并重建账本视图。","バックアップを適用して台帳を更新しています。","Applying backup data and updating the ledger.")],
  };
  const fallback=copies[action]||copies.cloud_upload;
  const copy=stages[stage];
  let title=copy?.[0]||fallback.title,detail=copy?.[1]||fallback.detail;
  if(state==="done"){title=m("备份已完成","バックアップが完了しました","Backup complete");detail=action==="cloud_restore"||action==="restore_local"?m("账本已恢复，恢复前的备份也已保留。","台帳を復元しました。復元前のバックアップも保存済みです。","The ledger is restored and a pre-restore backup was kept."):m("备份已保存。","バックアップを保存しました。","Your backup has been saved.");}
  if(state==="failed"){title=m("操作未完成","処理を完了できませんでした","Operation did not complete");detail=error||m("请检查网络和备份服务连接后重试。","ネットワークと接続を確認して再試行してください。","Check your network and backup connection, then try again.");}
  showCloudProgress(title,detail);
  const spinner=$("#cloudProgressDialog .cloud-progress-spinner");
  if(spinner)spinner.dataset.state=state;
}
async function runWithCloudProgress(action,provider,callback) {
  cloudProgressCopy(action,provider,action==="backup"?"backup_create":action==="restore_local"?"local_restore":"cloud_prepare");
  try {
    const result=await callback(job=>cloudProgressCopy(action,provider,job.stage));
    cloudProgressCopy(action,provider,"", "done");
    await sleepMobile(650);
    return result;
  } catch(error) {
    cloudProgressCopy(action,provider,"", "failed",error.message);
    await sleepMobile(900);
    throw error;
  } finally {hideCloudProgress();}
}
async function resumeJob() {
  const owner=currentUser?.id;if(!owner||jobRecoveryOwner===owner||activeJob)return;
  const id=localStorage.getItem("hh-active-job:"+owner);if(!id)return;
  const requestedAgent=localStorage.getItem("hh-active-job-agent:"+owner);
  const requestedConversation=localStorage.getItem("hh-active-job-conversation:"+owner)||"";
  jobRecoveryOwner=owner;
  window.cloudJobActive=true;updateConnection();
  try{let job=await api("/api/job?id="+encodeURIComponent(id));while(job.state==="running"){showDeviceChallenge(job);await sleepMobile(1500);if(currentUser?.id!==owner)return;job=await api("/api/job?id="+encodeURIComponent(id));}localStorage.removeItem("hh-active-job:"+owner);localStorage.removeItem("hh-active-job-agent:"+owner);localStorage.removeItem("hh-active-job-conversation:"+owner);if(job.state==="done"){
      if(job.result?.answer){const agent=["bookkeeping","food_health","ledger_query"].includes(requestedAgent)?requestedAgent:(job.result.agent||"bookkeeping"),sessionId=agent==="ledger_query"?(requestedConversation||"legacy"):"",key=chatCacheKey(owner,agent,sessionId);let saved=null;try{saved=await cacheGet(key);}catch{}const isCurrent=agent!=="ledger_query"||localStorage.getItem(chatSessionKey(owner))===sessionId;const transcript=Array.isArray(saved)?saved:(isCurrent?(chats[agent]||[]):[]);transcript.push({role:"assistant",text:job.result.answer,route:job.result.routedAgent||job.result.agent||agent,usage:job.result.usage||null});try{await cacheSet(key,transcript);}catch{}if(isCurrent){chats[agent]=transcript;renderAgent();}}
      if(job.result?.prepared){await queuePreparedAgent(job.result,owner);showToast(m("已在此设备保存，云端上传中…","この端末に保存しました。クラウドへ同期中…","Saved on this device. Syncing to cloud…"));void syncQueue();}
      else {await refreshLedgerViews();showToast(m("后台操作已完成","バックグラウンド処理が完了しました","Background action completed"));}
    }else showToast(job.result?.error||job.message,true);}
  catch{}finally{window.cloudJobActive=false;updateConnection();jobRecoveryOwner="";}
}
function showDeviceChallenge(job) {
  if(!job.result?.userCode)return;
  $("#deviceCode").textContent=job.result.userCode;$("#deviceHelp").textContent=m("打开 GitHub 验证页，输入下面的临时授权码。新设备还需要安装 App 到自己的账号。","GitHubの認証画面でコードを入力してください。新しい端末では自分のアカウントへのAppインストールも必要です。","Open GitHub verification and enter this temporary code. Install the app on your account if needed.");
  $("#deviceLinks").innerHTML='<a class="button primary" href="'+e(job.result.verificationUri)+'" target="_blank" rel="noopener">'+m("打开授权页","認証を開く","Open verification")+'</a><a class="button secondary" href="'+e(job.result.installUrl)+'" target="_blank" rel="noopener">'+m("安装 GitHub App","Appをインストール","Install GitHub App")+'</a>';
  if(!$("#deviceDialog").open)$("#deviceDialog").showModal();
}
async function restoreFile(file) {
  if(!file)return;
  if((await outboxAll()).length)throw new Error(m("请先同步待处理记录。","先に未同期の記録を同期してください。","Sync pending entries first."));
  if(!await confirmOnce(m("恢复文件：","ファイルを復元：","Restore file: ")+file.name,m("当前账本会被替换，恢复前会创建完整备份。","現在の台帳を置き換え、復元前の完全コピーを保存します。","The current ledger will be replaced after a full safety backup.")))return;
  showCloudProgress(m("正在上传并恢复备份…","バックアップを送信して復元中…","Uploading and restoring the backup…"),m("正在发送文件、备份当前账本并应用恢复内容。请勿重复点击或关闭页面。","ファイルを送信し、現在の台帳をバックアップしてから復元します。重複操作やページを閉じる操作はお控えください。","Uploading the file, backing up your current ledger, then restoring. Please do not click again or close the page."));
  try{await api("/api/restore-bundle",{method:"POST",body:file,headers:{"Content-Type":"application/zip","X-Confirm-Restore":"confirmed-once"}});await refreshLedgerViews();showToast(m("已恢复","復元しました","Restored"));}catch(error){showToast(error.message,true);}finally{hideCloudProgress();}
}

function renderAgent({refreshBalance=true}={}) {
  const root=$("#agentPanel");if(!root)return;
  const queryMode=chatAgent==="ledger_query",foodMode=chatAgent==="food_health";
  const agentBusy=!!(activeJob||agentSubmitting)&&activeJobAgent===chatAgent;
  const otherAgentBusy=!!(activeJob||agentSubmitting)&&!!activeJobAgent&&activeJobAgent!==chatAgent;
  const pending=agentBusy?'<span class="loading-pulse">'+m("处理中…","処理中…","Working…")+'</span>':otherAgentBusy?m("另一位助手正在处理；可以切换，完成后再发送。","別のアシスタントが処理中です。切り替えはできます。送信は完了後にできます。","Another assistant is working. You can switch modes; send after it finishes."):queryMode?m("自动理解你的话 · 按需查账、记账或闲聊","話の内容に合わせて照会・記帳・会話を切替","Understands your request and routes chat, ledger queries, or bookkeeping"):m("自然地说，认真地记","いつもの言葉で、ていねいに","Your words. A clear record.");
  const assistantHeader='<div class="smart-assistant-banner"><span class="smart-assistant-icon">'+icon("chat")+'</span><span class="smart-assistant-copy"><strong>'+m("智能助手","スマートアシスタント","Smart assistant")+'</strong><small>'+m("自动选择记账、查账或饮食助手","記帳・照会・食事の内容に応じて自動で選択","Automatically chooses bookkeeping, ledger query, or food assistant")+'</small></span></div>';
  const imageTools='<label class="icon-button" aria-label="'+m("添加图片","画像を追加","Add image")+'">'+icon("folder")+'<input id="chatImageInput" type="file" accept="image/jpeg,image/png,image/webp" multiple></label><span class="muted">'+m("可拖入或选择图片 · 单张不超过20MB · 自动压缩到3MB内","画像をドロップ/選択 · 1枚20MB以下 · 3MB以内に自動圧縮","Drop/select images · max 20 MB each · compressed to under 3 MB")+'</span>';
  const placeholder=queryMode?m("随便聊、问账本，或直接说要记什么","自由に話す、台帳を聞く、記帳を頼む","Chat, ask about your ledger, or tell me what to record"):foodMode?m("问问最近的饮食，或记录今天吃了什么","最近の食生活について質問、または今日の食事を記録","Ask about your diet or record what you ate today"):m("例如：午饭980日元","例：昼食980円","For example: lunch 980 yen");
  const composerAction=agentBusy?(activeJob?b("agent-cancel",m("中断","中断","Stop"),"","button secondary"):'<span class="muted">'+m("正在准备请求…","リクエストを準備中…","Preparing request…")+'</span>'):otherAgentBusy?'<span class="muted">'+m("请等待当前助手完成后发送","現在の処理が終わってから送信してください","Wait for the current request before sending")+'</span>':'<button type="submit" class="send-circle" aria-label="'+m("发送","送信","Send")+'">↑</button>';
  root.innerHTML=assistantHeader+'<div class="chat-caption">'+pending+b("agent-reset",m("新对话","新しい会話","New chat"),"","text-button")+'</div><section id="modelUsagePanel" class="model-usage-panel" aria-live="polite"></section><div id="chatMessages" class="chat-messages" aria-live="polite"></div><form id="chatForm" class="chat-composer"><div id="chatImages" class="chat-images"></div><textarea id="chatInput" rows="3" maxlength="24000" placeholder="'+placeholder+'" aria-label="'+m("消息","メッセージ","Message")+'"></textarea><div class="composer-tools">'+imageTools+composerAction+'</div></form>';
  const messages=chats[chatAgent]||[];
  const welcome=queryMode
    ?'<div class="chat-welcome"><span class="assistant-orb">'+icon("chat")+'</span><h2>'+m("你可以直接说，我会接着处理","そのまま話しかけてください","Just say what you need")+'</h2><p>'+m("可以闲聊、问收支余额、分析消费，也可以直接记账或发小票。我会自动选择合适的助手。","気軽な会話、残高や支出の確認、使い方の相談、記帳やレシート画像にも対応します。内容に合うAgentを自動で選びます。","Chat, ask about balances or spending, get an analysis, record an entry, or send a receipt. I’ll choose the right assistant automatically.")+'</p></div>'
    :'<div class="chat-welcome"><span class="assistant-orb">'+icon(foodMode?"food":"chat")+'</span><h2>'+m("让生活，清楚一点","暮らしを、少しクリアに","A clearer picture of everyday life")+'</h2><p>'+ (foodMode?m("问问最近的饮食，或记录今天吃了什么。","最近の食生活を質問したり、今日の食事を記録したりできます。","Ask about your recent meals or record what you ate today."):m("告诉我一笔收支，或拍下小票。信息不足时先确认，记录成功后再备份。","収支を伝えるか、レシートを撮影してください。不明点は確認してから記帳します。","Tell me about an entry, or photograph a receipt. Unclear details are checked before recording."))+'</p></div>';
  $("#chatMessages").innerHTML=messages.length?messages.map(item=>'<article class="bubble '+item.role+'"><span class="bubble-label">'+(item.role==="user"?m("你","あなた","You"):m("助手","アシスタント","Assistant"))+'</span><p>'+e(item.text)+'</p>'+(item.role==="assistant"&&chatAgent==="ledger_query"&&item.route?'<small class="bubble-usage">'+m("自动调用：","使用：","Used: ")+e(({chat:m("普通聊天","通常会話","Chat"),ledger_query:m("账本查询","台帳照会","Ledger query"),bookkeeping:m("记账助手","記帳Agent","Bookkeeping"),food_health:m("饮食助手","食事Agent","Food assistant")})[item.route]||item.route)+'</small>':"")+(item.role==="assistant"&&item.usage?'<small class="bubble-usage">'+usageCostLabels(item.usage,chatAgent)+'</small>':"")+'</article>').join(""):welcome;
  renderModelUsagePanel();
  if(refreshBalance)void refreshModelBalance(chatAgent,currentUsageVision||attachments.length>0);
  renderAttachments();
  $("#chatForm").onsubmit=sendAgent;
  $("#chatInput").onkeydown=event=>{
    if(event.key==="Enter"&&!event.shiftKey&&!event.ctrlKey&&!event.isComposing&&event.keyCode!==229){
      event.preventDefault();$("#chatForm").requestSubmit();
    }
  };
  const chatImageInput=$("#chatImageInput");
  if(chatImageInput)chatImageInput.onchange=async event=>{await guarded(()=>attachImages([...event.target.files]));event.target.value="";};
  const dropTarget=$("#agentPanel");
  dropTarget.dataset.dropLabel=m("松开鼠标添加图片","ドロップして画像を追加","Drop to add images");
  const carriesFiles=event=>Array.from(event.dataTransfer?.types||[]).includes("Files")||Boolean(event.dataTransfer?.files?.length);
  dropTarget.ondragenter=event=>{if(!carriesFiles(event))return;event.preventDefault();dropTarget.classList.add("drag-over");};
  dropTarget.ondragover=event=>{if(!carriesFiles(event))return;event.preventDefault();if(event.dataTransfer)event.dataTransfer.dropEffect="copy";dropTarget.classList.add("drag-over");};
  dropTarget.ondragleave=event=>{if(event.relatedTarget&&dropTarget.contains(event.relatedTarget))return;dropTarget.classList.remove("drag-over");};
  dropTarget.ondrop=event=>{
    if(!carriesFiles(event))return;
    event.preventDefault();dropTarget.classList.remove("drag-over");
    const files=Array.from(event.dataTransfer?.files||[]),allowed=files.filter(file=>["image/jpeg","image/png","image/webp"].includes(file.type));
    if(files.length!==allowed.length)showToast(m("仅支持 JPEG、PNG 或 WebP 图片。","JPEG・PNG・WebP画像のみ対応しています。","Only JPEG, PNG or WebP images are supported."),true);
    if(allowed.length)void guarded(()=>attachImages(allowed));
  };
  if(messages.length)$("#chatMessages").scrollTop=$("#chatMessages").scrollHeight;
}
function renderAttachments() {
  $("#chatImages").innerHTML=attachments.map((image,index)=>'<button type="button" data-action="image-remove" data-id="'+index+'" aria-label="'+m("移除图片","画像を削除","Remove image")+'"><img src="data:'+image.type+';base64,'+image.data+'" alt="'+e(image.name)+'"><span>×</span></button>').join("");
}
async function attachImages(files) {
  const owner=currentUser?.id;
  if(attachments.length+files.length>5)throw new Error(m("最多5张图片","画像は5枚までです","Up to 5 images"));
  for(const file of files){
    if(file.size>20*1024*1024)throw new Error(m("图片超过20MB","画像が20MBを超えています","Image exceeds 20 MB"));
    const url=URL.createObjectURL(file);
    try{
      const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error(m("无法读取图片，请使用 JPEG、PNG 或 WebP","JPEG・PNG・WebPを使用してください","Use JPEG, PNG or WebP")));img.src=url;});
      const canvas=document.createElement("canvas");let blob=null;
      for(const [maxSide,quality] of [[1920,0.9],[1920,0.84],[1920,0.78],[1600,0.8],[1440,0.76]]){
        const scale=Math.min(1,maxSide/Math.max(image.width,image.height));canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
        const context=canvas.getContext("2d");if(!context)throw new Error(m("无法处理图片","画像を処理できません","Could not process image"));
        context.fillStyle="#fff";context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(image,0,0,canvas.width,canvas.height);
        blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error(m("无法压缩图片","画像を圧縮できません","Could not compress image"))),"image/jpeg",quality));
        if(blob.size<=3*1024*1024)break;
      }
      if(!blob||blob.size>3*1024*1024)throw new Error(m("图片仍然过大，请裁剪后再上传","画像が大きすぎます。トリミングして再試行してください","Image is still too large; crop it and try again"));
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(",")[1]||"");reader.onerror=()=>reject(new Error(m("读取压缩图片失败","圧縮画像を読み込めません","Could not read compressed image")));reader.readAsDataURL(blob);});
      if(currentUser?.id!==owner)return;attachments.push({name:file.name,type:"image/jpeg",data});
    }finally{URL.revokeObjectURL(url);}
  }
  renderAttachments();
}
async function sendAgent(event) {
  event.preventDefault();if(activeJob||agentSubmitting){showToast(activeJobAgent?m("当前助手仍在处理请求，切换助手不受影响。","現在のアシスタントが処理中です。切り替えはできます。","The current assistant is still working. You can switch modes."):m("云端操作正在进行，完成后即可发送；切换助手不受影响。","クラウド処理中です。完了後に送信できます。切り替えは可能です。","A cloud operation is in progress. You can switch modes and send when it finishes."),true);return;}
  const text=$("#chatInput").value.trim();if(!text&&!attachments.length)return;
  agentSubmitting=true;
  const owner=currentUser?.id,agent=chatAgent,images=attachments.map(image=>({...image}));
  activeJobAgent=agent;
  try{
    await chatRestoreLoads.get(owner);
    const conversationId=await ensureChatSessionId(owner),chatKey=chatCacheKey(owner,agent,conversationId);
    const queued=await outboxAll();
    if(queued.length){
      void syncQueue();
      showToast(m("还有记录正在等待云端同步。请等顶部状态灯恢复绿色后再继续记账。","同期待ちの記録があります。上部の表示が緑に戻ってから続けてください。","Entries are still waiting to sync. Continue after the status at the top turns green."),true);
      return;
    }
    const vision=images.length>0,balanceKey=agent+":"+(vision?"vision":"text");currentUsageVision=vision;
    const beforeBalance=await refreshModelBalance(agent,vision,{force:true});
    if(agent==="ledger_query"&&localStorage.getItem(chatSessionKey(owner))!==conversationId)throw new Error(m("这段对话已在别处重开，请确认当前对话后再发送。","別の画面で新しい会話が始まりました。現在の会話を確認してから送信してください。","A new chat was started elsewhere. Check the current conversation before sending."));
    const history=(chats[agent]||[]).slice(-8).map(item=>({role:item.role,text:String(item.text||"").slice(0,1600),route:item.route||""}));
    chats[agent].push({role:"user",text:text+(images.length?"\n"+m("附图","画像","Images")+": "+images.length:"")});
    try{await cacheSet(chatKey,chats[agent]);}catch{}
    $("#chatInput").value="";attachments=[];renderAgent();
    const result=await runAction("agent_prepare",{agent,text,images,history,conversationId,language:currentLanguage,reportDate:reportDate||null},null,false);
    if(currentUser?.id!==owner)return;
    if(result.prepared){
      await queuePreparedAgent(result,owner);
      showToast(m("已在此设备保存，云端上传中…","この端末に保存しました。クラウドへ同期中…","Saved on this device. Syncing to cloud…"));
    }else if(result.cloudCommitted){
      void refreshLedgerViews();
    }
    const usageBreakdown=Array.isArray(result.usageBreakdown)&&result.usageBreakdown.length?result.usageBreakdown:[{agent:result.usageAgent||agent,vision,usage:result.usage}];
    const usageCosts=usageBreakdown.map(part=>estimateModelUsageCost(part.usage,selectedUsageProfile(part.agent||agent,!!part.vision),new Date()));
    let usagePricing=null;
    if(usageCosts.length&&usageCosts.every(cost=>cost?.available))usagePricing={available:true,currency:"CNY",estimated:true,hit_cny:usageCosts.reduce((sum,cost)=>sum+cost.hit_cny,0),miss_cny:usageCosts.reduce((sum,cost)=>sum+cost.miss_cny,0),output_cny:usageCosts.reduce((sum,cost)=>sum+cost.output_cny,0)};
    else if(result.usage)usagePricing={available:false};
    const assistantMessage={role:"assistant",text:result.answer,route:result.routedAgent||agent,usage:result.usage?{...result.usage,vision,cost_cny:usagePricing}:null};
    if(agent==="ledger_query"&&localStorage.getItem(chatSessionKey(owner))!==conversationId){let prior=[];try{prior=await cacheGet(chatKey)||[];}catch{}if(!Array.isArray(prior))prior=[];prior.push(assistantMessage);await cacheSet(chatKey,prior);}else{chats[agent].push(assistantMessage);await cacheSet(chatKey,chats[agent]);}
    const afterBalance=await refreshModelBalance(agent,vision,{force:true});
    const beforeAmounts=new Map((beforeBalance?.balances||[]).map(item=>[item.currency,Number(item.total)]));
    const afterEntry=(afterBalance?.balances||[]).find(item=>beforeAmounts.has(item.currency));
    if(afterEntry){const before=beforeAmounts.get(afterEntry.currency),after=Number(afterEntry.total);if(Number.isFinite(before)&&Number.isFinite(after)&&before>after)modelBalanceSpend[balanceKey]=afterEntry.currency+" "+(before-after).toFixed(4);else modelBalanceSpend[balanceKey]=m("暂未体现","まだ反映されていません","Not reflected yet");}
    if(result.prepared)void syncQueue();
  }catch(error){if(currentUser?.id===owner){const sessionId=await ensureChatSessionId(owner),key=chatCacheKey(owner,agent,sessionId),message={role:"assistant",text:error.message};if(agent==="ledger_query"&&localStorage.getItem(chatSessionKey(owner))!==sessionId){let prior=[];try{prior=await cacheGet(key)||[];}catch{}if(!Array.isArray(prior))prior=[];prior.push(message);try{await cacheSet(key,prior);}catch{}}else{chats[agent].push(message);try{await cacheSet(key,chats[agent]);}catch{}}if(images.length)attachments=images;showToast(error.message,true);}}
  finally{agentSubmitting=false;if(activeJobAgent===agent)activeJobAgent="";if(currentUser?.id===owner)renderAgent();}
}

function appearanceSettingsHtml(mode) {
  const choices = [["system",m("跟随系统","システム設定に従う","Follow system")],
    ["light",m("浅色模式","ライトモード","Light mode")],
    ["dark",m("深色模式","ダークモード","Dark mode")]];
  return '<section class="profile-editor"><h3>'+m("外观","外観","Appearance")+'</h3><label class="field"><span>'+
    m("明暗模式","表示モード","Color mode")+'</span><select id="settings-appearance">'+
    choices.map(([value,label])=>'<option value="'+value+'" '+(mode===value?'selected':'')+'>'+label+'</option>').join('')+
    '</select></label><p class="fineprint">'+m("只影响当前设备。选择后立即保存；跟随系统会自动切换。",
      "この端末のみに適用します。選択すると保存され、システム設定に自動で追従します。",
      "Applies to this device and saves as soon as selected. Follow system changes automatically.")+'</p></section>';
}

async function editSettings(inline=false) {
  if(!workspace)throw new Error(t("offline"));
  settingsDraft=inline&&tutorialTour?.mode==="required-setup"?deepCopy(tutorialTour.draft.settings):inline&&settingsDraft?settingsDraft:deepCopy(workspace.preferences);
  const cfg=settingsDraft;
  if(inline)$("#settingsPane").innerHTML='<form id="settingsInlineForm"><div id="settingsEditorBody"></div><div id="settingsInlineFooter" class="button-row settings-inline-footer"></div></form>';
  const editorBody=()=>inline?$("#settingsEditorBody"):$("#editorBody"),editorForm=()=>inline?$("#settingsInlineForm"):$("#editorForm"),editorFooter=()=>inline?$("#settingsInlineFooter"):$("#editorFooter");
  const savedKeyMask="••••••••••••";
  const skillWarning=agent=>cfg.skillErrors?.[agent]?'<p role="alert" class="fineprint">'+m("此 Agent 的 Skill 无法读取。请恢复默认文本或粘贴有效内容后保存；账本仍可正常查看。","このAgentのSkillを読み込めません。初期値を復元するか内容を貼り付けて保存してください。台帳は引き続き表示できます。","This agent's skill cannot be read. Restore the default text or paste valid content and save. The ledger remains available.")+'</p>':"";
  const cloudRuntime=typeof runtimeConfig!=="undefined"&&runtimeConfig?.deploymentMode==="cloud";
  const render=()=>{
    if(!inline){$("#editorTitle").textContent=m("Agent 相关设置","Agent関連設定","Agent settings");$("#editorCancel").textContent=m("‹ 返回更多","‹ その他へ戻る","‹ Back to More");$("#editorSave").textContent=m("确认","確定","Done");}
    const agentTitle=agent=>agent==="bookkeeping"?m("记账 Agent","記帳Agent","Ledger agent"):m("饮食健康 Agent","食生活Agent","Food agent");
    const profileEditor=(p,index)=>'<section class="profile-editor" data-profile-index="'+index+'"><div class="spread"><strong>'+m("服务","サービス","Service")+' '+(index+1)+'</strong>'+b("profile-remove",m("删除","削除","Remove"),index,"text-button danger-text")+'</div>'+[
        ["name",m("名称","名前","Name"),"text"],["api_url",m("接口完整地址","エンドポイントURL","Full endpoint URL"),"url"],["model",m("模型标识","モデルID","Model ID"),"text"],["api_key",m("API 密钥（已保存时显示为遮罩；留空保留）","APIキー（保存済みはマスク表示、空欄なら保持）","API key (masked when saved; blank keeps it)"),"password"]
      ].map(([key,label,type])=>{const masked=key==="api_key"&&p.keyPresent&&!p.api_key;const value=masked?savedKeyMask:(p[key]||"");return '<label class="field"><span>'+label+'</span><input type="'+type+'" data-profile-key="'+key+'" value="'+e(value)+'" '+(masked?'data-masked-saved-key="1" ':'')+(key==="api_key"?'autocomplete="new-password"':'required')+'></label>';}).join("")+
      '<label class="check-row"><input type="checkbox" data-profile-key="thinking_enabled" '+(p.thinking_enabled?"checked":"")+'><span>'+m("思考模式（支持的服务）","思考モード（対応API）","Thinking mode (supported providers)")+'</span></label><label class="field"><span>'+m("思考强度","思考強度","Reasoning effort")+'</span><select data-profile-key="reasoning_effort">'+["low","high","max"].map(value=>'<option '+(p.reasoning_effort===value?"selected":"")+'>'+value+'</option>').join("")+'</select></label></section>';
    const assignmentEditor=agent=>'<section class="agent-service-editor"><h4>'+agentTitle(agent)+'</h4>'+["agents","visionAgents"].map(group=>'<label class="field"><span>'+ (group==="agents"?m("文字服务","テキスト用","Text service"):m("图片服务","画像用","Image service"))+'</span><select data-agent="'+agent+'" data-group="'+group+'"><option value="">'+m("请选择","選択してください","Choose a service")+'</option>'+cfg.profiles.map(p=>'<option value="'+e(p.id)+'" '+(cfg[group][agent]===p.id?"selected":"")+'>'+e(p.name)+'</option>').join("")+'</select></label>').join("")+'</section>';
    const skillEditor=agent=>'<section class="skill-editor"><h3>'+agentTitle(agent)+'</h3>'+skillWarning(agent)+'<div class="spread"><label for="skill-'+agent+'">'+m("Skill 文本 · 复制粘贴后编辑","Skillテキスト・貼り付けて編集","Skill text · paste and edit")+'</label>'+b("skill-default",m("恢复默认","初期値に戻す","Restore default"),agent,"text-button accent")+'</div><textarea id="skill-'+agent+'" class="skill-text" data-skill="'+agent+'" spellcheck="false" rows="12">'+e(cfg.skills[agent]||"")+'</textarea><p class="fineprint">'+m("此文本会随该 Agent 的请求发送给你选择的模型服务。","このテキストは選択したモデルへのリクエストに含まれます。","This text is included in requests to the model service you select.")+'</p></section>';
    const inRequiredSetup=inline&&tutorialTour?.mode==="required-setup";
    editorBody().innerHTML='<p class="fineprint">'+m("设置会先保存在本次新手流程中，最后一步才统一提交。","設定はチュートリアル内に一時保存され、最後にまとめて送信されます。","Settings stay staged in this setup flow and are submitted together at the final step.")+'</p><p class="fineprint">'+m("新账号会自动载入网站通用 Skill；API 服务和密钥需要各账号自行配置，不会从其他账号复制。","新しいアカウントにはWeb共通Skillを読み込みます。APIサービスとキーは各アカウントで設定し、他のアカウントからコピーされません。","New accounts load the shared website Skills. Each account must configure its own API services and keys; they are never copied from another account.")+'</p>'+
      '<section id="apiServiceSettings" class="agent-setup-section"><div class="section-heading"><h3>'+m("API 服务","APIサービス","API services")+'</h3>'+b("profile-add",icon("plus"))+'</div><div id="profileList">'+cfg.profiles.map(profileEditor).join("")+'</div></section>'+
      '<section id="agentAssignments" class="agent-setup-section"><h3>'+m("Agent 服务分配","Agentサービスの割り当て","Assign services to Agents")+'</h3><div class="agent-service-grid">'+["bookkeeping","food_health"].map(assignmentEditor).join("")+'</div></section>'+
      '<section id="agentSkillSettings" class="agent-setup-section"><h3>'+m("Agent Skill","Agent Skill","Agent Skills")+'</h3><div class="agent-skill-grid">'+["bookkeeping","food_health"].map(skillEditor).join("")+'</div></section>'+
      (cloudRuntime?"":'<label class="check-row"><input id="settings-save-images" type="checkbox" '+(cfg.saveImages?"checked":"")+'><span>'+m("保存记账小票图片","記帳画像を保存","Save receipt images")+'</span></label>');
    editorFooter().innerHTML=inline?(inRequiredSetup?'<span class="fineprint">'+m("按右侧提示分步配置；最后统一保存。","案内に沿って設定し、最後にまとめて保存します。","Follow the guided steps; save everything at the end.")+'</span>':b("settings-apply",m("保存设置","設定を保存","Save settings"),"","button primary")+b("settings-discard",m("撤销未保存修改","未保存の変更を破棄","Discard changes"))):b("settings-apply",m("应用","適用","Apply"),"","button primary");
  };
  const capture=()=>{
    const body=editorBody();
    body.querySelectorAll(".profile-editor").forEach(node=>{if(node.dataset.profileIndex===undefined)return;const p=cfg.profiles[Number(node.dataset.profileIndex)];node.querySelectorAll("[data-profile-key]").forEach(input=>{if(input.dataset.profileKey==="api_key"&&input.dataset.maskedSavedKey==="1"&&input.value===savedKeyMask)p.api_key="";else p[input.dataset.profileKey]=input.type==="checkbox"?input.checked:input.value;});});
    body.querySelectorAll("[data-agent]").forEach(input=>cfg[input.dataset.group][input.dataset.agent]=input.value);
    body.querySelectorAll("[data-skill]").forEach(input=>{
      const agent=input.dataset.skill;
      if(cfg.skillErrors?.[agent]&&!input.value.trim())delete cfg.skills[agent];
      else cfg.skills[agent]=input.value;
    });
    const imageSaveToggle=body.querySelector("#settings-save-images");if(imageSaveToggle)cfg.saveImages=imageSaveToggle.checked;
    if(tutorialTour?.mode==="required-setup"){tutorialTour.draft.settings=deepCopy(cfg);tutorialTour.draft.dirty=true;settingsDraft=deepCopy(cfg);}
  };
  const prepareSettingsSave=()=>{capture();if(workspace?.preferences?.onboardingRequired){cfg.baseCurrency=tutorialTour?.draft.settings.baseCurrency||workspace.settings?.base_currency||cfg.baseCurrency||"JPY";cfg.billingCycleStartDay=Number(tutorialTour?.draft.settings.billingCycleStartDay||workspace.preferences.billingCycleStartDay||15);cfg.onboardingStep="skills";cfg.completeOnboarding=true;}};
  if(inline)settingsInlineCapture=capture;
  render();if(!inline)$("#editorDialog").showModal();
  const body=editorBody(),form=editorForm(),footer=editorFooter();
  body.querySelectorAll('[data-masked-saved-key="1"]').forEach(input=>input.addEventListener("focus",()=>input.select(),{once:true}));
  form.oninput=capture;
  form.onchange=capture;
  form.onsubmit=async event=>{event.preventDefault();prepareSettingsSave();if(tutorialTour?.batchSave){tutorialTour.draft.settings=deepCopy(cfg);tutorialTour.draft.dirty=true;settingsDraft=deepCopy(cfg);if(tutorialTour.mode==="required-setup"){const step=requiredSetupTourSteps[tutorialTour.index];if(step?.guideNext)advanceRequiredSetupGuide(step.form);else showToast(m("按右侧教程提示继续，所有设置最后统一保存。","右側の案内に沿って続けてください。設定は最後にまとめて保存します。","Continue with the guide on the right; everything saves at the end."));}else{showToast(m("Agent、API 和 Skill 已暂存；最后会和其他设置一起保存。","Agent・API・Skillを一時保存しました。最後に他の設定と一緒に保存します。","Agent, API, and Skills are staged; they will be saved with the other settings at the end."));renderTutorialTour();}return;}await guarded(async()=>{const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);if(inline){settingsDraft=null;settingsInlineCapture=null;await editSettings(true);if(!result?.queued)showToast(m("设置已保存","設定を保存しました","Settings saved"));}else $("#editorDialog").close();});};
  body.onclick=async event=>{
    const button=event.target.closest("[data-action]");if(!button)return;event.stopPropagation();capture();
    if(button.dataset.action==="profile-add"){cfg.profiles.push({id:crypto.randomUUID(),name:"",api_url:"https://",model:"",api_key:"",thinking_enabled:false,reasoning_effort:"low"});render();if(tutorialTour?.mode==="required-setup"){tutorialTour.focusSelector='#apiServiceSettings .profile-editor[data-profile-index="'+(cfg.profiles.length-1)+'"]';requestAnimationFrame(renderTutorialTour);}}
    if(button.dataset.action==="profile-remove"){const index=Number(button.dataset.id);if(await confirmOnce(m("删除 API 服务：","APIサービスを削除：","Remove API service: ")+cfg.profiles[index].name,m("保存设置后生效，使用它的 Agent 需要重新选择服务。","設定保存後に反映され、Agentのサービスを再選択する必要があります。","Takes effect when settings are saved. Reassign agents using this service."))){const id=cfg.profiles[index].id;cfg.profiles.splice(index,1);for(const group of ["agents","visionAgents"])for(const agent in cfg[group])if(cfg[group][agent]===id)cfg[group][agent]="";render();if(tutorialTour?.mode==="required-setup")requestAnimationFrame(renderTutorialTour);}}
    if(button.dataset.action==="skill-default"){const defaults=await api("/api/default-skills");cfg.skills[button.dataset.id]=defaults[button.dataset.id];render();if(tutorialTour?.mode==="required-setup")requestAnimationFrame(renderTutorialTour);}
  };
  footer.onclick=async event=>{
    const action=event.target.closest("[data-action]")?.dataset.action;
    if(action==="settings-apply"){prepareSettingsSave();if(tutorialTour?.batchSave){tutorialTour.draft.settings=deepCopy(cfg);tutorialTour.draft.dirty=true;settingsDraft=deepCopy(cfg);showToast(m("Agent、API 和 Skill 已暂存；最后会和其他设置一起保存。","Agent・API・Skillを一時保存しました。最後に他の設定と一緒に保存します。","Agent, API, and Skills are staged; they will be saved with the other settings at the end."));if(tutorialTour.mode==="required-setup")completeRequiredSetupStep("agent");else renderTutorialTour();return;}await guarded(async()=>{const result=await runAction("settings",cfg,null,false);if(!result?.queued)await loadWorkspace(true);if(inline){settingsDraft=null;settingsInlineCapture=null;await editSettings(true);if(!result?.queued)showToast(m("设置已保存","設定を保存しました","Settings saved"));}else if(!result?.queued)showToast(m("设置已应用","適用しました","Settings applied"));});}
    if(action==="settings-discard"){settingsDraft=null;settingsInlineCapture=null;await editSettings(true);}
  };
  if(!inline)$("#editorDialog").addEventListener("close",()=>{$("#editorForm").oninput=null;$("#editorForm").onchange=null;$("#editorBody").onclick=null;$("#editorFooter").onclick=null;settingsDraft=null;settingsInlineCapture=null;},{once:true});
}

function capturePaymentRulesDraft(){
  if(!Array.isArray(paymentRulesDraft))return;
  $$("#modulePanel [data-rule]").forEach(node=>{
    const rule=paymentRulesDraft[Number(node.dataset.rule)];if(!rule)return;
    $$(`[data-rule-key]`,node).forEach(input=>rule[input.dataset.ruleKey]=input.value);
    rule.account_order=$$(`[data-order]`,node).map(input=>input.value);
  });
}
function capturePointRewardsDraft(){
  if(!Array.isArray(pointRewardsDraft))return;
  $$("#modulePanel [data-point-rule]").forEach(node=>{
    const rule=pointRewardsDraft[Number(node.dataset.pointRule)];if(!rule)return;
    $$('[data-point-rule-key]',node).forEach(input=>rule[input.dataset.pointRuleKey]=input.value);
  });
}
async function handleMobileClick(event) {
  const button=event.target.closest("[data-action]");if(!button)return;
  // Specialized editors own their internal draft controls.
  if(button.closest("#editorBody")&&$("#editorBody").onclick)return;
  const action=button.dataset.action,id=button.dataset.id;
  await guarded(async()=>{
    if(action==="queue-discard"){
      const item=(await outboxAll()).find(row=>row.opId===id);
      if(!item||!item.conflict)throw new Error(m("此记录没有待处理的同步冲突。","この記録に未解決の同期競合はありません。","This entry has no pending sync conflict."));
      if(!await confirmOnce(m("丢弃本机待同步草稿？","端末の未送信草稿を破棄しますか？","Discard the pending entry on this device?"),m("云端账本保持不变。这会删除本机队列中的冲突记录，你可以刷新后重新输入。","クラウド台帳は変更しません。この端末の競合記録を削除します。更新後に再入力できます。","The cloud ledger will stay unchanged. This removes the conflicted local entry; refresh and enter it again if needed.")))return;
      await outboxDelete(id);await renderOutbox();await window.onDiscardPreparedAgent?.(item);
      showToast(m("本机待同步草稿已移除，云端账本未更改。","未送信の草稿を削除しました。クラウド台帳は変更していません。","Local pending entry removed. The cloud ledger was not changed."));return;
    }
    if(action==="queue-undo-delete"){
      const item=(await outboxAll()).find(row=>row.opId===id&&row.type==="pending_delete");
      const undone=await outboxUndoDelete(id);
      if(!undone){showToast(m("删除任务已经发往云端，不能再撤销。","削除タスクはクラウドへ送信済みのため、取り消せません。","The deletion has already been dispatched and can no longer be undone."),true);return;}
      if(item)applyPendingDeletePreview(item,false);
      await persistPendingDeletePreview();
      if($("#editorDialog")?.open)$("#editorDialog").close();
      renderMobile();await renderOutbox();
      showToast(m("已撤销删除，账目仍保留。","削除を取り消しました。取引は保持されています。","Deletion undone. The transaction is still in your ledger."));return;
    }
    if(action==="queue-undo-action"){
      const item=(await outboxAll()).find(row=>row.opId===id&&row.type==="pending_action");
      const undone=await outboxUndoPendingAction(id);
      if(!undone){showToast(m("这项更改已开始发送，或后面还有依赖它的操作，暂时不能撤销。","送信が始まったか、後続の変更があるため取り消せません。","This change is already being sent, or later changes depend on it, so it cannot be undone now."),true);return;}
      if(item)applyPendingActionPreview(item,false,true);
      await persistPendingActionPreview();
      await renderOutbox();renderMobile();
      showToast(m("已撤销最新更改，本机账本已恢复。","最新の変更を取り消し、端末の台帳を戻しました。","Latest change undone; the local ledger was restored."));
      return;
    }
    if(action==="page"){navigate(id);advanceTutorialTour(action,id);return;}
    if(action==="account-layout"){
      if(id!=="cards"&&id!=="list")return;
      accountViewMode=id;localStorage.setItem("hh-account-view",id);renderAccountViewControls();return;
    }
    if(action==="hero-mode-toggle"){heroProfitMode=!heroProfitMode;return renderDashboard();}
    if(action==="privacy"){hiddenAmounts=!hiddenAmounts;localStorage.setItem("hh-hide-amounts",hiddenAmounts?"1":"0");renderMobile();await renderAccounts();return;}
    if(action==="refresh"){
      await syncQueue();
      await refreshLedgerViews();
      return;
    }
    if(action==="workspace-retry"){workspaceError="";renderMobile();return loadWorkspace(true);}
    if(action==="asset-tab"){assetTab=id;renderAssetTabs();return;}
    if(action==="finance-tab"){financialTab=id;renderModule("finance");return;}
    if(action==="settings-tab"){settingsInlineCapture?.();settingsInlineCapture=null;settingsTab=id;renderModule("settings");advanceTutorialTour(action,id);return;}
    if(action==="backup-warning-reauthorize"){navigate("more");settingsTab="backup";moreTab="settings";renderMore();return;}
    if(action==="budget-trend-mode"){financeTrendMode=id;renderModule("finance");return;}
    if(action==="module-back"){resetMorePageState();const queuePanel=document.querySelector(".queue-panel");if(queuePanel)$("#backupPage")?.append(queuePanel);renderMore();return;}
    if(["payment-rules-save","rule-add","rule-remove","order-add","order-remove","order-up","order-down"].includes(action)){
      capturePaymentRulesDraft();
      const rules=paymentRulesDraft||[],[ruleIndex,orderIndex]=String(id||"").split(":").map(Number);
      if(action==="payment-rules-save"){
        const result=await runAction("payment_rules",{profiles:deepCopy(rules),revision:workspace.preferences?.paymentRevision});
        paymentRulesDraft=deepCopy(workspace?.preferences?.paymentRules||rules);renderModule("rules");
        if(!result?.queued)showToast(m("付款规则已保存。","支払ルールを保存しました。","Payment rules saved."));
        return;
      }
      if(action==="rule-add"){
        const accounts=fieldsAccount();if(!accounts.length){showToast(t("needsAccount"),true);return;}
        rules.push({payment_method:accounts[0][0],purpose:"",currency:"",account_order:[accounts[0][0]]});
      }
      if(action==="rule-remove"){
        if(!Number.isInteger(ruleIndex)||!rules[ruleIndex])return;
        if(!await confirmOnce(m("删除规则","ルールを削除","Delete rule")+" "+(ruleIndex+1),m("保存后不再自动匹配此用途。","保存後、この用途を自動適用しません。","After saving, this scenario will no longer match.")))return;
        rules.splice(ruleIndex,1);
      }
      if(action==="order-add"){
        const rule=rules[ruleIndex];if(!rule)return;
        const order=rule.account_order||(rule.account_order=[rule.payment_method].filter(Boolean));
        const candidate=(cachedBootstrap?.accounts||[]).find(account=>!order.includes(account.name));
        if(candidate)order.push(candidate.name);else showToast(m("没有可添加的其他账户。","追加できる口座がありません。","There are no other accounts to add."),true);
      }
      if(action==="order-remove"){
        const rule=rules[ruleIndex],accountName=rule?.account_order?.[orderIndex];if(!rule||accountName===undefined)return;
        if(!await confirmOnce(m("移除扣款来源：","引落元を削除：","Remove funding source: ")+accountName,m("保存后不再从此项扣款。","保存後、この項目から引き落としません。","This source will no longer be used after saving.")))return;
        rule.account_order.splice(orderIndex,1);
      }
      if(action==="order-up"&&Number.isInteger(orderIndex)&&orderIndex>0){const order=rules[ruleIndex]?.account_order;if(order)[order[orderIndex-1],order[orderIndex]]=[order[orderIndex],order[orderIndex-1]];}
      if(action==="order-down"){const order=rules[ruleIndex]?.account_order;if(order&&orderIndex<order.length-1)[order[orderIndex+1],order[orderIndex]]=[order[orderIndex],order[orderIndex+1]];}
      renderModule("rules");return;
    }
    if(["point-rewards-save","point-rule-add","point-rule-remove"].includes(action)){
      capturePointRewardsDraft();
      const rules=pointRewardsDraft||[],ruleIndex=Number(id);
      if(action==="point-rule-add"){
        const payments=(cachedBootstrap?.accounts||[]).filter(account=>account.type!=="points");
        const points=(cachedBootstrap?.accounts||[]).filter(account=>account.type==="points"&&account.currency==="JPY");
        if(!payments.length){showToast(m("请先添加一个付款账户。","先に支払口座を追加してください。","Add a payment account first."),true);return;}
        if(!points.length){showToast(m("请先在余额页添加积分账户。","先に残高ページでポイント口座を追加してください。","Add a points account under Balances first."),true);return;}
        const available=payments.find(account=>!rules.some(rule=>String(rule.payment_account_id)===String(account.id)));
        if(!available){showToast(m("每个付款账户只能添加一条返还规则。","支払口座ごとに設定できる還元ルールは1件です。","Each payment account can have one reward rule."),true);return;}
        rules.push({payment_account_id:String(available.id),points_account_id:String(points[0].id),rate_bps:0});
        renderModule("points");return;
      }
      if(action==="point-rule-remove"){
        if(!Number.isInteger(ruleIndex)||!rules[ruleIndex])return;
        rules.splice(ruleIndex,1);renderModule("points");return;
      }
      const normalized=[];const seen=new Set();
      for(const rule of rules){
        const paymentId=Number(rule.payment_account_id),pointsId=Number(rule.points_account_id),rate=Number(rule.rate_percent);
        if(!Number.isSafeInteger(paymentId)||!Number.isSafeInteger(pointsId)||!Number.isFinite(rate)||rate<=0||rate>100||Math.abs(rate*100-Math.round(rate*100))>1e-8){
          showToast(m("请检查每条规则的付款账户、积分账户和返还比例（0.01% 至 100%，最多两位小数）。","各ルールの支払口座・ポイント口座・還元率（0.01%〜100%、小数2桁まで）を確認してください。","Check each payment account, points account, and reward rate (0.01%–100%, up to two decimals)."),true);return;
        }
        if(seen.has(paymentId)){showToast(m("同一个付款账户只能设置一条规则。","同じ支払口座には1件だけ設定できます。","Only one rule is allowed per payment account."),true);return;}
        seen.add(paymentId);normalized.push({payment_account_id:paymentId,points_account_id:pointsId,rate_bps:Math.round(rate*100)});
      }
      const result=await runAction("point_rewards",{rules:normalized});
      pointRewardsDraft=normalized.map(rule=>({...rule,payment_account_id:String(rule.payment_account_id),points_account_id:String(rule.points_account_id),rate_percent:(rule.rate_bps/100).toFixed(2)}));
      renderModule("points");
      if(!result?.queued)showToast(m("积分返还规则已保存。","ポイント還元ルールを保存しました。","Points reward rules saved."));
      return;
    }
    if(action==="favorites-edit"){favoritesEditing=!favoritesEditing;renderMore();return;}
    if(action==="favorites-add"){favoritesEditing=true;renderMore();document.querySelector(".favorite-picker")?.scrollIntoView({behavior:"smooth",block:"nearest"});return;}
    if(action==="favorite-remove"){saveFavorites(getFavorites().filter(item=>item!==id));showToast(m("已移除常用功能","ショートカットを削除しました","Shortcut removed"));renderMore();return;}
    if(action==="favorite-add"){const values=getFavorites();if(!values.includes(id)&&values.length<8){values.push(id);saveFavorites(values);showToast(m("已添加常用功能","ショートカットを追加しました","Shortcut added"));}else if(values.length>=8)showToast(m("最多添加 8 个常用功能","ショートカットは8件までです","You can add up to 8 shortcuts"),true);favoritesEditing=false;renderMore();return;}
    if(action==="favorite")return openFavorite(id);
    if(action==="module"){navigate("more");if(id==="rules")paymentRulesDraft=deepCopy(workspace?.preferences?.paymentRules||[]);if(id==="points")pointRewardsDraft=deepCopy(workspace?.preferences?.pointRewardRules||[]);if(["backup","categories","settings"].includes(id)){settingsTab=id==="backup"?"backup":id==="categories"?"categories":"general";moreTab="settings";}else moreTab=id;renderMore();advanceTutorialTour(action,id);return;}
    if(action==="add-card"){navigate("assets");assetTab="cash";renderAssetTabs();$("#accountForm").classList.remove("hidden");$("#accountForm [name=type]").value="credit";$("#accountForm [name=name]").focus();return;}
    if(action==="backup"){await runWithCloudProgress("backup","",progress=>runAction("backup",{},progress));showToast(m("备份已创建","バックアップを作成しました","Backup created"));return;}
    if(action==="scope-cancel"){backupDraft=null;if(moreTab==="settings"){settingsTab="backup";renderModule("settings");}else renderCloud();return;}
    if(action==="scope-all"){const inputs=$$("#scopeForm .scope-grid input");const all=inputs.every(input=>input.checked);inputs.forEach(input=>input.checked=!all);$("#scopeForm").onchange();return;}
    if(action==="cloud-connect"){
      if(id==="github"){
        if(typeof window.startGithubBackupReauth!=="function")throw new Error(m("授权窗口尚未准备好，请刷新页面后重试。","認証画面を準備できません。画面を更新して再試行してください。","The authorization window is not ready. Refresh and try again."));
        await window.startGithubBackupReauth();
        return;
      }
      return openForm("Gitee",[field("token",m("私人令牌 · user_info 与 projects 权限","個人トークン・user_infoとprojects権限","Personal token · user_info and projects"),"password"),field("repositoryName",m("私有仓库名称","非公開リポジトリ名","Private repository name"),"text",workspace.preferences.cloud.gitee?.repositoryName||"household-bookkeeping-data")],data=>runAction("cloud_connect",{...data,provider:"gitee"}));
    }
    if(["cloud-upload","cloud-restore","cloud-disconnect","local-restore"].includes(action)){
      if((await outboxAll()).length)throw new Error(m("请先完成待同步记录","先に未同期記録を同期してください","Sync pending entries first"));
      const target=action==="local-restore"?id:id.toUpperCase();
      if(!await confirmOnce(button.textContent+" · "+target,m("上传可能替换云端快照；恢复会替换当前账本并先保留完整备份。断开连接只撤销本软件保存的授权。","アップロードはクラウドを置換、復元は台帳を置換します。先に完全コピーを保存します。切断は保存済み認証を解除します。","Uploads may replace the cloud snapshot. Restore replaces this ledger after a full safety copy. Disconnect removes the stored authorization.")))return;
      const map={"cloud-upload":"cloud_upload","cloud-restore":"cloud_restore","cloud-disconnect":"cloud_disconnect","local-restore":"restore_local"};
      if(action==="cloud-upload"||action==="cloud-restore"||action==="local-restore"){
        const jobAction=map[action];
        await runWithCloudProgress(jobAction,id,progress=>runAction(jobAction,{provider:id,name:id,confirmed:true},progress));
        showToast(action==="cloud-upload"?m("备份已上传到 "+(id==="github"?"GitHub":"Gitee"),"バックアップを "+(id==="github"?"GitHub":"Gitee")+" にアップロードしました","Backup uploaded to "+(id==="github"?"GitHub":"Gitee")):m("账本已恢复","台帳を復元しました","Ledger restored"));
        return;
      }
      return runAction(map[action],{provider:id,name:id,confirmed:true});
    }
    if(action==="agent-reset"){if(activeJob||agentSubmitting)return;if(!await confirmOnce(m("开始新对话","新しい会話を始める","Start a new chat"),m("新对话会从空白上下文开始，未完成的旧记账草稿不会带入；已保存的账目不受影响。","新しい会話は空の状態から始まり、未完了の記帳内容は引き継ぎません。保存済みの取引には影響しません。","The new chat starts with a clean context. Unfinished intent from the previous chat will not carry over; saved entries stay unchanged.")))return;const owner=currentUser?.id;if(!owner)return;await ensureChatSessionId(owner);const freshId=createChatSessionId();localStorage.setItem(chatSessionKey(owner),freshId);chatSessionLoads.set(owner,Promise.resolve(freshId));chats={bookkeeping:[],food_health:[],ledger_query:[]};attachments=[];const input=$("#chatInput");if(input)input.value="";try{await cacheSet(chatCacheKey(owner,"ledger_query",freshId),[]);}catch{}renderAttachments();renderAgent();showToast(m("新对话已开始，旧的未完成内容不会带入。","新しい会話を開始しました。前の未完了内容は引き継がれません。","New chat started. Unfinished context from the previous chat was left behind."));return;}
    if(action==="agent-cancel"){await api("/api/cancel-job",{method:"POST",body:JSON.stringify({id:activeJob})});showToast(m("正在中断","中断中","Stopping…"));return;}
    if(action==="image-remove"){if(await confirmOnce(m("移除这张待发送图片","送信前の画像を削除","Remove this pending image"),m("该图片将不会发送。","この画像は送信されません。","This image will not be sent."))){attachments.splice(Number(id),1);renderAttachments();}return;}
    const dateField=()=>field("date",t("date"),"date",workspace.date);
    const accountField=(name="account",type="all",value="")=>field(name,t("account"),"select",value,fieldsAccount(type));
    const amountField=(name="amount",label=t("amount"),value="")=>field(name,label,"decimal",value);
    if(action==="investment-add"||action==="investment-edit"){
      const existing=(workspace.investments||[]).find(row=>String(row.id)===String(id))||null;
      const toInput=row=>{const code=String(row.currency||"JPY"),places=Number(row.minor_digits??currencyMinorDigits(code,0));return {id:String(row.id),name:String(row.name||""),kind:String(row.kind||"other"),currency:code,cost:plainAmount(row.cost_minor,places,code),value:plainAmount(row.value_minor,places,code),quantity:String(row.quantity||""),fundCode:String(row.fund_code||""),updatedOn:String(row.updated_on||workspace.date||"")};};
      const positions=(workspace.investments||[]).map(toInput);
      const values=existing?toInput(existing):{name:"",kind:"fund",currency:"JPY",cost:"",value:"",quantity:"",fundCode:""};
      const kinds=[["fund",m("基金 / 投信","投資信託","Fund")],["jp_stock",m("日本股票","日本株","Japan stock")],["us_stock",m("美国股票","米国株","US stock")],["other",m("其他","その他","Other")]];
      const currencies=[["JPY","JPY · "+m("日元","日本円","Japanese yen")],["CNY","CNY · "+m("人民币","人民元","Chinese yuan")],["USD","USD · "+m("美元","米ドル","US dollar")]];
      return openForm(existing?m("修改投资持仓","投資保有情報を編集","Edit investment holding"):m("添加投资持仓","投資保有情報を追加","Add investment holding"),[
        field("name",m("产品名称","商品名","Product name"),"text",values.name),
        field("kind",m("产品类型","商品タイプ","Type"),"select",values.kind,kinds),
        {...field("fundCode",m("基金代码（可选）","ファンドコード（任意）","Fund code (optional)"),"text",values.fundCode),optional:true},
        field("currency",m("币种","通貨","Currency"),"select",values.currency,currencies),
        amountField("cost",m("累计投入","累計投資額","Total invested"),values.cost),
        {...amountField("value",m("手动估值（自动估值失败时使用）","手入力の評価額（自動取得できない場合に使用）","Manual value (used if auto valuation is unavailable)"),values.value),optional:true},
        {...field("quantity",m("持有口数 / 数量","保有口数 / 数量","Units held / quantity"),"decimal",values.quantity),optional:true}
      ],async data=>{
        const name=String(data.name||"").trim(),cost=String(data.cost||"").trim(),value=String(data.value||cost).trim();
        if(!name)throw new Error(m("请填写产品名称。","商品名を入力してください。","Enter a product name."));
        const kind=data.kind||"other",quantity=String(data.quantity||"").trim(),fundCode=kind==="fund"?String(data.fundCode||"").trim():"";
        if(fundCode&&!/^\d{6}$/.test(fundCode))throw new Error(m("基金代码请填写6位数字，或从产品搜索结果中选择。","ファンドコードは6桁の数字を入力するか、検索結果から選択してください。","Enter a six-digit fund code or select a search result."));
        if(fundCode&&(!quantity||!/^\d{1,16}(?:\.\d{1,8})?$/.test(quantity)||Number(quantity)<=0))throw new Error(m("已选自动估值基金，请填写大于0的持有口数。","自動評価する投信を選択した場合、0より大きい保有口数を入力してください。","Enter a unit count greater than zero for automatic fund valuation."));
        const next={id:existing?String(existing.id):createChatSessionId(),name,kind,currency:fundCode?"JPY":(data.currency||"JPY"),cost,value,quantity,fundCode,updatedOn:workspace.date};
        const updated=existing?positions.map(row=>row.id===String(existing.id)?next:row):[...positions,next];
        const result=await runAction("investment_save",{positions:updated});if(selectedPage==="investment")void refreshInvestmentQuotes();return result;
      },{note:m("输入基金名称可搜索三菱UFJ资管的产品，选中后填持有口数；打开投资页时会取一次上一交易日净值并计算估值。其他公司基金、股票和产品仍可手动估值。行情只在本机页面临时计算，不写账本，也不连接券商。","三菱UFJアセットマネジメントの投信は商品名で検索できます。選択後に保有口数を入力すると、投資ページを開く際に前営業日の基準価額を1回取得して評価額を計算します。その他の投信・株式などは手動評価です。相場データはページ内で一時計算し、台帳には書き込まず、証券口座にも接続しません。","Search MUFG Asset Management funds by name, then enter units held. Opening Investments fetches the prior business day's NAV once and calculates value. Enter other funds, stocks, or products manually. Quotes are calculated temporarily in this page; they are not written to the ledger and no brokerage account is connected.") ,onReady:installFundNameSearch});
    }
    if(action==="investment-delete"){
      const target=(workspace.investments||[]).find(row=>String(row.id)===String(id));if(!target)return;
      if(!await confirmOnce(m("删除投资持仓","投資保有情報を削除","Delete investment holding"),m("只会删除这条投资记录，不会影响账户余额或账单。","この投資記録だけを削除し、口座残高や明細には影響しません。","Only this investment record will be removed. Account balances and ledger entries stay unchanged.")))return;
      const positions=(workspace.investments||[]).filter(row=>String(row.id)!==String(id)).map(row=>{const currency=String(row.currency||"JPY"),digits=Number(row.minor_digits??currencyMinorDigits(currency,0));return {id:String(row.id),name:String(row.name||""),kind:String(row.kind||"other"),currency,cost:plainAmount(row.cost_minor,digits,currency),value:plainAmount(row.value_minor,digits,currency),quantity:String(row.quantity||""),fundCode:String(row.fund_code||""),updatedOn:String(row.updated_on||workspace.date||"")};});
      return runAction("investment_save",{positions});
    }
    const card=workspace.cards.find(row=>row.account_id===id);
    if(action==="account-rename"){
      const account=(cachedBootstrap?.accounts||[]).find(row=>String(row.id)===String(id));
      if(!account)throw new Error(m("找不到这个账户，请刷新后重试。","口座が見つかりません。更新して再試行してください。","Account not found. Refresh and try again."));
      return openForm(m("更改账户称呼","口座名を変更","Rename account"),[field("name",m("新称呼","新しい名前","New name"),"text",account.name)],data=>{
        const name=String(data.name||"").trim();
        if(name===account.name)return;
        return runAction("rename_account",{accountId:account.id,oldName:account.name,name});
      });
    }
    if(action==="credit-plan-delete"){
      if(!await confirmOnce(m("删除每月应还计划？","毎月の返済予定を削除しますか？","Delete the monthly repayment plan?"),m("删除后将停止后续自动记账，并取消尚未记账的本期计划金额；已记入账本的还款流水会保留。之后点“还款”可重新设置计划。本功能只管理账本，不会实际扣款。","削除すると今後の自動記帳を停止し、未記帳の今期予定額を取り消します。記帳済みの返済履歴は保持されます。「返済」から再設定できます。実際の引落は行いません。","This stops future automatic ledger entries and cancels unposted amounts. Posted repayment entries remain. Click Repay to set up the plan again. This only changes the ledger; it never makes a bank payment.")))return;
      return runAction("credit_plan_delete",{card:card.name,accountId:card.account_id});
    }
    if(action==="credit-snapshot")return openForm(m("录入额度快照","利用枠を記録","Credit snapshot")+" · "+card.name,[field("account",t("account"),"select",card.name,[[card.name,card.name]]),dateField(),amountField("limit",m("总额度","利用限度額","Total limit"),card.limit_minor?plainAmount(card.limit_minor,card.minor_digits,card.currency):""),amountField("available",m("当前可用额度","利用可能額","Available credit"),card.available_minor?plainAmount(card.available_minor,card.minor_digits,card.currency):""),field("includeDifference",m("将欠款差额计入账本（余额盘盈/盘亏）","利用残高の差額を台帳に記録（残高過剰・不足）","Post debt difference to ledger (balance surplus/shortage)"),"checkbox",true),{...field("note",m("备注","メモ","Note")),optional:true}],data=>runAction("credit_snapshot",{...data,accountId:card.account_id}),{note:m("默认将欠款差额计入账本。取消勾选则只保存快照；有历史额度记录时，差额按上次额度快照及此后卡片流水计算；首次记录时按账面信用卡欠款比较。","初期設定では債務差額を台帳に記録します。チェックを外すとスナップショットのみ保存します。過去の利用枠記録がある場合は、その記録以降のカード取引を反映した債務との差額を記帳し、初回のみ台帳上のカード債務と比較します。","By default, the debt difference is posted to the ledger. Uncheck to save only the snapshot. Existing snapshots use the latest snapshot plus later card transactions as the baseline; the first snapshot compares against the ledger card debt.")});
    if(action==="credit-repay"||action==="credit-plan"){
      const schedule=card.repayment_schedule||{},recreatingPlan=Boolean(Object.keys(schedule).length)&&schedule.enabled!=="1",isPlan=action==="credit-plan"||(action==="credit-repay"&&recreatingPlan);
      const planDate=schedule.next_due_date&&String(schedule.next_due_date)>=String(workspace.date||"")?schedule.next_due_date:workspace.date;
      const fields=[field("card",m("信用卡","カード","Credit card"),"select",card.name,[[card.name,card.name]]),accountField("source","cash",schedule.source_name),{...dateField(),value:isPlan?planDate:workspace.date}];
      const regionLabel=regionTimeZones.find(([value])=>value===(workspace.preferences?.timeZone||"Asia/Tokyo"))?.[1]||m("日本·东京","日本・東京","Japan · Tokyo");
      const timeLabel=currentLanguage==="ja-JP"?`自動記帳時刻（${regionLabel}）`:currentLanguage==="en-US"?`Automatic ledger time (${regionLabel})`:`自动记账时间（${regionLabel}）`;
      if(isPlan)fields.push(field("time",timeLabel,"time",schedule.due_time||"09:00"));
      const savedAmount=schedule.amount_minor===null||schedule.amount_minor===undefined?"":plainAmount(schedule.amount_minor,card.minor_digits,card.currency);
      fields.push({...amountField("amount",t("amount"),isPlan?savedAmount:""),optional:isPlan});
      const formTitle=isPlan?(recreatingPlan?m("重新设置应还计划","返済予定を再設定","Recreate repayment plan"):m("每月应还计划","毎月の返済予定","Monthly repayment plan")):m("记录还款","返済を記録","Record repayment");
      const planNote=recreatingPlan?m("原计划已删除或停用。填写还款账户、日期、时间和本期金额后保存，即可重新启用。只记入账本，不会实际扣款。","予定は削除または停止されています。口座・日付・時刻・今期金額を入力して保存すると再設定できます。台帳への記録のみで、実際の引落は行いません。","The previous plan was deleted or disabled. Enter the account, date, time, and amount, then save to set it up again. This only records in the ledger; no payment is made."):m("本期应还金额请手动填写；留空不会自动记账。日期已过的计划会标为错过，不会补记。此功能只记入账本，不会实际扣款；时间按所选地区执行，后台会在设定时间后的下一次检查时处理。","今月の返済額は入力してください。空欄の場合、自動記帳されません。期日を過ぎた予定は見送り扱いとなり、遡って記帳しません。帳簿への記録のみで、実際の引落は行いません。時刻は選択した地域の時刻で、設定時刻後の次回確認時に処理されます。","Enter this month's amount; blank means nothing is posted. Past-due plans are marked missed and are not backdated. This only records a ledger entry, never a bank debit. Times follow your selected region and are processed at the next background check after the selected time.");
      return openForm(formTitle,fields,data=>runAction(isPlan?"credit_plan":"credit_repay",data),{note:isPlan?planNote:""});
    }
    if(action==="credit-history"){
      const history=workspace.creditHistory[id]||{};$("#editorTitle").textContent=card.name;$("#editorCancel").textContent=m("退出教程","チュートリアルを終了","Exit tutorial");$("#editorSave").classList.add("hidden");$("#editorFooter").replaceChildren();$("#editorForm").onsubmit=event=>event.preventDefault();
      $("#editorBody").innerHTML='<h3>'+m("额度快照历史","利用枠履歴","Credit snapshots")+'</h3>'+(history.snapshots||[]).map(row=>'<div class="history-snapshot"><div><strong>'+e(hiddenAmounts?"••••":row.snapshot_date)+'</strong><p>'+money(row.available_minor,card.currency,card.minor_digits)+" / "+money(row.limit_minor,card.currency,card.minor_digits)+'</p><small>'+e(row.description||row.note||row.snapshot_type)+(row.pendingSync?" · "+m("待同步","同期待ち","Sync pending"):"")+'</small></div>'+(row.pendingSync?"":b("credit-restore",m("恢复","復元","Restore"),id+":"+row.snapshot_type+":"+row.id))+'</div>').join("")+'<h3>'+m("信用卡流水","カード取引","Card activity")+'</h3>'+(history.transactions||[]).map(row=>'<div class="report-row"><span>'+e(hiddenAmounts?"••••":row.occurred_on)+" · "+e(row.description)+'</span><b>'+money(row.card_amount_minor,card.currency,card.minor_digits)+'</b></div>').join("");$("#editorDialog").showModal();$("#editorDialog").addEventListener("close",()=>$("#editorSave").classList.remove("hidden"),{once:true});return;
    }
    if(action==="credit-restore"){const [accountId,snapshotType,snapshotId]=id.split(":");if(await confirmOnce(m("恢复额度快照","利用枠を復元","Restore credit snapshot"),m("移除较新的快照，保留账目；操作前会备份。","新しい枠履歴を削除し取引は保持。先にバックアップします。","Newer snapshots will be removed; entries stay. A backup is made first."))){await runAction("restore_credit",{accountId,snapshotType,snapshotId,confirmed:true});$("#editorDialog").close();}return;}
    if(action==="asset-edit"){
      const asset=workspace.assets.find(row=>row.id===id)||{};
      return openForm(m("固定资产","固定資産","Fixed asset"),[field("name",m("资产名称","資産名","Asset name"),"text",asset.name||""),field("currency",t("currency"),"select",asset.currency||"JPY",[["JPY","JPY"],["CNY","CNY"],["USD","USD"]]),amountField("cost",m("购入原值","取得原価","Acquisition cost"),plainAmount(asset.cost_minor,currencyMinorDigits(asset.currency,0),asset.currency)),field("month",m("购入月份","取得月","Acquisition month"),"month",asset.acquisition_month||workspace.date.slice(0,7)),field("months",m("预计使用月数","耐用月数","Useful life in months"),"integer",asset.useful_life_months||"36"),field("included",m("计入余额总额","残高合計に含める","Include in the balance total"),"checkbox",asset.include_in_balance_sheet!=="0"),{...field("disposal",m("报废月份（可空）","除却月（任意）","Disposal month (optional)"),"month",asset.disposal_month||""),optional:true}],data=>runAction("asset",{...data,id:asset.id||""}));
    }
    if(action==="asset-toggle"){const asset=(workspace.assets||[]).find(row=>String(row.id)===String(id));if(!asset)throw new Error(m("找不到这项固定资产。","固定資産が見つかりません。","Fixed asset not found."));return runAction("asset_toggle",{id:asset.id,included:asset.include_in_balance_sheet!=="1"});}
    if(action==="asset-delete"||action==="recurring-delete"){if(await confirmOnce(button.textContent+" #"+id,m("删除前保存完整备份；已有流水保留。","削除前に完全バックアップ。既存取引は保持。","A full backup is made before deletion. Posted entries remain.")))return runAction(action==="asset-delete"?"delete_asset":"delete_recurring",{id,confirmed:true});return;}
    if(action==="cash-adjust"){const account=cachedBootstrap.accounts.find(row=>row.id==id);if(hiddenAmounts)throw new Error(m("请先显示数字再调整","先に数字を表示してください","Show numbers before editing"));return openForm(m("核对实际余额","実残高を照合","Reconcile balance")+" · "+account.name,[amountField("amount",m("实际余额","実際の残高","Actual balance"),plainAmount(account.balanceMinor,account.minorDigits,account.currency)),dateField(),field("postDifferences",m("将差额记入账本","差額を記帳","Post the difference"),"checkbox",true)],data=>{
      if(tutorialTour?.batchSave){tutorialTour.draft.balanceChanges[account.name]=data.amount;tutorialTour.draft.adjustmentDate=data.date;tutorialTour.draft.postDifferences=!!data.postDifferences;tutorialTour.draft.confirmBalanceAdjustments=!!data.postDifferences;tutorialTour.draft.dirty=true;renderTutorialDraftNotice();renderTutorialTour();showToast(m("余额核对已暂存；教程最后一步统一上传。","残高照合を一時保存しました。最後にまとめて送信します。","Balance check staged; it will upload with the rest at the end."));return;}
      return runAction("reconcile",{date:data.date,postDifferences:data.postDifferences,amounts:{[account.name]:data.amount}});
    });}
    if(action==="cash-delete"){const account=cachedBootstrap.accounts.find(row=>row.id==id);if(await confirmOnce(m("删除账户：","口座を削除：","Delete account: ")+account.name,m("关联流水或计划的账户不能删除。删除前会备份。","取引・予定で使う口座は削除できません。先にバックアップします。","Accounts referenced by entries or plans cannot be deleted. A backup is made first.")))return runAction("delete_account",{name:account.name,confirmed:true});return;}
    if(action==="recurring-edit"){
      const row=workspace.recurring.find(row=>row.id===id)||{};return openForm(m("定期收支","定期取引","Recurring entry"),[field("name",m("规则名称","予定名","Schedule name"),"text",row.name||""),field("kind",t("type"),"select",row.kind||"expense",[["expense",t("expense")],["income",t("income")]]),accountField("account","all",row.account_name),field("currency",m("账单币种","請求通貨","Bill currency"),"select",row.currency||"JPY",[["JPY","JPY"],["CNY","CNY"],["USD","USD"]]),amountField("amount",t("amount"),row.amount_minor?plainAmount(row.amount_minor,row.minor_digits,row.currency):""),field("category",t("category"),"select",row.category_name,[...fieldsCategories("expense"),...fieldsCategories("income")]),field("frequency",m("周期","周期","Frequency"),"select",row.frequency||"monthly",[["daily",m("每天","毎日","Daily")],["weekly",m("每周","毎週","Weekly")],["monthly",m("每月","毎月","Monthly")],["yearly",m("每年","毎年","Yearly")]]),field("interval",m("每隔几个周期","間隔","Interval"),"integer",row.interval_count||"1"),{...dateField(),value:row.next_due_date||workspace.date}],data=>runAction("recurring",{...data,id:row.id||""}));
    }
    if(action==="recurring-toggle"){const row=workspace.recurring.find(row=>row.id===id);return runAction("recurring_toggle",{id,enabled:row.enabled!=="1"});}
    if(action==="run-due"){const result=await runAction("run_due");if(!result?.queued)showToast(m("到期项目已检查","期日の確認が完了しました","Due entries checked"));return;}
    if(action==="budget-edit"){
      const settings=workspace.settings||{};
      let plan={};try{plan=JSON.parse(settings["savings_plan:"+workspace.profit.start]||settings["savings_plan:monthly_template"]||"{}").items||{};}catch{}
      const categories=fieldsCategories("expense");
      const totalFromCategories=()=>categories.reduce((sum,_category,index)=>{
        const raw=( $("#edit-category"+index)?.value||"" ).replace(/[，,\s]/g,"").trim();
        return /^\d+$/.test(raw)?sum+BigInt(raw):sum;
      },0n).toString();
      return openForm(m("本期预算","今期予算","Period budget"),[
        {...amountField("total",m("总预算 · JPY（自动合计）","予算合計 · JPY（自動計算）","Total budget · JPY (automatic total)"),"0"),readonly:true,className:"budget-total-field"},
        amountField("goal",m("储蓄目标 · JPY","貯蓄目標 · JPY","Savings goal · JPY"),settings.savings_goal_jpy||"0"),
        ...categories.map(([name,label],index)=>({...amountField("category"+index,label,plan[name]||"0"),optional:true}))
      ],data=>runAction("budget",{total:totalFromCategories(),goal:data.goal,items:Object.fromEntries(categories.map(([name],index)=>[name,data["category"+index]||"0"]))}),{
        bodyClass:"budget-editor-body",
        onReady:()=>{
          const totalField=$("#edit-total"),updateTotal=()=>{if(totalField)totalField.value=totalFromCategories();};
          categories.forEach((_,index)=>$("#edit-category"+index)?.addEventListener("input",updateTotal));
          updateTotal();
        }
      });
    }
    if(action==="food-purchase"||action==="food-eaten")return openForm(action==="food-purchase"?m("添加食品采购","食品の購入","Food purchase"):m("记录饮食","食事を記録","Log a meal"),[dateField(),field("items",m("每行一种食物；数量可写在 | 后面","1行に1品。数量は | の後に記入","One food per line; optional quantity after |"),"textarea"),{...field("meal",m("餐次（可空）","食事区分（任意）","Meal (optional)")),optional:true},{...field("note",m("备注（可空）","メモ（任意）","Note (optional)")),optional:true}],data=>runAction(action==="food-purchase"?"food_purchase":"food_eaten",{...data,items:data.items.split("\n").filter(line=>line.trim()).map(line=>{const parts=line.split("|");return [parts[0].trim(),parts.slice(1).join("|").trim()];})}));
    if(action==="food-preference")return openForm(m("采购计入偏好","購入の計上設定","Purchase preference"),[field("enabled",m("将采购食品计入已吃回顾（不生成食用流水）","購入食品を食事回顧に含める（食事記録は作成しない）","Count food purchases in food reviews (does not create meals)"),"checkbox",workspace.settings?.food_review_purchases_count_as_eaten==="1")],data=>runAction("food_preference",data));
    if(action==="food-group")return openForm(m("食品分类","食品カテゴリ","Food group"),[field("group",t("category"),"select",workspace.food.find(row=>row.id===id).food_group,Object.entries(workspace.foodGroups))],data=>runAction("food_group",{...data,id}));
    if(action==="food-delete"){const [kind,num]=id.split(":");if(await confirmOnce(m("删除食品记录","食品記録を削除","Delete food record")+" #"+num,m("仅删除食品记录，不撤销财务流水；先备份。","食品記録のみ削除し、財務取引は保持。先にバックアップします。","Deletes the food record, keeping financial entries. A backup is made first.")))return runAction("delete_food",{id:num,kind,confirmed:true});return;}
    if(action==="category-add")return openForm(m("新增类别","カテゴリ追加","New category"),[field("name",t("categoryName")),field("kind",t("type"),"select","expense",[["expense",t("expense")],["income",t("income")]]),{...field("ja-JP",m("日语显示名（可空）","日本語表示名（任意）","Japanese name (optional)")),optional:true},{...field("en-US",m("英语显示名（可空）","英語表示名（任意）","English name (optional)")),optional:true}],data=>stageTutorialCategory("category",data)||runAction("category",data));
    if(action==="category-edit"){const row=cachedBootstrap.categories[Number(id)];return openForm(m("类别显示名","カテゴリ表示名","Category display name"),[field("language",m("语言","言語","Language"),"select",currentLanguage,[["zh-CN","简体中文"],["ja-JP","日本語"],["en-US","English"]]),field("name",m("显示名","表示名","Display name"),"text",row.display_name)],data=>{const change={...data,id:row.id};return stageTutorialCategory("category_translation",change)||runAction("category_translation",change);});}
    if(action==="tx-detail"){
      const row=findTransactionById(id);if(!row)return;
      $("#editorTitle").textContent=m("账单详情","取引の詳細","Entry details");$("#editorCancel").textContent=m("退出教程","チュートリアルを終了","Exit tutorial");$("#editorSave").classList.add("hidden");$("#editorFooter").replaceChildren();$("#editorForm").onsubmit=event=>event.preventDefault();
      const sign=row.kind==="income"?"+":row.kind==="expense"?"−":"";
      const pendingNote=row.pendingSync?'<p class="fineprint" role="status">'+(row.conflict?m("同步冲突，记录仍保留在本机，暂时不能编辑或删除。","同期競合のため、この端末に記録を保持しています。編集・削除はできません。","Sync conflict: this entry is safe on this device, but cannot be edited or deleted yet."):m("这笔记录已保存在本机，正在云端同步；同步完成后即可编辑或删除。","この記録は端末に保存済みで、クラウドへ同期中です。完了後に編集・削除できます。","Saved on this device and syncing to the cloud. Editing and deletion will be available after sync."))+'</p>':"";
      const pendingDeleteNote=row.pendingDelete?'<p class="fineprint" role="status">'+(row.pendingDeleteDispatched?m("删除任务已交给云端；云端会先备份再删除，关闭网页不会中断。","削除タスクはクラウドに送信済みです。先にバックアップしてから削除します。ページを閉じても処理は続きます。","The cloud accepted the deletion task. It will back up the ledger before deleting; closing this page will not stop it."):row.pendingDeleteSending?m("正在确认云端是否已接收。为避免重复操作，确认期间暂不能撤销。","クラウドが受け付けたか確認中です。重複処理を避けるため確認中は取り消せません。","Checking whether the cloud accepted it. Undo is paused until the status is known."):m("这笔账已在本机标为待删除。云端接收前可以撤销。","この取引は端末で削除待ちになっています。クラウド送信前なら取り消せます。","Marked for deletion on this device. You can undo before the cloud accepts it."))+(row.pendingDeleteError?"<br>"+e(row.pendingDeleteError):"")+'</p>':"";
      const actions=row.pendingDelete
        ? (!row.pendingDeleteSending?'<div class="button-row">'+b("queue-undo-delete",m("撤销删除","削除を取り消す","Undo deletion"),row.pendingDeleteOpId,"button secondary")+'</div>':"")
        : row.pendingSync?"":'<div class="button-row">'+(row.needs_review==="1"?b("tx-review",m("核对并确认","確認する","Review & confirm"),id):"")+b("tx-edit",m("编辑账单","取引を編集","Edit entry"),id)+b("tx-delete",m("删除这笔账","取引を削除","Delete this entry"),id,"button danger-text")+'</div>';
      $("#editorBody").innerHTML='<strong class="detail-amount kind-'+e(row.kind)+'">'+sign+money(row.amount_minor,row.currency,row.currency_minor_digits)+'</strong><p class="prewrap">'+e(transactionDisplayDescription(row))+'</p>'+["occurred_on","category_name","account_name","to_account_name","balance_effect"].map(key=>row[key]?'<div class="report-row"><span>'+e({occurred_on:t("date"),category_name:t("category"),account_name:t("fromAccount"),to_account_name:t("toAccount"),balance_effect:t("status")}[key])+'</span><strong>'+e(row[key])+'</strong></div>':"").join("")+pendingNote+pendingDeleteNote+actions;
      $("#editorDialog").showModal();$("#editorDialog").addEventListener("close",()=>$("#editorSave").classList.remove("hidden"),{once:true});return;
    }
    if(action==="tx-edit"){
      const row=findTransactionById(id);if(!row)return;
      const accounts=(cachedBootstrap?.accounts||[]).map(account=>[account.name,account.name+" · "+account.currency]);
      const accountOptions=[["",m("不指定账户","口座なし","No account")],...accounts];
      const currencies=[...new Set([row.currency,...(cachedBootstrap?.accounts||[]).map(account=>account.currency)])].map(code=>[code,code]);
      const categories=(cachedBootstrap?.categories||[]).map(item=>[item.name,item.display_name,item.kind]);
      if(row.category_name&&!categories.some(item=>item[0]===row.category_name))categories.push([row.category_name,row.category_name,row.kind]);
      const categoryOptions=[["",m("请选择类别","カテゴリを選択","Choose a category")],...categories.filter(item=>item[2]===row.kind||item[0]===row.category_name).map(([name,label])=>[name,label])];
      const digits=Number(row.currency_minor_digits??row.minor_digits??(["CNY","USD"].includes(row.currency)?2:0));
      const toDigits=Number(row.to_minor_digits??digits);
      return openForm(m("编辑账单","取引を編集","Edit entry"),[
        field("date",t("date"),"date",row.occurred_on),
        field("kind",t("type"),"select",row.kind,[["expense",t("expense")],["income",t("income")],["transfer",t("transfer")]]),
        field("description",m("说明","内容","Description"),"text",transactionDisplayDescription(row)),
        field("currency",t("currency"),"select",row.currency,currencies),
        amountField("amount",t("amount"),plainAmount(row.amount_minor,digits,row.currency)),
        {...field("account_name",t("account"),"select",row.account_name||"",accountOptions),optional:true},
        {...field("category_name",t("category"),"select",row.category_name||"",categoryOptions),optional:true},
        {...field("to_account_name",m("转入账户","振込先口座","Destination account"),"select",row.to_account_name||"",accountOptions),optional:true},
        {...amountField("to_amount",m("转入金额（跨币种时填写）","入金額（異なる通貨の場合）","Destination amount (for FX transfers)"),row.to_amount_minor?plainAmount(row.to_amount_minor,toDigits,row.to_currency||row.currency):""),optional:true},
        field("memo_only",m("备查记录（不影响账户余额）","メモ記録（残高に反映しない）","Memo only (does not affect balances)"),"checkbox",row.balance_effect==="memo"),
        field("needs_review",m("待核对","要確認","Needs review"),"checkbox",row.needs_review==="1"),
      ],async data=>{const result=await runAction("edit_transaction",{id,...data});if(!result?.queued)showToast(m("账单已保存，修改前备份已保留。","取引を保存し、変更前のバックアップを保管しました。","Entry saved. A pre-edit backup was kept."));return result;},{note:m("保存前会自动完整备份；信用卡自动还款流水需在还款计划中修改。","保存前に完全バックアップします。カード自動返済の流水は返済予定から変更してください。","A full backup is created before saving. Automatic card repayment entries must be changed in the repayment plan."),onReady:()=>{
        const kindSelect=$("#edit-kind"),categorySelect=$("#edit-category_name"),categoryLabel=categorySelect?.closest("label.field");
        const toggleKind=()=>{
          const transfer=kindSelect.value==="transfer";
          for(const name of ["category_name","to_account_name","to_amount","memo_only"]){const input=$("#edit-"+name),label=input?.closest("label");if(label)label.classList.toggle("hidden",transfer?!["to_account_name","to_amount"].includes(name):["to_account_name","to_amount"].includes(name));}
          if(categoryLabel)categoryLabel.classList.toggle("hidden",transfer);
          if(categorySelect){const previous=categorySelect.value;const choices=categories.filter(item=>item[2]===kindSelect.value).map(([name,label])=>[name,label]);categorySelect.replaceChildren(new Option(m("请选择类别","カテゴリを選択","Choose a category"),""),...choices.map(([name,label])=>new Option(label,name)));if(choices.some(([name])=>name===previous))categorySelect.value=previous;}
          if(categorySelect)categorySelect.required=!transfer;
          const destination=$("#edit-to_account_name");if(destination)destination.required=transfer;
          if(accountSelect)accountSelect.required=transfer||!memo?.checked;
        };
        const memo=$("#edit-memo_only"),accountSelect=$("#edit-account_name");
        kindSelect?.addEventListener("change",toggleKind);toggleKind();
        memo?.addEventListener("change",()=>{if(accountSelect)accountSelect.required=kindSelect.value==="transfer"||!memo.checked;});
      }});
    }
    if(action==="tx-delete"){
      const row=findTransactionById(id);if(!row||row.pendingDelete)return;
      if(await confirmOnce(m("删除账目：","取引を削除：","Delete entry: ")+row.description,m("账目会先在本机标为“待删除”，几秒内可撤销；云端接收后会先备份再删除，届时无法撤销。账户余额与额度会重新计算。","取引はまず端末で「削除待ち」になり、数秒間は取り消せます。クラウド受付後、バックアップしてから削除し、その後は取り消せません。残高と利用枠を再計算します。","The entry will be marked pending on this device and can be undone for a few seconds. After the cloud accepts it, a backup is made before deletion and it can no longer be undone. Balances and credit limits are recalculated."))){
        if(window.confirmBeforeQueuedOperation&&!await window.confirmBeforeQueuedOperation())return;
        const operation=newOperation("pending_delete",{id:String(row.id),baseRevision:String(workspace?.revision||cachedBootstrap?.revision||"")});
        const item={...operation,rowSnapshot:deepCopy(row),notBefore:Date.now()+3500,serverAccepted:false,dispatchStarted:false};
        await outboxPut(item);
        applyPendingDeletePreview(item,true);
        await persistPendingDeletePreview();
        $("#editorDialog").close();
        renderMobile();await renderOutbox();
        showToast(m("已标为待删除，可在待同步列表或账目详情中撤销。云端会先备份再删除。","削除待ちにしました。同期キューまたは取引詳細から取り消せます。クラウドで先にバックアップします。","Marked for deletion. Undo from the sync queue or transaction details. The cloud will back up before deleting."));
        if(navigator.onLine)void syncQueue();
      }
      return;
    }
    if(action==="tx-review"){const row=findTransactionById(id);if(!row)return;if(row.balance_effect==="memo"){return openForm(m("确认实际账户","実際の口座を確認","Confirm actual account"),[accountField()],data=>runAction("review_transaction",{id,...data}));}await runAction("review_transaction",{id});$("#editorDialog").close();}
  });
}

mountMobile();
window.onCloudLedgerRestored = () => {
  workspaceEpoch++;workspaceLoading=null;
  chats={bookkeeping:[],food_health:[],ledger_query:[]};workspace=null;workspaceOwner="";workspaceError="";backupDraft=null;
  if(currentUser)void Promise.allSettled([
    idbRequest("cache","readwrite",store=>store.delete("workspace:"+currentUser.id)),
    idbRequest("cache","readwrite",store=>store.delete("bootstrap:"+currentUser.id)),
    idbRequest("cache","readwrite",store=>store.delete("workspace-meta:"+currentUser.id)),
  ]);
  if(currentUser){const freshId=createChatSessionId();localStorage.setItem(chatSessionKey(currentUser.id),freshId);chatSessionLoads.set(currentUser.id,Promise.resolve(freshId));void cacheSet(chatCacheKey(currentUser.id,"ledger_query",freshId),[]).catch(()=>{});}
  ledgerRangeRows=null;attachments=[];renderAgent();
};
document.addEventListener("visibilitychange", async () => {
  // Login and the first visible-tab event can overlap. The in-flight initial
  // load already refreshes the ledger; forcing another pass here downloads the
  // full D1 snapshot twice and can hit the client timeout on the duplicate.
  if (document.hidden || !currentUser || cloudBootstrapFailed || !serverReachable || activeJob || sending || visibilityRefreshRunning || workspaceLoading || document.querySelector("dialog[open]")) return;
  visibilityRefreshRunning = true;
  try {
    await guarded(async () => {
      if (currentUser) await refreshLedgerViews();
      resumeJob();
    });
  } finally {
    visibilityRefreshRunning = false;
  }
});
const baseRenderAccounts=renderAccounts;
renderAccounts=async function(){
  await baseRenderAccounts();
  const accounts=(await localAccountsAndCategories()).accounts;
  renderAccountViewControls();
  $$("#accountGrid .account-card").forEach((node,index)=>{
    const account=accounts[index];if(!account)return;
    // Credit cards have their own tab with limit and debt details. Keep them
    // out of the funds list, which otherwise renders every account type.
    if(account.type==="credit"){node.remove();return;}
    if(hiddenAmounts)$(".account-balance",node).textContent="••••••";
    if(!account.pending&&!$(".account-actions",node)){
      const actions=document.createElement("div");actions.className="button-row account-actions";
      actions.innerHTML=b("account-rename",m("更改称呼","口座名を変更","Rename"),account.id,"text-button")+b("cash-adjust",m("核对余额","残高照合","Reconcile"),account.id,"text-button accent")+b("cash-delete",m("删除","削除","Delete"),account.id,"text-button danger-text");node.append(actions);
    }
  });
};
const baseRenderAll=renderAll;
renderAll=async function(){await baseRenderAll();await applyPendingAgentPreviews();renderMobile();};
const baseShowLoggedIn=showLoggedIn;
showLoggedIn=function(){baseShowLoggedIn(); if(currentUser){const owner=currentUser.id,restore=(async()=>{try{const sessionId=await ensureChatSessionId(owner),saved=await cacheGet(chatCacheKey(owner,"ledger_query",sessionId));if(currentUser?.id===owner&&localStorage.getItem(chatSessionKey(owner))===sessionId&&Array.isArray(saved)){chats.ledger_query=saved;renderAgent();}}catch{}})();chatRestoreLoads.set(owner,restore);for(const agent of ["bookkeeping","food_health"])cacheGet("chat:"+owner+":"+agent).then(saved=>{if(currentUser?.id===owner&&saved){chats[agent]=saved;}});} renderNavigation();renderAgent();if(!workspace||workspaceOwner!==currentUser?.id)loadWorkspace();else renderMobile();};
const baseShowLoggedOut=showLoggedOut;
 showLoggedOut=function(){setTutorialPageLocked(false);clearTutorialSpotlight();baseShowLoggedOut();workspaceEpoch++;workspaceLoading=null;workspace=null;workspaceOwner="";firstRunSetupReplay=false;firstRunSetupDraft=null;tutorialTour=null;firstRunTourStarted=false;ledgerRangeRows=null;backupDraft=null;settingsDraft=null;settingsInlineCapture=null;settingsTab="general";reportDate="";chats={bookkeeping:[],food_health:[],ledger_query:[]};attachments=[];activeJob="";activeJobAgent="";const queuePanel=document.querySelector(".queue-panel");if(queuePanel)$("#backupPage")?.append(queuePanel);document.querySelectorAll("dialog[open]").forEach(dialog=>dialog.close());$("#editorBody").replaceChildren();for(const id of ["accountGrid","ledgerList","page-home","creditPanel","fixedPanel","modulePanel","cloudControls"])$("#"+id)?.replaceChildren();renderAgent();};
const baseApplyLanguage=applyLanguage;
applyLanguage=function(){baseApplyLanguage();renderMobile();renderAgent();renderAccountViewControls();};
renderTransactions=renderMobileTransactions;
