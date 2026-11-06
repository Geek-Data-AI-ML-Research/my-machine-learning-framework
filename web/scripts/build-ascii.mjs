#!/usr/bin/env node
import * as esbuild from "esbuild";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outfile = join(root, "public/vendor/mymlfw-ascii.js");
mkdirSync(dirname(outfile), { recursive: true });

await esbuild.build({
  entryPoints: [join(root, "src/ascii-studio.mjs")],
  bundle: true,
  format: "esm",
  outfile,
  platform: "browser",
  target: ["es2022"],
  minify: false,
  sourcemap: true,
  logLevel: "info",
});

console.log("wrote", outfile);
