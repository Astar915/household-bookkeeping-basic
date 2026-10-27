"use strict";

const githubWords = {
  title:["一个 GitHub 账号，就能开始","GitHubアカウントですぐに開始","Your GitHub account. Your ledger."],
  intro:["首次授权自动建立你的私人账本，以后在其他设备使用同一个 GitHub 登录即可。","初回認証で専用の台帳を作成。同じGitHubアカウントで別の端末からもログインできます。","First authorization creates your private ledger. Use the same GitHub account on your other devices."],
  signIn:["使用 GitHub 登录","GitHubでログイン","Continue with GitHub"],
  privacy:["密码只在 GitHub 页面输入；登录不会上传或覆盖云备份。","パスワードはGitHubでのみ入力。ログインだけでクラウドを上書きしません。","Enter your password only on GitHub. Signing in never uploads or replaces a cloud backup."],
  instructions:["复制临时授权码，在 GitHub 验证页输入并确认，再返回这里。","一時コードをコピーしてGitHubの認証画面で入力し、承認後に戻ってください。","Copy this temporary code, enter it on GitHub and approve, then return here."],
  copyCode:["复制授权码","コードをコピー","Copy code"],
  openGithub:["打开 GitHub 授权","GitHubの認証を開く","Open GitHub authorization"],
  cancel:["取消登录","ログインを中止","Cancel sign-in"],
  legacyTitle:["已有旧账号？迁移原账本","以前のアカウントから台帳を移行","Have an old account? Keep your ledger"],
  legacyHelp:["先验证原账号，再关联 GitHub，保留原来的账目和设置。新用户直接使用上方 GitHub 登录。","旧アカウントを確認してからGitHubを連携し、既存データを保持します。新規の方は上のGitHubログインを使用してください。","Verify your old account, then link GitHub to retain entries and settings. New users can sign in with GitHub above."],
  legacyPassword:["原账号密码","旧パスワード","Old password"],
  legacyRecovery:["原账号恢复码","旧復旧コード","Old recovery code"],
  verifyLegacy:["验证原账号并保留账本","旧アカウントを確認して台帳を保持","Verify old account and keep ledger"],
  linkHelp:["关联 GitHub 后，以后直接使用 GitHub 登录，当前账本和设置会保留。","GitHubを連携すると今後GitHubでログインできます。現在の台帳と設定は保持します。","Link GitHub to sign in with it from now on, keeping this ledger and its settings."],
  linkButton:["关联 GitHub，保留当前账本","GitHubを連携して現在の台帳を保持","Link GitHub and keep this ledger"],
  starting:["正在连接 GitHub…","GitHubに接続中…","Connecting to GitHub…"],
  waiting:["等待 GitHub 授权，完成后会自动进入账本。","GitHubの承認を待っています。完了後、台帳を開きます。","Waiting for GitHub authorization. Your ledger will open automatically."],
  reconnecting:["连接暂时中断，返回页面后会继续检查。","接続が中断されました。画面に戻ると再確認します。","Connection interrupted. Return to this page to resume."],
  done:["GitHub 登录成功","GitHubでログインしました","Signed in with GitHub"],
  error:["GitHub 登录未完成，请重新发起并在 GitHub 确认授权。","GitHubログインが完了しませんでした。再度開始してGitHubで承認してください。","GitHub sign-in did not complete. Start again and approve on GitHub."],
};
const githubAuthErrors = {
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
  $("#githubLinkLegacy").disabled=githubStarting||!!githubLoginFlow;
  $("#githubLinkBanner").classList.toggle("hidden",!currentUser||currentUser.authProvider==="github");
  if(githubStarting)$("#githubSignIn").textContent=ghText("starting");
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
  }catch(error){setAuthMessage(error.message,true);showToast(error.message,true);}
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
      await establishSession(result.user);renderGithubLogin();showToast(ghText("done"));
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
$("#githubLinkLegacy").onclick=()=>startGithubLogin("link");
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
  renderGithubLogin();if(currentUser)loadWorkspace();
  try{const saved=JSON.parse(localStorage.getItem("hh-github-sign-in")||"null");if(saved?.flowId){rememberGithubFlow(saved);pollGithubLogin();}}catch{}
});
