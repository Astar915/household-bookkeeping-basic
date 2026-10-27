// Exercise the login download ordering with a synthetic service and IDB queue.
// No browser profile, cloud credentials or user ledger are accessed.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname,'../bookkeeping/web_static/app.js'),'utf8')
  .replace(/setupEvents\(\);\s*const appInitialization =[\s\S]*$/, '');

async function run(queue=[],fail=false) {
  const calls=[], messages=[];
  const context=vm.createContext({console, navigator:{language:'zh-CN'},
    localStorage:{getItem:()=>null}, document:{documentElement:{},cookie:''},
    crypto:{randomUUID:()=> 'synthetic-operation-id'},
    setTimeout:callback=>{callback();return 1;},clearTimeout:()=>{},
    window:{onCloudLedgerRestored:()=>calls.push('cleared-chat')},
    queue,calls,messages,fail});
  vm.runInContext(source,context);
  await vm.runInContext(`(async()=>{
    idb={};
    idbRequest=async store => store==='outbox'?queue:undefined;
    api=async path=>{
      calls.push(path);
      if(path==='/api/session')return {csrfToken:'synthetic'};
      if(path==='/api/action')return {id:'job',state:'running'};
      if(path.startsWith('/api/job'))return fail?{state:'failed',message:'download failed'}:{state:'done',result:{restored:true}};
      throw new Error(path);
    };
    fetchBootstrap=async()=>calls.push('bootstrap');
    showLoggedIn=()=>calls.push('logged-in');renderOutbox=async()=>{};
    updateConnection=()=>{};syncQueue=()=>calls.push('send-outbox');
    setAuthMessage=()=>{};showToast=message=>messages.push(message);
    await establishSession({id:'owner'});
  })()`,context);
  return {calls,messages};
}
(async()=>{
  let result=await run();
  assert.ok(result.calls.indexOf('/api/job?id=job')<result.calls.indexOf('bootstrap'));
  assert.ok(result.calls.indexOf('bootstrap')<result.calls.indexOf('logged-in'));
  assert.ok(result.calls.includes('cleared-chat'));
  result=await run([{ownerId:'owner',opId:'offline-item'}]);
  assert.ok(!result.calls.includes('/api/action'));
  assert.ok(result.calls.includes('logged-in'));
  assert.ok(result.messages[0].includes('离线'));
  result=await run([],true);
  assert.ok(result.calls.includes('logged-in'));
  assert.ok(result.messages[0].includes('自动下载未完成'));
  console.log('PASS: startup download precedes display; pending entries defer restore; failed download preserves login.');
})().catch(error=>{console.error(error);process.exitCode=1;});
