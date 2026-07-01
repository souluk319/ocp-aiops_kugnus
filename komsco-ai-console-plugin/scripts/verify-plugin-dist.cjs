'use strict';

const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const distDir = path.join(rootDir, 'dist');
const packageJsonPath = path.join(rootDir, 'package.json');
const manifestPath = path.join(distDir, 'plugin-manifest.json');
const entryPath = path.join(distDir, 'plugin-entry.js');

const failures = [];

const assertFile = (filePath, label) => {
  if (!fs.existsSync(filePath)) {
    failures.push(`${label} missing: ${path.relative(rootDir, filePath)}`);
  }
};

assertFile(manifestPath, 'plugin manifest');
assertFile(entryPath, 'plugin entry');

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
const exposedModules = packageJson.consolePlugin?.exposedModules || {};

for (const exposedName of Object.keys(exposedModules)) {
  assertFile(
    path.join(distDir, `exposed-${exposedName}-chunk.js`),
    `exposed module ${exposedName}`,
  );
}

const criticalChunks = [
  'components_AssistantLauncher_tsx-chunk.js',
  'exposed-NullContextProvider-chunk.js',
  'exposed-useAssistantOverlay-chunk.js',
];

for (const chunkName of criticalChunks) {
  assertFile(path.join(distDir, chunkName), `critical console chunk ${chunkName}`);
}

if (fs.existsSync(manifestPath)) {
  JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
}

if (fs.existsSync(entryPath)) {
  const entryText = fs.readFileSync(entryPath, 'utf8');
  for (const exposedName of Object.keys(exposedModules)) {
    const chunkId = `exposed-${exposedName}`;
    if (!entryText.includes(`"${chunkId}"`) && !entryText.includes(` ${chunkId} `)) {
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
