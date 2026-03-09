#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');
const stylesPath = path.join(repoRoot, 'ui', 'styles.css');
const appPath = path.join(repoRoot, 'ui', 'app.js');

function fail(message) {
  console.error(`[pdf-layout-contract] ${message}`);
  process.exit(1);
}

function readFile(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    fail(`Unable to read ${filePath}: ${err.message}`);
  }
}

const styles = readFile(stylesPath);
const startMarker = '/* PDF_LAYOUT_CONTRACT_START';
const endMarker = '/* PDF_LAYOUT_CONTRACT_END */';
const startIdx = styles.indexOf(startMarker);
const endIdx = styles.indexOf(endMarker);

if (startIdx < 0 || endIdx < 0 || endIdx <= startIdx) {
  fail('Missing or invalid PDF layout contract markers in ui/styles.css.');
}

const contractBlock = styles.slice(startIdx, endIdx);
const requiredStyleTokens = [
  '.pdf-wrap {',
  'flex: 1 1 auto;',
  'height: 100%;',
  'display: flex;',
  'flex-direction: column;',
  '.pdf-canvas-wrap,',
  '.pdf-frame {',
  'min-height: 0;',
  '.pdf-frame {',
  'height: 100%;'
];

for (const token of requiredStyleTokens) {
  if (!contractBlock.includes(token)) {
    fail(`Required style token missing from contract block: ${token}`);
  }
}

const appJs = readFile(appPath);
if (!appJs.includes('function enforcePdfLayoutContract()')) {
  fail('Runtime PDF layout enforcer function missing in ui/app.js.');
}

const enforceCallCount = (appJs.match(/\benforcePdfLayoutContract\(\);/g) || []).length;
if (enforceCallCount < 4) {
  fail(`Expected at least 4 runtime enforcer calls, found ${enforceCallCount}.`);
}

console.log('[pdf-layout-contract] OK');
