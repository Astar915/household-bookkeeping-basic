import { copyFile, mkdir, readdir, unlink } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "../../..");
const sourcePackage = path.join(projectRoot, "bookkeeping");
const workerSource = path.resolve(scriptDir, "../src/bookkeeping");
const DESKTOP_ONLY_MODULES = new Set([
  "cli.py",
  "desktop_favorites.py",
  "desktop_frame.py",
  "desktop_layout.py",
  "desktop_shell.py",
  "desktop_theme.py",
  "desktop_tooltip.py",
  "gui.py",
  "single_instance.py",
  "ui_confirm.py",
  "ui_fonts.py",
]);

await mkdir(workerSource, { recursive: true });
for (const entry of await readdir(sourcePackage, { withFileTypes: true })) {
  if (entry.isFile() && entry.name.endsWith(".py") && !DESKTOP_ONLY_MODULES.has(entry.name)) {
    await copyFile(path.join(sourcePackage, entry.name), path.join(workerSource, entry.name));
  }
}
for (const name of DESKTOP_ONLY_MODULES) {
  await unlink(path.join(workerSource, name)).catch((error) => {
    if (error.code !== "ENOENT") throw error;
  });
}

const defaultsSource = path.join(sourcePackage, "web_defaults");
const defaultsTarget = path.join(workerSource, "web_defaults");
await mkdir(defaultsTarget, { recursive: true });
for (const entry of await readdir(defaultsSource, { withFileTypes: true })) {
  if (entry.isFile()) {
    await copyFile(path.join(defaultsSource, entry.name), path.join(defaultsTarget, entry.name));
  }
}

process.stdout.write("Synced Python bookkeeping modules and built-in Agent Skills into the isolated Worker source.\n");
