import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node.js is needed to exercise the browser error handling")
class MobileClientErrorsTests(unittest.TestCase):
    def test_http_errors_are_not_reported_as_hotspot_disconnects(self):
        root = Path(__file__).resolve().parents[1]
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const app=fs.readFileSync('bookkeeping/web_static/app.js','utf8');
const mobile=fs.readFileSync('bookkeeping/web_static/mobile.js','utf8');
const a=app.indexOf('async function api('), b=app.indexOf('\nfunction setAuthMessage',a);
const c=mobile.indexOf('function workspaceLoadError('), d=mobile.indexOf('\nasync function loadWorkspace',c);
const ctx={currentUser:null,Headers:class {set(){}},FormData:class {},Blob:class {},localizeServerError:x=>x,
  m:(zh,ja,en)=>en,fetch:async()=>({ok:false,status:500,json:async()=>({error:'server read failed'})})};
vm.createContext(ctx);vm.runInContext(app.slice(a,b)+'\n'+mobile.slice(c,d),ctx);
(async()=>{
  let error;
  try {await ctx.api('/api/workspace');} catch(e){error=e;}
  assert.equal(error.status,500);
  const message=ctx.workspaceLoadError(error);
  assert(message.includes('server read failed'));
  assert(!message.includes('hotspot'));
  assert(ctx.workspaceLoadError({status:401}).includes('session expired'));
  assert(ctx.workspaceLoadError({name:'AbortError'}).includes('timed out'));
  assert(ctx.workspaceLoadError(new TypeError('fetch failed')).includes('hotspot'));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run([shutil.which("node"), "-e", script], cwd=root,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
