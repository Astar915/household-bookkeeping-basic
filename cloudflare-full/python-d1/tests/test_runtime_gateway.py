"""NoGilError must be contained by JS, without replaying ledger mutations."""
import json
import importlib.util
import sys
import shutil
import subprocess
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch, AsyncMock


@unittest.skipUnless(shutil.which("node"), "Node required")
class RuntimeGatewayTests(unittest.TestCase):
    def test_runtime_failover_and_private_transport(self):
        script = r'''
const assert=require('assert');
const {pathToFileURL}=require('url');
const root=process.cwd();let version=0;
async function gateway(){return (await import(pathToFileURL(root+'/cloudflare-full/python-d1/edge/index.js')+'?test='+version++)).default}
function env(primary,secondary){return {TOKEN_ENCRYPTION_KEY:'synthetic-key',APP_JOB_SHARED_SECRET:'synthetic-jobs',
  PYTHON_PRIMARY:{fetch:primary},PYTHON_SECONDARY:{fetch:secondary},ASSETS:{fetch:async()=>new Response('static')}};}
(async()=>{
 let app=await gateway(),a=0,b=0;
 let settings=env(async()=>{a++;throw new Error('NoGilError: Attempted to use PyProxy when Python GIL not held')},
  async request=>{b++;assert.equal(request.url,'https://ledger.example/api/workspace?includeBootstrap=1');
   assert.equal(request.headers.get('cookie'),'hh_session=synthetic');
   assert.equal(request.headers.get('x-ledger-owner'),'owner');
   assert.equal(request.headers.get('x-ledger-engine-token'),'synthetic-key');
   return Response.json({transactions:[{id:64}]})});
 let response=await app.fetch(new Request('https://ledger.example/api/workspace?includeBootstrap=1',{
  headers:{cookie:'hh_session=synthetic','X-Ledger-Owner':'owner','X-Ledger-Engine-Token':'forged'}}),settings);
 assert.equal(response.status,200);assert.equal((await response.json()).transactions[0].id,64);
 assert.equal(a,1);assert.equal(b,1);
 // A marked bad engine is bypassed by the following job poll.
 settings.PYTHON_SECONDARY.fetch=async()=>{b++;return Response.json({state:'done'})};
 response=await app.fetch(new Request('https://ledger.example/api/job?id=synthetic'),settings);
 assert.equal(response.status,200);assert.equal(a,1);

 app=await gateway();a=b=0;
 settings=env(async()=>{a++;return new Response('error code: 1101',{status:500})},
  async()=>{b++;return Response.json({ok:true})});
 response=await app.fetch(new Request('https://ledger.example/api/workspace'),settings);
 assert.equal(response.status,200);assert.equal(a,1);assert.equal(b,1);

 // POST is sent once even when the runtime may have already committed it.
 app=await gateway();a=b=0;
 settings=env(async request=>{a++;assert.equal(await request.text(),'synthetic-payload');throw new Error('NoGilError')},
  async()=>{b++;return Response.json({ok:true})});
 response=await app.fetch(new Request('https://ledger.example/api/action',{
  method:'POST',body:'synthetic-payload'}),settings);
 assert.equal(response.status,503);assert.equal(a,1);assert.equal(b,0);
 const error=await response.json();assert.equal(error.code,'RUNTIME_UNAVAILABLE');
 assert(!JSON.stringify(error).includes('synthetic-key'));

 // Auth/conflict responses belong to the application, not runtime failover.
 for(const status of [400,401,403,404,409,429]){
  app=await gateway();a=b=0;
  settings=env(async()=>{a++;return new Response('application-response',{status})},async()=>{b++;throw Error('unreachable')});
  response=await app.fetch(new Request('https://ledger.example/api/workspace'),settings);
  assert.equal(response.status,status);assert.equal(a,1);assert.equal(b,0);
 }
 app=await gateway();a=b=0;
 settings=env(async()=>{a++;throw Error('runtime')},async()=>{b++;throw Error('runtime')});
 response=await app.fetch(new Request('https://ledger.example/api/workspace'),settings);
 assert.equal(response.status,503);assert.equal(a+b,2);
 response=await app.fetch(new Request('https://ledger.example/'),settings);
 assert.equal(await response.text(),'static');assert.equal(a+b,2);
 for(const path of ['/__internal/run-scheduled','/__internal/run-scheduled/']){
  response=await app.fetch(new Request('https://ledger.example'+path,{method:'POST'}),settings);
  assert.equal(response.status,404);assert.equal(a+b,2);
 }
 // Cron is generated internally and forwards credentials only to a binding.
 app=await gateway();a=b=0;
 settings=env(async request=>{a++;assert.equal(new URL(request.url).pathname,'/__internal/run-scheduled');
   assert.equal(request.headers.get('x-ledger-engine-jobs'),'synthetic-jobs');return Response.json({ok:true})},
   async()=>{b++;throw Error('unreachable')});
 await app.scheduled({},settings);assert.equal(a,1);assert.equal(b,0);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run([shutil.which("node"), "-e", script],
                                cwd=Path(__file__).resolve().parents[3], capture_output=True,
                                encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_engines_have_no_public_url_or_cron(self):
        root = Path(__file__).resolve().parents[1]
        for slot in ("a", "b"):
            config = json.loads((root / f"wrangler.engine-{slot}.jsonc").read_text("utf-8"))
            self.assertFalse(config["workers_dev"])
            self.assertFalse(config["preview_urls"])
            self.assertNotIn("triggers", config)
            self.assertEqual(config["vars"]["PRIVATE_ENGINE"], "1")
            self.assertNotIn("secrets", config)


class EngineTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_engine_receives_credentials_only_in_private_mode(self):
        workers = ModuleType("workers")
        workers.WorkerEntrypoint = object
        workers.Response = SimpleNamespace(json=lambda value, status=200: {"value": value, "status": status})
        api, scheduled = ModuleType("api"), ModuleType("scheduled")
        api.dispatch = AsyncMock(return_value={"ok": True})
        scheduled.run_scheduled = AsyncMock()
        path = Path(__file__).resolve().parents[1] / "src/worker.py"
        spec = importlib.util.spec_from_file_location("fixture_engine_worker", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"workers": workers, "api": api, "scheduled": scheduled}):
            spec.loader.exec_module(module)
        worker = module.Default()
        worker.env = SimpleNamespace(PRIVATE_ENGINE="1", DB="fixture-db", APP_JOBS="fixture-jobs")
        request = SimpleNamespace(url="https://web.example/api/workspace", method="GET", headers={})
        response = await worker.fetch(request)
        self.assertEqual(response["status"], 403)
        api.dispatch.assert_not_awaited()
        request.headers = {"X-Ledger-Engine-Token": "synthetic-key", "X-Ledger-Engine-Jobs": "synthetic-secret"}
        await worker.fetch(request)
        env = api.dispatch.await_args.args[1]
        self.assertEqual(env.TOKEN_ENCRYPTION_KEY, "synthetic-key")
        self.assertEqual(env.APP_JOB_SHARED_SECRET, "synthetic-secret")
        self.assertEqual(env.DB, "fixture-db")
        self.assertFalse(hasattr(worker.env, "TOKEN_ENCRYPTION_KEY"))
        request.url = "https://scheduled.internal/__internal/run-scheduled"
        request.method = "POST"
        await worker.fetch(request)
        scheduled.run_scheduled.assert_awaited_once()
