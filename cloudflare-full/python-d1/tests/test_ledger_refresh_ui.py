"""Exercise actual web refresh functions with deferred reads, never a real API."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node is required for frontend regression checks")
class LedgerRefreshTests(unittest.TestCase):
    def test_refresh_races_retries_and_completed_agent_are_safe(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const mobile=fs.readFileSync('cloudflare-full/public/mobile.js','utf8');
const app=fs.readFileSync('cloudflare-full/public/app.js','utf8');
const source=mobile.slice(mobile.indexOf('function dateAtTimeZone('),mobile.indexOf('const plainAmount'))
 +mobile.slice(mobile.indexOf('async function readLedger('),mobile.indexOf('function renderMobile()'))
 +app.slice(app.indexOf('async function fetchBootstrap('),app.indexOf('let cloudBootstrapFailed'))
 +mobile.slice(mobile.indexOf('async function runAction('),mobile.indexOf('function cloudProgressCopy('));
function payload(id,owner='owner',revision='fixture-revision') {return {revision,transactions:[{id}],cash:[],bootstrap:{user:{id:owner},serverDate:'2026-11-09',transactions:[{id}],accounts:[],categories:[]}};}
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
const tick=()=>new Promise(setImmediate);
function setup(api,revisions=['fixture-revision']){
 const cache=new Map(),fields={historyStart:{value:''},historyEnd:{value:''}},calls=[],toasts=[];let revisionIndex=0;
 const ctx={currentUser:{id:'owner'},idb:{},workspace:null,workspaceOwner:'',workspaceLoading:null,
   workspaceEpoch:0,workspaceError:'',currentLanguage:'en-US',reportDate:'',cachedBootstrap:null,WORKSPACE_CACHE_FORMAT:2,chatAgent:'bookkeeping',
   ledgerRangeRows:null,ledgerRangeRequest:0,serverReachable:true,activeJob:'',navigator:{onLine:true},
   AbortController,URLSearchParams,setTimeout,clearTimeout,document:new Proxy({addEventListener(){}},{get:(target,key)=>target[key]||(()=>null)}),
   window:{addEventListener(){},dispatchEvent(){},removeEventListener(){},scrollTo(){},innerWidth:1000,innerHeight:800},
   api:async(...args)=>{calls.push(args[0]);if(args[0]==='/api/workspace/revision'){const revision=revisions[Math.min(revisionIndex++,revisions.length-1)];return {revision,configRevision:revision,updatedAt:'2026-11-09T00:00:00Z',serverTime:'2026-11-09T12:00:00Z'};}return api(...args)},
   cacheGet:async key=>cache.get(key),cacheSet:async(key,value)=>cache.set(key,value),
   outboxAll:async()=>[],
   sleepMobile:async()=>{},renderMobile(){ctx.renders++},renderAll:async()=>{ctx.baseRenders++},
   renderMobileTransactions(){},renderOutbox:async()=>{},syncQueue:async()=>{},resumeJob(){},renderAgent(){},updateConnection(){},
   showActionProgress(){},hideCloudProgress(){},runBackgroundCloudBackup:async()=>{},
   workspaceLoadError:error=>error.message,m:(zh,ja,en)=>en,t:x=>x,localizeServerError:x=>x,
   $:selector=>fields[selector.slice(1)],localStorage:{setItem(){},removeItem(){},getItem(){return null}},
   crypto:{randomUUID:()=> 'synthetic-operation'},showToast:(...args)=>toasts.push(args),
   renders:0,baseRenders:0,
 };
 vm.createContext(ctx);vm.runInContext(source,ctx);return {ctx,cache,fields,calls,toasts};
}
(async()=>{
 // A pre-write read must not satisfy a post-write force refresh or overwrite
 // the browser cache. Coalesce additional force calls into one fresh request.
 let old=deferred(),fresh=deferred(),count=0;
 let s=setup(()=>++count===1?old.promise:fresh.promise,['old-revision','new-revision']);
 let first=s.ctx.loadWorkspace();await tick();
 let forced=s.ctx.loadWorkspace(true),forcedAgain=s.ctx.loadWorkspace(true);
 old.resolve(payload(51,'owner','old-revision'));await tick();
 assert.equal(s.calls.length,4,JSON.stringify(s.calls));assert(!s.cache.has('workspace:owner'));
 fresh.resolve(payload(63,'owner','new-revision'));await Promise.all([first,forced,forcedAgain]);
 assert.equal(s.ctx.workspace.transactions[0].id,63);
 assert.equal(s.ctx.cachedBootstrap.transactions[0].id,63);
 assert.equal(s.cache.get('workspace:owner').transactions[0].id,63);
 assert.equal(s.ctx.baseRenders,1);assert.equal(s.ctx.workspaceLoading,null);

 // Retry exactly one transient read; never retry authentication errors.
 count=0;s=setup(()=>{if(++count===1)throw Object.assign(new Error('HTTP 500'),{status:500});return payload(63)});
 await s.ctx.fetchBootstrap();assert.equal(s.calls.length,3);assert.equal(s.ctx.workspaceError,'');
 s=setup(()=>{throw Object.assign(new Error('expired'),{status:401})});
 await assert.rejects(()=>s.ctx.fetchBootstrap(),/expired/);assert.equal(s.calls.length,2);

 // Do not replace a newer in-memory view with an older offline cache after
 // both read attempts fail; report failure instead of claiming a refresh.
 s=setup(()=>{throw Object.assign(new Error('HTTP 500'),{status:500})});
 s.ctx.workspace={transactions:[{id:63}]};s.ctx.workspaceOwner='owner';
 s.cache.set('workspace:owner',{transactions:[{id:51}]});
 await assert.rejects(()=>s.ctx.fetchBootstrap(),/500/);
 assert.equal(s.calls.length,3);assert.equal(s.ctx.workspace.transactions[0].id,63);

 // An old account's delayed response cannot render/cache into a new session.
 old=deferred();s=setup(()=>old.promise);first=s.ctx.loadWorkspace(true);
 s.ctx.currentUser={id:'different-owner'};s.ctx.workspaceEpoch++;
 old.resolve(payload(63));await first;assert.equal(s.ctx.workspace,null);assert.equal(s.cache.size,0);

 // Switching the report date while a read runs requires a fresh response.
 old=deferred();count=0;s=setup(()=>++count===1?old.promise:payload(64));
 first=s.ctx.loadWorkspace(true);await tick();s.ctx.reportDate='2026-10-15';old.resolve(payload(51));await first;
 assert.equal(s.calls.length,4);assert(s.calls[3].includes('asOf=2026-10-15'));
 assert.equal(s.ctx.workspace.transactions[0].id,64);

 // A delayed pre-write date-filter response cannot overwrite the fresh list.
 old=deferred();fresh=deferred();count=0;s=setup(()=>++count===1?old.promise:fresh.promise);
 first=s.ctx.loadLedgerRange();let latest=s.ctx.loadLedgerRange();
 fresh.resolve([{id:63}]);await latest;old.resolve([{id:51}]);await first;
 assert.equal(s.ctx.ledgerRangeRows[0].id,63);

 // Successful jobs use one combined GET for all views and refresh an active
 // date filter. A failed refresh never turns a committed job into a retry.
 let posts=0;s=setup(path=>path==='/api/action'?(posts++,{id:'job',state:'done',result:{answer:'recorded'}})
   :path.startsWith('/api/transactions')?[{id:63}]:payload(63));
 s.fields.historyStart.value='2026-10-01';s.ctx.ledgerRangeRows=[{id:51}];
 let result=await s.ctx.runAction('agent',{},()=>{});
 assert.equal(posts,1);assert.equal(result.answer,'recorded');
 assert.equal(s.calls.filter(x=>x.startsWith('/api/workspace?')).length,1);
 assert(!s.calls.some(x=>x.startsWith('/api/bootstrap')));
 assert.equal(s.ctx.ledgerRangeRows[0].id,63);assert.equal(s.ctx.cachedBootstrap.transactions[0].id,63);
 posts=0;s=setup(path=>{if(path==='/api/action'){posts++;return {id:'job',state:'done',result:{answer:'recorded'}}}
   throw Object.assign(new Error('HTTP 500'),{status:500})});
 result=await s.ctx.runAction('agent',{},()=>{});
 assert.equal(result.answer,'recorded');assert.equal(posts,1);
 assert(s.toasts.some(([text,error])=>error&&text.includes('do not submit it again')));
 assert.equal(s.ctx.activeJob,'');

 // A matching IndexedDB revision uses one lightweight validator request and
 // skips the full D1 workspace snapshot, including on a forced refresh.
 s=setup(path=>{throw new Error('unchanged cache must not download the workspace')});
 s.ctx.workspace={revision:'fixture-revision',transactions:[],cash:[]};s.ctx.workspaceOwner='owner';
 s.ctx.cachedBootstrap={user:{id:'owner'},serverDate:'2026-11-09',accounts:[],categories:[],transactions:[]};
 s.cache.set('workspace-meta:owner',{format:2,revision:'fixture-revision',configRevision:'fixture-revision',serverDate:'2026-11-09',language:'en-US',reportDate:''});
 await s.ctx.loadWorkspace(true);
 assert.deepEqual(s.calls,['/api/workspace/revision']);assert.equal(s.ctx.workspaceError,'');

 // A changed revision always falls through to a full snapshot refresh.
 s=setup(path=>payload(88));
 s.ctx.workspace={revision:'old-revision',transactions:[],cash:[]};s.ctx.workspaceOwner='owner';
 s.ctx.cachedBootstrap={user:{id:'owner'},serverDate:'2026-11-09',accounts:[],categories:[],transactions:[]};
 s.cache.set('workspace-meta:owner',{format:2,revision:'old-revision',configRevision:'old-revision',serverDate:'2026-11-09',language:'en-US',reportDate:''});
 await s.ctx.loadWorkspace(true);
 assert.equal(s.calls.filter(x=>x==='/api/workspace/revision').length,1);
 assert.equal(s.calls.filter(x=>x.startsWith('/api/workspace?')).length,1);
 assert.equal(s.ctx.workspace.transactions[0].id,88);

 // The regional day boundary follows the cached account region, not UTC.
 s=setup(path=>{throw new Error('same local day must keep the cached workspace')});
 s.ctx.workspace={revision:'fixture-revision',preferences:{timeZone:'America/Los_Angeles'},transactions:[],cash:[]};s.ctx.workspaceOwner='owner';
 s.ctx.cachedBootstrap={user:{id:'owner'},timeZone:'America/Los_Angeles',serverDate:'2026-11-09',accounts:[],categories:[],transactions:[]};
 s.cache.set('workspace-meta:owner',{format:2,revision:'fixture-revision',configRevision:'fixture-revision',serverDate:'2026-11-09',language:'en-US',reportDate:''});
 s.ctx.api=async(...args)=>{s.calls.push(args[0]);if(args[0]==='/api/workspace/revision')return {revision:'fixture-revision',configRevision:'fixture-revision',serverTime:'2026-11-10T02:00:00Z'};throw new Error('same local day must keep the cached workspace')};
 await s.ctx.loadWorkspace(true);assert.deepEqual(s.calls,['/api/workspace/revision']);

 // Once that same region crosses midnight, force a full snapshot refresh.
 s=setup(path=>payload(91),['fixture-revision']);
 s.ctx.workspace={revision:'fixture-revision',preferences:{timeZone:'America/Los_Angeles'},transactions:[],cash:[]};s.ctx.workspaceOwner='owner';
 s.ctx.cachedBootstrap={user:{id:'owner'},timeZone:'America/Los_Angeles',serverDate:'2026-11-09',accounts:[],categories:[],transactions:[]};
 s.cache.set('workspace-meta:owner',{format:2,revision:'fixture-revision',configRevision:'fixture-revision',serverDate:'2026-11-09',language:'en-US',reportDate:''});
 s.ctx.api=async(...args)=>{s.calls.push(args[0]);if(args[0]==='/api/workspace/revision')return {revision:'fixture-revision',configRevision:'fixture-revision',serverTime:'2026-11-10T08:00:00Z'};return payload(91)};
 await s.ctx.loadWorkspace(true);assert.equal(s.calls.filter(x=>x.startsWith('/api/workspace?')).length,1);
 assert.equal(s.ctx.workspace.transactions[0].id,91);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run([shutil.which("node"), "-e", script],
                                cwd=Path(__file__).resolve().parents[3],
                                capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
