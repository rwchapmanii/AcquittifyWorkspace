#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');
const appPath = path.join(repoRoot, 'ui', 'app.js');
const stylesPath = path.join(repoRoot, 'ui', 'styles.css');
const indexHtmlPath = path.join(repoRoot, 'ui', 'index.html');

function fail(message) {
  console.error(`[ui-smoke] ${message}`);
  process.exit(1);
}

function readFile(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    fail(`Unable to read ${filePath}: ${err.message}`);
  }
}

function assertIncludes(haystack, token, sourceName) {
  if (!haystack.includes(token)) {
    fail(`Missing token in ${sourceName}: ${token}`);
  }
}

const appJs = readFile(appPath);
const stylesCss = readFile(stylesPath);
const indexHtml = readFile(indexHtmlPath);

const requiredAppTokens = [
  'function initShell()',
  'class="app-shell"',
  'class="sidebar-layout"',
  'class="center-pane"',
  'class="right-pane"',
  'id="editor"',
  'id="pdfWrap"',
  'id="mediaWrap"',
  'id="graphWrap"',
  'id="ontologyGraphWrap"',
  'id="agentConversationSelect"',
  'id="agentMessages"',
  'id="agentInput"',
  'id="leftSidebarResizer"',
  'id="rightSidebarResizer"',
  'function wireEvents()',
  'els.saveBtn.onclick = saveActive;',
  'els.refreshBtn.onclick = async () => {',
  'els.appReloadBtn.onclick = async () => {',
  'els.agentSend.onclick = runAgent;',
  'window.acquittifyApi.runAgent({',
  'viewKind,',
  'caselawVaultRoots',
  'if (normalizedMeta === \'workspace\') {',
  'return;',
  'function applyVaultViewMode()'
];

for (const token of requiredAppTokens) {
  assertIncludes(appJs, token, 'ui/app.js');
}

const requiredStyleTokens = [
  '.app-shell {',
  '--left-sidebar-width',
  '--right-sidebar-width',
  '--pane-resizer-width',
  'grid-template-columns:',
  'var(--left-sidebar-width)',
  '.pane-resizer',
  '.pane-resizer::before',
  '.left-pane',
  '.center-pane',
  '.right-pane',
  '.pdf-wrap',
  '.graph-wrap',
  '.ontology-graph-wrap',
  '.agent-layout'
];

for (const token of requiredStyleTokens) {
  assertIncludes(stylesCss, token, 'ui/styles.css');
}

const templateMatch = appJs.match(/root\.innerHTML\s*=\s*`([\s\S]*?)`;\s*\n}/);
if (!templateMatch || !templateMatch[1]) {
  fail('Could not extract initShell template from ui/app.js');
}
const templateHtml = templateMatch[1];

const htmlIds = Array.from(templateHtml.matchAll(/\sid="([^"]+)"/g)).map((m) => m[1]);
const indexIds = Array.from(indexHtml.matchAll(/\sid="([^"]+)"/g)).map((m) => m[1]);
const htmlIdSet = new Set([...htmlIds, ...indexIds]);
if (!htmlIdSet.size) {
  fail('No ids found in initShell template.');
}

const duplicateHtmlIds = Array.from(
  htmlIds.reduce((map, id) => {
    map.set(id, (map.get(id) || 0) + 1);
    return map;
  }, new Map())
)
  .filter(([, count]) => count > 1)
  .map(([id]) => id);
if (duplicateHtmlIds.length) {
  fail(`Duplicate ids in initShell template: ${duplicateHtmlIds.join(', ')}`);
}

const getElementByIdRefs = Array.from(appJs.matchAll(/document\.getElementById\('([^']+)'\)/g)).map((m) => m[1]);
const missingRefs = Array.from(new Set(getElementByIdRefs.filter((id) => !htmlIdSet.has(id))));
if (missingRefs.length) {
  fail(`IDs referenced in cache/events but absent from initShell template: ${missingRefs.join(', ')}`);
}

const requiredControls = [
  'vaultImportBtn',
  'vaultChooseBtn',
  'saveBtn',
  'refreshBtn',
  'appReloadBtn',
  'agentSend',
  'agentNewConversation',
  'agentConversationSelect',
  'leftSidebarResizer',
  'rightSidebarResizer'
];

for (const controlId of requiredControls) {
  if (!htmlIdSet.has(controlId)) {
    fail(`Expected control id missing from template: ${controlId}`);
  }
}

console.log('[ui-smoke] OK');
