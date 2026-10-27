import { copyFile, mkdir, readdir, stat } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(projectRoot, "..");
const sourceRoot = join(repositoryRoot, "bookkeeping", "web_static");
const destinationRoot = join(projectRoot, "public");

async function copyTree(source, destination) {
  await mkdir(destination, { recursive: true });
  for (const entry of await readdir(source, { withFileTypes: true })) {
    const sourcePath = join(source, entry.name);
    const destinationPath = join(destination, entry.name);
    if (entry.isDirectory()) {
      await copyTree(sourcePath, destinationPath);
    } else if (entry.isFile()) {
      await mkdir(dirname(destinationPath), { recursive: true });
      await copyFile(sourcePath, destinationPath);
    }
  }
}

const sourceInfo = await stat(sourceRoot).catch(() => null);
if (!sourceInfo?.isDirectory()) {
  throw new Error(`PWA source directory is missing: ${relative(projectRoot, sourceRoot)}`);
}

await copyTree(sourceRoot, destinationRoot);
console.log(`Synced PWA assets from ${relative(projectRoot, sourceRoot)} to public/.`);
