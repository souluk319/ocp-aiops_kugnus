'use strict';

const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const distDir = path.join(rootDir, 'dist');
const packageJsonPath = path.join(rootDir, 'package.json');
const manifestPath = path.join(distDir, 'plugin-manifest.json');

const failures = [];

const assertFile = (filePath, label) => {
  if (!fs.existsSync(filePath)) {
    failures.push(`${label} missing: ${path.relative(rootDir, filePath)}`);
  }
};

const assertDistFileByPrefix = (prefix, label) => {
  const match = fs
    .readdirSync(distDir)
    .find((fileName) => fileName.startsWith(prefix) && fileName.endsWith('.js'));
  if (!match) {
    failures.push(`${label} missing: dist/${prefix}*.js`);
  }
  return match ? path.join(distDir, match) : undefined;
};

assertFile(manifestPath, 'plugin manifest');

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
const exposedModules = packageJson.consolePlugin?.exposedModules || {};
const manifest = fs.existsSync(manifestPath)
  ? JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
  : undefined;
const loadScripts = Array.isArray(manifest?.loadScripts) ? manifest.loadScripts : [];

if (loadScripts.length === 0) {
  failures.push('plugin manifest loadScripts missing');
}

const entryPaths = loadScripts
  .filter((scriptName) => typeof scriptName === 'string' && scriptName.endsWith('.js'))
  .map((scriptName) => path.join(distDir, scriptName));

for (const entryPath of entryPaths) {
  assertFile(entryPath, 'plugin load script');
}

for (const exposedName of Object.keys(exposedModules)) {
  assertDistFileByPrefix(`exposed-${exposedName}-chunk`, `exposed module ${exposedName}`);
}

const criticalChunks = [
  'exposed-AIOpsFlags-chunk',
  'exposed-NullContextProvider-chunk',
  'exposed-useAssistantOverlay-chunk',
  'exposed-useOpenAIOps-chunk',
];

const extensions = Array.isArray(manifest?.extensions) ? manifest.extensions : [];
const hasLightspeedFlag = extensions.some(
  (extension) =>
    extension?.type === 'console.flag' &&
    extension?.properties?.handler?.$codeRef === 'AIOpsFlags.enableLightspeedPluginFlag',
);
const hasOpenHandler = extensions.some(
  (extension) =>
    extension?.type === 'console.action/provider' &&
    extension?.properties?.contextId === 'ols-open-handler' &&
    extension?.properties?.provider?.$codeRef === 'useOpenAIOps',
);
const hasAssistantOverlay = extensions.some(
  (extension) =>
    extension?.type === 'console.context-provider' &&
    extension?.properties?.useValueHook?.$codeRef === 'useAssistantOverlay',
);

if (!hasLightspeedFlag) {
  failures.push('console.flag AIOpsFlags.enableLightspeedPluginFlag missing');
}

if (!hasOpenHandler) {
  failures.push('console.action/provider ols-open-handler -> useOpenAIOps missing');
}

if (!hasAssistantOverlay) {
  failures.push('console.context-provider useAssistantOverlay missing');
}

for (const chunkName of criticalChunks) {
  assertDistFileByPrefix(chunkName, `critical console chunk ${chunkName}`);
}

const entryPath = entryPaths.find((candidate) => fs.existsSync(candidate));
if (entryPath) {
  const entryText = fs.readFileSync(entryPath, 'utf8');
  for (const exposedName of Object.keys(exposedModules)) {
    const chunkId = `exposed-${exposedName}`;
    if (!entryText.includes(chunkId)) {
      failures.push(`plugin entry does not reference ${chunkId}`);
    }
  }
}

if (failures.length > 0) {
  console.error('Plugin dist verification failed:');
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log(
  `Plugin dist verification passed: ${Object.keys(exposedModules).length} exposed modules and ${criticalChunks.length} critical chunks found.`,
);
