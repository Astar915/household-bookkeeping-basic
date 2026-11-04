// Keep Python initialization failures outside the browser-facing runtime.
// Engines are private service bindings sharing the same D1 database. Public
// mutations stay single-engine; verified durable Agent preparation steps may
// fail over because their job IDs and commits are replay-safe.
const unhealthyUntil = new Map();
let sequence = 0;

function unavailable(diagnostic=null) {
  const body={error:"云端运行服务暂时不可用，请稍后刷新核对账本；请勿重复提交已成功的记账。",code:"RUNTIME_UNAVAILABLE"};
  if(diagnostic)body.diagnostic=diagnostic;
  return Response.json(body,
    {status:503,headers:{"cache-control":"no-store"}});
}

function safeDiagnostic(value){
  const type=String(value?.type||"");
  const locations=String(value?.locations||"");
  if(!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(type))return null;
  if(locations.length>400||!/^[A-Za-z0-9_.:/ >-]*$/.test(locations))return null;
  return {type,locations};
}

async function dispatchEngine(request, env) {
  const engines=[env.PYTHON_PRIMARY,env.PYTHON_SECONDARY];
  if(!engines.every(Boolean)||!env.TOKEN_ENCRYPTION_KEY||!env.APP_JOB_SHARED_SECRET)return unavailable();
  const path=new URL(request.url).pathname.replace(/\/+$/g,"")||"/";
  const preferred=sequence++%engines.length;
  const order=[preferred,1-preferred].sort((a,b)=>
    Number((unhealthyUntil.get(a)||0)>Date.now())-Number((unhealthyUntil.get(b)||0)>Date.now()));
  const safeRead=["GET","HEAD"].includes(request.method);
  const replaySafeAgentAdvance=request.method==="POST"
    &&path==="/__internal/job/advance"
    &&request.headers.get("X-App-Job-Secret")===String(env.APP_JOB_SHARED_SECRET)
    &&request.headers.get("X-App-Job-Action")==="agent_prepare";
  const attempts=(safeRead||replaySafeAgentAdvance)?order:[order[0]];
  let lastDiagnostic=null;
  for(const index of attempts){
    try{
      const headers=new Headers(request.headers);
      // Never trust caller-supplied transport credentials. These values travel
      // only over private bindings, never to a public origin or the browser.
      headers.set("X-Ledger-Engine-Token",env.TOKEN_ENCRYPTION_KEY);
      headers.set("X-Ledger-Engine-Jobs",env.APP_JOB_SHARED_SECRET);
      headers.set("X-Ledger-Gitee-Client-ID",String(env.GITEE_CLIENT_ID||""));
      headers.set("X-Ledger-Gitee-Client-Secret",String(env.GITEE_CLIENT_SECRET||""));
      headers.set("X-Ledger-Gitee-Redirect-URI",String(env.GITEE_REDIRECT_URI||""));
      const forwarded=new Request(request.clone(),{headers});
      const response=await engines[index].fetch(forwarded);
      if(response.status<500){unhealthyUntil.delete(index);return response;}
      unhealthyUntil.set(index,Date.now()+30000);
      try{
        const result=await response.clone().json();
        lastDiagnostic=safeDiagnostic(result?.diagnostic)||lastDiagnostic;
      }catch{}
      await response.body?.cancel().catch(()=>{});
    }catch{
      // Do not log exceptions, headers, URLs or bodies here: an engine failure
      // can occur before Python's own sanitized error handling is initialized.
      unhealthyUntil.set(index,Date.now()+30000);
    }
  }
  return unavailable(lastDiagnostic);
}

export default {
  async fetch(request,env){
    const path=new URL(request.url).pathname.replace(/\/+$/,"")||"/";
    if(path==="/__internal/run-scheduled")return new Response("Not found",{status:404});
    if(path.startsWith("/api/")||path.startsWith("/__internal/"))return dispatchEngine(request,env);
    return env.ASSETS.fetch(request);
  },
  async scheduled(controller,env){
    const response=await dispatchEngine(new Request("https://scheduled.internal/__internal/run-scheduled",{method:"POST"}),env);
    if(!response.ok)throw new Error("Scheduled ledger dispatch unavailable.");
  },
};
