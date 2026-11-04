import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
for(const target of ["engine-a","engine-b","web"]){
  const result=spawnSync(process.execPath,[path.join(root,"node_modules/wrangler/bin/wrangler.js"),
    "deploy","--config",`python-d1/wrangler.${target}.jsonc`],{cwd:root,stdio:"inherit"});
  if(result.status!==0)process.exit(result.status||1);
}
