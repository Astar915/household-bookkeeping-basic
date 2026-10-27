// Synthetic HTTP service and a fresh browser profile; no user ledger or credentials.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');
const { chromium, webkit } = require('playwright');
const root = path.resolve(__dirname, '../bookkeeping/web_static');
const report = {
  start:'2026-10-15',through:'2026-10-24',
  jpy_equivalent:{expense_minor:'0',income_minor:'0',missing_conversion_count:'0',categories:{}},
};
const balance = {net_assets:{JPY:'10000',CNY:'0'},rows:[]};
const fixture = {
  date:'2026-10-24',cash:[],cards:[],creditHistory:{},repaymentPlans:[],recurring:[],assets:[],
  balanceSheet:balance,profit:report,reports:{balanceSheet:balance,profit:report},
  settings:{},food:[],eaten:[],foodGroups:{},foodReview:'Synthetic review',transactions:[],
  validation:{errors:[],reviews:[]},backups:[],receipts:[],
  preferences:{profiles:[],agents:{bookkeeping:'',food_health:''},visionAgents:{bookkeeping:'',food_health:''},
    scope:{},cloud:{},autoSync:true,saveImages:true,autoStatus:'',skills:{}},
};
const user = {id:'11111111-1111-4111-8111-111111111111',username:'Synthetic user',authProvider:'github'};
let workspaceMode='ok',workspaceRequests=0;
const sockets=new Set();
const server=http.createServer(async (req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
  if(url.pathname==='/api/config')return json({});
  if(url.pathname==='/api/session')return json({user,csrfToken:'synthetic'});
  if(url.pathname==='/api/action')return json({id:'cloud-job',state:'done',result:{restored:false,status:'no_cloud'}});
  if(url.pathname==='/api/bootstrap')return json({accounts:[],categories:[],transactions:[],serverDate:fixture.date});
  if(url.pathname==='/api/workspace'){
    workspaceRequests++;
    if(workspaceMode==='hang')return;
    if(workspaceMode==='error')return json({error:'Synthetic service failure'},503);
    return json(fixture);
  }
  if(url.pathname.startsWith('/api/'))return json({error:'Synthetic unavailable endpoint'},404);
  const file=path.resolve(root,url.pathname==='/'?'index.html':'.'+url.pathname);
  if(!file.startsWith(root+path.sep))return res.writeHead(404).end();
  try{
    const data=await fs.readFile(file);
    const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'};
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});res.end(data);
  }catch{res.writeHead(404).end();}
});
server.on('connection',socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));});

async function check(engine,options){
  const browser=await engine.launch({headless:true,...options});
  try{
    const context=await browser.newContext({viewport:{width:393,height:852},isMobile:true,hasTouch:true,serviceWorkers:'block'});
    const page=await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    workspaceMode='ok';
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.locator('.hero-balance').waitFor({timeout:15000});
    assert.deepEqual(errors,[],`${engine.name()}: login errors`);
    console.log(`${engine.name()}: normal authenticated startup loaded the ledger`);
    await page.evaluate(()=>navigate('more'));
    await page.locator('#moreMenu [data-id="settings"]').click();
    await page.locator('#editorDialog[open]').waitFor();
    assert.match(await page.locator('#editorCancel').innerText(),/返回更多|その他へ戻る|Back to More/);
    await page.locator('#editorCancel').click();
    await page.locator('#moreMenu').waitFor({state:'visible'});
    // A settings subpage must be escapable even before workspace data is available.
    await page.evaluate(()=>{workspace=null;navigate('more');moreTab='recurring';renderMore();});
    await page.locator('#modulePanel [data-action="module-back"]').click({timeout:3000});
    await page.locator('#moreMenu').waitFor({state:'visible'});
    await page.evaluate(()=>{moreTab='backup';renderMore();renderCloud();});
    await page.locator('#backupPage #cloudControls [data-action="module-back"]').click({timeout:3000});
    await page.locator('#moreMenu').waitFor({state:'visible'});
    // A settled failure must leave a retry control, never an endless loading label.
    workspaceMode='error';
    await page.evaluate(async()=>{workspace=null;await cacheSet('workspace:'+currentUser.id,null);navigate('home');await loadWorkspace(true);});
    await page.locator('#page-home [data-action="workspace-retry"]').waitFor({timeout:3000});
    assert.ok(!/正在载入|Loading your ledger/.test(await page.locator('#page-home').innerText()));
    workspaceMode='ok';
    await page.locator('#page-home [data-action="workspace-retry"]').click();
    await page.locator('.hero-balance').waitFor({timeout:5000});
    // A black-holed connection must time out and allow another request.
    workspaceMode='hang';
    await page.evaluate(async()=>{workspace=null;await cacheSet('workspace:'+currentUser.id,null);void loadWorkspace(true);});
    await page.locator('#page-home [data-action="workspace-retry"]').waitFor({timeout:18000});
    workspaceMode='ok';
    await page.locator('#page-home [data-action="workspace-retry"]').click();
    await page.locator('.hero-balance').waitFor({timeout:5000});
    assert.deepEqual(errors,[],`${engine.name()}: browser errors`);
    await context.close();
    console.log(`${engine.name()}: failure, timeout, retry and More return paths passed`);
  }finally{await browser.close();}
}
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try{
    await check(chromium,{executablePath:process.env.BOOKKEEPING_TEST_CHROMIUM_EXECUTABLE||'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'});
    if(process.env.BOOKKEEPING_TEST_SKIP_WEBKIT!=='1')await check(webkit,{});
  }finally{for(const socket of sockets)socket.destroy();await new Promise(resolve=>server.close(resolve));}
  console.log('PASS: mobile login recovery and settings return navigation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
