# Exercise the returning-user session path in an isolated browser facade.
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for login UI checks")
class CloudLoginSessionTests(unittest.TestCase):
    def run_script(self, script):
        result = subprocess.run(
            [shutil.which("node"), "-e", script], cwd=Path(__file__).resolve().parents[3],
            capture_output=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_date_does_not_require_mobile_workspace_during_startup(self):
        self.run_script(r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const app=fs.readFileSync('cloudflare-full/public/app.js','utf8');
const source=app.slice(app.indexOf('function localDate('),app.indexOf('function updateConnection('));
const context={cachedBootstrap:null,Intl,Date};
vm.createContext(context);vm.runInContext(source,context);
assert.match(context.localDate(),/^\d{4}-\d{2}-\d{2}$/);
''')

    def test_returning_user_opens_app_without_waiting_for_first_device_workspace(self):
        self.run_script(r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const app=fs.readFileSync('cloudflare-full/public/app.js','utf8');
const source=app.slice(app.indexOf('async function establishSession('),app.indexOf('function newOperation('));
const elements=new Map();
function element(){return {disabled:false,classList:{add(){},remove(){},toggle(){}}};}
const events=[];let context;
context={
 currentLanguage:'en-US',currentUser:null,csrfToken:'',serverReachable:false,
 $:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)},
 showSessionPending(){events.push('session-pending')},cacheSet:async()=>{},readCookie:()=>'',
 api:async()=>{throw new Error('a valid session must not issue a duplicate request')},
 showLoggedIn(){events.push('app-visible');void context.loadWorkspace()},
 loadWorkspace(){events.push('workspace-requested');return new Promise(()=>{})},
 renderOutbox:async()=>events.push('outbox-rendered'),
 fetchBootstrap:async()=>{throw new Error('login must not wait for a bootstrap fetch')},
 updateConnection(){events.push('connection-updated')},window:{},
};
vm.createContext(context);vm.runInContext(source,context);
(async()=>{
 const user={id:'fixture-user',username:'Synthetic User'};
 const session={user,csrfToken:'synthetic-csrf'};
 const result=await Promise.race([
   context.establishSession(user,session).then(()=>true),
   new Promise(resolve=>setTimeout(()=>resolve(false),150)),
 ]);
 assert.equal(result,true,'the login screen must be dismissed even while the first workspace request is pending');
 assert.equal(context.currentUser.id,user.id);
 assert.equal(context.csrfToken,'synthetic-csrf');
 assert(events.includes('app-visible'));
 assert(events.includes('workspace-requested'));
 assert(events.includes('outbox-rendered'));
 assert.equal(events.filter(value=>value==='connection-updated').length,1);
})().catch(error=>{console.error(error);process.exitCode=1});
''')

    def test_returning_user_and_backup_error_never_show_the_main_login_screen(self):
        self.run_script(r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const app=fs.readFileSync('cloudflare-full/public/app.js','utf8');
const html=fs.readFileSync('cloudflare-full/public/index.html','utf8');
assert(/id="authScreen" class="[^"]*hidden/.test(html));
const sessionMarkup=html.slice(html.indexOf('<section id="sessionScreen"'),html.indexOf('<section id="authScreen"'));
assert(!sessionMarkup.includes('id="githubSignIn"'));assert(sessionMarkup.includes('id="reconnectGithubBackup"'));
const source=app.slice(app.indexOf('function renderSessionStatus('),app.indexOf('function formatMinor('));
const nodes={};for(const id of ['#authScreen','#appScreen','#toolbar','#sessionScreen','#cloudBootstrapBlocked',
 '#cloudBootstrapError','#sessionIdentity','#sessionWelcome','#sessionLoadingText','#sessionLoadingIndicator','#usernameLabel']){
 const classes=new Set(['hidden']);nodes[id]={textContent:'',classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),
 contains:x=>classes.has(x),toggle:(x,flag)=>flag?classes.add(x):classes.delete(x)}};
}
const ctx={$:id=>nodes[id],currentUser:{id:'owner',username:'Returning User'},currentLanguage:'en-US',
 cloudBootstrapFailed:false,updateTopbarLayout(){},updateConnection(){}};
vm.createContext(ctx);vm.runInContext(source,ctx);
ctx.showSessionPending();
assert(nodes['#authScreen'].classList.contains('hidden'));
assert(!nodes['#sessionScreen'].classList.contains('hidden'));
assert.equal(nodes['#sessionWelcome'].textContent,'Welcome back');
assert(nodes['#sessionIdentity'].textContent.includes('Returning User'));
ctx.showCloudBootstrapBlocked('authorization error');
assert(nodes['#authScreen'].classList.contains('hidden'));
assert(!nodes['#sessionScreen'].classList.contains('hidden'));
assert(nodes['#sessionLoadingIndicator'].classList.contains('hidden'));
assert(nodes['#sessionLoadingText'].textContent.includes('still signed in'));
assert.equal(nodes['#cloudBootstrapError'].textContent,'authorization error');
ctx.showLoggedIn();assert(nodes['#sessionScreen'].classList.contains('hidden'));
assert(!nodes['#appScreen'].classList.contains('hidden'));
ctx.currentUser=null;ctx.showLoggedOut();
assert(!nodes['#authScreen'].classList.contains('hidden'));
assert(nodes['#sessionScreen'].classList.contains('hidden'));
''')


if __name__ == "__main__":
    unittest.main()
