const WORDS = {
  "zh-CN": {
    appName:"家庭记账",privateLedger:"私人账本 · 多设备同步",heroTitle:"每一笔，都清楚。",heroText:"断网时先保存在本机；恢复网络后再安全同步到你的独立账本。",feature1:"每个账号有独立账本",feature2:"离线记录，联网续传",feature3:"电脑和手机共用同一网页",login:"登录",register:"创建账号",recover:"找回账号",username:"用户名",password:"密码",passwordAtLeast:"密码（至少12位）",inviteCode:"邀请码",recoveryNotice:"创建后会显示一次恢复码，请离线妥善保存。",recoveryCode:"恢复码",newPassword:"新密码（至少12位）",resetPassword:"重置密码",overview:"总览",yourLedger:"你的家庭账本",accounts:"账户",accountsHint:"余额按已入账流水计算，离线暂存记录单独显示。",addAccount:"＋ 添加账户",accountName:"账户名称",accountType:"类型",currency:"币种",openingBalance:"期初余额",openingDate:"期初日期",completeness:"余额状态",known:"完整",partial:"部分核实",inferred:"包含推算",saveToQueue:"保存并同步",cancel:"取消",quickEntry:"快速记账",entryHint:"提交后先进入同步队列；网络中断时保留在此设备。",expense:"支出",income:"收入",transfer:"转账",date:"日期",amount:"金额",category:"消费类别",fromAccount:"付款/转出账户",toAccount:"转入账户",toAmount:"实际转入金额（跨币种时填写）",description:"说明",saveEntry:"保存记账",categoryName:"类别名称",categoryType:"类别类型",add:"添加",pendingSync:"待同步",queueHint:"只要队列项目未成功写入云账本，就会继续保留并重试。",importDesktop:"导入桌面账本",importHint:"只会上传你主动选择的SQLite文件；请先关闭桌面软件，避免遗漏尚未写入文件的内容。",chooseFile:"选择账本文件",recentTransactions:"最近流水",recentHint:"默认展示最近2000条；可按日期检索更早的账目。",type:"类型",account:"账户/方向",status:"状态",privacyNote:"账本保存在服务端；离线记录在恢复连接后续传。",syncNow:"立即同步",logout:"退出",saveRecovery:"请保存账号恢复码",recoveryExplain:"恢复码只显示这一次。丢失密码且没有恢复码时，目前无法通过邮件找回。",copy:"复制",savedContinue:"我已保存，继续",online:"服务已连接",offline:"离线暂存",pendingCount:"{count} 条待同步",syncing:"正在同步…",synced:"同步完成",syncFailed:"同步失败，数据仍在此设备待同步",networkHint:"无法连接服务。新记录会保存在此设备，恢复连接后可点击同步。",emptyQueue:"没有待同步记录。",noAccounts:"还没有账户，请先添加账户。",noTransactions:"还没有流水。",posted:"已入账",memo:"备查",review:"待核对",accountTypes:{bank:"银行账户",wallet:"钱包",prepaid:"预付/券",transit:"交通卡",points:"积分",credit:"信用卡"},successAccount:"账户已加入同步队列。",successCategory:"类别已加入同步队列。",successTransaction:"记账已加入同步队列。",needsAccount:"请先添加账户。",importConfirm:"将选中的桌面账本上传到当前账号。只能导入空账本；继续吗？",importDone:"导入完成：{accounts} 个账户、{transactions} 条流水。",importError:"账本导入失败。",recoverSaved:"请保存新的恢复码；旧恢复码已经失效。",logoutOffline:"当前离线，无法通知服务器撤销登录。请联网后再退出。",amountRequired:"请输入有效金额。",selectAccount:"请选择账户",selectCategory:"请选择类别",expenseLabel:"支出",incomeLabel:"收入",transferLabel:"转账",outgoing:"转出",incoming:"转入",queued:"本机待同步",syncError:"同步错误：{message}",networkUnavailable:"服务暂时不可用，记录已安全保存在本机队列。",emptyAccounts:"暂无账户",newAccount:"新账户",langChanged:"语言已切换",noCategory:"无类别",importing:"正在导入…",categoryAdded:"类别已添加",accountAdded:"账户已添加",transactionAdded:"流水已记入",statusReview:"待核对",amountCannotEdit:"流水不会由网页自动修改或删除。"
  },
  "ja-JP": {
    appName:"家計簿",privateLedger:"プライベート台帳・複数端末同期",heroTitle:"暮らしを、少しクリアに。",heroText:"オフライン中は端末に保存し、接続が戻ったら専用台帳に同期します。",feature1:"アカウントごとに独立した台帳",feature2:"オフライン記録・再接続後に送信",feature3:"PCとスマートフォンで同じWeb画面",login:"ログイン",register:"アカウント作成",recover:"アカウント復旧",username:"ユーザー名",password:"パスワード",passwordAtLeast:"パスワード（12文字以上）",inviteCode:"招待コード",recoveryNotice:"作成後に復旧コードが一度だけ表示されます。安全な場所に保存してください。",recoveryCode:"復旧コード",newPassword:"新しいパスワード（12文字以上）",resetPassword:"パスワードを再設定",overview:"概要",yourLedger:"家計台帳",accounts:"口座",accountsHint:"残高は記帳済み取引から計算し、オフラインの記録は別に表示します。",addAccount:"＋ 口座を追加",accountName:"口座名",accountType:"種類",currency:"通貨",openingBalance:"開始残高",openingDate:"開始日",completeness:"残高の状態",known:"確定",partial:"一部確認済み",inferred:"推定を含む",saveToQueue:"保存して同期",cancel:"キャンセル",quickEntry:"簡単記帳",entryHint:"保存後に同期キューへ入ります。通信が切れてもこの端末に残ります。",expense:"支出",income:"収入",transfer:"振替",date:"日付",amount:"金額",category:"カテゴリ",fromAccount:"支払元口座",toAccount:"振替先口座",toAmount:"実際の入金額（異通貨の場合）",description:"内容",saveEntry:"記帳を保存",categoryName:"カテゴリ名",categoryType:"種類",add:"追加",pendingSync:"同期待ち",queueHint:"サーバーへの保存に成功するまで、項目は保持して再試行します。",importDesktop:"デスクトップ台帳を取り込む",importHint:"選択したSQLiteファイルだけをアップロードします。未保存データの欠落を防ぐため、先にデスクトップ版を終了してください。",chooseFile:"台帳ファイルを選択",recentTransactions:"最近の取引",recentHint:"直近2000件を表示。日付指定で過去の取引も検索できます。",type:"種類",account:"口座/方向",status:"状態",privacyNote:"台帳はサービスに保存。オフライン記録は再接続後に同期します。",syncNow:"今すぐ同期",logout:"ログアウト",saveRecovery:"復旧コードを保存してください",recoveryExplain:"復旧コードは今回のみ表示されます。パスワードとコードを紛失した場合、メールでの復旧は現在できません。",copy:"コピー",savedContinue:"保存しました。続ける",online:"サーバー接続中",offline:"オフライン保存",pendingCount:"同期待ち {count} 件",syncing:"同期中…",synced:"同期完了",syncFailed:"同期できません。データは端末に保持されています",networkHint:"サーバーに接続できません。新規記録は端末に保存され、接続後に同期できます。",emptyQueue:"同期待ちはありません。",noAccounts:"口座がありません。先に追加してください。",noTransactions:"取引はまだありません。",posted:"記帳済み",memo:"備考",review:"要確認",accountTypes:{bank:"銀行口座",wallet:"ウォレット",prepaid:"プリペイド/券",transit:"交通系カード",points:"ポイント",credit:"クレジットカード"},successAccount:"口座を同期キューに追加しました。",successCategory:"カテゴリを同期キューに追加しました。",successTransaction:"取引を同期キューに追加しました。",needsAccount:"先に口座を作成してください。",importConfirm:"選択したデスクトップ台帳をこのアカウントにアップロードします。空の台帳にのみ取り込めます。続けますか？",importDone:"取り込み完了：口座{accounts}件、取引{transactions}件。",importError:"台帳の取り込みに失敗しました。",recoverSaved:"新しい復旧コードを保存してください。古いコードは無効になりました。",logoutOffline:"オフラインのためサーバーにログアウトを通知できません。接続後にログアウトしてください。",amountRequired:"有効な金額を入力してください。",selectAccount:"口座を選択してください",selectCategory:"カテゴリを選択してください",expenseLabel:"支出",incomeLabel:"収入",transferLabel:"振替",outgoing:"振出",incoming:"振入",queued:"端末で同期待ち",syncError:"同期エラー：{message}",networkUnavailable:"サーバーが利用できません。記録は端末のキューに保存しました。",emptyAccounts:"口座なし",newAccount:"新しい口座",langChanged:"言語を切り替えました",noCategory:"カテゴリなし",importing:"取り込み中…",categoryAdded:"カテゴリを追加しました",accountAdded:"口座を追加しました",transactionAdded:"取引を記帳しました",statusReview:"要確認",amountCannotEdit:"Webから取引を自動変更・削除することはありません。"
  },
  "en-US": {
    appName:"Household Ledger",privateLedger:"Private ledger · Multi-device sync",heroTitle:"A little more clarity.",heroText:"Entries stay on this device while offline, then sync to your private ledger after the connection returns.",feature1:"Separate ledger for each account",feature2:"Work offline, resume sync later",feature3:"Use the same web app on PC and phone",login:"Sign in",register:"Create account",recover:"Recover account",username:"Username",password:"Password",passwordAtLeast:"Password (at least 12 characters)",inviteCode:"Invitation code",recoveryNotice:"A recovery code is shown once after signup. Store it somewhere safe.",recoveryCode:"Recovery code",newPassword:"New password (at least 12 characters)",resetPassword:"Reset password",overview:"Overview",yourLedger:"Your household ledger",accounts:"Accounts",accountsHint:"Balances use posted entries; offline entries are shown separately.",addAccount:"＋ Add account",accountName:"Account name",accountType:"Type",currency:"Currency",openingBalance:"Opening balance",openingDate:"Opening date",completeness:"Balance status",known:"Complete",partial:"Partially verified",inferred:"Includes estimates",saveToQueue:"Save and sync",cancel:"Cancel",quickEntry:"Quick entry",entryHint:"Entries enter the sync queue first and stay on this device if the network drops.",expense:"Expense",income:"Income",transfer:"Transfer",date:"Date",amount:"Amount",category:"Category",fromAccount:"Pay from / transfer out",toAccount:"Transfer to",toAmount:"Actual received amount (for cross-currency transfers)",description:"Description",saveEntry:"Save entry",categoryName:"Category name",categoryType:"Category type",add:"Add",pendingSync:"Pending sync",queueHint:"Queue items stay here and retry until they are saved to the ledger.",importDesktop:"Import desktop ledger",importHint:"Only the SQLite file you select is uploaded. Close the desktop app first so recent changes are written to the file.",chooseFile:"Choose ledger file",recentTransactions:"Recent transactions",recentHint:"Shows the latest 2,000 entries; choose dates to retrieve older records.",type:"Type",account:"Account / direction",status:"Status",privacyNote:"The ledger lives in the service; offline entries sync after reconnection.",syncNow:"Sync now",logout:"Sign out",saveRecovery:"Save your recovery code",recoveryExplain:"The recovery code is shown once. Without your password or code, email recovery is not available yet.",copy:"Copy",savedContinue:"I saved it — continue",online:"Service connected",offline:"Saved offline",pendingCount:"{count} pending",syncing:"Syncing…",synced:"Sync complete",syncFailed:"Sync failed; data remains on this device",networkHint:"Cannot reach the service. New entries will stay on this device until it is reachable.",emptyQueue:"Nothing is waiting to sync.",noAccounts:"No accounts yet. Add one to begin.",noTransactions:"No transactions yet.",posted:"Posted",memo:"Memo",review:"Needs review",accountTypes:{bank:"Bank account",wallet:"Wallet",prepaid:"Prepaid / voucher",transit:"Transit card",points:"Points",credit:"Credit card"},successAccount:"Account added to the sync queue.",successCategory:"Category added to the sync queue.",successTransaction:"Entry added to the sync queue.",needsAccount:"Create an account first.",importConfirm:"Upload the selected desktop ledger to this account. Import is allowed only into an empty web ledger. Continue?",importDone:"Imported: {accounts} accounts and {transactions} transactions.",importError:"Ledger import failed.",recoverSaved:"Save the new recovery code. The old code no longer works.",logoutOffline:"Offline: the server cannot revoke this session. Sign out after reconnecting.",amountRequired:"Enter a valid amount.",selectAccount:"Choose an account",selectCategory:"Choose a category",expenseLabel:"Expense",incomeLabel:"Income",transferLabel:"Transfer",outgoing:"Out",incoming:"In",queued:"Waiting on device",syncError:"Sync error: {message}",networkUnavailable:"The service is unavailable. Your entry is safe in the local queue.",emptyAccounts:"No accounts",newAccount:"New account",langChanged:"Language changed",noCategory:"No category",importing:"Importing…",categoryAdded:"Category added",accountAdded:"Account added",transactionAdded:"Entry saved",statusReview:"Needs review",amountCannotEdit:"The web app does not automatically edit or delete entries."
  }
};

for (const [language, messages] of Object.entries({
  "zh-CN": {
    syncNow: "立即上传", syncing: "正在上传…",
    networkHint: "无法连接服务。新记录会保存在此设备，恢复网络后可点击“立即上传”。",
    nothingToUpload: "账本已保存在云端，没有待上传记录。",
    uploadWaiting: "正在检查云端账本，请稍候再上传。",
    uploadConflict: "存在待处理的同步冲突，请先刷新并核对记录。",
    uploadComplete: "上传完成，账本已保存到云端。",
    uploadRefreshFailed: "记录已上传到云端，但页面刷新失败。请点击刷新核对，不要重复记账。",
    uploadHint: "只上传本机待同步记录；不会覆盖整本云端账本。",
  },
  "ja-JP": {
    syncNow: "今すぐアップロード", syncing: "アップロード中…",
    networkHint: "サービスに接続できません。新しい記録はこの端末に保存され、再接続後に「今すぐアップロード」できます。",
    nothingToUpload: "台帳はクラウドに保存済みです。アップロード待ちの記録はありません。",
    uploadWaiting: "クラウド台帳を確認中です。完了後にアップロードしてください。",
    uploadConflict: "未解決の同期競合があります。先に台帳を更新して記録を確認してください。",
    uploadComplete: "アップロード完了。台帳をクラウドに保存しました。",
    uploadRefreshFailed: "記録はクラウドに保存されましたが、画面を更新できません。再記帳せず、更新して確認してください。",
    uploadHint: "端末で同期待ちの記録だけを送信します。クラウド台帳全体は上書きしません。",
  },
  "en-US": {
    syncNow: "Upload now", syncing: "Uploading…",
    networkHint: "The service is unavailable. New entries stay on this device; click Upload now after reconnecting.",
    nothingToUpload: "Your ledger is already saved in the cloud. Nothing is waiting to upload.",
    uploadWaiting: "The cloud ledger is being checked. Try uploading again in a moment.",
    uploadConflict: "A sync conflict needs review. Refresh the ledger and check the pending entry first.",
    uploadComplete: "Upload complete. Your ledger is saved in the cloud.",
    uploadRefreshFailed: "The entry reached the cloud, but the page could not refresh. Refresh to verify it; do not enter it again.",
    uploadHint: "Uploads only pending entries from this device; it does not replace the full cloud ledger.",
  },
})) Object.assign(WORDS[language], messages);

const DB_NAME = "household-ledger-web-v1";
const DB_VERSION = 1;
let idb;
let currentLanguage = ["zh-CN","ja-JP","en-US"].includes(localStorage.getItem("hh-language")) ? localStorage.getItem("hh-language") : "zh-CN";
let csrfToken = "";
let currentUser = null;
let runtimeConfig = {};
let serverReachable = false;
let cachedBootstrap = null;
let sending = false;
let pendingSyncCount = 0;
let syncConflict = false;
let syncRetryTimer = null;
let syncRetryAttempt = 0;
let selectedKind = "expense";
let toastTimer;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const t = (key, values = {}) => {
  let value = key.split(".").reduce((obj, part) => obj && obj[part], WORDS[currentLanguage]) ?? WORDS["zh-CN"][key] ?? key;
  if (typeof value !== "string") return key;
  return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
};

function applyLanguage() {
  document.documentElement.lang = currentLanguage;
  document.title = WORDS[currentLanguage].appName;
  $$('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
  const languageSelect = $("#languageSelect");
  if (languageSelect) {
    languageSelect.value = currentLanguage;
    languageSelect.setAttribute("aria-label", currentLanguage === "ja-JP" ? "表示言語" : currentLanguage === "en-US" ? "Display language" : "显示语言");
  }
  const authLanguageSelect = $("#authLanguageSelect");
  if (authLanguageSelect) {
    authLanguageSelect.value = currentLanguage;
    authLanguageSelect.setAttribute("aria-label", currentLanguage === "ja-JP" ? "表示言語" : currentLanguage === "en-US" ? "Display language" : "显示语言");
    $("#authLanguageLabel").textContent = currentLanguage === "ja-JP" ? "表示言語" : currentLanguage === "en-US" ? "Language" : "界面语言";
  }
  const tutorialButton = $("#tutorialButton");
  if (tutorialButton) tutorialButton.textContent = currentLanguage === "ja-JP" ? "チュートリアル" : currentLanguage === "en-US" ? "Tutorial" : "新手教程";
  $(".segmented").setAttribute("aria-label", currentLanguage === "ja-JP" ? "取引の種類" : currentLanguage === "en-US" ? "Transaction type" : "交易类型");
  $("#showCategoryForm").setAttribute("aria-label", currentLanguage === "ja-JP" ? "カテゴリを追加" : currentLanguage === "en-US" ? "Add category" : "添加类别");
  $("#accountForm [name=type]").innerHTML = ["bank","wallet","prepaid","transit","points","credit"].map(type => `<option value="${type}">${escapeHtml(WORDS[currentLanguage].accountTypes[type])}</option>`).join("");
  $("#exportLedger").textContent = currentLanguage === "ja-JP" ? "クラウド台帳をエクスポート" : currentLanguage === "en-US" ? "Export cloud ledger" : "导出云端账本";
  $("#transactionForm [name=description]").placeholder = currentLanguage === "zh-CN" ? "例如：超市买菜" : currentLanguage === "ja-JP" ? "例：スーパーで食材" : "e.g. groceries";
  if (cachedBootstrap) renderAll();
  window.dispatchEvent(new CustomEvent("household-language-changed", {detail: {language: currentLanguage}}));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function localizeServerError(message) {
  const source = String(message || "");
  if (currentLanguage === "zh-CN") return source;
  if (/云端账本已更新|云端已有更新|云端版本冲突/.test(source)) {
    return currentLanguage === "ja-JP"
      ? "クラウド台帳に新しい変更があるため同期を停止しました。記録はこの端末に保持しています。台帳を更新して確認してください。"
      : "A newer cloud change was found, so sync paused. The entry remains on this device. Refresh the ledger and review it.";
  }
  const cloudErrors = {
    "本机有尚未同步的修改，已暂停自动下载；请先核对并上传或手动恢复。":["未同期の変更があるため自動取得を保留しました。確認後にアップロードするか、手動で復元してください。","Automatic download paused because local edits have not synced. Review and upload them, or restore manually."],
    "无法检查云端账本，请检查网络与云端授权。":["クラウド台帳を確認できません。接続と認証を確認してください。","Cannot check the cloud ledger. Check the connection and authorization."],
    "此账号正在下载最新云端账本，请稍后再试。":["このアカウントの台帳を取得中です。しばらくしてから再試行してください。","This account is already downloading its ledger. Try again shortly."],
    "Agent 正在处理请求，已暂停自动下载，请稍后重试。":["Agent が処理中のため自動取得を保留しました。後で再試行してください。","Automatic download paused while the Agent is working. Try again later."]
  };
  if (cloudErrors[source]) return cloudErrors[source][currentLanguage === "ja-JP" ? 0 : 1];
  if (/ユーザー名|用户名|パスワード|密码|復旧コード|恢复码|招待コード|邀请码/.test(source)) {
    return currentLanguage === "ja-JP" ? "ユーザー名、パスワード、復旧コード、または招待コードを確認してください。" : "Check the username, password, recovery code, or invitation code.";
  }
  if (/金額|金额|小数|通貨|币种|口座|账户|カテゴリ|类别|日付|日期|為替|汇率/.test(source)) {
    return currentLanguage === "ja-JP" ? "金額、日付、口座、カテゴリ、通貨、為替レートを確認してください。" : "Check the amount, date, account, category, currency, and exchange-rate details.";
  }
  return currentLanguage === "ja-JP" ? "操作を完了できませんでした。入力内容を確認して、もう一度お試しください。" : "The request could not be completed. Review the entry and try again.";
}

function openIdb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("outbox")) db.createObjectStore("outbox", {keyPath:"opId"});
      if (!db.objectStoreNames.contains("cache")) db.createObjectStore("cache");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function idbRequest(store, mode, callback) {
  return new Promise((resolve, reject) => {
    const tx = idb.transaction(store, mode);
    const request = callback(tx.objectStore(store));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
const cacheGet = key => idbRequest("cache", "readonly", s => s.get(key));
const cacheSet = (key, value) => idbRequest("cache", "readwrite", s => s.put(value, key));
const outboxAll = async () => (await idbRequest("outbox", "readonly", s => s.getAll())).filter(item => item.ownerId === currentUser?.id);
const outboxDelete = opId => idbRequest("outbox", "readwrite", s => s.delete(opId));
const outboxPut = operation => idbRequest("outbox", "readwrite", s => s.put(operation));
function outboxMutate(opId, mutate) {
  return new Promise((resolve,reject)=>{
    const tx=idb.transaction("outbox","readwrite"),store=tx.objectStore("outbox"),request=store.get(opId);
    let result=null;
    request.onsuccess=()=>{
      const item=request.result;
      if(!item||item.ownerId!==currentUser?.id)return;
      result=mutate(item);
      if(result===null){store.delete(opId);result={removed:true};}else if(result)store.put(result);
    };
    tx.oncomplete=()=>resolve(result);
    tx.onerror=()=>reject(tx.error||request.error);
    tx.onabort=()=>reject(tx.error||request.error||new Error("本机待处理队列更新失败。"));
  });
}
const outboxStartDispatch = opId => outboxMutate(opId,item=>({...item,dispatchStarted:true,dispatchStartedAt:item.dispatchStartedAt||new Date().toISOString(),error:""}));
const outboxUndoDelete = async opId => (await outboxMutate(opId,item=>item.type==="pending_delete"&&!item.dispatchStarted?null:item))?.removed===true;
const outboxUndoPendingAction = async opId => {
  const queue=(await outboxAll()).sort((a,b)=>a.createdAt.localeCompare(b.createdAt));
  if(queue.at(-1)?.opId!==opId)return false;
  return (await outboxMutate(opId,item=>item.type==="pending_action"&&!item.dispatchStarted&&!item.serverAccepted?null:item))?.removed===true;
};
function scheduleSyncRetry() {
  if(syncRetryTimer||!navigator.onLine)return;
  const delay=Math.min(1000*2**syncRetryAttempt,30000);
  syncRetryAttempt=Math.min(syncRetryAttempt+1,5);
  syncRetryTimer=setTimeout(()=>{syncRetryTimer=null;void syncQueue();},delay);
}

function readCookie(name) {
  const prefix = `${name}=`;
  const found = document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith(prefix));
  return found ? decodeURIComponent(found.slice(prefix.length)) : "";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (currentUser?.id) headers.set("X-Ledger-Owner", currentUser.id);
  if (options.body instanceof FormData || options.body instanceof Blob) {
    // Upload endpoints set their own content type.
  } else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.method && options.method !== "GET") {
    const token = csrfToken || readCookie("hh_csrf");
    if (token) headers.set("X-CSRF-Token", token);
  }
  const response = await fetch(path, {...options, headers, credentials:"same-origin", cache:"no-store"});
  const value = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(localizeServerError(value?.error || `HTTP ${response.status}`));
    error.status = response.status;
    throw error;
  }
  if (response.headers.get("X-Bookkeeping-Cloud-Saved") === "false" && value && typeof value === "object") {
    Object.defineProperty(value, "cloudSnapshotSaved", {value:false});
  }
  serverReachable = true;
  updateConnection();
  return value;
}

function setAuthMessage(message, isError = false) {
  const node = $("#authMessage");
  node.textContent = message;
  node.classList.toggle("hidden", !message);
  node.classList.toggle("error", isError);
}

function showCloudProgress(title, detail, {modal = true} = {}) {
  const dialog = $("#cloudProgressDialog");
  if (!dialog) { setAuthMessage(title); return; }
  $("#cloudProgressTitle").textContent = title;
  $("#cloudProgressDetail").textContent = detail;
  dialog.classList.toggle("nonblocking", !modal);
  const spinner = $("#cloudProgressDialog .cloud-progress-spinner");
  if (spinner) spinner.dataset.state = "running";
  const nextMode = modal ? "modal" : "nonblocking";
  if (dialog.open && dialog.dataset.progressMode !== nextMode) dialog.close();
  if (!dialog.open) {
    if (modal) dialog.showModal();
    else dialog.show();
    dialog.dataset.progressMode = nextMode;
  }
}

$("#cloudProgressDialog")?.addEventListener("cancel", event => event.preventDefault());

function hideCloudProgress() {
  const dialog = $("#cloudProgressDialog");
  if (dialog?.open) dialog.close();
  dialog?.classList.remove("nonblocking");
  if (dialog) delete dialog.dataset.progressMode;
  const cancel = $("#cloudProgressCancel");
  if (cancel) { cancel.classList.add("hidden"); cancel.disabled = false; cancel.onclick = null; }
}

function showToast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("hidden", false);
  node.classList.toggle("error", error);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.add("hidden"), 3800);
}

function showAuthTab(name) {
  $$(".auth-tab").forEach(button => button.classList.toggle("active", button.dataset.authTab === name));
  for (const formName of ["login", "recover"]) $("#" + formName + "Form").classList.toggle("hidden", formName !== name);
  setAuthMessage("");
}

function updateTopbarLayout(isAuthenticated) {
  const topbar = $(".topbar");
  topbar.classList.toggle("is-authenticated", isAuthenticated);
}

const topbarForViewport = $(".topbar");
if (topbarForViewport && "ResizeObserver" in window) {
  const topbarHeightObserver = new ResizeObserver(() => {
    document.documentElement.style.setProperty(
      "--topbar-height",
      `${Math.ceil(topbarForViewport.getBoundingClientRect().height)}px`,
    );
  });
  topbarHeightObserver.observe(topbarForViewport);
}

function renderSessionStatus() {
  const text = (zh,ja,en) => currentLanguage === "ja-JP" ? ja : currentLanguage === "en-US" ? en : zh;
  $("#sessionIdentity").textContent = currentUser
    ? text("已登录：", "ログイン中：", "Signed in: ") + (currentUser.username || "")
    : text("正在恢复安全会话", "安全なセッションを確認中", "Restoring your secure session");
  $("#sessionWelcome").textContent = currentUser
    ? text("欢迎回来", "おかえりなさい", "Welcome back")
    : text("正在打开家庭记账", "家計簿を開いています", "Opening your ledger");
  $("#sessionLoadingText").textContent = cloudBootstrapFailed
    ? text("网页仍保持登录。以下提示仅涉及 GitHub 备份，不需要重新注册或创建账本。", "Web版にはログイン済みです。以下はGitHubバックアップの状態であり、新規登録や台帳作成は不要です。", "You are still signed in. The message below concerns your GitHub backup; no new account or ledger is needed.")
    : currentUser
      ? text("正在打开你的账本，请稍候。", "台帳を開いています。しばらくお待ちください。", "Opening your ledger. Please wait.")
      : text("正在检查此浏览器的登录状态，请稍候。", "このブラウザーのログイン状態を確認しています。", "Checking this browser's saved session. Please wait.");
}

function showSessionPending(blocked = false) {
  $("#authScreen").classList.add("hidden");
  $("#appScreen").classList.add("hidden");
  $("#toolbar").classList.add("hidden");
  $("#sessionScreen").classList.remove("hidden");
  $("#cloudBootstrapBlocked").classList.toggle("hidden", !blocked);
  $("#sessionLoadingIndicator").classList.toggle("hidden", blocked);
  renderSessionStatus();
  updateTopbarLayout(false);
}

function showLoggedIn() {
  cloudBootstrapFailed = false;
  $("#sessionScreen").classList.add("hidden");
  $("#authScreen").classList.add("hidden");
  $("#appScreen").classList.remove("hidden");
  $("#toolbar").classList.remove("hidden");
  $("#usernameLabel").textContent = currentUser?.username || "";
  updateTopbarLayout(true);
  updateConnection();
}

function showLoggedOut() {
  $("#sessionScreen").classList.add("hidden");
  $("#authScreen").classList.remove("hidden");
  $("#appScreen").classList.add("hidden");
  $("#toolbar").classList.add("hidden");
  updateTopbarLayout(false);
}

function showCloudBootstrapBlocked(message) {
  cloudBootstrapFailed = true;
  showSessionPending(true);
  $("#cloudBootstrapError").textContent = message;
}

function formatMinor(minor, currency, digits, accountType = "") {
  const places = Number(digits || 0);
  const locale = currentLanguage === "ja-JP" ? "ja-JP" : currentLanguage === "en-US" ? "en-US" : "zh-CN";
  const value = BigInt(String(minor || 0));
  const negative = value < 0n;
  const absolute = negative ? -value : value;
  const factor = 10n ** BigInt(places);
  const whole = absolute / factor;
  const fraction = absolute % factor;
  const formattedWhole = new Intl.NumberFormat(locale, {maximumFractionDigits:0}).format(whole);
  const decimal = places ? new Intl.NumberFormat(locale).formatToParts(1.1).find(part => part.type === "decimal")?.value || "." : "";
  const formatted = `${negative ? "−" : ""}${formattedWhole}${places ? decimal + fraction.toString().padStart(places,"0") : ""}`;
  return accountType === "points" ? `${formatted} ${currentLanguage === "ja-JP" ? "pt" : "点"}` : `${formatted} ${currency}`;
}

function parseMinorPreview(input, currency) {
  const digits = ["CNY","USD"].includes(currency) ? 2 : 0;
  const match = String(input || "").trim().match(digits ? /^(\d+)(?:\.(\d{0,2}))?$/ : /^(\d+)$/);
  if (!match) return 0;
  const whole = BigInt(match[1]);
  const fraction = BigInt((match[2] || "").padEnd(digits,"0") || "0");
  return (whole * (10n ** BigInt(digits)) + fraction).toString();
}

function localDate() {
  if (cachedBootstrap?.serverDate) return cachedBootstrap.serverDate;
  const parts = new Intl.DateTimeFormat("en-US", {timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
  const values=Object.fromEntries(parts.map(part=>[part.type,part.value]));
  return values.year+"-"+values.month+"-"+values.day;
}

function updateConnection() {
  const online = serverReachable && navigator.onLine;
  const state = !navigator.onLine ? "offline" : syncConflict ? "conflict" : sending ? "syncing" : window.backgroundBackupActive ? "backup" : window.cloudJobActive ? "working" : pendingSyncCount ? "pending" : online ? "online" : "offline";
  const labels = {
    "zh-CN": {online:"服务已连接",offline:"离线保存",syncing:"云端上传中…",backup:"云端备份中…",working:"云端处理中…",pending:`等待云端同步 ${pendingSyncCount} 条`,conflict:"同步冲突，需处理"},
    "ja-JP": {online:"サービス接続中",offline:"オフライン保存",syncing:"クラウドへ同期中…",backup:"クラウドにバックアップ中…",working:"クラウドで処理中…",pending:`同期待ち ${pendingSyncCount} 件`,conflict:"同期の競合を確認してください"},
    "en-US": {online:"Service connected",offline:"Saved offline",syncing:"Uploading to cloud…",backup:"Backing up to cloud…",working:"Processing in the cloud…",pending:`${pendingSyncCount} pending`,conflict:"Sync conflict needs attention"},
  };
  const status = $("#connectionState");
  status.textContent = labels[currentLanguage]?.[state] || labels["zh-CN"][state];
  status.dataset.state = state;
  status.classList.toggle("is-offline", state === "offline");
  status.classList.toggle("is-syncing", state === "syncing" || state === "backup" || state === "working");
  status.classList.toggle("has-pending", state === "pending");
  status.classList.toggle("has-conflict", state === "conflict");
  $("#offlineBanner").classList.toggle("hidden", online || !currentUser);
  $("#offlineBanner").textContent = t("networkHint");
  $("#syncButton").disabled = sending || !navigator.onLine;
  $("#syncButton").textContent = sending ? t("syncing") : t("syncNow");
  $("#syncButton").title = t("uploadHint");
}

function renderAll() {
  if (!cachedBootstrap) return;
  renderAccounts();
  renderCategories();
  renderTransactions();
  renderOutbox();
}

async function localAccountsAndCategories() {
  const queue = await outboxAll();
  const optimisticAccounts = queue.filter(item => item.type === "account").map(item => ({
    id:`pending-${item.opId}`, name:item.data.name, type:item.data.type, currency:item.data.currency,
    minorDigits:["CNY","USD"].includes(item.data.currency) ? 2 : 0, openingDate:item.data.openingDate,
    balanceMinor:parseMinorPreview(item.data.openingBalance,item.data.currency), pending:true
  }));
  const optimisticCategories = queue.filter(item => item.type === "category").map(item => ({name:item.data.name,kind:item.data.kind,display_name:item.data.name,pending:true}));
  return {accounts:[...(cachedBootstrap?.accounts || []), ...optimisticAccounts], categories:[...(cachedBootstrap?.categories || []), ...optimisticCategories]};
}

async function renderAccounts() {
  const {accounts} = await localAccountsAndCategories();
  const grid = $("#accountGrid");
  grid.replaceChildren();
  if (!accounts.length) {
    const empty = document.createElement("p"); empty.className = "empty-state"; empty.textContent = t("noAccounts"); grid.append(empty);
  }
  for (const account of accounts) {
    const card = document.createElement("article"); card.className = "account-card";
    const name = document.createElement("div"); name.className = "account-title"; name.textContent = account.name;
    const type = document.createElement("div"); type.className = "account-meta"; type.textContent = `${WORDS[currentLanguage].accountTypes[account.type] || account.type} · ${account.currency}`;
    const balance = document.createElement("div"); balance.className = "account-balance";
    balance.textContent = account.pending ? t("queued") : formatMinor(account.balanceMinor, account.currency, account.minorDigits, account.type);
    card.append(name,type,balance);
    if (account.pending) card.classList.add("pending-card");
    grid.append(card);
  }
  fillAccountSelects(accounts);
}

function fillAccountSelects(accounts) {
  const source = $("#transactionForm [name=accountName]");
  const destination = $("#transactionForm [name=toAccountName]");
  const oldSource = source.value, oldDest = destination.value;
  const choiceAccounts = accounts.filter(account => account.type !== "points");
  const opts = [`<option value="">${escapeHtml(t("selectAccount"))}</option>`, ...choiceAccounts.map(a => `<option value="${escapeHtml(a.name)}" data-currency="${escapeHtml(a.currency)}" data-type="${escapeHtml(a.type)}">${escapeHtml(a.name)} · ${escapeHtml(a.currency)}${a.pending ? ` · ${escapeHtml(t("queued"))}` : ""}</option>`)].join("");
  source.innerHTML = opts;
  destination.innerHTML = opts;
  if ([...source.options].some(option => option.value === oldSource)) source.value = oldSource;
  if ([...destination.options].some(option => option.value === oldDest)) destination.value = oldDest;
  if (!source.value && accounts.length) source.value = accounts[0].name;
  updateTransactionCurrency();
}

async function renderCategories() {
  const {categories} = await localAccountsAndCategories();
  const select = $("#transactionForm [name=categoryName]");
  const previous = select.value;
  const rows = categories.filter(item => item.kind === selectedKind);
  select.innerHTML = [`<option value="">${escapeHtml(t("selectCategory"))}</option>`, ...rows.map(category => `<option value="${escapeHtml(category.name)}">${escapeHtml(category.display_name || category.name)}${category.pending ? ` · ${escapeHtml(t("queued"))}` : ""}</option>`)].join("");
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
  if (!select.value && rows.length) select.value = rows[0].name;
  $("#categoryRow").classList.toggle("hidden", selectedKind === "transfer");
  $("#toAccountRow").classList.toggle("hidden", selectedKind !== "transfer");
  $("#toAmountRow").classList.toggle("hidden", selectedKind !== "transfer" || !needsToAmount());
  select.required = selectedKind !== "transfer";
}

function needsToAmount() {
  const sourceCurrency = $("#transactionForm [name=accountName]").selectedOptions[0]?.dataset.currency;
  const destCurrency = $("#transactionForm [name=toAccountName]").selectedOptions[0]?.dataset.currency;
  return Boolean(sourceCurrency && destCurrency && sourceCurrency !== destCurrency);
}

function updateTransactionCurrency() {
  const currency = $("#transactionForm [name=accountName]").selectedOptions[0]?.dataset.currency || "JPY";
  $("#amountCurrency").textContent = currency;
  const toCurrency = $("#transactionForm [name=toAccountName]").selectedOptions[0]?.dataset.currency || currency;
  $("#toCurrency").textContent = toCurrency;
  const row = $("#toAccountRow");
  const amountRow = $("#toAmountRow");
  row.classList.toggle("hidden", selectedKind !== "transfer");
  amountRow.classList.toggle("hidden", selectedKind !== "transfer" || !needsToAmount());
  const toAmount = $("#transactionForm [name=toAmount]");
  toAmount.required = selectedKind === "transfer" && needsToAmount();
  $("#transactionForm [name=toAccountName]").required = selectedKind === "transfer";
}

function renderTransactions() {
  const body = $("#transactionRows");
  body.replaceChildren();
  const rows = cachedBootstrap?.transactions || [];
  $("#transactionCount").textContent = `${rows.length}`;
  if (!rows.length) {
    const tr = document.createElement("tr"), td = document.createElement("td"); td.colSpan = 7; td.className = "empty-state"; td.textContent = t("noTransactions"); tr.append(td); body.append(tr); return;
  }
  for (const row of rows) {
    const tr = document.createElement("tr");
    const kind = row.kind === "expense" ? t("expense") : row.kind === "income" ? t("income") : t("transfer");
    const account = row.kind === "transfer" ? `${row.account_name || ""} → ${row.to_account_name || ""}` : row.account_name || "—";
    const amount = row.kind === "transfer" ? `${formatMinor(row.amount_minor,row.currency,row.minor_digits,row.account_type)} → ${formatMinor(row.to_amount_minor,row.to_currency || row.currency,row.to_minor_digits ?? row.minor_digits,row.to_account_type)}` : formatMinor(row.amount_minor,row.currency,row.minor_digits,row.account_type);
    const status = row.needs_review ? t("review") : row.balance_effect === "memo" ? t("memo") : t("posted");
    const values = [row.occurred_on,kind,row.description,row.category_name || "—",account,amount,status];
    for (let i=0;i<values.length;i++) { const td=document.createElement("td"); td.textContent=values[i]; if (i===5) td.className="right nowrap"; if (i===1) td.className=`kind-${row.kind}`; tr.append(td); }
    body.append(tr);
  }
}

async function renderOutbox() {
  const queue = (await outboxAll()).sort((a,b) => a.createdAt.localeCompare(b.createdAt));
  pendingSyncCount = queue.length;
  syncConflict = queue.some(item => item.conflict);
  updateConnection();
  $("#pendingCount").textContent = String(queue.length);
  $("#syncSummary").textContent = queue.length ? t("pendingCount", {count:queue.length}) : "";
  const list = $("#outboxList");
  list.replaceChildren();
  list.classList.toggle("empty-state", !queue.length);
  if (!queue.length) { list.textContent = t("emptyQueue"); return; }
  for (const item of queue) {
    const row = document.createElement("div"); row.className = "outbox-item";
    const main = document.createElement("div"); main.className = "outbox-main";
    const title = document.createElement("strong");
    if (item.type === "prepared_agent") title.textContent = item.previewTitle || (currentLanguage === "ja-JP" ? "Agent の記帳" : currentLanguage === "en-US" ? "Agent entry" : "Agent 记账");
    else if (item.type === "pending_delete") title.textContent = `${currentLanguage === "ja-JP" ? "削除待ち" : currentLanguage === "en-US" ? "Pending deletion" : "待删除"}: ${item.rowSnapshot?.description || item.data?.id || ""}`;
    else if (item.type === "pending_action") title.textContent = item.displayLabel || (currentLanguage === "ja-JP" ? "台帳の変更" : currentLanguage === "en-US" ? "Ledger change" : "账本变更");
    else if (item.type === "transaction") title.textContent = `${item.data.date} · ${item.data.description} · ${item.data.amount} ${item.data.currency}`;
    else if (item.type === "account") title.textContent = `${t("newAccount")}: ${item.data.name}`;
    else title.textContent = `${t("categoryName")}: ${item.data.name}`;
    const detail = document.createElement("small");
    if(item.type==="pending_action") detail.textContent=item.error
      ? (item.serverAccepted ? (currentLanguage==="ja-JP"?"クラウド側の処理状態を確認中です。":currentLanguage==="en-US"?"Cloud task status is being checked.":"云端任务状态待确认；重试会继续同一任务。"):item.dispatchStarted?(currentLanguage==="ja-JP"?"送信結果を確認中です。同じ操作番号で再試行します。":currentLanguage==="en-US"?"Dispatch status is uncertain; retrying with the same operation ID.":"发送结果待确认；重试会沿用同一操作编号。"):"")+" "+item.error
      : item.serverAccepted ? (currentLanguage==="ja-JP"?"クラウドが受け付けました。処理はサーバー側で続き、ページを閉じても中断しません。":currentLanguage==="en-US"?"Accepted by the cloud. Processing continues on the server if you close this page.":"云端已接收，任务会在服务器继续；关闭网页不会中断。")
      : item.dispatchStarted ? (currentLanguage==="ja-JP"?"クラウドの受付を確認中です。確認中は取り消せません。":currentLanguage==="en-US"?"Checking whether the cloud accepted it. Undo is paused until confirmed.":"正在确认云端是否已接收，确认期间不能撤销。")
      : (currentLanguage==="ja-JP"?"端末に保存済みです。クラウド受付前なら取り消せます。":currentLanguage==="en-US"?"Saved on this device. You can undo before cloud acceptance.":"已先保存在本机，正在等待云端接收；接收前可以撤销。");
    else if(item.type==="pending_delete") detail.textContent=item.error
      ? (item.serverAccepted ? (currentLanguage==="ja-JP"?"クラウド側の処理状態を確認中です。":currentLanguage==="en-US"?"Cloud task status is being checked.":"云端任务状态待确认；重试会继续同一任务。"):item.dispatchStarted?(currentLanguage==="ja-JP"?"送信結果を確認中です。同じ操作番号で再試行します。":currentLanguage==="en-US"?"Dispatch status is uncertain; retrying with the same operation ID.":"发送结果待确认；重试会沿用同一操作编号。"):"")+" "+item.error
      : item.serverAccepted ? (currentLanguage==="ja-JP"?"クラウドが受け付けました。バックアップ後に削除します。":currentLanguage==="en-US"?"Accepted by the cloud. It will be backed up and deleted; closing this page will not stop it.":"云端已接收，将在备份后删除；关闭网页不影响任务继续。")
      : item.dispatchStarted ? (currentLanguage==="ja-JP"?"送信結果を確認中です。確認中は取り消せません。":currentLanguage==="en-US"?"Checking dispatch status. Undo is paused until confirmed.":"正在确认云端是否已接收，确认期间不能撤销。")
      : (currentLanguage==="ja-JP"?"送信待ちです。送信前なら取り消せます。":currentLanguage==="en-US"?"Waiting to send. You can undo before dispatch.":"等待发送；发送前可以撤销。");
    else detail.textContent = item.error ? t("syncError", {message:item.error}) : t("queued");
    main.append(title,detail); row.append(main); list.append(row);
    if(item.type==="pending_delete"&&!item.dispatchStarted){
      const undo=document.createElement("button");undo.type="button";undo.className="button text-button";
      undo.dataset.action="queue-undo-delete";undo.dataset.id=item.opId;
      undo.textContent=currentLanguage==="ja-JP"?"取り消す":currentLanguage==="en-US"?"Undo":"撤销";
      row.append(undo);
    }
    if(item.type==="pending_action"&&!item.dispatchStarted&&!item.serverAccepted&&queue.at(-1)?.opId===item.opId){
      const undo=document.createElement("button");undo.type="button";undo.className="button text-button";
      undo.dataset.action="queue-undo-action";undo.dataset.id=item.opId;
      undo.textContent=currentLanguage==="ja-JP"?"取り消す":currentLanguage==="en-US"?"Undo":"撤销";
      row.append(undo);
    }
    if(item.conflict&&item.type==="prepared_agent"){
      const discard=document.createElement("button");discard.type="button";discard.className="button text-button";
      discard.dataset.action="queue-discard";discard.dataset.id=item.opId;
      discard.textContent=currentLanguage==="ja-JP"?"この端末の草稿を破棄":currentLanguage==="en-US"?"Discard local draft":"丢弃本机草稿";
      row.append(discard);
    }
  }
}

async function fetchBootstrap() {
  if(typeof loadWorkspace==="function"){
    const owner=currentUser?.id;
    await loadWorkspace(true);
    if(currentUser?.id!==owner)return;
    if(workspaceError)throw new Error(workspaceError);
    return;
  }
  const owner=currentUser?.id;if(!owner)return;
  const data = await api(`/api/bootstrap?lang=${encodeURIComponent(currentLanguage)}`);
  if(currentUser?.id!==owner)return;
  cachedBootstrap = data;
  await cacheSet(`bootstrap:${owner}`, data);
  await renderAll();
}

let cloudBootstrapFailed = false;
async function establishSession(user) {
  currentUser = user;
  cloudBootstrapFailed = false;
  showSessionPending();
  await cacheSet("identity", user);
  $("#cloudBootstrapBlocked").classList.add("hidden");
  $("#githubSignIn").classList.remove("hidden");
  $("#retryCloudBootstrap").disabled=false;
  try {
    const session = await api("/api/session");
    csrfToken = session.csrfToken || readCookie("hh_csrf");
    await fetchBootstrap();
    serverReachable = true;
  } catch (error) {
    serverReachable = false;
    cachedBootstrap = await cacheGet(`bootstrap:${currentUser.id}`);
    if (!cachedBootstrap) throw error;
    await renderAll();
  }
  showLoggedIn();
  await renderOutbox();
  updateConnection();
  if (serverReachable) setTimeout(() => window.runBackgroundCloudBackup?.("login"), 0);
}

async function initialize() {
  applyLanguage();
  showSessionPending();
  $("#transactionForm [name=date]").value = localDate();
  $("#accountForm [name=openingDate]").value = localDate();
  idb = await openIdb();
  try {
    runtimeConfig = await api("/api/config");
    // GitHub sign-in creates the account after verified authorization.
  } catch { serverReachable = false; }
  try {
    const session = await api("/api/session");
    if (session.user) {
      csrfToken = session.csrfToken || readCookie("hh_csrf");
      await establishSession(session.user);
      return;
    }
    await cacheSet("identity", null);
  } catch {
    serverReachable = false;
    const identity = await cacheGet("identity");
    if (identity) {
      currentUser = identity;
      cachedBootstrap = await cacheGet(`bootstrap:${identity.id}`);
      if (cachedBootstrap) { showLoggedIn(); await renderAll(); updateConnection(); return; }
    }
  }
  showLoggedOut();
}

function newOperation(type, data) {
  const opId = crypto.randomUUID();
  const sequence = Number(localStorage.getItem("hh-operation-sequence") || "0") + 1;
  localStorage.setItem("hh-operation-sequence", String(sequence));
  return {opId,type,data,ownerId:currentUser?.id,createdAt:`${new Date().toISOString()}-${String(sequence).padStart(8,"0")}`,error:""};
}

async function completePendingDelete(item, succeeded, message="") {
  await outboxDelete(item.opId);
  await window.onPendingDeleteFinished?.(item,succeeded,message);
  await renderOutbox();
}

async function sendPendingDelete(item, owner) {
  const started=await outboxStartDispatch(item.opId);
  if(!started)return "removed";
  let serverAccepted=Boolean(started.serverAccepted);
  await window.onPendingDeleteDispatched?.(started);
  let job;
  try {
    if(started.serverAccepted&&started.jobId){
      job=await api("/api/job?id="+encodeURIComponent(started.jobId));
    } else {
      const data={id:started.data.id,confirmed:true};
      if(started.data.baseRevision)data.baseRevision=started.data.baseRevision;
      job=await api("/api/action",{method:"POST",body:JSON.stringify({action:"delete_transaction",data,opId:started.opId})});
      serverAccepted=true;
      const accepted={...started,serverAccepted:true,jobId:job.id||started.opId,serverAcceptedAt:new Date().toISOString(),error:""};
      await outboxPut(accepted);
      await window.onPendingDeleteDispatched?.(accepted);
    }
    while(job?.state==="running"||job?.state==="queued"){
      await new Promise(resolve=>setTimeout(resolve,1000));
      if(currentUser?.id!==owner)return "stopped";
      job=await api("/api/job?id="+encodeURIComponent(job.id||started.opId));
    }
    if(currentUser?.id!==owner)return "stopped";
    if(job?.state!=="done"){
      const message=localizeServerError(job?.result?.error||job?.message||"删除任务未完成。");
      await completePendingDelete(started,false,message);
      const conflict=/云端账本已更新|云端已有更新|版本冲突|revision conflict|newer cloud change/i.test(message);
      showToast(conflict
        ? (currentLanguage==="ja-JP"?"台帳が別の端末で更新されたため、削除を中止しました。最新の台帳を読み直します。":currentLanguage==="en-US"?"The ledger changed on another device. Deletion was cancelled; the latest ledger is being reloaded.":"账本已在其他设备更新，删除已取消；正在刷新最新账本。")
        : (currentLanguage==="ja-JP"?"削除できませんでした。記録を表示に戻しました。":"删除未完成，账目已恢复显示：")+message,true);
      return "stopped";
    }
    await completePendingDelete(started,true);
    return "done";
  } catch(error) {
    const rejectedBeforeAcceptance=!serverAccepted&&error.status>=400&&error.status<500&&![408,429].includes(error.status);
    if(rejectedBeforeAcceptance&&error.status!==401){
      await completePendingDelete(started,false,error.message);
      const conflict=error.status===409||/版本冲突|云端账本已更新|云端已有更新/i.test(error.message);
      showToast(conflict
        ? (currentLanguage==="ja-JP"?"台帳の版が変わったため削除を中止しました。":"账本版本已变化，删除已取消；正在刷新核对。")
        : (currentLanguage==="ja-JP"?"削除要求が受け付けられませんでした。記録を表示に戻しました。":"删除请求未被接收，账目已恢复显示：")+error.message,true);
      return "stopped";
    }
    if(error.status===401&&!serverAccepted){
      await outboxPut({...started,dispatchStarted:false,dispatchStartedAt:"",error:error.message});
      await window.onPendingDeleteDispatched?.({...started,dispatchStarted:false,error:error.message});
      await renderOutbox();
      showToast(error.message,true);
      return "stopped";
    }
    const latest=(await outboxAll()).find(row=>row.opId===item.opId);
    if(latest){await outboxPut({...latest,dispatchStarted:true,error:error.message||"连接中断，云端任务状态待确认。"});await window.onPendingDeleteDispatched?.({...latest,dispatchStarted:true,error:error.message});}
    throw error;
  }
}

async function sendPendingAction(item, owner) {
  const started=await outboxStartDispatch(item.opId);
  if(!started)return "removed";
  let serverAccepted=Boolean(started.serverAccepted);
  await window.onPendingActionDispatched?.(started);
  let job;
  try {
    if(started.serverAccepted&&started.jobId){
      job=await api("/api/job?id="+encodeURIComponent(started.jobId));
    }else{
      job=await api("/api/action",{method:"POST",body:JSON.stringify({action:started.action,data:started.data,opId:started.opId})});
      serverAccepted=true;
      const accepted={...started,serverAccepted:true,jobId:job.id||started.opId,serverAcceptedAt:new Date().toISOString(),error:""};
      delete accepted.data;
      await outboxPut(accepted);
      await window.onPendingActionDispatched?.(accepted);
    }
    let pollFailures=0;
    while(job?.state==="running"||job?.state==="queued"){
      await new Promise(resolve=>setTimeout(resolve,pollFailures?Math.min(1000*2**Math.min(pollFailures-1,3),8000):1000));
      if(currentUser?.id!==owner)return "stopped";
      try{job=await api("/api/job?id="+encodeURIComponent(job.id||started.opId));pollFailures=0;}
      catch(error){
        const retryable=!error.status||[408,429,500,502,503,504].includes(error.status);
        if(!retryable)throw error;
        pollFailures++;
      }
    }
    if(currentUser?.id!==owner)return "stopped";
    if(job?.state!=="done"){
      const message=localizeServerError(job?.result?.error||job?.message||"操作未完成。");
      await outboxDelete(item.opId);
      await window.onPendingActionFinished?.(started,false,message);
      await renderOutbox();
      showToast(message,true);
      return "failed";
    }
    await outboxDelete(item.opId);
    await window.onPendingActionFinished?.(started,true);
    if(job.cloudSnapshotSaved===false||job.result?.cloudSnapshotSaved===false){
      showToast(currentLanguage==="ja-JP"?"変更は反映されましたが、クラウドスナップショットを保存できませんでした。後でバックアップを確認してください。":currentLanguage==="en-US"?"The change was applied, but its cloud snapshot was not saved. Check the backup later.":"更改已完成，但云端快照未保存；请稍后检查备份。",true);
    }
    return "done";
  }catch(error){
    const rejectedBeforeAcceptance=!serverAccepted&&error.status>=400&&error.status<500&&![408,429].includes(error.status);
    if(rejectedBeforeAcceptance&&error.status!==401){
      await outboxDelete(item.opId);
      await window.onPendingActionFinished?.(started,false,error.message);
      showToast(error.message,true);
      return "failed";
    }
    if(error.status===401&&!serverAccepted){
      await outboxPut({...started,dispatchStarted:false,dispatchStartedAt:"",error:error.message});
      await window.onPendingActionDispatched?.({...started,dispatchStarted:false,error:error.message});
      await renderOutbox();showToast(error.message,true);return "stopped";
    }
    const latest=(await outboxAll()).find(row=>row.opId===item.opId);
    if(latest){await outboxPut({...latest,dispatchStarted:true,serverAccepted,error:error.message||"连接中断，云端任务状态待确认。"});await window.onPendingActionDispatched?.({...latest,dispatchStarted:true,serverAccepted,error:error.message});}
    throw error;
  }
}

async function saveOperation(type, data, successMessage) {
  if(window.confirmBeforeQueuedOperation&&!await window.confirmBeforeQueuedOperation())throw new Error(currentLanguage==="ja-JP"?"今回の変更は取り消しました。前の同期が完了してから再度お試しください。":currentLanguage==="en-US"?"This change was cancelled. Try again after the earlier sync finishes.":"已取消本次操作；请等前一项同步完成后再试。");
  const operation = newOperation(type, data);
  await outboxPut(operation);
  await renderOutbox();
  await window.onLocalQueueChanged?.(operation);
  showToast(currentLanguage === "ja-JP" ? "端末に保存しました。クラウドへバックグラウンドで同期します。" : currentLanguage === "en-US" ? "Saved on this device. Syncing to the cloud in the background." : "已先保存在本机，正在后台同步云端。");
  if (navigator.onLine && serverReachable) void syncQueue();
  renderAccounts(); renderCategories();
}

async function syncQueue({manual=false}={}) {
  if (sending || !navigator.onLine || !currentUser) { updateConnection(); return; }
  const queue = (await outboxAll()).sort((a,b) => a.createdAt.localeCompare(b.createdAt));
  if (!queue.length) { syncRetryAttempt=0; updateConnection(); if(manual)showToast(t("nothingToUpload")); return; }
  if(queue.some(item=>item.conflict)){updateConnection();if(manual)showToast(t("uploadConflict"),true);return;}
  if($("#cloudProgressDialog")?.open||$("#actionConfirmDialog")?.open){
    if(!syncRetryTimer)syncRetryTimer=setTimeout(()=>{syncRetryTimer=null;syncQueue();},700);
    if(manual)showToast(t("uploadWaiting"));
    return;
  }
  sending = true; updateConnection();
  try {
    let needsBootstrapRefresh = false;
    let completedDelete = false;
    let completedAction = false;
    let completedActionFailed = false;
    for (let start = 0; start < queue.length; ) {
      const first = queue[start];
      if(first.type==="pending_delete"){
        if(Date.now()<Number(first.notBefore||0)){
          const delay=Math.max(100,Number(first.notBefore)-Date.now());
          if(!syncRetryTimer)syncRetryTimer=setTimeout(()=>{syncRetryTimer=null;void syncQueue();},delay);
          if(manual)showToast(t("uploadWaiting"));
          return;
        }
        if(activeJob){
          if(!syncRetryTimer)syncRetryTimer=setTimeout(()=>{syncRetryTimer=null;void syncQueue();},700);
          if(manual)showToast(t("uploadWaiting"));
          return;
        }
        const result=await sendPendingDelete(first,currentUser.id);
        if(result==="done"){completedDelete=true;needsBootstrapRefresh=true;start++;continue;}
        if(result==="removed"){start++;continue;}
        return;
      }
      if(first.type==="pending_action"){
        if(Date.now()<Number(first.notBefore||0)){
          const delay=Math.max(100,Number(first.notBefore)-Date.now());
          if(!syncRetryTimer)syncRetryTimer=setTimeout(()=>{syncRetryTimer=null;void syncQueue();},delay);
          if(manual)showToast(t("uploadWaiting"));
          return;
        }
        if(activeJob){
          if(!syncRetryTimer)syncRetryTimer=setTimeout(()=>{syncRetryTimer=null;void syncQueue();},700);
          if(manual)showToast(t("uploadWaiting"));
          return;
        }
        const result=await sendPendingAction(first,currentUser.id);
        if(result==="done"){completedAction=true;needsBootstrapRefresh=true;start++;continue;}
        if(result==="failed"){completedActionFailed=true;needsBootstrapRefresh=true;start++;continue;}
        if(result==="removed"){start++;continue;}
        return;
      }
      // Prepared Agent writes are based on one exact cloud revision. Send them
      // alone so two device snapshots can never be layered onto one another.
      let end=start+1;
      if(first.type!=="prepared_agent")while(end<queue.length&&end<start+100&&queue[end].type!=="prepared_agent"&&queue[end].type!=="pending_delete"&&queue[end].type!=="pending_action")end++;
      const batch=queue.slice(start,end);
      const owner = currentUser.id;
      let job = await api("/api/sync", {method:"POST", body:JSON.stringify({operations:batch.map(({opId,type,data,ownerId}) => ({opId,type,data,ownerId}))})});
      while (job.state === "running") {
        await new Promise(resolve => setTimeout(resolve, 1000));
        if (currentUser?.id !== owner) return;
        job = await api("/api/job?id=" + encodeURIComponent(job.id));
      }
      if (job.state !== "done") {
        const message = localizeServerError(job.result?.error || job.message || "同步失败");
        const conflict = /云端账本已更新|云端已有更新|同步冲突|newer cloud change|base revision|revision conflict/i.test(message);
        for (const item of batch) await outboxPut({...item,error:message,conflict});
        await renderOutbox();
        if(conflict)for(const item of batch)if(item.type==="prepared_agent")void window.onPreparedAgentConflict?.({...item,error:message,conflict:true});
        showToast(conflict ? (currentLanguage === "ja-JP" ? "クラウド側に新しい変更があるため同期を停止しました。記録はこの端末に保持しています。" : currentLanguage === "en-US" ? "A newer cloud change was found. Sync paused and the entry remains on this device." : "云端已有更新，已暂停同步；待同步记录仍保留在本机。") : message, true);
        if(!conflict)scheduleSyncRetry();
        return;
      }
      const response = job.result || {};
      if(response.cloudSnapshotSaved===false){const error=new Error(currentLanguage==="ja-JP"?"クラウドスナップショットを保存できませんでした。取引は端末の同期キューに残っています。後でもう一度お試しください。":currentLanguage==="en-US"?"The cloud snapshot was not saved. Entries remain in this device's sync queue; retry later.":"云端快照未保存；记录仍保留在本机待同步队列，请稍后重试。");error.cloudSnapshotFailed=true;throw error;}
      const results = new Map((response.results || []).map(item => [item.opId,item]));
      for (const item of batch) {
        const result = results.get(item.opId);
        if (result?.ok) {
          if (item.type === "prepared_agent") await window.onPreparedAgentSynced?.(item, response.revision || "");
          else { window.onLocalQueueSynced?.(item); needsBootstrapRefresh = true; }
          await outboxDelete(item.opId);
        } else if (result) {
          const message=localizeServerError(result.error || "同步失败"),conflict=/云端账本已更新|云端已有更新|同步冲突|newer cloud change|base revision|revision conflict/i.test(message);
          await outboxPut({...item,error:message,conflict});
          if(conflict&&item.type==="prepared_agent")void window.onPreparedAgentConflict?.({...item,error:message,conflict:true});
        }
      }
      start += batch.length;
    }
    const remaining = await outboxAll();
    if (!remaining.length) {
      syncRetryAttempt=0;
      if (needsBootstrapRefresh) {
        try { await fetchBootstrap(); }
        catch { showToast(t("uploadRefreshFailed"),true); return; }
      }
      if(completedActionFailed){
        // The rejected action already showed its error and restored the local view.
      }else if(completedAction){
        showToast(currentLanguage==="ja-JP"?"変更をクラウドに同期しました。":currentLanguage==="en-US"?"Changes synced to the cloud.":"更改已同步到云端。");
      }else showToast(completedDelete
        ? (currentLanguage==="ja-JP"?"削除が完了しました。実行前のバックアップを保存しました。":currentLanguage==="en-US"?"Deletion completed. A pre-delete backup was saved.":"删除已完成，删除前备份已保留。")
        : manual ? t("uploadComplete") : t("synced"));
    } else {
      await renderOutbox();
      if (!remaining.some(item=>item.conflict)) { showToast(t("syncFailed"), true); scheduleSyncRetry(); }
    }
  } catch (error) {
    if (error.cloudSnapshotFailed) {
      const latest = await outboxAll();
      await Promise.all(latest.map(item => outboxPut({...item,error:error.message})));
      await renderOutbox();
      showToast(error.message,true);
      scheduleSyncRetry();
      return;
    }
    serverReachable = false;
    const latest = await outboxAll();
    await Promise.all(latest.map(item => outboxPut({...item,error:error.message || "offline"})));
    await renderOutbox();
    showToast(t("networkUnavailable"), true);
    scheduleSyncRetry();
  } finally {
    sending = false; updateConnection(); await renderOutbox();
    if (!pendingSyncCount && serverReachable && navigator.onLine) void window.runBackgroundCloudBackup?.("write");
  }
}

async function postAuth(path, data) {
  const result = await api(path, {method:"POST",body:JSON.stringify(data)});
  return result;
}

async function handleImport(file) {
  if (!file) return;
  if ((await outboxAll()).length) {
    const message = currentLanguage === "ja-JP" ? "未同期の記録を先に同期してから、台帳を取り込んでください。" : currentLanguage === "en-US" ? "Sync pending entries before importing a ledger." : "请先同步本机待处理记录，再导入桌面账本。";
    showToast(message,true); $("#ledgerFile").value=""; return;
  }
  if (!await confirmOnce(t("importDesktop"),t("importConfirm"))) { $("#ledgerFile").value=""; return; }
  const button = $("#ledgerFile").closest("label"); button.classList.add("disabled");
  showCloudProgress(t("importing"), currentLanguage === "ja-JP" ? "台帳ファイルをサーバーに送信しています。完了まで操作しないでください。" : currentLanguage === "en-US" ? "Uploading the ledger file to the server. Please wait and do not repeat the action." : "正在把账本文件上传到服务器，请勿重复点击或关闭页面。");
  try {
    const result = await api("/api/import-ledger", {method:"POST",body:file,headers:{"Content-Type":"application/vnd.sqlite3"}});
    await fetchBootstrap();
    void window.runBackgroundCloudBackup?.("write");
    showToast(t("importDone", result));
  } catch (error) {
    showToast(`${t("importError")} ${error.message}`, true);
  } finally { button.classList.remove("disabled"); $("#ledgerFile").value=""; hideCloudProgress(); }
}

async function exportLedger() {
  try {
    const response = await fetch("/api/export-ledger", {credentials:"same-origin",cache:"no-store"});
    if (!response.ok) { const data=await response.json().catch(()=>({})); throw new Error(data.error || `HTTP ${response.status}`); }
    const blob = await response.blob();
    const link = document.createElement("a");
    const disposition = response.headers.get("Content-Disposition") || "";
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] || "household-ledger.sqlite3";
    link.href = URL.createObjectURL(blob); link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    serverReachable = true; updateConnection();
  } catch (error) { showToast(error.message,true); }
}

function setupEvents() {
  $$(".auth-tab").forEach(button => button.addEventListener("click", () => showAuthTab(button.dataset.authTab)));
  $("#loginForm")?.addEventListener("submit", async event => {
    event.preventDefault(); setAuthMessage("");
    const form = new FormData(event.currentTarget);
    try { const result = await postAuth("/api/login", {username:form.get("username"),password:form.get("password")}); await establishSession(result.user); }
    catch (error) { setAuthMessage(error.message, true); }
  });
  $("#recoverForm")?.addEventListener("submit", async event => {
    event.preventDefault(); setAuthMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await postAuth("/api/recover", {username:form.get("username"),recoveryCode:form.get("recoveryCode"),newPassword:form.get("newPassword")});
      $("#recoveryCodeDisplay").textContent = result.recoveryCode;
      $("#recoveryDialog").showModal();
      setAuthMessage(currentLanguage === "ja-JP" ? "パスワードを再設定しました。新しい復旧コードを保存してください。" : currentLanguage === "en-US" ? "Password reset. Save the new recovery code." : result.message);
    } catch (error) { setAuthMessage(error.message, true); }
  });
  $("#copyRecovery").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("#recoveryCodeDisplay").textContent); showToast(t("copy")); }
    catch { showToast($("#recoveryCodeDisplay").textContent); }
  });
  $("#closeRecovery").addEventListener("click", () => $("#recoveryDialog").close());
  document.addEventListener("change", async event => {
    const languageSelect=event.target;
    if(!["languageSelect","authLanguageSelect"].includes(languageSelect?.id))return;
    const next=languageSelect.value;
    if(languageSelect.id==="languageSelect"&&currentUser && typeof chats!=="undefined") {
      if(!confirm(currentLanguage==="ja-JP"?"言語を変更すると会話と未送信入力をクリアします。続行しますか？":currentLanguage==="en-US"?"Changing language clears chats and unsent input. Continue?":"切换语言会清空对话和未发送的内容，继续吗？")){languageSelect.value=currentLanguage;return;}
      try { for(const agent of ["bookkeeping","food_health"]) await runAction("agent_reset",{agent},null,false); }
      catch(error){languageSelect.value=currentLanguage;showToast(error.message,true);return;}
      chats={bookkeeping:[],food_health:[]};attachments=[];for(const agent of ["bookkeeping","food_health"]) await cacheSet("chat:"+currentUser.id+":"+agent,[]);
    }
    currentLanguage = next; localStorage.setItem("hh-language",currentLanguage); applyLanguage();
    if (currentUser && serverReachable) try { await fetchBootstrap(); } catch {}
  });
  $("#syncButton").addEventListener("click", () => { void syncQueue({manual:true}); });
  $("#logoutButton").addEventListener("click", async () => {
    if (!navigator.onLine || !serverReachable) { showToast(t("logoutOffline"),true); return; }
    if ((await outboxAll()).length) {
      await syncQueue();
      if ((await outboxAll()).length) {
        const message = currentLanguage === "ja-JP" ? "未同期の記録があるためログアウトできません。同期を完了してから再度お試しください。" : currentLanguage === "en-US" ? "Sign out is paused because entries are still waiting to sync. Sync them first." : "还有记录尚未同步，为避免丢失，暂不退出。请先完成同步后再试。";
        showToast(message,true); return;
      }
    }
    try { await api("/api/logout",{method:"POST",body:"{}"}); }
    catch (error) { showToast(error.message,true); return; }
    await cacheSet("identity",null);
    await new Promise(resolve => { const tx=idb.transaction(["outbox","cache"],"readwrite"); tx.objectStore("outbox").clear(); tx.objectStore("cache").clear(); tx.oncomplete=resolve; });
    currentUser=null; cachedBootstrap=null; csrfToken=""; serverReachable=true; showLoggedOut();
  });
  $$(".segmented button").forEach(button => button.addEventListener("click", async () => {
    selectedKind = button.dataset.kind;
    $("#transactionForm [name=kind]").value = selectedKind;
    $$(".segmented button").forEach(item => item.classList.toggle("selected",item===button));
    await renderCategories(); updateTransactionCurrency();
  }));
  $("#transactionForm [name=accountName]").addEventListener("change", updateTransactionCurrency);
  $("#transactionForm [name=toAccountName]").addEventListener("change", updateTransactionCurrency);
  $("#transactionForm").addEventListener("submit", async event => {
    event.preventDefault();
    const target = event.currentTarget;
    if (target.dataset.saving) return;
    target.dataset.saving = "1";
    const submit = target.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      const form = new FormData(target);
      const amount = String(form.get("amount")||"").trim();
      if (!amount || !Number.isFinite(Number(amount)) || Number(amount) <= 0) { showToast(t("amountRequired"),true); return; }
      const sourceName = String(form.get("accountName")||"");
      const source = cachedBootstrap?.accounts?.find(a => a.name===sourceName) || (await localAccountsAndCategories()).accounts.find(a => a.name===sourceName);
      if (!source) { showToast(t("needsAccount"),true); return; }
      const data = {kind:selectedKind,date:form.get("date"),amount,currency:source.currency,description:String(form.get("description")||"").trim(),accountName:sourceName};
      if (selectedKind !== "transfer") data.categoryName = String(form.get("categoryName")||"");
      else { data.toAccountName=String(form.get("toAccountName")||""); data.toAmount=String(form.get("toAmount")||"").trim(); }
      if (!data.description) { showToast(t("description"),true); return; }
      await saveOperation("transaction",data,t("successTransaction"));
      target.reset();
      target.querySelector("[name=date]").value=localDate();
      target.querySelector("[name=kind]").value=selectedKind;
      await renderAccounts(); await renderCategories();
    } catch (error) {
      showToast(error.message || t("networkUnavailable"),true);
    } finally {
      delete target.dataset.saving;
      submit.disabled = false;
    }
  });
  $("#showAccountForm").addEventListener("click", () => {
    const form=$("#accountForm");form.classList.toggle("hidden");
    if(!form.classList.contains("hidden"))requestAnimationFrame(()=>form.scrollIntoView({behavior:"smooth",block:"center"}));
  });
  $("#cancelAccount").addEventListener("click", () => $("#accountForm").classList.add("hidden"));
  $("#accountForm").addEventListener("submit", async event => {
    event.preventDefault(); const target=event.currentTarget;
    if (target.dataset.saving) return;
    target.dataset.saving="1"; const submit=target.querySelector("button[type=submit]"); submit.disabled=true;
    try {
      const form=new FormData(target);
      const data={name:String(form.get("name")).trim(),type:form.get("type"),currency:form.get("currency"),openingBalance:String(form.get("openingBalance")).trim(),openingDate:form.get("openingDate"),completeness:form.get("completeness"),note:""};
      await saveOperation("account",data,t("successAccount"));
      target.reset(); target.querySelector("[name=openingDate]").value=localDate(); target.classList.add("hidden");
    } catch (error) { showToast(error.message || t("networkUnavailable"),true); }
    finally { delete target.dataset.saving; submit.disabled=false; }
  });
  $("#showCategoryForm").addEventListener("click", () => { $("#categoryForm [name=kind]").value=selectedKind==="transfer"?"expense":selectedKind; $("#categoryForm").classList.toggle("hidden"); });
  $("#cancelCategory").addEventListener("click", () => $("#categoryForm").classList.add("hidden"));
  $("#categoryForm").addEventListener("submit", async event => {
    event.preventDefault(); const target=event.currentTarget;
    if (target.dataset.saving) return;
    target.dataset.saving="1"; const submit=target.querySelector("button[type=submit]"); submit.disabled=true;
    try {
      const form=new FormData(target);
      await saveOperation("category",{name:String(form.get("name")).trim(),kind:form.get("kind")},t("successCategory"));
      target.reset(); target.classList.add("hidden"); await renderCategories();
    } catch (error) { showToast(error.message || t("networkUnavailable"),true); }
    finally { delete target.dataset.saving; submit.disabled=false; }
  });
  $("#ledgerFile").addEventListener("change", event => handleImport(event.target.files?.[0]));
  $("#exportLedger").addEventListener("click", exportLedger);
  window.addEventListener("online", () => { updateConnection(); syncQueue(); });
  window.addEventListener("offline", updateConnection);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) syncQueue(); });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
}

setupEvents();
const appInitialization = initialize().catch(error => { serverReachable=false; showLoggedOut(); setAuthMessage(error.message || t("networkHint"),true); });
