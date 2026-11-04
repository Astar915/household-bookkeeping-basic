"use strict";

const githubWords = {
  title:["选择登录方式","ログイン方法を選択","Choose a sign-in method"],
  intro:["GitHub 或 Gitee 均可独立登录。首次使用某个身份会创建独立账本；已关联的身份会进入同一账本。开启自动云备份后，登录会在后台备份当前网页版账本，不会自动下载或替换账本。","GitHubとGiteeはどちらも単独でログインできます。初回利用時はそのID専用の台帳を作成し、連携済みのIDは同じ台帳を開きます。自動クラウドバックアップが有効な場合、ログイン後にWeb版台帳をバックアップします。自動取得や置き換えは行いません。","Sign in with GitHub or Gitee independently. First use creates a separate ledger; linked identities open the same ledger. If automatic cloud backup is enabled, sign-in backs up the current web ledger in the background. It never downloads or replaces the ledger automatically."],
  signIn:["使用 GitHub 登录","GitHubでログイン","Continue with GitHub"],
  linkGithub:["关联 GitHub","GitHubを連携","Link GitHub"],
  linkingGithub:["正在关联 GitHub…","GitHubを連携中…","Linking GitHub…"],
  linkedGithub:["GitHub 已关联到当前账本。","GitHubを現在の台帳に連携しました。","GitHub is now linked to this ledger."],
  reconnectBackup:["重新连接 GitHub 备份","GitHubバックアップに再接続","Reconnect GitHub backup"],
  privacy:["密码只在 GitHub 或 Gitee 页面输入；网站不收集密码。开启自动云备份后，登录会在后台备份当前网页版账本，不会自动下载或替换账本。","パスワードはGitHubまたはGiteeの画面で入力します。サイトはパスワードを収集しません。自動クラウドバックアップが有効な場合、ログイン後にWeb版台帳をバックアップし、自動取得や置き換えは行いません。","Enter your password only on GitHub or Gitee. This site never collects it. If automatic cloud backup is enabled, sign-in backs up the current web ledger in the background; it never downloads or replaces the ledger automatically."],
  instructions:["复制临时授权码，在 GitHub 验证页输入并确认，再返回这里。","一時コードをコピーしてGitHubの認証画面で入力し、承認後に戻ってください。","Copy this temporary code, enter it on GitHub and approve, then return here."],
  copyCode:["复制授权码","コードをコピー","Copy code"],
  openGithub:["打开 GitHub 授权","GitHubの認証を開く","Open GitHub authorization"],
  cancel:["取消登录","ログインを中止","Cancel sign-in"],
  restoreRequired:["网页版账本暂未载入","Web版台帳をまだ読み込めていません","The web ledger has not loaded yet"],
  retryDownload:["重试载入账本","台帳の読み込みを再試行","Retry loading ledger"],
  restoreAfterConflict:["先备份当前账本后下载云端账本","現在の台帳をバックアップしてからクラウド台帳を取得","Back up the current ledger, then download the cloud ledger"],
  confirmRestoreAfterConflict:["将先创建当前账本的完整恢复备份，再用 GitHub 云端账本替换当前账本。确定继续？","現在の台帳を完全バックアップしてから、GitHubの台帳で置き換えます。続けますか？","A full recovery backup of the current ledger will be created before it is replaced with the GitHub ledger. Continue?"],
  restoringCloud:["正在备份当前账本并下载 GitHub 云端版本…","現在の台帳をバックアップし、GitHubから取得中…","Backing up the current ledger and downloading the GitHub version…"],
  restoredCloud:["云端账本已恢复，恢复前的账本备份已保留。","クラウド台帳を復元しました。復元前のバックアップも保存されています。","Cloud ledger restored. A backup of the previous ledger was kept."],
  pendingOutbox:["当前设备还有待同步记录，已停止恢复，避免覆盖。请先完成同步后再试。","この端末に未同期の記録があるため復元を停止しました。同期後に再試行してください。","Restore stopped because this device has unsynced entries. Sync them before trying again."],
  starting:["正在连接 GitHub…","GitHubに接続中…","Connecting to GitHub…"],
  waiting:["等待 GitHub 授权，完成后会自动进入账本。","GitHubの承認を待っています。完了後、台帳を開きます。","Waiting for GitHub authorization. Your ledger will open automatically."],
  reconnecting:["连接暂时中断，返回页面后会继续检查。","接続が中断されました。画面に戻ると再確認します。","Connection interrupted. Return to this page to resume."],
  done:["GitHub 登录成功","GitHubでログインしました","Signed in with GitHub"],
  error:["GitHub 登录未完成，请重新发起并在 GitHub 确认授权。","GitHubログインが完了しませんでした。再度開始してGitHubで承認してください。","GitHub sign-in did not complete. Start again and approve on GitHub."],
};
const githubAuthErrors = {
  "GitHub 续期授权与当前应用不匹配；请重新连接 GitHub。":["GitHub 续期授权与当前应用不匹配；请重新连接 GitHub。","GitHubの更新認証が現在のアプリと一致しません。GitHubに再接続してください。","GitHub token renewal does not match this app. Reconnect GitHub."],
  "GitHub 刷新令牌已过期；请重新连接 GitHub。":["GitHub 刷新令牌已过期；请重新连接 GitHub。","GitHubの更新トークンが失効しました。GitHubに再接続してください。","The GitHub refresh token has expired. Reconnect GitHub."],
  "登录账号已变化，请刷新页面后再操作，待同步记录仍然保留。":["登录账号已变化，请刷新页面后再操作，待同步记录仍然保留。","ログインアカウントが変わりました。画面を更新してください。未同期記録は保持されています。","The signed-in account changed. Refresh before continuing; pending entries are retained."],
  "待同步记录属于另一个账号，已停止写入。":["待同步记录属于另一个账号，已停止写入。","未同期記録は別アカウントのため、書き込みを停止しました。","These pending entries belong to another account, so posting was stopped."],
  "GitHub 登录已过期，请重新开始。":["GitHub 登录已过期，请重新开始。","GitHubログインの有効期限が切れました。再度開始してください。","GitHub sign-in expired. Please start again."],
  "GitHub 登录请求过多，请稍后再试。":["GitHub 登录请求过多，请稍后再试。","GitHubログインのリクエストが多すぎます。しばらくして再試行してください。","Too many GitHub sign-in requests. Please try again later."],
  "GitHub 授权地址校验失败，请稍后再试。":["GitHub 授权地址校验失败，请稍后再试。","GitHub認証先を確認できません。後で再試行してください。","The GitHub verification address could not be validated. Try again later."],
  "请先在 GitHub 完成授权。":["请先在 GitHub 完成授权。","先にGitHubで認証を完了してください。","Complete authorization on GitHub first."],
  "原账号会话已变化，请重新验证原账号后关联。":["原账号会话已变化，请重新验证原账号后关联。","旧アカウントのセッションが変わりました。再確認してから連携してください。","The old-account session changed. Verify it again before linking."],
  "这个 GitHub 已关联另一份账本。当前账本保持不变，请使用原关联账号。":["这个 GitHub 已关联另一份账本。当前账本保持不变，请使用原关联账号。","このGitHubは別の台帳に連携済みです。現在のデータは保持されます。元の連携アカウントを使用してください。","This GitHub account is linked to another ledger. This ledger is unchanged; use its original linked account."],
  "当前账本已关联其他 GitHub，不能直接替换。":["当前账本已关联其他 GitHub，不能直接替换。","この台帳は別のGitHubに連携済みで、直接変更できません。","This ledger is already linked to another GitHub account and cannot be reassigned here."],
  "原账号不存在，请重新登录。":["原账号不存在，请重新登录。","旧アカウントが見つかりません。再度ログインしてください。","The old account was not found. Please sign in again."],
  "找不到账号账本，请检查服务备份。":["找不到账号账本，请检查服务备份。","台帳が見つかりません。サービスのバックアップを確認してください。","The account ledger is missing. Check the service backups."],
  "已改为使用 GitHub 登录，无需注册。":["已改为使用 GitHub 登录，无需注册。","GitHubログインに変更されました。新規登録は不要です。","Use GitHub sign-in. No app registration is needed."],
};
const previousGithubError=localizeServerError;
localizeServerError=function(message){const values=githubAuthErrors[String(message)];return values?m(...values):previousGithubError(message);};
const ghText = key => m(...githubWords[key]);
let githubLoginFlow=null, githubPolling=false, githubStarting=false, githubTimer=null;
const githubDialog=document.createElement("dialog");
githubDialog.id="githubAuthDialog";githubDialog.className="dialog-card github-auth-dialog";
githubDialog.append($("#githubLoginProgress"));document.body.append(githubDialog);

function renderGithubLogin() {
  $$("[data-gh-text]").forEach(node=>node.textContent=ghText(node.dataset.ghText));
  $("#githubSignIn").disabled=githubStarting||!!githubLoginFlow;
  if(githubStarting)$("#githubSignIn").textContent=ghText("starting");
  else $("#githubSignIn").textContent=ghText("signIn");
  const linkGithub=$("#linkGithubButton");
  linkGithub.classList.toggle("hidden",!currentUser||currentUser.authProvider!=="gitee"||currentUser.githubLinked===true);
  linkGithub.disabled=githubStarting||!!githubLoginFlow;
  linkGithub.textContent=githubStarting&&githubLoginFlow?.mode==="link"?ghText("linkingGithub"):ghText("linkGithub");
  renderSessionStatus();
}
function rememberGithubFlow(flow) {
  githubLoginFlow=flow;
  if(flow)localStorage.setItem("hh-github-sign-in",JSON.stringify({flowId:flow.flowId,mode:flow.mode}));
  else localStorage.removeItem("hh-github-sign-in");
  renderGithubLogin();
}
function showGithubFlow(flow) {
  if(flow.userCode)$("#githubLoginCode").textContent=flow.userCode;
  $("#githubLoginProgress").classList.remove("hidden");
  $("#githubLoginState").textContent=ghText("waiting");
  if(!githubDialog.open)githubDialog.showModal();
}
async function startGithubLogin(mode="login") {
  if(githubStarting||githubLoginFlow)return;
  githubStarting=true;renderGithubLogin();setAuthMessage("");
  try {
    const flow=await api("/api/auth/github/start",{method:"POST",body:JSON.stringify({mode})});
    rememberGithubFlow({...flow,mode});showGithubFlow(flow);pollGithubLogin();
  }catch(error){if(currentUser)showCloudBootstrapBlocked(error.message);else setAuthMessage(error.message,true);showToast(error.message,true);}
  finally{githubStarting=false;renderGithubLogin();}
}
async function pollGithubLogin() {
  if(githubPolling||!githubLoginFlow)return;
  clearTimeout(githubTimer);githubPolling=true;
  const flow=githubLoginFlow;
  try {
    const status=await api("/api/auth/github/status",{method:"POST",body:JSON.stringify({flowId:flow.flowId})});
    if(githubLoginFlow?.flowId!==flow.flowId)return;
    if(status.state==="failed")throw new Error(ghText("error"));
    if(status.state==="authorized") {
      const result=await api("/api/auth/github/finish",{method:"POST",body:JSON.stringify({flowId:flow.flowId})});
      rememberGithubFlow(null);githubDialog.close();
      await establishSession(result.user);renderGithubLogin();if(!cloudBootstrapFailed)showToast(flow.mode==="link"?ghText("linkedGithub"):ghText("done"));
    }else{showGithubFlow(status);githubTimer=setTimeout(pollGithubLogin,1500);}
  }catch(error){
    if(githubLoginFlow?.flowId!==flow.flowId)return;
    if(error instanceof TypeError||!navigator.onLine){$("#githubLoginState").textContent=ghText("reconnecting");githubTimer=setTimeout(pollGithubLogin,3500);}
    else{rememberGithubFlow(null);githubDialog.close();setAuthMessage(error.message,true);showToast(error.message,true);}
  }finally{githubPolling=false;if(githubLoginFlow&&githubLoginFlow.flowId!==flow.flowId)githubTimer=setTimeout(pollGithubLogin,0);}
}
async function cancelGithubLogin() {
  const flow=githubLoginFlow;rememberGithubFlow(null);clearTimeout(githubTimer);githubDialog.close();
  if(flow)try{await api("/api/auth/github/cancel",{method:"POST",body:JSON.stringify({flowId:flow.flowId})});}catch{}
}
$("#githubSignIn").onclick=()=>startGithubLogin();
$("#linkGithubButton").onclick=()=>startGithubLogin("link");
$("#reconnectGithubBackup").onclick=()=>startGithubLogin();
$("#githubCancelLogin").onclick=cancelGithubLogin;
$("#githubCopyCode").onclick=async()=>{try{await navigator.clipboard.writeText($("#githubLoginCode").textContent);showToast(t("copy"));}catch{showToast($("#githubLoginCode").textContent);}};
githubDialog.addEventListener("cancel",event=>{event.preventDefault();cancelGithubLogin();});
document.addEventListener("visibilitychange",()=>{if(!document.hidden)pollGithubLogin();});
window.addEventListener("online",pollGithubLogin);
const beforeGithubLanguage=applyLanguage;
applyLanguage=function(){beforeGithubLanguage();renderGithubLogin();};
const beforeGithubShowIn=showLoggedIn;
showLoggedIn=function(){beforeGithubShowIn();renderGithubLogin();};
const beforeGithubShowOut=showLoggedOut;
showLoggedOut=function(){beforeGithubShowOut();renderGithubLogin();};
renderGithubLogin();
appInitialization.then(()=>{
  renderGithubLogin();if(currentUser&&!cloudBootstrapFailed)loadWorkspace();
  try{const saved=JSON.parse(localStorage.getItem("hh-github-sign-in")||"null");if(saved?.flowId){rememberGithubFlow(saved);pollGithubLogin();}}catch{}
});

$("#retryCloudBootstrap").onclick=async()=>{
  if(!currentUser)return;
  $("#retryCloudBootstrap").disabled=true;
  $("#cloudBootstrapError").textContent=currentLanguage==="ja-JP"?"クラウドを確認しています…":currentLanguage==="en-US"?"Checking the cloud backup…":"正在重新检查云端账本…";
  try{await establishSession(currentUser);}
  catch(error){$("#cloudBootstrapError").textContent=error.message;}
  finally{$("#retryCloudBootstrap").disabled=false;}
};

$("#restoreCloudAfterConflict").onclick=async()=>{
  if(!currentUser||$("#restoreCloudAfterConflict").disabled)return;
  const owner=currentUser.id;
  if(!window.confirm(ghText("confirmRestoreAfterConflict")))return;
  $("#restoreCloudAfterConflict").disabled=true;
  $("#retryCloudBootstrap").disabled=true;
  try{
    if((await outboxAll()).length){
      $("#cloudBootstrapError").textContent=ghText("pendingOutbox");
      return;
    }
    if(currentUser?.id!==owner)return;
    $("#cloudBootstrapError").textContent=ghText("restoringCloud");
    await runAction("cloud_restore",{provider:"github",confirmed:true},null,false);
    if(currentUser?.id!==owner)return;
    for(const agent of ["bookkeeping","food_health"])await cacheSet("chat:"+owner+":"+agent,[]);
    window.onCloudLedgerRestored?.();
    await establishSession(currentUser);
    if(cloudBootstrapFailed)throw new Error($("#cloudBootstrapError").textContent);
    showToast(ghText("restoredCloud"));
  }catch(error){
    if(currentUser?.id===owner)$("#cloudBootstrapError").textContent=error.message;
  }finally{
    if(currentUser?.id===owner){
      $("#restoreCloudAfterConflict").disabled=false;
      $("#retryCloudBootstrap").disabled=false;
    }
  }
};
