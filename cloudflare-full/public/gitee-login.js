"use strict";

const giteeStarting = {login:false,link:false};
const giteeText = (zh,ja,en) => m(zh,ja,en);

function renderGiteeButtons() {
  const enabled = runtimeConfig?.giteeAuthEnabled === true;
  const signIn = $("#giteeSignIn");
  const link = $("#linkGiteeButton");
  $("#githubAuthTitle").textContent = enabled
    ? giteeText("选择登录方式","ログイン方法を選択","Choose a sign-in method")
    : giteeText("一个 GitHub 账号，就能开始","GitHubアカウントですぐに開始","Your GitHub account. Your ledger.");
  $("#githubAuthIntro").textContent = enabled
    ? giteeText("GitHub 或 Gitee 均可独立登录。首次使用某个身份会创建独立账本；已关联的身份会进入同一账本。想共用已有账本，请先用原登录方式进入，再关联另一身份。","GitHubとGiteeはどちらも単独でログインできます。初回利用時は専用台帳を作成し、連携済みのIDは同じ台帳を開きます。既存台帳を共有する場合は、元のログイン方法で入り、もう一方のIDを連携してください。","GitHub and Gitee can each sign in independently. First use creates a separate ledger; linked identities open the same ledger. To share an existing ledger, sign in with its current method and link the other identity.")
    : giteeText("首次授权会建立你的私人账本；以后在其他设备使用同一个 GitHub 登录即可。","初回認証で専用の台帳を作成。同じGitHubアカウントで別の端末からもログインできます。","First authorization creates your private ledger. Use the same GitHub account on your other devices.");
  $("[data-gh-text='privacy']").textContent = enabled
    ? giteeText("密码只在 GitHub 或 Gitee 页面输入；网站不收集密码。开启自动云备份后，登录会在后台备份当前网页版账本，不会自动下载或替换账本。","パスワードはGitHubまたはGiteeの画面で入力します。サイトはパスワードを収集しません。自動クラウドバックアップが有効な場合、ログイン後にWeb版台帳をバックアップし、自動取得や置き換えは行いません。","Enter your password only on GitHub or Gitee. This site never collects it. If automatic cloud backup is enabled, sign-in backs up the current web ledger in the background; it never downloads or replaces the ledger automatically.")
    : giteeText("密码只在 GitHub 页面输入；网站不收集密码。开启自动云备份后，登录会在后台备份当前网页版账本，不会自动下载或替换账本。","パスワードはGitHubでのみ入力します。サイトはパスワードを収集しません。自動クラウドバックアップが有効な場合、ログイン後にWeb版台帳をバックアップし、自動取得や置き換えは行いません。","Enter your password only on GitHub. This site never collects it. If automatic cloud backup is enabled, sign-in backs up the current web ledger in the background; it never downloads or replaces the ledger automatically.");
  signIn.classList.toggle("hidden",!enabled);
  signIn.disabled = giteeStarting.login;
  signIn.textContent = giteeStarting.login
    ? giteeText("正在连接 Gitee…","Giteeに接続中…","Connecting to Gitee…")
    : giteeText("使用 Gitee 登录","Giteeでログイン","Continue with Gitee");
  link.classList.toggle("hidden",!enabled||!currentUser||currentUser.giteeLinked===true);
  link.disabled = giteeStarting.link;
  link.textContent = giteeStarting.link
    ? giteeText("正在关联…","連携中…","Linking…")
    : giteeText("关联 Gitee","Giteeを連携","Link Gitee");
}

async function startGiteeOAuth(mode) {
  if(giteeStarting[mode])return;
  giteeStarting[mode]=true;renderGiteeButtons();
  if(mode==="login")setAuthMessage("");
  try {
    const result=await api("/api/auth/gitee/start",{
      method:"POST",
      body:JSON.stringify({mode}),
    });
    if(!result.authorizationUrl)throw new Error(giteeText("Gitee 登录未能启动，请稍后重试。","Giteeログインを開始できませんでした。後でもう一度お試しください。","Could not start Gitee sign-in. Please try again."));
    window.location.assign(result.authorizationUrl);
  } catch(error) {
    if(mode==="login")setAuthMessage(error.message,true);
    showToast(error.message,true);
    giteeStarting[mode]=false;renderGiteeButtons();
  }
}

$("#giteeSignIn").addEventListener("click",()=>startGiteeOAuth("login"));
$("#linkGiteeButton").addEventListener("click",()=>startGiteeOAuth("link"));

const beforeGiteeLanguage=applyLanguage;
applyLanguage=function(){beforeGiteeLanguage();renderGiteeButtons();};
const beforeGiteeShowIn=showLoggedIn;
showLoggedIn=function(){beforeGiteeShowIn();renderGiteeButtons();};
const beforeGiteeShowOut=showLoggedOut;
showLoggedOut=function(){beforeGiteeShowOut();renderGiteeButtons();};

function showGiteeCallbackResult() {
  const params=new URLSearchParams(location.search);
  const linked=params.get("gitee_linked")==="1";
  const signedIn=params.get("gitee_login")==="1";
  const error=params.get("gitee_error");
  if(linked)showToast(giteeText("Gitee 已关联到当前账本。","Giteeを現在の台帳に連携しました。","Gitee is now linked to this ledger."));
  else if(signedIn&&params.get("gitee_created")==="1")showToast(giteeText("Gitee 登录成功，已为这个身份创建独立账本；其他登录身份的数据不会合并或覆盖。","Giteeでログインし、このID専用の台帳を作成しました。他のログインIDのデータは統合・上書きされません。","Signed in with Gitee. A separate ledger was created for this identity; other sign-in identities were not merged or overwritten."));
  else if(signedIn)showToast(giteeText("Gitee 登录成功。","Giteeでログインしました。","Signed in with Gitee."));
  else if(error) {
    const messages={
      not_linked:giteeText("这个 Gitee 账号还没有账本，请重新登录以创建独立账本；现有账本不会受影响。","このGiteeアカウントには台帳がありません。専用台帳を作るため、再度ログインしてください。既存の台帳には影響しません。","This Gitee account has no ledger yet. Sign in again to create one; existing ledgers are unchanged."),
      denied:giteeText("你取消或拒绝了 Gitee 授权。","Giteeの認証をキャンセルまたは拒否しました。","Gitee authorization was canceled or denied."),
      not_configured:giteeText("Gitee 登录尚未配置，请稍后重试。","Giteeログインがまだ設定されていません。後でもう一度お試しください。","Gitee sign-in is not configured yet. Please try again later."),
      expired:giteeText("Gitee 登录已过期，请重新开始。","Giteeログインの有効期限が切れました。やり直してください。","Gitee sign-in expired. Please start again."),
      invalid_state:giteeText("Gitee 登录校验失败，请重新开始。","Giteeログインを確認できませんでした。やり直してください。","Gitee sign-in could not be verified. Please start again."),
      session_expired:giteeText("原账本登录已过期，请重新登录后再关联 Gitee。","元の台帳のログイン期限が切れました。再ログインしてからGiteeを連携してください。","The existing ledger session expired. Sign in again before linking Gitee."),
      identity_in_use:giteeText("这个 Gitee 账号已关联另一份账本。","このGiteeアカウントは別の台帳に連携済みです。","This Gitee account is already linked to another ledger."),
      another_identity:giteeText("当前账本已关联另一个 Gitee 账号。","この台帳には別のGiteeアカウントが連携済みです。","This ledger is already linked to another Gitee account."),
      rate_limited:giteeText("Gitee 登录请求过多，请十分钟后再试。","Giteeログインの試行回数が多すぎます。10分後に再試行してください。","Too many Gitee sign-in attempts. Try again in ten minutes."),
      provider_unavailable:giteeText("暂时无法连接 Gitee，请稍后重试。","Giteeに接続できません。後でもう一度お試しください。","Could not reach Gitee. Please try again later."),
    };
    const message=messages[error]||giteeText("Gitee 登录未完成，请重新开始。","Giteeログインが完了しませんでした。やり直してください。","Gitee sign-in did not complete. Please start again.");
    if(!currentUser)setAuthMessage(message,true);
    showToast(message,true);
  } else return;
  history.replaceState(null,"",location.pathname+location.hash);
}

appInitialization.then(()=>{
  renderGiteeButtons();
  showGiteeCallbackResult();
});
