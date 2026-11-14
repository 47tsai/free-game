import { readFileSync, existsSync } from "node:fs";
import { resolve, relative } from "node:path";

const root = process.cwd();
const site = resolve(root, "site");
const read = (path) => readFileSync(resolve(root, path), "utf8");
const html = read("site/index.html");
const css = read("site/fg.css");
const sharedCss = read("site/chi-system/components.css");
const tokens = read("site/chi-system/tokens.css");
const app = read("site/app.js");
const release = JSON.parse(read("site/release.json"));
const errors = [];

function assert(condition, message) {
  if (!condition) errors.push(message);
}

assert(/<html[^>]*lang="zh-Hant"[^>]*data-chi-layout="header"[^>]*data-chi-brand="fg"/.test(html),
  "HTML must declare zh-Hant, Header layout, and the fg brand.");
assert((html.match(/<main\b/g) || []).length === 1, "The page must contain exactly one main landmark.");
assert(html.includes('data-chi-theme-toggle'), "The shared theme toggle is missing.");
assert(html.includes('id="login"'), "The Chi Auth login control is missing.");
assert(html.includes('id="games"') && html.includes('id="pagination"'), "The game list or pagination mount is missing.");
assert(html.includes('chi-system/theme.js') && html.includes('chi-system/tokens.css') && html.includes('chi-system/components.css'),
  "The page must load the vendored CHI runtime, tokens, and components.");
assert(!html.includes("icons.svg") && !html.includes("navigation.css"), "The page still references removed legacy CHI assets.");
assert(!app.includes("icons.svg") && !app.includes("function icon("), "The application still depends on the legacy icon sprite.");
assert(!existsSync(resolve(site, "chi-system/navigation.css")) && !existsSync(resolve(site, "chi-system/icons.svg")),
  "Legacy navigation.css/icons.svg should not remain in the vendored distribution.");
assert(release.chiSystemVersion === "1.0.0", "release.json must pin CHI v1.0.0.");
assert(/^[0-9a-f]{40}$/.test(release.chiSystemCommit || ""), "release.json must pin the full CHI source commit.");

const assetRefs = [
  ...html.matchAll(/<script[^>]+src="([^"]+)"/g),
  ...html.matchAll(/<link[^>]+href="([^"]+)"/g),
  ...html.matchAll(/<img[^>]+src="([^"]+)"/g),
];
for (const match of assetRefs) {
  const ref = match[1];
  if (/^(?:https?:)?\/\//.test(ref) || ref.startsWith("data:") || ref.startsWith("#")) continue;
  const localRef = ref.split(/[?#]/, 1)[0];
  const path = resolve(site, localRef);
  const rel = relative(site, path);
  if (rel.startsWith("..") || !existsSync(path)) errors.push("Missing or unsafe local asset reference: " + ref);
}

const declared = new Set([...tokens.matchAll(/(--chi-[\w-]+)\s*:/g)].map((m) => m[1]));
const used = new Set(
  [...(css + "\n" + sharedCss).matchAll(/var\((--chi-[\w-]+)/g)].map((m) => m[1])
);
for (const name of used) if (!declared.has(name)) errors.push("Undefined CHI token used by site CSS: " + name);

const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
for (const id of new Set(duplicates)) errors.push("Duplicate HTML id: " + id);

if (errors.length) {
  console.error("Free Game site validation failed:");
  for (const error of errors) console.error("- " + error);
  process.exit(1);
}
console.log("Free Game site validation passed: CHI v" + release.chiSystemVersion +
  " pinned assets, local references, semantic mounts, and CSS token usage.");
