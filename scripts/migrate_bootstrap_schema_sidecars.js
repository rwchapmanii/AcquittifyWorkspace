#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const BOOTSTRAP_SCHEMA_FILENAME = 'BOOTSTRAP_SCHEMA_README.md';
const BOOTSTRAP_SCHEMA_VERSION = '1.2';
const SIDE_CAR_MARKER = `<!-- ACQUITTIFY_BOOTSTRAP_SCHEMA_SIDECAR_VERSION:${BOOTSTRAP_SCHEMA_VERSION} -->`;
const WALK_SKIP_DIRS = new Set([
  '.git',
  'node_modules',
  'dist',
  'build',
  '.next',
  '.cache'
]);

function toPosixRel(root, absPath) {
  return path.relative(root, absPath).replaceAll('\\', '/');
}

function loadSchemaInfo(workspaceRoot, searchRoot) {
  const candidates = [
    path.resolve(workspaceRoot, BOOTSTRAP_SCHEMA_FILENAME),
    path.resolve(searchRoot, BOOTSTRAP_SCHEMA_FILENAME),
    path.resolve(workspaceRoot, 'AcquittifyElectron', BOOTSTRAP_SCHEMA_FILENAME)
  ];
  for (const candidate of candidates) {
    try {
      if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) continue;
      const text = String(fs.readFileSync(candidate, 'utf-8') || '').trim();
      if (!text) continue;
      return { path: candidate, text };
    } catch {
      // continue
    }
  }
  return {
    path: '',
    text: [
      '# Bootstrap Schema',
      '',
      `Schema file not found. Expected filename: ${BOOTSTRAP_SCHEMA_FILENAME}`,
      '',
      `Required bootstrap schema version: ${BOOTSTRAP_SCHEMA_VERSION}`
    ].join('\n')
  };
}

function summarizeBootstrapJsonTopLevel(value) {
  if (Array.isArray(value)) {
    return [
      '- Top-level type: `array`',
      `- Item count: ${value.length}`
    ];
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value);
    const preview = keys.slice(0, 60).map((k) => `  - \`${k}\``);
    if (keys.length > 60) preview.push(`  - ... ${keys.length - 60} more key(s)`);
    return [
      '- Top-level type: `object`',
      `- Key count: ${keys.length}`,
      '- Keys:',
      ...preview
    ];
  }
  const raw = String(value ?? '');
  const preview = raw.length > 160 ? `${raw.slice(0, 160)}...` : raw;
  return [
    '- Top-level type: `scalar`',
    `- Value preview: \`${preview.replaceAll('`', "'")}\``
  ];
}

function buildBootstrapSchemaSidecarMarkdown(caseRoot, absJsonPath, value, schemaInfo) {
  const relJsonPath = toPosixRel(caseRoot, absJsonPath);
  const nodeType = String(value?.node_type || '').trim();
  const nodeId = String(value?.node_id || '').trim();
  const nodeBootstrapVersion = String(value?.bootstrap_version || '').trim() || BOOTSTRAP_SCHEMA_VERSION;
  const schemaSourcePath = String(schemaInfo?.path || '').trim() || BOOTSTRAP_SCHEMA_FILENAME;
  const schemaText = String(schemaInfo?.text || '').trim();

  return [
    '# Bootstrap Schema Sidecar',
    SIDE_CAR_MARKER,
    '',
    `- JSON file: \`${relJsonPath}\``,
    `- Bootstrap schema version: \`${BOOTSTRAP_SCHEMA_VERSION}\``,
    `- Node bootstrap version: \`${nodeBootstrapVersion}\``,
    `- Node type: \`${nodeType || 'n/a'}\``,
    `- Node id: \`${nodeId || 'n/a'}\``,
    `- Generated at: \`${new Date().toISOString()}\``,
    `- Schema source: \`${schemaSourcePath}\``,
    '',
    '## File Shape',
    ...summarizeBootstrapJsonTopLevel(value),
    '',
    '## Established Bootstrap Schema',
    '',
    schemaText,
    ''
  ].join('\n');
}

function walkDirs(startRoot, onDir) {
  const stack = [path.resolve(startRoot)];
  const seen = new Set();
  while (stack.length) {
    const cur = stack.pop();
    if (!cur) continue;
    let real = cur;
    try {
      real = fs.realpathSync.native(cur);
    } catch {
      // continue with unresolved path
    }
    if (seen.has(real)) continue;
    seen.add(real);

    let stat = null;
    try {
      stat = fs.statSync(cur);
    } catch {
      continue;
    }
    if (!stat.isDirectory()) continue;

    onDir(cur);

    let entries = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      if (entry.isSymbolicLink()) continue;
      if (WALK_SKIP_DIRS.has(entry.name)) continue;
      stack.push(path.join(cur, entry.name));
    }
  }
}

function findCasefileRoots(searchRoot) {
  const out = [];
  walkDirs(searchRoot, (dirPath) => {
    if (path.basename(dirPath).toLowerCase() === 'casefile') {
      out.push(path.resolve(dirPath));
    }
  });
  return out.sort((a, b) => a.localeCompare(b));
}

function collectJsonFiles(casefileRoot) {
  const out = [];
  const stack = [casefileRoot];
  while (stack.length) {
    const cur = stack.pop();
    if (!cur) continue;
    let entries = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const abs = path.join(cur, entry.name);
      if (entry.isDirectory()) {
        stack.push(abs);
        continue;
      }
      if (!entry.isFile()) continue;
      if (!entry.name.toLowerCase().endsWith('.json')) continue;
      out.push(abs);
    }
  }
  return out.sort((a, b) => a.localeCompare(b));
}

function readJsonFileSafe(absPath) {
  try {
    return JSON.parse(fs.readFileSync(absPath, 'utf-8'));
  } catch {
    return {};
  }
}

function migrateCasefileRoot(casefileRoot, schemaInfo) {
  let written = 0;
  const jsonFiles = collectJsonFiles(casefileRoot);
  for (const absJsonPath of jsonFiles) {
    const value = readJsonFileSafe(absJsonPath);
    const sidecarPath = absJsonPath.replace(/\.json$/i, '.md');
    const markdown = buildBootstrapSchemaSidecarMarkdown(casefileRoot, absJsonPath, value, schemaInfo);
    fs.mkdirSync(path.dirname(sidecarPath), { recursive: true });
    fs.writeFileSync(sidecarPath, `${markdown.trimEnd()}\n`, 'utf-8');
    written += 1;
  }
  return { jsonFiles: jsonFiles.length, sidecarsWritten: written };
}

function run() {
  const workspaceRoot = path.resolve(__dirname, '..');
  const searchRoot = path.resolve(process.argv[2] || process.cwd());

  if (!fs.existsSync(searchRoot) || !fs.statSync(searchRoot).isDirectory()) {
    throw new Error(`Search root is not a directory: ${searchRoot}`);
  }

  const schemaInfo = loadSchemaInfo(workspaceRoot, searchRoot);
  const casefileRoots = findCasefileRoots(searchRoot);

  let totalJson = 0;
  let totalSidecars = 0;
  for (const casefileRoot of casefileRoots) {
    const result = migrateCasefileRoot(casefileRoot, schemaInfo);
    totalJson += result.jsonFiles;
    totalSidecars += result.sidecarsWritten;
    console.log(`casefile=${casefileRoot} json=${result.jsonFiles} sidecars_written=${result.sidecarsWritten}`);
  }

  console.log(`casefiles_found=${casefileRoots.length}`);
  console.log(`json_files_processed=${totalJson}`);
  console.log(`sidecars_written=${totalSidecars}`);
}

try {
  run();
} catch (err) {
  console.error(err?.message || err);
  process.exitCode = 1;
}

