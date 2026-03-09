#!/usr/bin/env node
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.resolve(__dirname, '..');
const LOCK_PATH = path.join(ROOT_DIR, 'config', 'ontology-graph-lock.json');
const DEFAULT_LOCKED_FILES = [
  'main.js',
  'ui/app.js',
  'ui/styles.css',
  'scripts/verify-ontology-filters.js'
];

function toPosix(relPath) {
  return String(relPath || '').replace(/\\/g, '/');
}

function hashFile(absPath) {
  const content = fs.readFileSync(absPath);
  return crypto.createHash('sha256').update(content).digest('hex');
}

function loadLockFile() {
  if (!fs.existsSync(LOCK_PATH)) return null;
  const raw = fs.readFileSync(LOCK_PATH, 'utf8');
  return JSON.parse(raw);
}

function buildLockPayload(paths) {
  const files = paths.map((relPath) => {
    const normalizedPath = toPosix(relPath);
    const absPath = path.join(ROOT_DIR, normalizedPath);
    return {
      path: normalizedPath,
      sha256: hashFile(absPath)
    };
  });
  return {
    version: 1,
    generated_at: new Date().toISOString(),
    note: 'Update intentionally with: npm run check:ontology-graph-lock:update',
    files
  };
}

function writeLockFile(payload) {
  fs.mkdirSync(path.dirname(LOCK_PATH), { recursive: true });
  fs.writeFileSync(LOCK_PATH, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function updateLock() {
  const existing = loadLockFile();
  const filePaths = Array.isArray(existing?.files) && existing.files.length
    ? existing.files.map((entry) => toPosix(entry.path)).filter(Boolean)
    : DEFAULT_LOCKED_FILES.slice();
  const payload = buildLockPayload(filePaths);
  writeLockFile(payload);
  console.log(`[ontology-graph-lock] updated ${LOCK_PATH}`);
  console.log(`[ontology-graph-lock] locked files: ${filePaths.length}`);
}

function verifyLock() {
  const payload = loadLockFile();
  if (!payload || !Array.isArray(payload.files) || !payload.files.length) {
    console.error('[ontology-graph-lock] lock file missing or invalid.');
    console.error('[ontology-graph-lock] run: npm run check:ontology-graph-lock:update');
    process.exit(1);
  }

  const mismatches = [];
  for (const entry of payload.files) {
    const relPath = toPosix(entry?.path);
    const expected = String(entry?.sha256 || '').trim().toLowerCase();
    const absPath = path.join(ROOT_DIR, relPath);
    if (!relPath || !expected) {
      mismatches.push({ path: relPath || '<invalid>', reason: 'invalid_lock_entry' });
      continue;
    }
    if (!fs.existsSync(absPath)) {
      mismatches.push({ path: relPath, reason: 'missing_file' });
      continue;
    }
    const actual = hashFile(absPath);
    if (actual !== expected) {
      mismatches.push({
        path: relPath,
        reason: 'hash_mismatch',
        expected,
        actual
      });
    }
  }

  if (mismatches.length) {
    console.error('[ontology-graph-lock] locked ontology graph files changed.');
    for (const item of mismatches) {
      if (item.reason === 'hash_mismatch') {
        console.error(`  - ${item.path}: expected ${item.expected}, got ${item.actual}`);
      } else {
        console.error(`  - ${item.path}: ${item.reason}`);
      }
    }
    console.error('[ontology-graph-lock] if this change is intentional, run:');
    console.error('  npm run check:ontology-graph-lock:update');
    process.exit(1);
  }

  console.log(`[ontology-graph-lock] ok (${payload.files.length} files)`);
}

if (process.argv.includes('--update')) {
  updateLock();
} else {
  verifyLock();
}
