"use strict";

// Mobile presentation only; financial rules stay in the shared Python services.
const m = (zh, ja, en) => currentLanguage === "ja-JP" ? ja : currentLanguage === "en-US" ? en : zh;
const e = escapeHtml;
const icons = {
  home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
  chat:'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3v-9a9 9 0 0 1 18-2Z"/><path d="M7 10h10M7 14h6"/>',
  book:'<path d="M5 3h14v18H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M7 3v18M11 8h5M11 12h5"/>',
  wallet:'<rect x="3" y="5" width="18" height="15" rx="4"/><path d="M16 11h5v5h-5a2.5 2.5 0 0 1 0-5ZM4 6l12-3"/>',
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
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
  photo:'<rect x="2" y="5" width="20" height="16" rx="4"/><path d="m8 5 2-3h4l2 3"/><circle cx="12" cy="13" r="4"/>',
};
const icon = name => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(icons[name]||icons.book)+'</svg>';
const b = (action, text, id="", cls="button secondary") => {
  const names={privacy:m("显示或隐藏金额","金額表示の切替","Show or hide amounts"),refresh:m("刷新","更新","Refresh"),"budget-edit":m("编辑预算","予算編集","Edit budget"),"add-card":m("添加信用卡","カード追加","Add credit card"),"asset-edit":m("登记资产","資産を登録","Register asset"),"profile-add":m("添加 API 服务","APIを追加","Add API service"),backup:m("创建备份","バックアップ作成","Create backup"),"order-up":m("上移","上へ","Move up"),"order-down":m("下移","下へ","Move down"),"order-remove":m("移除扣款来源","引落元を削除","Remove funding source"),"favorites-edit":m("编辑常用功能","ショートカットを編集","Edit shortcuts"),"favorites-add":m("添加常用功能","ショートカットを追加","Add shortcut"),"favorite-remove":m("移除此常用功能","ショートカットを削除","Remove shortcut")};
  return '<button type="button" class="'+cls+'" data-action="'+action+'" data-id="'+e(id)+'"'+(names[action]?' aria-label="'+e(names[action])+'"':"")+'>'+text+'</button>';
};
const money = (value, currency="JPY", digits=null) => hiddenAmounts ? "••••••" : formatMinor(value || "0", currency, digits === null ? currency === "CNY" ? 2 : 0 : digits);
const plainAmount = (minor, digits=0) => {
  const v=BigInt(String(minor || 0)), factor=10n**BigInt(digits);
  const a=v<0n?-v:v; return (v<0n?"-":"")+(a/factor).toString()+(digits ? "."+(a%factor).toString().padStart(digits,"0"):"");
};
let workspace = null, workspaceOwner = "", workspaceLoading = null, workspaceLoadingOwner = "";
let workspaceEpoch = 0;
let workspaceError = "";
let selectedPage = "home", assetTab = "cash", moreTab = "", reportDate = "", ledgerSearchTimer = null, ledgerRangeRows = null, backupDraft = null, favoritesEditing = false;
let hiddenAmounts = localStorage.getItem("hh-hide-amounts") === "1";
let chatAgent = "bookkeeping", chats = {bookkeeping:[], food_health:[]}, attachments=[];
let activeJob = "", loadingJob = false, selectedHistory = null;
let jobRecoveryOwner = "", settingsDraft = null;
const sleepMobile = ms => new Promise(resolve => setTimeout(resolve,ms));

function mountMobile() {
  const app=$("#appScreen"), heading=$(".page-heading",app), banner=$("#offlineBanner");
  const accounts=$(".accounts-panel"), entry=$(".entry-panel"), queue=$(".queue-panel"), history=$(".history-panel");
  $(".table-scroll",history).classList.add("legacy-table");
  const legacyNote=$(".privacy-note",app); legacyNote?.remove();
  app.replaceChildren(heading,$("#githubLinkBanner"),banner);
  heading.classList.add("mobile-heading");
  heading.querySelector("h1").removeAttribute("data-i18n");
  const tools=document.createElement("div"); tools.className="heading-tools";
  tools.innerHTML=b("privacy",icon("eye"),"","icon-button")+b("refresh",icon("repeat"),"","icon-button");
  heading.append(tools);
  for(const name of ["home","entry","ledger","assets","more"]) {
    const section=document.createElement("section"); section.id="page-"+name; section.className="mobile-page";
    section.dataset.page=name; app.append(section);
  }
  $("#page-entry").innerHTML='<div id="agentPanel" class="panel chat-panel"></div><details class="panel manual-entry"><summary>'+m("手动记一笔","手入力で記帳","Manual entry")+'</summary></details>';
  $(".manual-entry").append(entry);
  $("#page-assets").innerHTML='<div id="assetTabs" class="mode-pills"></div><div id="creditPanel"></div><div id="fixedPanel"></div>';
  $("#page-assets").append(accounts);
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
  dlg.innerHTML='<form id="editorForm"><header class="sheet-heading"><button type="button" id="editorCancel" class="text-button"></button><h2 id="editorTitle"></h2><button type="submit" class="text-button accent" id="editorSave"></button></header><div id="editorBody" class="sheet-body"></div><footer id="editorFooter" class="sheet-footer"></footer></form>';
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
  document.addEventListener("visibilitychange",()=>{if(!document.hidden&&currentUser){loadWorkspace(true);resumeJob();}});
  if(window.visualViewport) window.visualViewport.addEventListener("resize",()=>{
    const raised=window.innerHeight-window.visualViewport.height>140;
    document.body.classList.toggle("keyboard-visible",raised);
  });
}

function renderNavigation() {
  const labels={home:m("总览","概要","Today"),entry:m("记账","記帳","Record"),ledger:m("账单","明細","Ledger"),assets:m("资产","資産","Assets"),more:m("更多","その他","More")};
  $("#bottomNav").innerHTML=Object.keys(labels).map((name,index)=>'<button data-action="page" data-id="'+name+'" class="nav-item '+(selectedPage===name?"active":"")+'" aria-current="'+(selectedPage===name?"page":"false")+'">'+icon(["home","chat","book","wallet","more"][index])+'<span>'+labels[name]+'</span></button>').join("");
  for(const page of $$(".mobile-page"))page.classList.toggle("hidden",page.dataset.page!==selectedPage);
  $(".page-heading h1").textContent=labels[selectedPage];
  $(".page-heading .eyebrow").textContent=m("生活，有迹可循","暮らしを、ていねいに","A little more clarity");
}
function navigate(page) {selectedPage=page;renderNavigation();window.scrollTo({top:0,behavior:"instant"});if(page==="more")renderMore();}
function workspaceLoadError(error) {
  if(error?.status===401)return m("登录已过期，请退出后重新登录。","ログインの有効期限が切れました。再ログインしてください。","Your session expired. Sign out and sign in again.");
  const cloud=typeof runtimeConfig!=="undefined"&&runtimeConfig?.deploymentMode==="cloud";
  if(error?.status)return m(cloud?"云端服务未能读取账本：":"电脑服务未能读取账本：",cloud?"クラウドサービスで台帳を読み込めません：":"PC側で台帳を読み込めません：",cloud?"The cloud service could not read the ledger: ":"The computer could not read the ledger: ")+error.message;
  if(error?.name==="AbortError")return cloud?m("云端账本加载超时，请稍后重试。","クラウド台帳の読み込みがタイムアウトしました。後で再試行してください。","Loading the cloud ledger timed out. Please try again."):m("账本加载超时。请确认电脑服务仍在运行，然后重试。","台帳の読み込みがタイムアウトしました。PC側のサービスを確認して再試行してください。","Ledger loading timed out. Check that the computer service is running, then retry.");
  return cloud?m("暂时无法连接云端服务，请检查网络后重试。","クラウドサービスに接続できません。通信を確認して再試行してください。","Cannot reach the cloud service. Check your connection and try again."):m("暂时连不上电脑。电脑连接本手机热点也可以；请保持热点和电脑记账服务开启，并确认当前访问地址。","PCに接続できません。この端末のテザリングでも利用できます。テザリングとPC側のサービスを有効にし、アクセス先のアドレスを確認してください。","Cannot reach the computer. This phone's hotspot is supported; keep the hotspot and computer service on and check the current address.");
}
async function loadWorkspace(force=false) {
  if(!currentUser||!idb)return;
  const owner=currentUser.id;
  const epoch=workspaceEpoch;
  if(workspaceLoading&&workspaceLoadingOwner===owner)return workspaceLoading;
  workspaceLoadingOwner=owner;
  workspaceError="";
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),15000);
  workspaceLoading=(async()=>{
    try{
      if(!force&&!workspace&&workspaceOwner!==owner){
        try{workspace=await cacheGet("workspace:"+owner);if(workspace)workspaceOwner=owner;}catch{}
      }
      const data=await api("/api/workspace?lang="+currentLanguage+(reportDate?"&asOf="+encodeURIComponent(reportDate):""),{signal:controller.signal});
      if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;
      workspace=data;workspaceOwner=owner;workspaceError="";
      try{await cacheSet("workspace:"+owner,data);}catch{}
    }catch(error){
      if(currentUser?.id!==owner||workspaceEpoch!==epoch)return;
      try{const cached=await cacheGet("workspace:"+owner);workspace=cached||null;if(cached)workspaceOwner=owner;}catch{workspace=null;}
      if(!workspace)workspaceOwner="";
      workspaceError=workspaceLoadError(error);
    }finally{
      clearTimeout(timeout);
      if(currentUser?.id===owner&&workspaceEpoch===epoch){renderMobile();resumeJob();}
    }
  })().finally(()=>{if(workspaceLoadingOwner===owner&&workspaceEpoch===epoch)workspaceLoading=null;});
  return workspaceLoading;
}
async function loadLedgerRange() {
  if(!currentUser||!serverReachable)return;
  const owner=currentUser.id,start=$("#historyStart").value,end=$("#historyEnd").value;
  const params=new URLSearchParams();if(start)params.set("start",start);if(end)params.set("end",end);
  const rows=await api("/api/transactions?"+params);
  if(currentUser?.id!==owner||$("#historyStart").value!==start||$("#historyEnd").value!==end)return;
  ledgerRangeRows=rows;renderMobileTransactions();
}
function renderMobile() {
  renderNavigation();renderDashboard();renderAssetTabs();renderCredits();renderAssets();renderMore();renderCloud();renderMobileTransactions();
  if(!$("#editorDialog").open){$("#editorCancel").textContent=t("cancel");$("#editorSave").textContent=m("保存","保存","Save");}
}
function metric(label,value,extra="",cls="") {
  return '<article class="metric '+cls+'"><span>'+label+'</span><strong>'+value+'</strong>'+(extra?'<small>'+extra+'</small>':"")+'</article>';
}
function renderDashboard() {
  const root=$("#page-home");
  if(!workspace){root.innerHTML=workspaceError?'<div class="panel workspace-error" role="alert"><p>'+e(workspaceError)+'</p>'+b("workspace-retry",m("重试","再試行","Retry"),"","button primary")+'</div>':'<div class="panel empty-state">'+m("正在载入你的账本…","台帳を読み込み中…","Loading your ledger…")+'</div>';return;}
  const p=workspace.profit,j=p.jpy_equivalent,bal=workspace.balanceSheet;
  const total=workspace.settings.monthly_jpy_budget_minor||"0";
  const remaining=BigInt(total)-BigInt(j.expense_minor);
  const percent=BigInt(total)>0n?Math.min(100,Math.max(0,Number(BigInt(j.expense_minor)*100n/BigInt(total)))):0;
  root.innerHTML='<section class="hero-balance glass"><div class="hero-top"><span>'+m("总净资产 · JPY","総純資産 · JPY","Total net assets · JPY")+'</span><span class="live-badge">'+m("我的账本","マイ台帳","My ledger")+'</span></div><div class="hero-value">'+money(bal.net_assets.JPY)+'</div><p>'+m("人民币资产独立核算","人民元資産は別集計","CNY assets tracked separately")+' · '+money(bal.net_assets.CNY,"CNY")+'</p><div class="hero-actions">'+b("page",icon("plus")+" "+m("记一笔","記帳する","Record"),"entry","button hero-primary")+b("page",m("查看账户","口座を見る","Accounts"),"assets","button hero-secondary")+'</div></section>'+
    '<div class="metrics-grid">'+metric(m("本期支出","今期の支出","Period spending"),money(j.expense_minor),p.start+" — "+p.through,"expense-metric")+metric(m("本期收入","今期の収入","Period income"),money(j.income_minor),m("含人民币参考汇率折算","人民元の参考換算を含む","Includes CNY reference conversion"),"income-metric")+'</div>'+
    '<section class="panel budget-card"><div class="section-heading"><h2>'+m("预算，还剩","予算の残り","Room in your budget")+'</h2>'+b("module",icon("arrow"),"budget","icon-button")+'</div><strong class="budget-value">'+money(remaining)+'</strong><div class="budget-track"><progress max="100" value="'+percent+'"></progress></div><div class="spread muted"><span>'+m("已用","使用済み","Used")+' '+percent+'%</span><span>'+m("预算","予算","Budget")+' '+money(total)+'</span></div></section>'+
    '<section class="panel"><div class="section-heading"><h2>'+m("钱花在哪里","支出の内訳","Where it went")+'</h2>'+b("module",m("报表","レポート","Reports"),"reports","text-button accent")+'</div>'+categoryBars(j.categories)+'</section>'+
    '<section class="panel"><div class="section-heading"><h2>'+m("最近记录","最近の記録","Latest activity")+'</h2>'+b("page",m("全部","すべて","See all"),"ledger","text-button accent")+'</div>'+(workspace.transactions.slice(0,4).map(txCard).join("")||empty(m("从第一笔开始记录生活","最初の記帳から始めましょう","Start with your first entry")))+'</section>'+
    (j.missing_conversion_count!=="0"?'<p class="fineprint">'+m("部分历史人民币记录缺少汇率，未计入合并报表。","一部の過去の人民元取引は為替未登録のため合計に含まれません。","Some historical CNY entries lack exchange rates and are excluded from combined totals.")+'</p>':"");
}
function empty(text){return '<div class="empty-state">'+text+'</div>';}
function categoryBars(categories={}) {
  const entries=Object.entries(categories).sort((a,b)=>BigInt(b[1])>BigInt(a[1])?1:-1).slice(0,8);
  const max=entries.reduce((x,item)=>BigInt(item[1])>x?BigInt(item[1]):x,1n);
  return entries.map(([name,amount],index)=>'<div class="category-bar"><div class="spread"><span>'+e(name)+'</span><strong>'+money(amount)+'</strong></div><svg viewBox="0 0 300 7" preserveAspectRatio="none" class="spark-bar color-'+index+'"><rect width="300" height="7" rx="3.5" class="bar-track"/><rect width="'+Number(BigInt(amount)*300n/max)+'" height="7" rx="3.5" class="bar-fill"/></svg></div>').join("")||empty(m("记录后会在这里呈现","記帳するとここに表示されます","Your spending will appear here"));
}
function txCard(row) {
  const arrow=row.kind==="income"?"↙":row.kind==="transfer"?"⇄":"↗";
  const account=row.kind==="transfer"?(row.account_name||"")+" → "+(row.to_account_name||""):row.account_name||m("备查","メモ","Memo");
  const sign=row.kind==="income"?"+":row.kind==="expense"?"−":"";
  return '<button class="transaction-card" data-action="tx-detail" data-id="'+e(row.id)+'"><span class="transaction-icon kind-'+e(row.kind)+'">'+arrow+'</span><span class="transaction-description"><strong>'+e(row.description)+'</strong><small>'+e(row.category_name||t(row.kind))+' · '+e(account)+'</small><time>'+e(row.occurred_on)+(row.needs_review&&row.needs_review!=="0"?" · "+t("review"):"")+'</time></span><span class="transaction-amount kind-'+e(row.kind)+'">'+sign+money(row.amount_minor,row.currency,row.currency_minor_digits||row.minor_digits)+'</span></button>';
}
function renderMobileTransactions() {
  const node=$("#ledgerList");if(!node)return;
  let rows=(ledgerRangeRows&&($("#historyStart").value||$("#historyEnd").value)?ledgerRangeRows:null)||workspace?.transactions||cachedBootstrap?.transactions||[];
  const query=$("#historySearch").value.trim().toLocaleLowerCase(),start=$("#historyStart").value,end=$("#historyEnd").value;
  rows=rows.filter(row=>(!start||row.occurred_on>=start)&&(!end||row.occurred_on<=end)&&(!query||[row.description,row.account_name,row.to_account_name,row.category_name,row.amount_minor].join(" ").toLocaleLowerCase().includes(query)));
  $("#transactionCount").textContent=rows.length+"";
  node.innerHTML=rows.map(txCard).join("")||empty(t("noTransactions"));
  $(".history-panel .section-heading p").removeAttribute("data-i18n");
  $(".history-panel .section-heading p").textContent=m("按日期、账户或说明查找最近2000条记录","最近2000件を日付・口座・内容で検索","Search the latest 2,000 entries by date, account or description");
}
function renderAssetTabs() {
  $("#assetTabs").innerHTML=[["cash",m("资金账户","資金口座","Cash")],["credit",m("信用卡","カード","Credit")],["fixed",m("固定资产","固定資産","Property")]].map(([id,label])=>b("asset-tab",label,id,"pill "+(assetTab===id?"selected":""))).join("");
  $(".accounts-panel").classList.toggle("hidden",assetTab!=="cash");
  $("#creditPanel").classList.toggle("hidden",assetTab!=="credit");
  $("#fixedPanel").classList.toggle("hidden",assetTab!=="fixed");
}
function renderCredits() {
  const cards=workspace?.cards||[];
  $("#creditPanel").innerHTML='<div class="section-heading"><h2>'+m("信用卡管理","カード管理","Credit cards")+'</h2>'+b("add-card",icon("plus"),"","icon-button")+'</div>'+
    '<p class="fineprint">'+m("欠款为额度差额估算，不代表当月账单。还款仅记录转账，不操作银行。","債務は利用枠の差による目安です。返済は台帳内の振替のみです。","Debt is an estimate from credit availability. Repayments only record ledger transfers.")+'</p>'+
    (cards.map((card,i)=>'<article class="credit-card credit-'+i%3+'"><div class="spread"><h3>'+e(card.name)+'</h3>'+icon("card")+'</div><span>'+m("当前可用额度","利用可能額","Available credit")+'</span><strong>'+ (card.available_minor===null?"—":money(card.available_minor,card.currency,card.minor_digits))+'</strong><div class="credit-details"><span>'+m("总额度","利用限度額","Total limit")+'<b>'+(card.limit_minor===null?"—":money(card.limit_minor,card.currency,card.minor_digits))+'</b></span><span>'+m("欠款估算","債務の目安","Estimated debt")+'<b>'+(card.debt_estimate_minor===null?"—":money(card.debt_estimate_minor,card.currency,card.minor_digits))+'</b></span></div><p>'+m("快照","スナップショット","Snapshot")+' '+e(hiddenAmounts?"••••":card.snapshot_date||"—")+'</p><div class="button-row">'+b("credit-snapshot",m("录入快照","枠を入力","Snapshot"),card.account_id)+b("credit-repay",m("还款","返済","Repay"),card.account_id)+b("credit-history",m("恢复额度快照","枠履歴を復元","Restore snapshot"),card.account_id)+b("credit-plan",m("应还计划","返済予定","Due plan"),card.account_id)+(card.repayment_schedule?b("credit-toggle",card.repayment_schedule.enabled==="1"?m("暂停计划","予定を停止","Pause plan"):m("启用计划","予定を有効化","Enable plan"),card.account_id):"")+'</div></article>').join("")||empty(m("先登记一张信用卡","カードを追加してください","Add your first credit card")));
}
function renderAssets() {
  const balanceRows=workspace?.balanceSheet?.rows||[];
  $("#fixedPanel").innerHTML='<div class="section-heading"><h2>'+m("固定资产","固定資産","Fixed assets")+'</h2>'+b("asset-edit",icon("plus"),"","icon-button")+'</div>'+
    (workspace?.assets||[]).map(asset=>{const row=balanceRows.find(item=>String(item.asset_id)===String(asset.id));const original=row?.original_cost_minor??asset.cost_minor;const depreciation=BigInt(row?.accumulated_depreciation_minor||"0");return '<article class="panel asset-card"><div class="spread"><h3>'+e(asset.name)+'</h3>'+b("asset-edit",m("编辑","編集","Edit"),asset.id,"text-button accent")+'</div><strong class="asset-price">'+money(original,asset.currency)+'</strong><p class="muted asset-depreciation">'+m("累计折旧","累計減価償却","Accumulated depreciation")+' <strong>'+(depreciation>0n?"−":"")+money(depreciation.toString(),asset.currency)+'</strong></p><div class="button-row">'+b("asset-toggle",asset.include_in_balance_sheet==="1"?m("已计入报表","集計対象","Included"):m("未计入报表","集計対象外","Excluded"),asset.id)+b("asset-delete",m("删除","削除","Delete"),asset.id,"button danger-text")+'</div></article>';}).join("");
}
const modules=()=>[
  ["rules","card",m("付款方式与扣款顺序","支払ルールと優先順位","Payment rules"),m("用途匹配，按账户顺序扣款","用途と口座優先順位","Scenarios and account priorities")],
  ["recurring","repeat",m("定期付款与收入","定期支払・収入","Recurring entries"),m("周期、账单币种与到期处理","周期・請求通貨・期日処理","Schedules, currencies and due dates")],
  ["budget","chart",m("预算与储蓄","予算と貯蓄","Budget & savings"),m("本期分配与消费趋势","今期予算と支出推移","Allocation and spending trends")],
  ["reports","chart",m("家庭财务报表","家計レポート","Financial reports"),m("资产负债与15日至14日收支","貸借・15日〜14日の損益","Balance sheet and period activity")],
  ["food","food",m("食材与饮食健康","食材と食生活","Food & wellbeing"),m("采购、食用记录与回顾","購入・食事記録・振り返り","Purchases, meals and reviews")],
  ["backup","cloud",m("备份与多设备恢复","バックアップと復元","Backup & restore"),m("GitHub、Gitee 与本机快照","GitHub・Gitee・ローカル","GitHub, Gitee and local snapshots")],
  ["categories","book",m("记账类别","取引カテゴリ","Categories"),m("收入、支出与三种显示语言","収入・支出・表示名","Income, expense and display names")],
  ["settings","settings",m("设置与 Agent Skill","設定・Agent Skill","Settings & agent skills"),m("API 服务、文本 Skill 与隐私","API・Skillテキスト・プライバシー","API services, text skills and privacy")],
  ["install","plus",m("安装到 iPhone","iPhoneにインストール","Install on iPhone"),m("添加到主屏幕与离线使用","ホーム画面・オフライン","Home Screen and offline access")],
];
function renderMore() {
  const catalog=favoriteCatalog(),saved=getFavorites(),editing=favoritesEditing;
  const favorites='<section class="mobile-favorites"><div class="section-heading"><h2>'+m("常用功能","よく使う機能","Quick access")+'</h2><div class="favorite-tools">'+b("favorites-edit",editing?m("完成","完了","Done"):m("编辑","編集","Edit"),"","text-button accent")+b("favorites-add",icon("plus"),"","icon-button")+'</div></div>'+
    (saved.length?'<div class="favorite-grid">'+saved.map(id=>{const item=catalog.find(row=>row.id===id);return item?'<div class="favorite-item">'+b("favorite",'<span class="module-icon">'+icon(item.icon)+'</span><strong>'+item.title+'</strong>',id,"favorite-tile")+(editing?b("favorite-remove","×",id,"favorite-remove"):'')+'</div>':"";}).join("")+'</div>':'<p class="muted">'+m("点击 + 添加常用功能。","＋から機能を追加できます。","Tap + to add shortcuts.")+'</p>')+
    (editing?'<div class="favorite-picker"><p>'+m("添加常用功能","機能を追加","Add a shortcut")+'</p><div class="favorite-options">'+catalog.filter(item=>!saved.includes(item.id)).map(item=>b("favorite-add",icon(item.icon)+" "+item.title,item.id,"text-button")).join("")+'</div></div>':"")+'</section>';
  $("#moreMenu").innerHTML=favorites+modules().map(([id,ico,title,subtitle])=>'<button class="module-row" data-action="module" data-id="'+id+'"><span class="module-icon">'+icon(ico)+'</span><span><strong>'+title+'</strong><small>'+subtitle+'</small></span>'+icon("arrow")+'</button>').join("");
  $("#moreMenu").classList.toggle("hidden",!!moreTab);
  $("#modulePanel").classList.toggle("hidden",!moreTab||moreTab==="backup"||moreTab==="settings");
  $("#backupPage").classList.toggle("hidden",moreTab!=="backup");
  if(moreTab && !["backup","settings"].includes(moreTab))renderModule(moreTab);
}
function favoriteCatalog(){return [
  {id:"home",icon:"home",title:m("总览","概要","Overview")},
  {id:"entry",icon:"chat",title:m("记账","記帳","Record")},
  {id:"ledger",icon:"book",title:m("账单记录","取引一覧","Ledger")},
  {id:"assets",icon:"wallet",title:m("资产","資産","Assets")},
  ...modules().map(([id,ico,title])=>({id,icon:ico,title}))
];}
function getFavorites(){const key="hh-mobile-favorites:"+(currentUser?.id||"guest");try{const stored=localStorage.getItem(key);const values=stored===null?["ledger","assets","reports"]:JSON.parse(stored);const allowed=new Set(favoriteCatalog().map(item=>item.id));return Array.isArray(values)?[...new Set(values.filter(id=>allowed.has(id)))].slice(0,8):["ledger","assets","reports"];}catch{return ["ledger","assets","reports"];}}
function saveFavorites(values){localStorage.setItem("hh-mobile-favorites:"+(currentUser?.id||"guest"),JSON.stringify(values));}
function openFavorite(id){if(["home","entry","ledger","assets"].includes(id)){navigate(id);return;}navigate("more");if(id==="settings")return editSettings();if(id==="rules")return editRules();moreTab=id;renderMore();}
function moduleHeader(id) {
  const item=modules().find(row=>row[0]===id);
  return '<div class="module-header">'+b("module-back",m("‹ 更多","‹ その他","‹ More"),"","text-button accent")+'<h2>'+e(item?.[2]||"")+'</h2></div>';
}
function renderModule(id) {
  const root=$("#modulePanel"), w=workspace;if(!w){root.innerHTML=moduleHeader(id)+'<div class="panel workspace-error" role="alert"><p>'+e(workspaceError||m("账本尚未载入。","台帳を読み込み中です。","The ledger has not loaded yet."))+'</p>'+b("workspace-retry",m("重试","再試行","Retry"),"","button primary")+'</div>';return;}
  let content=moduleHeader(id);
  if(id==="recurring")content+='<div class="button-row">'+b("recurring-edit",icon("plus")+" "+m("新增规则","予定を追加","New schedule"))+b("run-due",m("处理到期项目","期日を処理","Process due entries"))+'</div>'+
    w.recurring.map(row=>'<article class="panel"><div class="spread"><h3>'+e(row.name)+'</h3><strong>'+money(row.amount_minor,row.currency,row.minor_digits)+'</strong></div><p>'+e(row.account_name)+" · "+e(row.category_name)+'</p><p class="muted">'+e(row.next_due_date)+" · "+e({daily:m("每天","毎日","Daily"),weekly:m("每周","毎週","Weekly"),monthly:m("每月","毎月","Monthly"),yearly:m("每年","毎年","Yearly")}[row.frequency])+'</p><div class="button-row">'+b("recurring-edit",m("编辑","編集","Edit"),row.id)+b("recurring-toggle",row.enabled==="1"?m("暂停","停止","Pause"):m("启用","有効化","Enable"),row.id)+b("recurring-delete",m("删除","削除","Delete"),row.id,"button danger-text")+'</div></article>').join("");
  if(id==="reports") {
    const w=workspace.reports||workspace;
    content+='<label class="field report-date"><span>'+m("报告截至日期","レポート基準日","Report through date")+'</span><input id="reportDate" type="date" value="'+e(reportDate||workspace.date)+'"></label>';
    content+='<section class="panel"><p class="eyebrow">'+e(w.profit.start)+" — "+e(w.profit.through)+'</p><h3>'+m("本期收支","今期の損益","Period activity")+'</h3><div class="metrics-grid">'+metric(t("income"),money(w.profit.jpy_equivalent.income_minor))+metric(t("expense"),money(w.profit.jpy_equivalent.expense_minor))+'</div>'+categoryBars(w.profit.jpy_equivalent.categories)+'</section><section class="panel"><h3>'+m("资产负债表","貸借対照表","Balance sheet")+'</h3>'+
      w.balanceSheet.rows.map(row=>'<div class="report-row"><div><strong>'+e(row.name)+'</strong><small>'+e(row.section)+" · "+e(row.status||"")+'</small></div><b>'+money(row.amount_minor,row.currency)+'</b></div>').join("")+'</section><p class="fineprint">'+m("备查支出单独保留；信用卡负债为额度估算，转账不计作消费。","メモ支出を区別し、カード債務は目安として表示。振替は支出に含みません。","Memo expenses remain distinct. Credit debt is an estimate; transfers are excluded from spending.")+'</p>';
  }
  if(id==="budget") {
    const j=w.profit.jpy_equivalent,total=w.settings.monthly_jpy_budget_minor||"0";
    let plan={};try{plan=JSON.parse(w.settings["savings_plan:"+w.profit.start]||w.settings["savings_plan:monthly_template"]||"{}").items||{};}catch{}
    content+='<div class="button-row">'+b("budget-edit",m("编辑本期预算","今期予算を編集","Edit budget"))+'</div><section class="panel"><div class="metrics-grid">'+metric(m("预算","予算","Budget"),money(total))+metric(m("剩余","残り","Remaining"),money(BigInt(total)-BigInt(j.expense_minor)))+'</div>'+
      Object.entries(plan).map(([name,value])=>'<div class="report-row"><strong>'+e(name)+'</strong><span>'+money(j.categories[name]||0)+" / "+money(value)+'</span></div>').join("")+'</section><section class="panel"><h3>'+m("最近30天 · JPY","直近30日 · JPY","Last 30 days · JPY")+'</h3>'+trendChart()+'</section><p class="fineprint">'+m("人民币支出按交易日参考汇率计入日元报表；原币流水仍独立保存。","人民元は取引日の参考レートで換算し、元通貨明細も保持します。","CNY spending uses its transaction-date reference rate; original-currency entries remain separate.")+'</p>';
  }
  if(id==="food") {
    content+='<div class="button-row">'+b("food-purchase",m("添加采购","購入を追加","Add purchase"))+b("food-eaten",m("记录饮食","食事を記録","Log meal"))+b("food-preference",m("采购计入偏好","購入の計上設定","Purchase preference"))+'</div><section class="panel"><h3>'+m("饮食回顾","食生活の振り返り","Food review")+'</h3><p class="prewrap">'+e(w.foodReview)+'</p></section><h3>'+m("采购食品","購入した食品","Food purchases")+'</h3>'+
      w.food.map(row=>'<div class="panel food-row"><div><strong>'+e(row.item_name)+'</strong><small>'+e(row.purchase_date)+" · "+e(row.quantity_text||"")+" · "+e(w.foodGroups[row.food_group]||row.food_group)+'</small></div>'+b("food-group",m("分类","分類","Group"),row.id,"text-button accent")+b("food-delete",m("删除","削除","Delete"),"purchase:"+row.id,"text-button danger-text")+'</div>').join("")+
      '<h3>'+m("食用记录","食事記録","Meals")+'</h3>'+w.eaten.map(row=>'<div class="panel food-row"><div><strong>'+e(row.item_name)+'</strong><small>'+e(row.consumed_on)+" · "+e(row.meal)+" · "+e(row.quantity_text)+'</small></div>'+b("food-delete",m("删除","削除","Delete"),"eaten:"+row.id,"text-button danger-text")+'</div>').join("");
  }
  if(id==="categories")content+='<div class="button-row">'+b("category-add",icon("plus")+" "+m("添加类别","カテゴリを追加","Add category"))+'</div><section class="panel">'+(cachedBootstrap?.categories||[]).map((row,index)=>'<div class="report-row"><div><strong>'+e(row.display_name)+'</strong><small>'+e(t(row.kind))+" · "+e(row.name)+'</small></div>'+b("category-edit",m("翻译","表示名","Translate"),index,"text-button accent")+'</div>').join("")+'</section>';
  if(id==="install"){
    const cloud=typeof runtimeConfig!=="undefined"&&runtimeConfig?.deploymentMode==="cloud";
    const installHelp=cloud
      ?m("添加后可从主屏幕快速打开。手动账目可离线暂存，重新联网后同步；Agent 和云备份需要网络。","ホーム画面からすぐ開けます。手動記録はオフラインで一時保存でき、再接続後に同期します。Agent とクラウドバックアップには通信が必要です。","Open it quickly from your Home Screen. Manual entries can queue offline and sync when reconnected; Agents and cloud backups need a connection.")
      :m("同 Wi-Fi 测试时，电脑需保持开机并运行服务。离线可暂存手动账目；Agent 和云备份需要连接服务。","同じWi-FiでのテストはPCとサービスの起動が必要です。オフラインでは手動取引を保存できます。","For Wi-Fi testing, keep the computer and service running. Manual entries can be queued offline; Agents and cloud backups need a connection.");
    content+='<section class="panel installation"><div class="install-symbol">'+icon("plus")+'</div><h3>'+m("让记账住进你的主屏幕","ホーム画面に家計簿を","A place on your Home Screen")+'</h3><ol><li>'+m("在 iPhone Safari 打开当前 HTTPS 地址。","iPhoneのSafariでこのHTTPSアドレスを開きます。","Open this HTTPS address in Safari on iPhone.")+'</li><li>'+m("点“分享”，选择“添加到主屏幕”。","共有から「ホーム画面に追加」を選択。","Tap Share, then Add to Home Screen.")+'</li><li>'+m("开启“作为网页 App 打开”（如有），再点“添加”。","表示される場合はWebアプリとして開くを有効にし「追加」。","Enable Open as Web App if shown, then tap Add.")+'</li></ol><p>'+installHelp+'</p><p class="address-display">'+e(location.origin)+'</p>'+(cloud?"":'<a class="button secondary" href="/test-ca.cer">'+m("下载本机测试证书","テスト証明書を取得","Download test certificate")+'</a>')+'</section>';
  }
  root.innerHTML=content;
}
function trendChart() {
  const days={},date=new Date((workspace.date||localDate())+"T12:00:00");
  for(let i=29;i>=0;i--){const d=new Date(date);d.setDate(d.getDate()-i);days[d.toISOString().slice(0,10)]=0n;}
  for(const row of workspace.transactions){if(row.kind!=="expense"||row.balance_effect!=="posted"||!(row.occurred_on in days))continue;const val=row.currency==="JPY"?row.amount_minor:row.jpy_equiv_minor;if(val!==null&&val!==undefined)days[row.occurred_on]+=BigInt(val);}
  const max=Object.values(days).reduce((a,b)=>a>b?a:b,1n);
  return '<svg class="trend-chart" viewBox="0 0 300 110" role="img" aria-label="'+m("每日支出趋势","毎日の支出","Daily spending")+'">'+Object.values(days).map((v,index)=>{const height=hiddenAmounts?8:Number(v*90n/max);return '<rect x="'+(index*10+1)+'" y="'+(100-height)+'" width="7" height="'+Math.max(2,height)+'" rx="3"/>';}).join("")+'</svg>';
}

function renderCloud() {
  const cfg=workspace?.preferences;if(!cfg){$("#cloudControls").innerHTML=moduleHeader("backup")+'<div class="panel workspace-error" role="alert"><p>'+e(workspaceError||m("账本尚未载入。","台帳を読み込み中です。","The ledger has not loaded yet."))+'</p>'+b("workspace-retry",m("重试","再試行","Retry"),"","button primary")+'</div>';return;}
  const selected=backupDraft||cfg;
  const scopes={settings:m("设置与自定义 Skill","設定・カスタムSkill","Settings & skills"),bills:m("账单与小票","取引・レシート","Entries & receipts"),payment_methods:m("付款方式","支払ルール","Payment rules"),recurring_payments:m("定期付款","定期支払","Recurring entries"),bank_accounts:m("银行与资金账户","銀行・資金口座","Cash accounts"),credit_cards:m("信用卡","カード","Credit cards"),assets:m("资产管理","固定資産","Assets")};
  $("#cloudControls").innerHTML=moduleHeader("backup")+
    '<section class="panel"><div class="section-heading"><h3>'+m("备份范围","バックアップ範囲","Backup scope")+'</h3>'+b("scope-all",m("全选 / 取消全选","全選択 / 解除","Select / clear all"),"","text-button accent")+'</div><form id="scopeForm"><div class="scope-grid">'+Object.entries(scopes).map(([key,name])=>'<label class="check-row"><input type="checkbox" name="'+key+'" '+(selected.scope[key]?"checked":"")+'><span>'+name+'</span></label>').join("")+'</div><label class="check-row"><input type="checkbox" name="autoSync" '+(selected.autoSync?"checked":"")+'><span>'+m("记账后自动云备份","記帳後に自動バックアップ","Back up after recording")+'</span></label><button class="button primary" type="submit">'+m("应用备份设置","設定を適用","Apply backup settings")+'</button>'+b("scope-cancel",t("cancel"))+ '</form><p class="fineprint">'+m("API 密钥与 GitHub/Gitee 授权不包含在备份中。恢复会替换账本，恢复前自动保留完整副本。","APIキーやGitHub/Gitee認証は含めません。復元前に現在の完全コピーを保存します。","API keys and GitHub/Gitee authorization are excluded. Restoring replaces the ledger after making a full safety copy.")+'</p></section>'+
    ["github","gitee"].map(provider=>{const cloud=cfg.cloud[provider]||{};return '<section class="panel cloud-card"><div class="spread"><h3>'+provider.toUpperCase()+'</h3><span class="status-dot '+(cloud.connected?"connected":"")+'">'+(cloud.connected?m("已连接","接続済み","Connected"):m("未连接","未接続","Not connected"))+'</span></div><p class="muted">'+e(cloud.repository||m("使用你自己账号下的独立私有仓库","自分のアカウントの非公開リポジトリ","A private repository in your own account"))+'</p><div class="button-row">'+b("cloud-connect",m("连接 / 重新授权","接続・再認証","Connect / authorize"),provider)+(cloud.connected?b("cloud-upload",m("上传备份","アップロード","Upload"),provider)+b("cloud-restore",m("从云端恢复","復元","Restore"),provider)+b("cloud-disconnect",m("断开","切断","Disconnect"),provider,"button danger-text"):"")+'</div></section>';}).join("")+
    '<p class="fineprint">'+e(cfg.autoStatus)+'</p><section class="panel"><div class="section-heading"><h3>'+m("本机备份历史","ローカル履歴","Local backup history")+'</h3>'+b("backup",icon("plus"))+'</div>'+
    (workspace.backups||[]).map(row=>'<div class="backup-row"><div><strong>'+e(row.name)+'</strong><small>'+e(new Date(row.date).toLocaleString())+" · "+Math.ceil(Number(row.size)/1024)+" KB"+'</small></div><a class="text-button accent" href="/api/backup?name='+encodeURIComponent(row.name)+'">'+m("下载","保存","Download")+'</a>'+b("local-restore",m("恢复","復元","Restore"),row.name,"text-button")+'</div>').join("")+
    '<label class="button secondary file-button">'+m("导入完整备份包","バックアップを取り込む","Restore a backup file")+'<input id="bundleFile" type="file" accept=".zip,application/zip"></label></section>'+
    '<section class="panel"><h3>'+m("小票图片","レシート画像","Receipt images")+'</h3><div class="receipt-grid">'+(workspace.receipts||[]).slice(-24).map(name=>'<a href="/api/receipt?name='+encodeURIComponent(name)+'" target="_blank" rel="noopener"><img loading="lazy" src="/api/receipt?name='+encodeURIComponent(name)+'" alt="'+m("已保存小票","保存済みレシート","Saved receipt")+'"></a>').join("")+'</div></section>';
  $("#scopeForm").onsubmit=async event=>{event.preventDefault();const form=new FormData(event.currentTarget);const draft=deepCopy(cfg);for(const key in scopes)draft.scope[key]=form.has(key);draft.autoSync=form.has("autoSync");await guarded(async()=>{await runAction("settings",draft);backupDraft=null;renderCloud();});};
  $("#scopeForm").onchange=()=>{const form=new FormData($("#scopeForm"));backupDraft={scope:Object.fromEntries(Object.keys(scopes).map(key=>[key,form.has(key)])),autoSync:form.has("autoSync")};};
  $("#bundleFile").onchange=event=>guarded(()=>restoreFile(event.target.files?.[0]));
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
  $("#editorBody").innerHTML=(options.note?'<p class="fineprint">'+e(options.note)+'</p>':"")+fields.map(item=>{
    const id="edit-"+item.name;
    let control;
    if(item.type==="select")control='<select id="'+id+'" name="'+item.name+'" '+(item.optional?"":"required")+'>'+item.options.map(option=>'<option value="'+e(option[0])+'" '+(String(option[0])===String(item.value)?"selected":"")+'>'+e(option[1])+'</option>').join("")+'</select>';
    else if(item.type==="textarea")control='<textarea id="'+id+'" name="'+item.name+'" rows="'+(item.rows||5)+'" '+(item.optional?"":"required")+'>'+e(item.value)+'</textarea>';
    else if(item.type==="checkbox")control='<input id="'+id+'" name="'+item.name+'" type="checkbox" '+(item.value?"checked":"")+'>';
    else control='<input id="'+id+'" name="'+item.name+'" type="'+(["decimal","integer"].includes(item.type)?"text":item.type)+'" '+(item.type==="decimal"?'inputmode="decimal"':item.type==="integer"?'inputmode="numeric"':"")+' value="'+e(item.value)+'" '+(item.optional?"":"required")+' '+(item.type==="password"?'autocomplete="new-password"':"")+'>';
    return '<label class="'+(item.type==="checkbox"?"check-row":"field")+'"><span>'+e(item.label)+'</span>'+control+'</label>';
  }).join("");
  const dialog=$("#editorDialog"); if(!dialog.open)dialog.showModal();
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
async function confirmOnce(target,impact) {
  return confirm(target+"\n\n"+impact);
}
async function runAction(action,data={},progress=null,refresh=true) {
  if(!navigator.onLine||!serverReachable)throw new Error(m("此操作需要连接服务；内容还在当前编辑页。","この操作にはサービスへの接続が必要です。入力は編集画面に残っています。","This action needs a connection. Your input remains in the editor."));
  const owner=currentUser?.id;if(!owner)throw new Error(t("login"));
  const opId=crypto.randomUUID();
  let job=await api("/api/action",{method:"POST",body:JSON.stringify({action,data,opId})});
  if(currentUser?.id!==owner)throw new Error(t("logout"));
  localStorage.setItem("hh-active-job:"+owner,job.id);activeJob=job.id;
  if(action==="agent")renderAgent();
  while(job.state==="running"){
    if(progress)progress(job);
    await sleepMobile(1000);
    if(currentUser?.id!==owner)throw new Error(t("logout"));
    try{job=await api("/api/job?id="+encodeURIComponent(job.id));}catch(error){activeJob="";renderAgent();throw error;}
  }
  if(currentUser?.id!==owner)throw new Error(t("logout"));
  localStorage.removeItem("hh-active-job:"+owner);activeJob="";
  if(job.state!=="done")throw new Error(localizeServerError(job.result?.error||job.message||m("操作未完成","操作未完了","Action did not complete")));
  if(job.cloudSnapshotSaved===false)showToast(m("操作已完成，但云端快照未能保存。请保持服务运行并稍后重试备份。","操作は完了しましたが、クラウドスナップショットを保存できませんでした。サービスを終了せず、後でバックアップを再試行してください。","The action completed, but its cloud snapshot was not saved. Keep the service running and retry the backup later."),true);
  if(refresh){await fetchBootstrap();await loadWorkspace(true);if($("#historyStart").value||$("#historyEnd").value)await loadLedgerRange();}
  return job.result;
}
async function resumeJob() {
  const owner=currentUser?.id;if(!owner||jobRecoveryOwner===owner||activeJob)return;
  const id=localStorage.getItem("hh-active-job:"+owner);if(!id)return;
  jobRecoveryOwner=owner;
  try{let job=await api("/api/job?id="+encodeURIComponent(id));while(job.state==="running"){showDeviceChallenge(job);await sleepMobile(1500);if(currentUser?.id!==owner)return;job=await api("/api/job?id="+encodeURIComponent(id));}localStorage.removeItem("hh-active-job:"+owner);if(job.state==="done"){if(job.result?.answer){const agent=job.result.agent||"bookkeeping";chats[agent].push({role:"assistant",text:job.result.answer});await cacheSet("chat:"+owner+":"+agent,chats[agent]);renderAgent();}await fetchBootstrap();await loadWorkspace(true);showToast(m("后台操作已完成","バックグラウンド処理が完了しました","Background action completed"));}else showToast(job.result?.error||job.message,true);}
  catch{}finally{jobRecoveryOwner="";}
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
  try{await api("/api/restore-bundle",{method:"POST",body:file,headers:{"Content-Type":"application/zip","X-Confirm-Restore":"confirmed-once"}});await fetchBootstrap();await loadWorkspace(true);showToast(m("已恢复","復元しました","Restored"));}catch(error){showToast(error.message,true);}
}

function renderAgent() {
  const root=$("#agentPanel");if(!root)return;
  const pending=activeJob?'<span class="loading-pulse">'+m("处理中…","処理中…","Working…")+'</span>':m("自然地说，认真地记","いつもの言葉で、ていねいに","Your words. A clear record.");
  root.innerHTML='<div class="mode-pills">'+b("agent-switch",m("记账助手","記帳アシスタント","Ledger assistant"),"bookkeeping","pill "+(chatAgent==="bookkeeping"?"selected":""))+b("agent-switch",m("饮食健康","食生活","Food & wellbeing"),"food_health","pill "+(chatAgent==="food_health"?"selected":""))+'</div><div class="chat-caption">'+pending+b("agent-reset",m("新对话","新しい会話","New chat"),"","text-button")+'</div><div id="chatMessages" class="chat-messages" aria-live="polite"></div><form id="chatForm" class="chat-composer"><div id="chatImages" class="chat-images"></div><textarea id="chatInput" rows="3" maxlength="24000" placeholder="'+m(chatAgent==="bookkeeping"?"例如：午饭980日元":"问问最近的饮食，或记录今天吃了什么",chatAgent==="bookkeeping"?"例：昼食980円":"最近の食生活について聞いてみましょう",chatAgent==="bookkeeping"?"For example: lunch 980 yen":"Ask about your recent meals")+'" aria-label="'+m("消息","メッセージ","Message")+'"></textarea><div class="composer-tools"><label class="icon-button" aria-label="'+m("添加图片","画像を追加","Add image")+'">'+icon("photo")+'<input id="chatImageInput" type="file" accept="image/jpeg,image/png,image/webp" multiple></label><span class="muted">'+m("文字与小票都可以","テキストもレシートも","Words or receipts")+'</span>'+(activeJob?b("agent-cancel",m("中断","中断","Stop"),"","button secondary"):'<button type="submit" class="send-circle" aria-label="'+m("发送","送信","Send")+'">↑</button>')+'</div></form>';
  const messages=chats[chatAgent];
  $("#chatMessages").innerHTML=messages.length?messages.map(item=>'<article class="bubble '+item.role+'"><span class="bubble-label">'+(item.role==="user"?m("你","あなた","You"):m("助手","アシスタント","Assistant"))+'</span><p>'+e(item.text)+'</p></article>').join(""):'<div class="chat-welcome"><span class="assistant-orb">'+icon(chatAgent==="bookkeeping"?"chat":"food")+'</span><h2>'+m("让生活，清楚一点","暮らしを、少しクリアに","A clearer picture of everyday life")+'</h2><p>'+m("告诉我一笔收支，或拍下小票。信息不足时先确认，记录成功后再备份。","収支を伝えるか、レシートを撮影してください。不明点は確認してから記帳します。","Tell me about an entry, or photograph a receipt. Unclear details are checked before recording.")+'</p></div>';
  renderAttachments();
  $("#chatForm").onsubmit=sendAgent;
  $("#chatImageInput").onchange=async event=>{await guarded(()=>attachImages([...event.target.files]));event.target.value="";};
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
      const scale=Math.min(1,2560/Math.max(image.width,image.height));const canvas=document.createElement("canvas");canvas.width=Math.round(image.width*scale);canvas.height=Math.round(image.height*scale);const context=canvas.getContext("2d");context.fillStyle="#fff";context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(image,0,0,canvas.width,canvas.height);
      const data=canvas.toDataURL("image/jpeg",0.94).split(",")[1];if(currentUser?.id!==owner)return;attachments.push({name:file.name,type:"image/jpeg",data});
    }finally{URL.revokeObjectURL(url);}
  }
  renderAttachments();
}
async function sendAgent(event) {
  event.preventDefault();if(activeJob)return;
  const text=$("#chatInput").value.trim();if(!text&&!attachments.length)return;
  const owner=currentUser?.id,agent=chatAgent,images=attachments.map(image=>({...image}));
  chats[agent].push({role:"user",text:text+(images.length?"\n"+m("附图","画像","Images")+": "+images.length:"")});
  $("#chatInput").value="";attachments=[];renderAgent();
  try{
    const result=await runAction("agent",{agent,text,images,language:currentLanguage},null,true);
    if(currentUser?.id!==owner)return;
    chats[agent].push({role:"assistant",text:result.answer});
    await cacheSet("chat:"+currentUser.id+":"+agent,chats[agent]);
  }catch(error){if(currentUser?.id===owner){chats[agent].push({role:"assistant",text:error.message});if(images.length)attachments=images;}}
  finally{if(currentUser?.id===owner)renderAgent();}
}

function appearanceSettingsHtml(mode) {
  const choices = [["system",m("跟随系统","システム設定に従う","Follow system")],
    ["light",m("浅色模式","ライトモード","Light mode")],
    ["dark",m("深色模式","ダークモード","Dark mode")]];
  return '<section class="profile-editor"><h3>'+m("外观","外観","Appearance")+'</h3><label class="field"><span>'+
    m("明暗模式","表示モード","Color mode")+'</span><select id="settings-appearance">'+
    choices.map(([value,label])=>'<option value="'+value+'" '+(mode===value?'selected':'')+'>'+label+'</option>').join('')+
    '</select></label><p class="fineprint">'+m("只影响当前设备。跟随系统会自动切换，点击应用或确认后保存。",
      "この端末のみに適用。システムの外観に自動で追従します。「適用」または「確定」で保存します。",
      "Applies to this device. Follow system changes automatically. Apply or Done saves your choice.")+'</p></section>';
}

async function editSettings() {
  if(!workspace)throw new Error(t("offline"));
  settingsDraft=deepCopy(workspace.preferences);
  const cfg=settingsDraft;
  const skillWarning=agent=>cfg.skillErrors?.[agent]?'<p role="alert" class="fineprint">'+m("此 Agent 的 Skill 无法读取。请恢复默认文本或粘贴有效内容后保存；账本仍可正常查看。","このAgentのSkillを読み込めません。初期値を復元するか内容を貼り付けて保存してください。台帳は引き続き表示できます。","This agent's skill cannot be read. Restore the default text or paste valid content and save. The ledger remains available.")+'</p>':"";
  const cloudRuntime=typeof runtimeConfig!=="undefined"&&runtimeConfig?.deploymentMode==="cloud";
  let appearanceDraft=window.HouseholdAppearance.mode;
  const render=()=>{
    $("#editorTitle").textContent=m("设置与 Skill","設定とSkill","Settings & skills");
    $("#editorCancel").textContent=m("‹ 返回更多","‹ その他へ戻る","‹ Back to More");$("#editorSave").textContent=m("确认","確定","Done");
    $("#editorBody").innerHTML='<p class="fineprint">'+m("编辑内容不会自动保存。点应用保留当前页，点确认保存并关闭；取消撤回尚未应用的修改。","変更は自動保存されません。「適用」で保存し画面を維持、「確定」で保存して閉じます。","Changes are not saved automatically. Apply saves and stays here; Done saves and closes. Cancel discards unapplied changes.")+'</p>'+appearanceSettingsHtml(appearanceDraft)+'<div class="section-heading"><h3>'+m("API 服务","APIサービス","API services")+'</h3>'+b("profile-add",icon("plus"))+'</div><div id="profileList">'+cfg.profiles.map((p,index)=>'<section class="profile-editor" data-profile-index="'+index+'"><div class="spread"><strong>'+m("服务","サービス","Service")+' '+(index+1)+'</strong>'+b("profile-remove",m("删除","削除","Remove"),index,"text-button danger-text")+'</div>'+[
        ["name",m("名称","名前","Name"),"text"],["api_url",m("接口完整地址","エンドポイントURL","Full endpoint URL"),"url"],["model",m("模型标识","モデルID","Model ID"),"text"],["api_key",m("API 密钥（留空保留已保存密钥）","APIキー（空欄で既存を保持）","API key (blank keeps saved key)"),"password"]
      ].map(([key,label,type])=>'<label class="field"><span>'+label+'</span><input type="'+type+'" data-profile-key="'+key+'" value="'+e(p[key]||"")+'" '+(key==="api_key"?'autocomplete="new-password"':'required')+'></label>').join("")+
      '<label class="check-row"><input type="checkbox" data-profile-key="thinking_enabled" '+(p.thinking_enabled?"checked":"")+'><span>'+m("思考模式（支持的服务）","思考モード（対応API）","Thinking mode (supported providers)")+'</span></label><label class="field"><span>'+m("思考强度","思考強度","Reasoning effort")+'</span><select data-profile-key="reasoning_effort">'+["low","high","max"].map(value=>'<option '+(p.reasoning_effort===value?"selected":"")+'>'+value+'</option>').join("")+'</select></label></section>').join("")+'</div>'+
      ["bookkeeping","food_health"].map(agent=>'<section class="skill-editor"><h3>'+ (agent==="bookkeeping"?m("记账 Agent","記帳Agent","Ledger agent"):m("饮食健康 Agent","食生活Agent","Food agent"))+'</h3>'+["agents","visionAgents"].map(group=>'<label class="field"><span>'+ (group==="agents"?m("文字服务","テキスト用","Text service"):m("图片服务","画像用","Image service"))+'</span><select data-agent="'+agent+'" data-group="'+group+'"><option value="">'+m("请选择","選択してください","Choose a service")+'</option>'+cfg.profiles.map(p=>'<option value="'+e(p.id)+'" '+(cfg[group][agent]===p.id?"selected":"")+'>'+e(p.name)+'</option>').join("")+'</select></label>').join("")+
      skillWarning(agent)+'<div class="spread"><label for="skill-'+agent+'">'+m("Skill 文本 · 复制粘贴后编辑","Skillテキスト・貼り付けて編集","Skill text · paste and edit")+'</label>'+b("skill-default",m("恢复默认","初期値に戻す","Restore default"),agent,"text-button accent")+'</div><textarea id="skill-'+agent+'" class="skill-text" data-skill="'+agent+'" spellcheck="false" rows="12">'+e(cfg.skills[agent]||"")+'</textarea><p class="fineprint">'+m("此文本会随该 Agent 的请求发送给你选择的模型服务。","このテキストは選択したモデルへのリクエストに含まれます。","This text is included in requests to the model service you select.")+'</p></section>').join("")+
      (cloudRuntime?"":'<label class="check-row"><input id="settings-save-images" type="checkbox" '+(cfg.saveImages?"checked":"")+'><span>'+m("保存记账小票图片","記帳画像を保存","Save receipt images")+'</span></label>');
    $("#editorFooter").innerHTML=b("settings-apply",m("应用","適用","Apply"),"","button primary");
  };
  const capture=()=>{
    $$(".profile-editor").forEach(node=>{const p=cfg.profiles[Number(node.dataset.profileIndex)];$$("[data-profile-key]",node).forEach(input=>p[input.dataset.profileKey]=input.type==="checkbox"?input.checked:input.value);});
    $$("[data-agent]").forEach(input=>cfg[input.dataset.group][input.dataset.agent]=input.value);
    $$("[data-skill]").forEach(input=>{
      const agent=input.dataset.skill;
      if(cfg.skillErrors?.[agent]&&!input.value.trim())delete cfg.skills[agent];
      else cfg.skills[agent]=input.value;
    });
    const imageSaveToggle=$("#settings-save-images");if(imageSaveToggle)cfg.saveImages=imageSaveToggle.checked;
    appearanceDraft=$("#settings-appearance").value;
  };
  render();$("#editorDialog").showModal();
  $("#editorForm").oninput=capture;
  $("#editorForm").onchange=capture;
  $("#editorForm").onsubmit=async event=>{event.preventDefault();capture();await guarded(async()=>{await runAction("settings",cfg);window.HouseholdAppearance.save(appearanceDraft);$("#editorDialog").close();});};
  $("#editorBody").onclick=async event=>{
    const button=event.target.closest("[data-action]");if(!button)return;event.stopPropagation();capture();
    if(button.dataset.action==="profile-add"){cfg.profiles.push({id:crypto.randomUUID(),name:"",api_url:"https://",model:"",api_key:"",thinking_enabled:false,reasoning_effort:"low"});render();}
    if(button.dataset.action==="profile-remove"){const index=Number(button.dataset.id);if(await confirmOnce(m("删除 API 服务：","APIサービスを削除：","Remove API service: ")+cfg.profiles[index].name,m("保存设置后生效，使用它的 Agent 需要重新选择服务。","設定保存後に反映され、Agentのサービスを再選択する必要があります。","Takes effect when settings are saved. Reassign agents using this service."))){const id=cfg.profiles[index].id;cfg.profiles.splice(index,1);for(const group of ["agents","visionAgents"])for(const agent in cfg[group])if(cfg[group][agent]===id)cfg[group][agent]="";render();}}
    if(button.dataset.action==="skill-default"){const defaults=await api("/api/default-skills");cfg.skills[button.dataset.id]=defaults[button.dataset.id];render();}
  };
  $("#editorFooter").onclick=async event=>{if(event.target.closest("[data-action=settings-apply]")){capture();await guarded(async()=>{await runAction("settings",cfg);window.HouseholdAppearance.save(appearanceDraft);showToast(m("设置已应用","適用しました","Settings applied"));});}};
  $("#editorDialog").addEventListener("close",()=>{$("#editorForm").oninput=null;$("#editorForm").onchange=null;$("#editorBody").onclick=null;$("#editorFooter").onclick=null;settingsDraft=null;},{once:true});
}

async function editRules() {
  const cfg=workspace.preferences,rules=deepCopy(cfg.paymentRules),accounts=fieldsAccount();
  const render=()=>{
    $("#editorTitle").textContent=m("付款方式与扣款顺序","支払ルールと優先順位","Payment rules");
    $("#editorSave").textContent=m("保存","保存","Save");$("#editorCancel").textContent=m("‹ 返回更多","‹ その他へ戻る","‹ Back to More");$("#editorFooter").replaceChildren();
    $("#editorBody").innerHTML='<p class="fineprint">'+m("用途决定何时使用；扣款顺序决定先用哪个账户。同一规则只使用同币种账户，积分可加入日元顺序。","用途が適用場面を決め、口座順が引落優先順位を決めます。同一通貨のみ使用します。","The purpose matches a scenario; the ordered accounts determine funding. Keep one currency per rule; points may join JPY orders.")+'</p>'+rules.map((rule,index)=>'<section class="rule-editor" data-rule="'+index+'"><div class="spread"><strong>'+m("规则","ルール","Rule")+' '+(index+1)+'</strong>'+b("rule-remove",m("删除","削除","Remove"),index,"text-button danger-text")+'</div><label class="field"><span>'+m("支付账户","支払口座","Payment account")+'</span><select data-rule-key="payment_method">'+accounts.map(([name,label])=>'<option value="'+e(name)+'" '+(rule.payment_method===name?"selected":"")+'>'+e(label)+'</option>').join("")+'</select></label><label class="field"><span>'+t("currency")+'</span><select data-rule-key="currency">'+[["",m("不限","指定なし","Any")],["JPY","JPY"],["CNY","CNY"]].map(([value,label])=>'<option value="'+value+'" '+(rule.currency===value?"selected":"")+'>'+label+'</option>').join("")+'</select></label><label class="field"><span>'+m("用途提示","適用する用途","Purpose / scenario")+'</span><textarea data-rule-key="purpose" rows="3">'+e(rule.purpose)+'</textarea></label><p class="fineprint">'+m("从上到下依次扣款","上から順に引き落とし","Funding priority, top to bottom")+'</p><div class="funding-order">'+(rule.account_order||[rule.payment_method]).map((name,position)=>'<div class="order-row"><span>'+(position+1)+'</span><select data-order="'+position+'">'+(cachedBootstrap.accounts||[]).map(a=>'<option value="'+e(a.name)+'" '+(a.name===name?"selected":"")+'>'+e(a.name)+" · "+e(a.currency)+'</option>').join("")+'</select>'+b("order-up","↑",index+":"+position,"icon-button")+b("order-down","↓",index+":"+position,"icon-button")+b("order-remove","×",index+":"+position,"icon-button")+'</div>').join("")+'</div>'+b("order-add",m("添加扣款来源","引落元を追加","Add funding source"),index)+'</section>').join("")+b("rule-add",icon("plus")+" "+m("添加规则","ルールを追加","Add rule"));
  };
  const capture=()=>{
    $$("[data-rule]").forEach(node=>{const rule=rules[Number(node.dataset.rule)];$$("[data-rule-key]",node).forEach(input=>rule[input.dataset.ruleKey]=input.value);rule.account_order=$$("[data-order]",node).map(input=>input.value);});
  };
  render();$("#editorDialog").showModal();
  $("#editorForm").onsubmit=async event=>{event.preventDefault();capture();await guarded(async()=>{await runAction("payment_rules",{profiles:rules,revision:cfg.paymentRevision});$("#editorDialog").close();});};
  $("#editorBody").onclick=async event=>{
    const button=event.target.closest("[data-action]");if(!button)return;event.stopPropagation();capture();const action=button.dataset.action;
    const [i,j]=button.dataset.id.split(":").map(Number);
    if(action==="rule-add"){if(!accounts.length){showToast(t("needsAccount"),true);return;}rules.push({payment_method:accounts[0][0],purpose:"",currency:"",account_order:[accounts[0][0]]});}
    if(action==="rule-remove"){if(!await confirmOnce(m("删除规则","ルールを削除","Remove rule")+" "+(i+1),m("保存后不再自动匹配此用途。","保存後、この用途を自動適用しません。","After saving, this scenario will no longer match.")))return;rules.splice(i,1);}
    if(action==="order-add"){const used=rules[i].account_order;const candidate=cachedBootstrap.accounts.find(a=>!used.includes(a.name));if(candidate)used.push(candidate.name);}
    if(action==="order-remove"){if(!await confirmOnce(m("移除扣款来源：","引落元を削除：","Remove funding source: ")+rules[i].account_order[j],m("保存后不再从此项扣款。","保存後、この項目から引き落としません。","This source will no longer be used after saving.")))return;rules[i].account_order.splice(j,1);}
    if(action==="order-up"&&j>0)[rules[i].account_order[j-1],rules[i].account_order[j]]=[rules[i].account_order[j],rules[i].account_order[j-1]];
    if(action==="order-down"&&j<rules[i].account_order.length-1)[rules[i].account_order[j+1],rules[i].account_order[j]]=[rules[i].account_order[j],rules[i].account_order[j+1]];
    render();
  };
  $("#editorDialog").addEventListener("close",()=>$("#editorBody").onclick=null,{once:true});
}

async function handleMobileClick(event) {
  const button=event.target.closest("[data-action]");if(!button)return;
  // Specialized editors own their internal draft controls.
  if(button.closest("#editorBody")&&$("#editorBody").onclick)return;
  const action=button.dataset.action,id=button.dataset.id;
  await guarded(async()=>{
    if(action==="page")return navigate(id);
    if(action==="privacy"){hiddenAmounts=!hiddenAmounts;localStorage.setItem("hh-hide-amounts",hiddenAmounts?"1":"0");renderMobile();await renderAccounts();return;}
    if(action==="refresh"){await syncQueue();await fetchBootstrap();return loadWorkspace(true);}
    if(action==="workspace-retry"){workspaceError="";renderMobile();return loadWorkspace(true);}
    if(action==="asset-tab"){assetTab=id;renderAssetTabs();return;}
    if(action==="module-back"){moreTab="";renderMore();return;}
    if(action==="favorites-edit"){favoritesEditing=!favoritesEditing;renderMore();return;}
    if(action==="favorites-add"){favoritesEditing=true;renderMore();document.querySelector(".favorite-picker")?.scrollIntoView({behavior:"smooth",block:"nearest"});return;}
    if(action==="favorite-remove"){saveFavorites(getFavorites().filter(item=>item!==id));showToast(m("已移除常用功能","ショートカットを削除しました","Shortcut removed"));renderMore();return;}
    if(action==="favorite-add"){const values=getFavorites();if(!values.includes(id)&&values.length<8){values.push(id);saveFavorites(values);showToast(m("已添加常用功能","ショートカットを追加しました","Shortcut added"));}else if(values.length>=8)showToast(m("最多添加 8 个常用功能","ショートカットは8件までです","You can add up to 8 shortcuts"),true);favoritesEditing=false;renderMore();return;}
    if(action==="favorite")return openFavorite(id);
    if(action==="module"){navigate("more");if(id==="settings")return editSettings();if(id==="rules")return editRules();moreTab=id;renderMore();return;}
    if(action==="add-card"){navigate("assets");assetTab="cash";renderAssetTabs();$("#accountForm").classList.remove("hidden");$("#accountForm [name=type]").value="credit";$("#accountForm [name=name]").focus();return;}
    if(action==="backup"){await runAction("backup");showToast(m("备份已创建","バックアップを作成しました","Backup created"));return;}
    if(action==="scope-cancel"){backupDraft=null;renderCloud();return;}
    if(action==="scope-all"){const inputs=$$("#scopeForm .scope-grid input");const all=inputs.every(input=>input.checked);inputs.forEach(input=>input.checked=!all);$("#scopeForm").onchange();return;}
    if(action==="cloud-connect"){
      if(id==="github"){await runAction("github_auth",{provider:"github"},showDeviceChallenge);$("#deviceDialog").close();const message=await pullCloudOnLogin();if(message)showToast(message);await loadWorkspace(true);return;}
      return openForm("Gitee",[field("token",m("私人令牌 · user_info 与 projects 权限","個人トークン・user_infoとprojects権限","Personal token · user_info and projects"),"password"),field("repositoryName",m("私有仓库名称","非公開リポジトリ名","Private repository name"),"text",workspace.preferences.cloud.gitee?.repositoryName||"household-bookkeeping-data")],data=>runAction("cloud_connect",{...data,provider:"gitee"}));
    }
    if(["cloud-upload","cloud-restore","cloud-disconnect","local-restore"].includes(action)){
      if((await outboxAll()).length)throw new Error(m("请先完成待同步记录","先に未同期記録を同期してください","Sync pending entries first"));
      const target=action==="local-restore"?id:id.toUpperCase();
      if(!await confirmOnce(button.textContent+" · "+target,m("上传可能替换云端快照；恢复会替换当前账本并先保留完整备份。断开连接只撤销本软件保存的授权。","アップロードはクラウドを置換、復元は台帳を置換します。先に完全コピーを保存します。切断は保存済み認証を解除します。","Uploads may replace the cloud snapshot. Restore replaces this ledger after a full safety copy. Disconnect removes the stored authorization.")))return;
      const map={"cloud-upload":"cloud_upload","cloud-restore":"cloud_restore","cloud-disconnect":"cloud_disconnect","local-restore":"restore_local"};
      return runAction(map[action],{provider:id,name:id,confirmed:true});
    }
    if(action==="agent-switch"){if(activeJob)throw new Error(m("请等待当前请求完成","現在の処理をお待ちください","Wait for the current request"));chatAgent=id;attachments=[];const saved=await cacheGet("chat:"+currentUser.id+":"+chatAgent);if(saved)chats[chatAgent]=saved;renderAgent();return;}
    if(action==="agent-reset"){if(activeJob)return;if(!await confirmOnce(m("清空当前对话","会話を消去","Clear this conversation"),m("未完成的草稿和聊天显示会清除，已入账记录保留。","未確定下書きと会話を消去します。記帳済み取引は保持します。","Pending drafts and displayed chat will clear. Posted entries remain.")))return;await runAction("agent_reset",{agent:chatAgent});chats[chatAgent]=[];await cacheSet("chat:"+currentUser.id+":"+chatAgent,[]);renderAgent();return;}
    if(action==="agent-cancel"){await api("/api/cancel-job",{method:"POST",body:JSON.stringify({id:activeJob})});showToast(m("正在中断","中断中","Stopping…"));return;}
    if(action==="image-remove"){if(await confirmOnce(m("移除这张待发送图片","送信前の画像を削除","Remove this pending image"),m("该图片将不会发送。","この画像は送信されません。","This image will not be sent."))){attachments.splice(Number(id),1);renderAttachments();}return;}
    const dateField=()=>field("date",t("date"),"date",workspace.date);
    const accountField=(name="account",type="all",value="")=>field(name,t("account"),"select",value,fieldsAccount(type));
    const amountField=(name="amount",label=t("amount"),value="")=>field(name,label,"decimal",value);
    const card=workspace.cards.find(row=>row.account_id===id);
    if(action==="credit-toggle")return runAction("credit_plan_toggle",{card:card.name,enabled:card.repayment_schedule.enabled!=="1"});
    if(action==="credit-snapshot")return openForm(m("录入额度快照","利用枠を記録","Credit snapshot")+" · "+card.name,[field("account",t("account"),"select",card.name,[[card.name,card.name]]),dateField(),amountField("limit",m("总额度","利用限度額","Total limit"),card.limit_minor?plainAmount(card.limit_minor,card.minor_digits):""),amountField("available",m("当前可用额度","利用可能額","Available credit"),card.available_minor?plainAmount(card.available_minor,card.minor_digits):""),{...field("note",m("备注","メモ","Note")),optional:true}],data=>runAction("credit_snapshot",data));
    if(action==="credit-repay"||action==="credit-plan")return openForm(action==="credit-repay"?m("记录还款","返済を記録","Record repayment"):m("每月应还计划","毎月の返済予定","Monthly repayment plan"),[field("card",m("信用卡","カード","Credit card"),"select",card.name,[[card.name,card.name]]),accountField("source","cash",card.repayment_schedule?.source_name),{...dateField(),value:action==="credit-plan"?(card.repayment_schedule?.next_due_date||workspace.date):workspace.date},{...amountField(),optional:action==="credit-plan"}],data=>runAction(action==="credit-repay"?"credit_repay":"credit_plan",data),{note:action==="credit-plan"?m("本期金额每月重填，空白不记账。只记录本地转账，不实际扣款。","当月金額は毎月入力。空欄なら記帳しません。実際の銀行引落は行いません。","Enter this period's amount each month. Blank amounts are not posted. No actual bank debit occurs."):""});
    if(action==="credit-history"){
      const history=workspace.creditHistory[id]||{};$("#editorTitle").textContent=card.name;$("#editorCancel").textContent=m("关闭","閉じる","Close");$("#editorSave").classList.add("hidden");$("#editorFooter").replaceChildren();$("#editorForm").onsubmit=event=>event.preventDefault();
      $("#editorBody").innerHTML='<h3>'+m("额度快照历史","利用枠履歴","Credit snapshots")+'</h3>'+(history.snapshots||[]).map(row=>'<div class="history-snapshot"><div><strong>'+e(hiddenAmounts?"••••":row.snapshot_date)+'</strong><p>'+money(row.available_minor,card.currency,card.minor_digits)+" / "+money(row.limit_minor,card.currency,card.minor_digits)+'</p><small>'+e(row.description||row.note||row.snapshot_type)+'</small></div>'+b("credit-restore",m("恢复","復元","Restore"),id+":"+row.snapshot_type+":"+row.id)+'</div>').join("")+'<h3>'+m("信用卡流水","カード取引","Card activity")+'</h3>'+(history.transactions||[]).map(row=>'<div class="report-row"><span>'+e(hiddenAmounts?"••••":row.occurred_on)+" · "+e(row.description)+'</span><b>'+money(row.card_amount_minor,card.currency,card.minor_digits)+'</b></div>').join("");$("#editorDialog").showModal();$("#editorDialog").addEventListener("close",()=>$("#editorSave").classList.remove("hidden"),{once:true});return;
    }
    if(action==="credit-restore"){const [accountId,snapshotType,snapshotId]=id.split(":");if(await confirmOnce(m("恢复额度快照","利用枠を復元","Restore credit snapshot"),m("移除较新的快照，保留账目；操作前会备份。","新しい枠履歴を削除し取引は保持。先にバックアップします。","Newer snapshots will be removed; entries stay. A backup is made first."))){await runAction("restore_credit",{accountId,snapshotType,snapshotId,confirmed:true});$("#editorDialog").close();}return;}
    if(action==="asset-edit"){
      const asset=workspace.assets.find(row=>row.id===id)||{};
      return openForm(m("固定资产","固定資産","Fixed asset"),[field("name",m("资产名称","資産名","Asset name"),"text",asset.name||""),field("currency",t("currency"),"select",asset.currency||"JPY",[["JPY","JPY"],["CNY","CNY"]]),amountField("cost",m("购入原值","取得原価","Acquisition cost"),plainAmount(asset.cost_minor,asset.currency==="CNY"?2:0)),field("month",m("购入月份","取得月","Acquisition month"),"month",asset.acquisition_month||workspace.date.slice(0,7)),field("months",m("预计使用月数","耐用月数","Useful life in months"),"integer",asset.useful_life_months||"36"),field("included",m("计入资产负债表","貸借対照表に含める","Include in balance sheet"),"checkbox",asset.include_in_balance_sheet!=="0"),{...field("disposal",m("报废月份（可空）","除却月（任意）","Disposal month (optional)"),"month",asset.disposal_month||""),optional:true}],data=>runAction("asset",{...data,id:asset.id||""}));
    }
    if(action==="asset-toggle"){const asset=workspace.assets.find(row=>row.id===id);return runAction("asset_toggle",{id,included:asset.include_in_balance_sheet!=="1"});}
    if(action==="asset-delete"||action==="recurring-delete"){if(await confirmOnce(button.textContent+" #"+id,m("删除前保存完整备份；已有流水保留。","削除前に完全バックアップ。既存取引は保持。","A full backup is made before deletion. Posted entries remain.")))return runAction(action==="asset-delete"?"delete_asset":"delete_recurring",{id,confirmed:true});return;}
    if(action==="cash-adjust"){const account=cachedBootstrap.accounts.find(row=>row.id==id);if(hiddenAmounts)throw new Error(m("请先显示数字再调整","先に数字を表示してください","Show numbers before editing"));return openForm(m("核对实际余额","実残高を照合","Reconcile balance")+" · "+account.name,[amountField("amount",m("实际余额","実際の残高","Actual balance"),plainAmount(account.balanceMinor,account.minorDigits)),dateField(),field("postDifferences",m("将差额记入账本","差額を記帳","Post the difference"),"checkbox",true)],data=>runAction("reconcile",{date:data.date,postDifferences:data.postDifferences,amounts:{[account.name]:data.amount}}));}
    if(action==="cash-delete"){const account=cachedBootstrap.accounts.find(row=>row.id==id);if(await confirmOnce(m("删除账户：","口座を削除：","Delete account: ")+account.name,m("关联流水或计划的账户不能删除。删除前会备份。","取引・予定で使う口座は削除できません。先にバックアップします。","Accounts referenced by entries or plans cannot be deleted. A backup is made first.")))return runAction("delete_account",{name:account.name,confirmed:true});return;}
    if(action==="recurring-edit"){
      const row=workspace.recurring.find(row=>row.id===id)||{};return openForm(m("定期收支","定期取引","Recurring entry"),[field("name",m("规则名称","予定名","Schedule name"),"text",row.name||""),field("kind",t("type"),"select",row.kind||"expense",[["expense",t("expense")],["income",t("income")]]),accountField("account","all",row.account_name),field("currency",m("账单币种","請求通貨","Bill currency"),"select",row.currency||"JPY",[["JPY","JPY"],["CNY","CNY"]]),amountField("amount",t("amount"),row.amount_minor?plainAmount(row.amount_minor,row.minor_digits):""),field("category",t("category"),"select",row.category_name,[...fieldsCategories("expense"),...fieldsCategories("income")]),field("frequency",m("周期","周期","Frequency"),"select",row.frequency||"monthly",[["daily",m("每天","毎日","Daily")],["weekly",m("每周","毎週","Weekly")],["monthly",m("每月","毎月","Monthly")],["yearly",m("每年","毎年","Yearly")]]),field("interval",m("每隔几个周期","間隔","Interval"),"integer",row.interval_count||"1"),{...dateField(),value:row.next_due_date||workspace.date}],data=>runAction("recurring",{...data,id:row.id||""}));
    }
    if(action==="recurring-toggle"){const row=workspace.recurring.find(row=>row.id===id);return runAction("recurring_toggle",{id,enabled:row.enabled!=="1"});}
    if(action==="run-due"){const result=await runAction("run_due");showToast(m("到期项目已检查","期日の確認が完了しました","Due entries checked"));return;}
    if(action==="budget-edit"){
      let plan={};try{plan=JSON.parse(workspace.settings["savings_plan:"+workspace.profit.start]||workspace.settings["savings_plan:monthly_template"]||"{}").items||{};}catch{}
      const categories=fieldsCategories("expense");return openForm(m("本期预算","今期予算","Period budget"),[amountField("total",m("总预算 · JPY","予算合計 · JPY","Total budget · JPY"),workspace.settings.monthly_jpy_budget_minor||"0"),amountField("goal",m("储蓄目标 · JPY","貯蓄目標 · JPY","Savings goal · JPY"),workspace.settings.savings_goal_jpy||"0"),...categories.map(([name,label],index)=>({...amountField("category"+index,label,plan[name]||"0"),optional:true}))],data=>runAction("budget",{total:data.total,goal:data.goal,items:Object.fromEntries(categories.map(([name],index)=>[name,data["category"+index]||"0"]))}));
    }
    if(action==="food-purchase"||action==="food-eaten")return openForm(action==="food-purchase"?m("添加食品采购","食品の購入","Food purchase"):m("记录饮食","食事を記録","Log a meal"),[dateField(),field("items",m("每行一种食物；数量可写在 | 后面","1行に1品。数量は | の後に記入","One food per line; optional quantity after |"),"textarea"),{...field("meal",m("餐次（可空）","食事区分（任意）","Meal (optional)")),optional:true},{...field("note",m("备注（可空）","メモ（任意）","Note (optional)")),optional:true}],data=>runAction(action==="food-purchase"?"food_purchase":"food_eaten",{...data,items:data.items.split("\n").filter(line=>line.trim()).map(line=>{const parts=line.split("|");return [parts[0].trim(),parts.slice(1).join("|").trim()];})}));
    if(action==="food-preference")return openForm(m("采购计入偏好","購入の計上設定","Purchase preference"),[field("enabled",m("将采购食品计入已吃回顾（不生成食用流水）","購入食品を食事回顧に含める（食事記録は作成しない）","Count food purchases in food reviews (does not create meals)"),"checkbox",workspace.settings.food_review_purchases_count_as_eaten==="1")],data=>runAction("food_preference",data));
    if(action==="food-group")return openForm(m("食品分类","食品カテゴリ","Food group"),[field("group",t("category"),"select",workspace.food.find(row=>row.id===id).food_group,Object.entries(workspace.foodGroups))],data=>runAction("food_group",{...data,id}));
    if(action==="food-delete"){const [kind,num]=id.split(":");if(await confirmOnce(m("删除食品记录","食品記録を削除","Delete food record")+" #"+num,m("仅删除食品记录，不撤销财务流水；先备份。","食品記録のみ削除し、財務取引は保持。先にバックアップします。","Deletes the food record, keeping financial entries. A backup is made first.")))return runAction("delete_food",{id:num,kind,confirmed:true});return;}
    if(action==="category-add")return openForm(m("新增类别","カテゴリ追加","New category"),[field("name",t("categoryName")),field("kind",t("type"),"select","expense",[["expense",t("expense")],["income",t("income")]]),{...field("ja-JP",m("日语显示名（可空）","日本語表示名（任意）","Japanese name (optional)")),optional:true},{...field("en-US",m("英语显示名（可空）","英語表示名（任意）","English name (optional)")),optional:true}],data=>runAction("category",data));
    if(action==="category-edit"){const row=cachedBootstrap.categories[Number(id)];return openForm(m("类别显示名","カテゴリ表示名","Category display name"),[field("language",m("语言","言語","Language"),"select",currentLanguage,[["zh-CN","简体中文"],["ja-JP","日本語"],["en-US","English"]]),field("name",m("显示名","表示名","Display name"),"text",row.display_name)],data=>runAction("category_translation",{...data,id:row.id}));}
    if(action==="tx-detail"){
      const row=[...(ledgerRangeRows||[]),...workspace.transactions].find(row=>row.id===id);if(!row)return;
      $("#editorTitle").textContent=m("账单详情","取引の詳細","Entry details");$("#editorCancel").textContent=m("关闭","閉じる","Close");$("#editorSave").classList.add("hidden");$("#editorFooter").replaceChildren();$("#editorForm").onsubmit=event=>event.preventDefault();
      const sign=row.kind==="income"?"+":row.kind==="expense"?"−":"";
      $("#editorBody").innerHTML='<strong class="detail-amount kind-'+e(row.kind)+'">'+sign+money(row.amount_minor,row.currency,row.currency_minor_digits)+'</strong><p class="prewrap">'+e(row.description)+'</p>'+["occurred_on","category_name","account_name","to_account_name","balance_effect"].map(key=>row[key]?'<div class="report-row"><span>'+e({occurred_on:t("date"),category_name:t("category"),account_name:t("fromAccount"),to_account_name:t("toAccount"),balance_effect:t("status")}[key])+'</span><strong>'+e(row[key])+'</strong></div>':"").join("")+'<div class="button-row">'+(row.needs_review==="1"?b("tx-review",m("核对并确认","確認する","Review & confirm"),id):"")+b("tx-edit",m("编辑账单","取引を編集","Edit entry"),id)+b("tx-delete",m("删除这笔账","取引を削除","Delete this entry"),id,"button danger-text")+'</div>';
      $("#editorDialog").showModal();$("#editorDialog").addEventListener("close",()=>$("#editorSave").classList.remove("hidden"),{once:true});return;
    }
    if(action==="tx-edit"){
      const row=[...(ledgerRangeRows||[]),...workspace.transactions].find(row=>row.id===id);if(!row)return;
      const accounts=(cachedBootstrap?.accounts||[]).map(account=>[account.name,account.name+" · "+account.currency]);
      const accountOptions=[["",m("不指定账户","口座なし","No account")],...accounts];
      const currencies=[...new Set([row.currency,...(cachedBootstrap?.accounts||[]).map(account=>account.currency)])].map(code=>[code,code]);
      const categories=(cachedBootstrap?.categories||[]).map(item=>[item.name,item.display_name,item.kind]);
      if(row.category_name&&!categories.some(item=>item[0]===row.category_name))categories.push([row.category_name,row.category_name,row.kind]);
      const categoryOptions=[["",m("请选择类别","カテゴリを選択","Choose a category")],...categories.filter(item=>item[2]===row.kind||item[0]===row.category_name).map(([name,label])=>[name,label])];
      const digits=Number(row.currency_minor_digits??row.minor_digits??(row.currency==="CNY"?2:0));
      const toDigits=Number(row.to_minor_digits??digits);
      return openForm(m("编辑账单","取引を編集","Edit entry"),[
        field("date",t("date"),"date",row.occurred_on),
        field("kind",t("type"),"select",row.kind,[["expense",t("expense")],["income",t("income")],["transfer",t("transfer")]]),
        field("description",m("说明","内容","Description"),"text",row.description||""),
        field("currency",t("currency"),"select",row.currency,currencies),
        amountField("amount",t("amount"),plainAmount(row.amount_minor,digits)),
        {...field("account_name",t("account"),"select",row.account_name||"",accountOptions),optional:true},
        {...field("category_name",t("category"),"select",row.category_name||"",categoryOptions),optional:true},
        {...field("to_account_name",m("转入账户","振込先口座","Destination account"),"select",row.to_account_name||"",accountOptions),optional:true},
        {...amountField("to_amount",m("转入金额（跨币种时填写）","入金額（異なる通貨の場合）","Destination amount (for FX transfers)"),row.to_amount_minor?plainAmount(row.to_amount_minor,toDigits):""),optional:true},
        field("memo_only",m("备查记录（不影响账户余额）","メモ記録（残高に反映しない）","Memo only (does not affect balances)"),"checkbox",row.balance_effect==="memo"),
        field("needs_review",m("待核对","要確認","Needs review"),"checkbox",row.needs_review==="1"),
      ],async data=>{const result=await runAction("edit_transaction",{id,...data});showToast(m("账单已保存，修改前备份已保留。","取引を保存し、変更前のバックアップを保管しました。","Entry saved. A pre-edit backup was kept."));return result;},{note:m("保存前会自动完整备份；信用卡自动还款流水需在还款计划中修改。","保存前に完全バックアップします。カード自動返済の流水は返済予定から変更してください。","A full backup is created before saving. Automatic card repayment entries must be changed in the repayment plan."),onReady:()=>{
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
    if(action==="tx-delete"){const row=[...(ledgerRangeRows||[]),...workspace.transactions].find(row=>row.id===id);if(await confirmOnce(m("删除账目：","取引を削除：","Delete entry: ")+row.description,m("账户余额与相关额度恢复点会重新计算；操作前保留完整备份。","残高と関連する利用枠を再計算します。先に完全バックアップします。","Balances and related credit recovery points will be recalculated after a full backup."))){await runAction("delete_transaction",{id,confirmed:true});$("#editorDialog").close();}return;}
    if(action==="tx-review"){const row=[...(ledgerRangeRows||[]),...workspace.transactions].find(row=>row.id===id);if(row.balance_effect==="memo"){return openForm(m("确认实际账户","実際の口座を確認","Confirm actual account"),[accountField()],data=>runAction("review_transaction",{id,...data}));}await runAction("review_transaction",{id});$("#editorDialog").close();}
  });
}

mountMobile();
window.onCloudLedgerRestored = () => {
  workspaceEpoch++;workspaceLoading=null;
  chats={bookkeeping:[],food_health:[]};workspace=null;workspaceOwner="";workspaceError="";backupDraft=null;
  ledgerRangeRows=null;attachments=[];renderAgent();
};
document.addEventListener("visibilitychange", async () => {
  if (document.hidden || !currentUser || !serverReachable || activeJob || sending) return;
  const message = await pullCloudOnLogin();
  if (message) showToast(message);
  await guarded(async () => { await fetchBootstrap(); await loadWorkspace(true); });
});
const baseRenderAccounts=renderAccounts;
renderAccounts=async function(){
  await baseRenderAccounts();
  const accounts=(await localAccountsAndCategories()).accounts;
  $$("#accountGrid .account-card").forEach((node,index)=>{
    const account=accounts[index];if(!account)return;
    // Credit cards have their own tab with limit and debt details. Keep them
    // out of the funds list, which otherwise renders every account type.
    if(account.type==="credit"){node.remove();return;}
    if(hiddenAmounts)$(".account-balance",node).textContent="••••••";
    if(!account.pending){
      const actions=document.createElement("div");actions.className="button-row account-actions";
      actions.innerHTML=b("cash-adjust",m("核对余额","残高照合","Reconcile"),account.id,"text-button accent")+b("cash-delete",m("删除","削除","Delete"),account.id,"text-button danger-text");node.append(actions);
    }
  });
};
const baseRenderAll=renderAll;
renderAll=function(){baseRenderAll();loadWorkspace();renderMobileTransactions();};
const baseShowLoggedIn=showLoggedIn;
showLoggedIn=function(){baseShowLoggedIn(); if(currentUser){const owner=currentUser.id;for(const agent of ["bookkeeping","food_health"])cacheGet("chat:"+owner+":"+agent).then(saved=>{if(currentUser?.id===owner&&saved){chats[agent]=saved;renderAgent();}});} renderNavigation();renderAgent();loadWorkspace();};
const baseShowLoggedOut=showLoggedOut;
showLoggedOut=function(){baseShowLoggedOut();workspace=null;workspaceOwner="";ledgerRangeRows=null;backupDraft=null;reportDate="";chats={bookkeeping:[],food_health:[]};attachments=[];activeJob="";document.querySelectorAll("dialog[open]").forEach(dialog=>dialog.close());$("#editorBody").replaceChildren();for(const id of ["accountGrid","ledgerList","page-home","creditPanel","fixedPanel","modulePanel","cloudControls"])$("#"+id)?.replaceChildren();renderAgent();};
const baseApplyLanguage=applyLanguage;
applyLanguage=function(){baseApplyLanguage();renderMobile();renderAgent();};
renderTransactions=renderMobileTransactions;
