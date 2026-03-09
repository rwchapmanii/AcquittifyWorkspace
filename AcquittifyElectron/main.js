const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const os = require('os');
const path = require('path');
const fs = require('fs');
const readline = require('readline');
const http = require('http');
const querystring = require('querystring');
const crypto = require('crypto');
const { spawnSync, spawn } = require('child_process');
const { Readable } = require('stream');
const { pathToFileURL, URL } = require('url');
const mammoth = require('mammoth');
const xlsx = require('xlsx');
let yaml = null;
try {
  yaml = require('js-yaml');
} catch {
  yaml = null;
}
const { simpleParser } = require('mailparser');
const MsgReader = require('@kenjiuno/msgreader').default;

const STARTUP_LOG_FILENAME = 'acquittify.startup.log';
const STARTUP_LOG_ENABLED = process.env.ACQUITTIFY_STARTUP_LOG !== '0';
function resolveStartupLogPath() {
  try {
    const userData = app.getPath('userData');
    if (userData) return path.join(userData, STARTUP_LOG_FILENAME);
  } catch {
    // ignore and fall back
  }
  return path.join(
    os.homedir(),
    'Library',
    'Application Support',
    'acquittifyelectron',
    STARTUP_LOG_FILENAME
  );
}

function logStartup(message) {
  if (!STARTUP_LOG_ENABLED) return;
  try {
    const target = resolveStartupLogPath();
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.appendFileSync(target, `[${new Date().toISOString()}] ${message}\n`, 'utf-8');
  } catch {
    // ignore logging failures
  }
}

process.on('uncaughtException', (err) => {
  logStartup(`uncaughtException: ${err?.stack || err}`);
});

process.on('unhandledRejection', (reason) => {
  logStartup(`unhandledRejection: ${reason?.stack || reason}`);
});

logStartup(`main.js loaded (pid=${process.pid}) log=${resolveStartupLogPath()}`);

function loadEnvFile(filePath) {
  let raw = '';
  try {
    raw = fs.readFileSync(filePath, 'utf-8');
  } catch {
    return;
  }

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const exportPrefix = 'export ';
    const clean = trimmed.startsWith(exportPrefix) ? trimmed.slice(exportPrefix.length).trim() : trimmed;
    const idx = clean.indexOf('=');
    if (idx <= 0) continue;

    const key = clean.slice(0, idx).trim();
    if (!key || process.env[key] !== undefined) continue;

    let value = clean.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

loadEnvFile(path.join(__dirname, '.env'));
loadEnvFile(path.join(__dirname, '..', '.env'));

const OPENAI_BASE_URL = (process.env.ACQUITTIFY_OPENAI_BASE_URL || 'https://api.openai.com/v1').replace(/\/+$/, '');
const OPENAI_MODEL = process.env.ACQUITTIFY_AGENT_MODEL || process.env.ACQUITTIFY_OPENAI_MODEL || 'gpt-5.2-codex';
const OPENAI_API_KEY = process.env.ACQUITTIFY_OPENAI_API_KEY || process.env.OPENAI_API_KEY || '';
const OPENCLAW_CONFIG_PATH = path.join(os.homedir(), '.openclaw', 'openclaw.json');
const OPENCLAW_AGENT_ID =
  process.env.ACQUITTIFY_OPENCLAW_AGENT_ID ||
  process.env.OPENCLAW_AGENT_ID ||
  'main';
const OPENCLAW_GATEWAY_HOST =
  process.env.ACQUITTIFY_OPENCLAW_HOST ||
  process.env.OPENCLAW_GATEWAY_HOST ||
  '';
const OPENCLAW_GATEWAY_PORT = Number(
  process.env.ACQUITTIFY_OPENCLAW_PORT || process.env.OPENCLAW_GATEWAY_PORT || 0
);
const OPENCLAW_GATEWAY_TOKEN =
  process.env.ACQUITTIFY_OPENCLAW_TOKEN ||
  process.env.OPENCLAW_GATEWAY_TOKEN ||
  '';
const GRAPH_FILE_LIMIT = Math.max(250, Number(process.env.ACQUITTIFY_GRAPH_FILE_LIMIT || 6000) || 6000);
const ONTOLOGY_GRAPH_FILE_LIMIT = Math.max(
  500,
  Number(process.env.ACQUITTIFY_ONTOLOGY_GRAPH_FILE_LIMIT || 18000) || 18000
);
const CASELAW_DB_GRAPH_SCRIPT = path.join(__dirname, '..', 'scripts', 'caselaw_db_graph.py');
const CASELAW_DB_GRAPH_LIMIT = Math.max(
  500,
  Number(process.env.ACQ_CASELAW_GRAPH_LIMIT || ONTOLOGY_GRAPH_FILE_LIMIT) || ONTOLOGY_GRAPH_FILE_LIMIT
);
const ONTOLOGY_VAULT_ENV =
  process.env.ACQUITTIFY_ONTOLOGY_VAULT ||
  process.env.ACQ_ONTOLOGY_VAULT_ROOT ||
  '';
const VAULT_MARKER_RELATIVE_PATH = path.join('Admin', 'Taxonomy', 'acquittify_taxonomy.yaml');
const VAULT_IMPORT_RELATIVE_DIR = path.join('Evidence', 'Imported');
const MAX_EXTRACTED_TEXT_CHARS = Math.max(50000, Number(process.env.ACQUITTIFY_MAX_EXTRACTED_TEXT || 600000) || 600000);
const LOCAL_DEV_APP_DIR = process.env.ACQUITTIFY_DEV_APP_DIR || path.join(os.homedir(), 'Desktop', 'Acquittify', 'AcquittifyElectron');
const ENABLE_DEV_RELOAD_SWITCH = process.env.ACQUITTIFY_ENABLE_DEV_RELOAD_SWITCH === '1';
const WHATSAPP_ENABLED = process.env.ACQUITTIFY_WHATSAPP_ENABLED === '1';
const WHATSAPP_BIND_HOST = String(process.env.ACQUITTIFY_WHATSAPP_BIND_HOST || '127.0.0.1');
const WHATSAPP_PORT = Math.max(1, Number(process.env.ACQUITTIFY_WHATSAPP_PORT || 8788) || 8788);
const WHATSAPP_VALIDATE_SIGNATURE = process.env.ACQUITTIFY_WHATSAPP_VALIDATE_SIGNATURE === '1';
const WHATSAPP_AUTH_TOKEN = String(process.env.ACQUITTIFY_WHATSAPP_AUTH_TOKEN || process.env.TWILIO_AUTH_TOKEN || '');
const WHATSAPP_PUBLIC_URL = String(process.env.ACQUITTIFY_WHATSAPP_PUBLIC_URL || '').trim();
const WHATSAPP_DEFAULT_MODE = process.env.ACQUITTIFY_WHATSAPP_DEFAULT_MODE === 'caselaw' ? 'caselaw' : 'casefile';
const WHATSAPP_HISTORY_LIMIT = Math.max(4, Number(process.env.ACQUITTIFY_WHATSAPP_HISTORY_LIMIT || 24) || 24);
const WHATSAPP_MAX_MESSAGE_CHARS = Math.max(240, Number(process.env.ACQUITTIFY_WHATSAPP_MAX_MESSAGE_CHARS || 1400) || 1400);
const WHATSAPP_REQUEST_BODY_LIMIT = Math.max(2048, Number(process.env.ACQUITTIFY_WHATSAPP_REQUEST_BODY_LIMIT || 256000) || 256000);
const WHATSAPP_MAX_DOC_EXCERPT_CHARS = Math.max(
  300,
  Number(process.env.ACQUITTIFY_WHATSAPP_MAX_DOC_EXCERPT_CHARS || 1200) || 1200
);
const WHATSAPP_MAX_LIST_ITEMS = Math.max(3, Number(process.env.ACQUITTIFY_WHATSAPP_MAX_LIST_ITEMS || 8) || 8);
const WHATSAPP_ALLOWED_NUMBERS = new Set(
  String(process.env.ACQUITTIFY_WHATSAPP_ALLOWED_NUMBERS || '')
    .split(',')
    .map((item) => String(item || '').trim().toLowerCase())
    .filter(Boolean)
);
const WHATSAPP_ENFORCE_ALLOWLIST =
  process.env.ACQUITTIFY_WHATSAPP_ENFORCE_ALLOWLIST === '1' || WHATSAPP_ALLOWED_NUMBERS.size > 0;
const WHATSAPP_SESSIONS_FILE = 'acquittify.whatsapp.sessions.v1.json';
const PEREGRINE_API_URL = (
  process.env.PEREGRINE_API_URL ||
  process.env.ACQUITTIFY_API_URL ||
  'http://localhost:8000'
).replace(/\/+$/, '');
const PEREGRINE_API_TOKEN =
  process.env.PEREGRINE_API_TOKEN ||
  process.env.ACQUITTIFY_API_TOKEN ||
  process.env.PEREGRINE_API_KEY ||
  '';
const PEREGRINE_API_TIMEOUT_MS = Math.max(
  1000,
  Number(process.env.ACQUITTIFY_WHATSAPP_PEREGRINE_TIMEOUT_MS || 30000) || 30000
);

const PDF_EXTENSIONS = new Set(['.pdf']);
const WORD_EXTENSIONS = new Set(['.doc', '.docx', '.odt', '.rtf']);
const SPREADSHEET_EXTENSIONS = new Set(['.xls', '.xlsx', '.xlsm', '.ods', '.csv', '.tsv']);
const EMAIL_EXTENSIONS = new Set(['.eml', '.msg']);
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.heic', '.heif']);
const AUDIO_EXTENSIONS = new Set(['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma', '.aiff', '.m4b']);
const PRESENTATION_EXTENSIONS = new Set(['.ppt', '.pptx', '.odp']);
const TEXT_EXTENSIONS = new Set([
  '.md',
  '.markdown',
  '.txt',
  '.json',
  '.yaml',
  '.yml',
  '.xml',
  '.html',
  '.htm',
  '.log',
  '.ini',
  '.cfg',
  '.toml'
]);

const ORIGINATING_CIRCUIT_CODES = new Set([
  'ca1',
  'ca2',
  'ca3',
  'ca4',
  'ca5',
  'ca6',
  'ca7',
  'ca8',
  'ca9',
  'ca10',
  'ca11',
  'cadc'
]);

const ORIGINATING_CIRCUIT_LABELS = {
  ca1: 'First Circuit',
  ca2: 'Second Circuit',
  ca3: 'Third Circuit',
  ca4: 'Fourth Circuit',
  ca5: 'Fifth Circuit',
  ca6: 'Sixth Circuit',
  ca7: 'Seventh Circuit',
  ca8: 'Eighth Circuit',
  ca9: 'Ninth Circuit',
  ca10: 'Tenth Circuit',
  ca11: 'Eleventh Circuit',
  cadc: 'D.C. Circuit'
};

const CRIMINAL_CASE_KEYWORDS = [
  'criminal',
  'felony',
  'misdemeanor',
  'indictment',
  'indicted',
  'prosecution',
  'conviction',
  'convicted',
  'sentence',
  'sentencing',
  'habeas',
  'miranda',
  'suppression',
  'probable cause',
  'search warrant',
  'guilty plea',
  'plea agreement',
  'acquittal',
  'double jeopardy',
  'incarcerat',
  'parole',
  'probation'
];

const CIVIL_CASE_KEYWORDS = [
  'civil',
  'plaintiff',
  'damages',
  'injunction',
  'tort',
  'negligence',
  'contract',
  'breach',
  'liability',
  'summary judgment',
  'class action',
  'bankruptcy',
  'patent',
  'trademark',
  'copyright',
  'employment',
  'discrimination',
  'declaratory',
  'equity',
  'administrative procedure'
];

const IMPORT_DIALOG_EXTENSIONS = [
  ...PDF_EXTENSIONS,
  ...WORD_EXTENSIONS,
  ...SPREADSHEET_EXTENSIONS,
  ...EMAIL_EXTENSIONS,
  ...IMAGE_EXTENSIONS,
  ...AUDIO_EXTENSIONS,
  ...PRESENTATION_EXTENSIONS,
  ...TEXT_EXTENSIONS
].map((ext) => ext.slice(1));

const BOOTSTRAP_SCHEMA_FILENAME = 'BOOTSTRAP_SCHEMA_README.md';
const BOOTSTRAP_SCHEMA_VERSION = '1.2';
const PEREGRINE_BOOTSTRAP_PROMPT_VERSION = '2.4';
const PEREGRINE_BOOTSTRAP_PROMPT_ROOT_REL = 'BOOTSTRAP_PROMPT.md';
const PEREGRINE_BOOTSTRAP_PROMPT_NOTE_REL = path.join('Trial', 'Peregrine Bootstrap Prompt.md').replace(/\\/g, '/');
const PEREGRINE_BOOTSTRAP_REFRESH_PROMPT_ROOT_REL = 'BOOTSTRAP_REFRESH_PROMPT.md';
const PEREGRINE_BOOTSTRAP_REFRESH_PROMPT_NOTE_REL = path
  .join('Trial', 'Peregrine Bootstrap Refresh Prompt.md')
  .replace(/\\/g, '/');
const BOOTSTRAP_SKIP_DIRS = new Set([
  '.git',
  'node_modules',
  'dist',
  'build',
  '.next',
  'Casefile'
]);

const FEDERAL_CITATION_PATTERN =
  /\b\d{1,4}\s+(?:U\.?\s*S\.?|S\.?\s*Ct\.?|L\.?\s*Ed\.?\s*2d|L\.?\s*Ed\.?|F\.?\s*Supp\.?\s*3d|F\.?\s*Supp\.?\s*2d|F\.?\s*Supp\.?|F\.?\s*App(?:'|’)?x|F\.?\s*4th|F\.?\s*3d|F\.?\s*2d|F\.?)(?:\s*\([^)\r\n]{1,80}\))?\s+\d{1,5}\b/gi;
const FEDERAL_CITATION_HINT_PATTERN =
  /(U\.?\s*S\.?|S\.?\s*Ct\.?|L\.?\s*Ed\.?|F\.?\s*Supp\.?|F\.?\s*App(?:'|’)?x|F\.?\s*\d+d|F\.?\s*4th)/i;
const ACQUITTIFY_DATA_ROOT = process.env.ACQUITTIFY_DATA_ROOT
  ? path.resolve(process.env.ACQUITTIFY_DATA_ROOT)
  : path.join(os.homedir(), 'AcquittifyData');
const ACQUITTIFY_DATASET_DIR = process.env.ACQUITTIFY_DATASET_DIR
  ? path.resolve(process.env.ACQUITTIFY_DATASET_DIR)
  : path.join(ACQUITTIFY_DATA_ROOT, 'acquittify-data');
const FEDERAL_CAP_CASES_CANDIDATE_DIRS = [
  path.resolve(__dirname, '..', 'acquittify-data', 'ingest', 'cases'),
  path.resolve(process.cwd(), 'acquittify-data', 'ingest', 'cases'),
  path.join(ACQUITTIFY_DATASET_DIR, 'ingest', 'cases'),
  path.resolve(os.homedir(), 'Desktop', 'Acquittify', 'acquittify-data', 'ingest', 'cases')
];
const COURTLISTENER_CITATION_SEARCH_URL = 'https://www.courtlistener.com/api/rest/v4/search/';
const FEDERAL_CITATION_REMOTE_FALLBACK_ENABLED = process.env.ACQUITTIFY_CITATION_REMOTE_FALLBACK !== '0';
const FEDERAL_CITATION_REMOTE_MAX_LOOKUPS = Math.max(
  0,
  Number(process.env.ACQUITTIFY_CITATION_REMOTE_MAX_LOOKUPS || 48) || 48
);
const FEDERAL_CITATION_REMOTE_TIMEOUT_MS = Math.max(
  1000,
  Number(process.env.ACQUITTIFY_CITATION_REMOTE_TIMEOUT_MS || 9000) || 9000
);
const federalCitationLookupCache = new Map();
const federalCitationRemoteLookupCache = new Map();
let federalCapCitationFilesCache = null;
let federalCapCitationIndexCache = null;

const iconPngPath = path.join(__dirname, '..', 'assets', 'app_icon.png');
const iconIcnsPath = path.join(__dirname, '..', 'assets', 'app_icon.icns');
const iconPath = process.platform === 'darwin' ? iconIcnsPath : iconPngPath;

let cachedPdfParseModule = null;
let cachedPdfParseInitError = null;

function loadPdfParseModule() {
  if (cachedPdfParseModule) return cachedPdfParseModule;
  if (cachedPdfParseInitError) throw cachedPdfParseInitError;

  try {
    if (
      typeof globalThis.DOMMatrix === 'undefined' ||
      typeof globalThis.ImageData === 'undefined' ||
      typeof globalThis.Path2D === 'undefined'
    ) {
      try {
        const canvas = require('@napi-rs/canvas');
        if (canvas?.DOMMatrix && typeof globalThis.DOMMatrix === 'undefined') {
          globalThis.DOMMatrix = canvas.DOMMatrix;
        }
        if (canvas?.ImageData && typeof globalThis.ImageData === 'undefined') {
          globalThis.ImageData = canvas.ImageData;
        }
        if (canvas?.Path2D && typeof globalThis.Path2D === 'undefined') {
          globalThis.Path2D = canvas.Path2D;
        }
      } catch {
        // Continue; newer pdf-parse may still work without these depending on runtime.
      }
    }

    cachedPdfParseModule = require('pdf-parse');
    return cachedPdfParseModule;
  } catch (err) {
    cachedPdfParseInitError = err;
    throw err;
  }
}

function getSettingsPath() {
  return path.join(app.getPath('userData'), 'acquittify.settings.json');
}

function readAppSettings() {
  const settingsPath = getSettingsPath();
  try {
    const raw = fs.readFileSync(settingsPath, 'utf-8');
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeAppSettings(nextSettings) {
  const settingsPath = getSettingsPath();
  try {
    fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
    fs.writeFileSync(settingsPath, JSON.stringify(nextSettings || {}, null, 2), 'utf-8');
  } catch {
    // ignore settings persistence issues
  }
}

function readOpenclawConfig() {
  try {
    const raw = fs.readFileSync(OPENCLAW_CONFIG_PATH, 'utf-8');
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function resolveOpenclawGatewayConfig() {
  const cfg = readOpenclawConfig();
  const gateway = cfg.gateway || {};
  const auth = gateway.auth || {};
  const token = String(OPENCLAW_GATEWAY_TOKEN || auth.token || '').trim();
  const port = Number(OPENCLAW_GATEWAY_PORT || gateway.port || 18789);
  const bind = String(OPENCLAW_GATEWAY_HOST || gateway.bind || 'loopback').trim();
  let host = '127.0.0.1';
  if (bind && bind !== 'loopback' && bind !== 'localhost' && bind !== '127.0.0.1') {
    if (bind === '0.0.0.0' || bind === '::' || bind === '::1') {
      host = '127.0.0.1';
    } else {
      host = bind;
    }
  }
  return {
    baseUrl: `http://${host}:${port}`,
    token,
    agentId: OPENCLAW_AGENT_ID || 'main'
  };
}

function buildOpenclawSessionUser(conversationId = '') {
  const normalized = String(conversationId || '').trim();
  if (normalized) return `acquittify:${normalized}`;
  return `acquittify:${crypto.randomUUID()}`;
}

function extractOpenclawOutputText(payload) {
  if (!payload || typeof payload !== 'object') return '';
  if (typeof payload.output_text === 'string') return payload.output_text;
  const output = Array.isArray(payload.output) ? payload.output : [];
  const parts = [];
  for (const item of output) {
    if (!item || typeof item !== 'object') continue;
    const content = Array.isArray(item.content) ? item.content : [];
    for (const part of content) {
      if (part && typeof part.text === 'string') parts.push(part.text);
    }
  }
  return parts.join('');
}

async function fetchOpenclawResponses(payload, { signal } = {}) {
  if (typeof fetch !== 'function') {
    throw new Error('Fetch API is unavailable in this runtime.');
  }
  const cfg = resolveOpenclawGatewayConfig();
  if (!cfg.token) {
    throw new Error('OpenClaw gateway token is missing.');
  }
  const res = await fetch(`${cfg.baseUrl}/v1/responses`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${cfg.token}`,
      'Content-Type': 'application/json',
      'x-openclaw-agent-id': cfg.agentId
    },
    body: JSON.stringify(payload),
    signal
  });
  return res;
}

async function runOpenclawResponse(prompt, conversationId = '') {
  const user = buildOpenclawSessionUser(conversationId);
  const payload = {
    model: 'openclaw',
    input: String(prompt || ''),
    stream: false,
    user
  };
  const res = await fetchOpenclawResponses(payload);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`OpenClaw gateway error (${res.status}): ${errText}`);
  }
  const data = await res.json();
  if (data?.error?.message) {
    throw new Error(String(data.error.message));
  }
  const answer = extractOpenclawOutputText(data) || 'No response.';
  return {
    answer,
    model: 'openclaw',
    responseId: data?.id || ''
  };
}

function parseSseChunk(raw = '') {
  const lines = String(raw || '').split(/\r?\n/);
  let eventType = '';
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim();
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (!dataLines.length) return null;
  const data = dataLines.join('\n');
  if (data === '[DONE]') return { done: true };
  try {
    const payload = JSON.parse(data);
    return { done: false, eventType, payload };
  } catch {
    return { done: false, eventType, payload: null, raw: data };
  }
}

async function streamOpenclawResponse({ prompt, conversationId, runId }) {
  const user = buildOpenclawSessionUser(conversationId);
  const payload = {
    model: 'openclaw',
    input: String(prompt || ''),
    stream: true,
    user
  };
  const res = await fetchOpenclawResponses(payload);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`OpenClaw gateway error (${res.status}): ${errText}`);
  }
  if (!res.body) {
    throw new Error('OpenClaw gateway stream unavailable.');
  }
  const stream = Readable.fromWeb(res.body);
  let buffer = '';
  let accumulated = '';

  for await (const chunk of stream) {
    buffer += chunk.toString('utf-8');
    let boundaryIndex = -1;
    let boundaryLength = 0;
    const findBoundary = () => {
      const idxLF = buffer.indexOf('\n\n');
      const idxCRLF = buffer.indexOf('\r\n\r\n');
      if (idxLF !== -1 && (idxCRLF === -1 || idxLF < idxCRLF)) {
        boundaryIndex = idxLF;
        boundaryLength = 2;
        return true;
      }
      if (idxCRLF !== -1) {
        boundaryIndex = idxCRLF;
        boundaryLength = 4;
        return true;
      }
      return false;
    };
    while (findBoundary()) {
      const raw = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + boundaryLength);
      const event = parseSseChunk(raw);
      if (!event) continue;
      if (event.done) {
        sendAgentStreamEvent(runId, { type: 'complete', text: accumulated });
        return accumulated;
      }
      const payloadEvent = event.payload;
      const type = payloadEvent?.type || event.eventType;
      if (type === 'response.output_text.delta') {
        const delta = payloadEvent?.delta;
        if (typeof delta === 'string' && delta.length) {
          accumulated += delta;
          sendAgentStreamEvent(runId, { type: 'delta', delta });
        }
        continue;
      }
      if (type === 'response.failed') {
        const errMsg =
          payloadEvent?.error?.message ||
          payloadEvent?.error ||
          'OpenClaw response failed.';
        sendAgentStreamEvent(runId, { type: 'error', error: String(errMsg) });
        return accumulated;
      }
    }
  }

  sendAgentStreamEvent(runId, { type: 'complete', text: accumulated });
  return accumulated;
}

function looksLikeAcquittifyVault(candidatePath) {
  try {
    const markerPath = path.join(candidatePath, VAULT_MARKER_RELATIVE_PATH);
    return fs.existsSync(markerPath) && fs.statSync(markerPath).isFile();
  } catch {
    return false;
  }
}

function looksLikeCaselawVault(candidatePath) {
  try {
    const ontologyDir = path.join(candidatePath, 'Ontology', 'precedent_vault');
    return fs.existsSync(ontologyDir) && fs.statSync(ontologyDir).isDirectory();
  } catch {
    return false;
  }
}

function looksLikeCasefileWorkspace(candidatePath) {
  try {
    const casefileDir = path.join(candidatePath, 'Casefile');
    if (fs.existsSync(casefileDir) && fs.statSync(casefileDir).isDirectory()) return true;
  } catch {
    // ignore and keep checking
  }
  return looksLikeAcquittifyVault(candidatePath);
}

function listObsidianVaultDirectories() {
  if (process.env.ACQUITTIFY_SKIP_OBSIDIAN_DISCOVERY === '1') {
    logStartup('listObsidianVaultDirectories: skipped via env');
    return [];
  }
  const docsRoot = path.join(os.homedir(), 'Library', 'Mobile Documents', 'iCloud~md~obsidian', 'Documents');
  let entries = [];
  try {
    logStartup(`listObsidianVaultDirectories: scanning ${docsRoot}`);
    entries = fs.readdirSync(docsRoot, { withFileTypes: true });
  } catch {
    logStartup('listObsidianVaultDirectories: scan failed');
    return [];
  }
  return entries
    .filter((entry) => entry && typeof entry.isDirectory === 'function' && entry.isDirectory())
    .map((entry) => path.join(docsRoot, entry.name));
}

const CIRCUIT_NAME_PATTERNS = [
  { label: 'First Circuit', patterns: [/\bfirst\b/i, /\b1st\b/i, /\bca[\s._-]*1\b/i, /\bcircuit[\s._-]*1\b/i] },
  { label: 'Second Circuit', patterns: [/\bsecond\b/i, /\b2nd\b/i, /\bca[\s._-]*2\b/i, /\bcircuit[\s._-]*2\b/i] },
  { label: 'Third Circuit', patterns: [/\bthird\b/i, /\b3rd\b/i, /\bca[\s._-]*3\b/i, /\bcircuit[\s._-]*3\b/i] },
  { label: 'Fourth Circuit', patterns: [/\bfourth\b/i, /\b4th\b/i, /\bca[\s._-]*4\b/i, /\bcircuit[\s._-]*4\b/i] },
  { label: 'Fifth Circuit', patterns: [/\bfifth\b/i, /\b5th\b/i, /\bca[\s._-]*5\b/i, /\bcircuit[\s._-]*5\b/i] },
  { label: 'Sixth Circuit', patterns: [/\bsixth\b/i, /\b6th\b/i, /\bca[\s._-]*6\b/i, /\bcircuit[\s._-]*6\b/i] },
  { label: 'Seventh Circuit', patterns: [/\bseventh\b/i, /\b7th\b/i, /\bca[\s._-]*7\b/i, /\bcircuit[\s._-]*7\b/i] },
  { label: 'Eighth Circuit', patterns: [/\beighth\b/i, /\b8th\b/i, /\bca[\s._-]*8\b/i, /\bcircuit[\s._-]*8\b/i] },
  { label: 'Ninth Circuit', patterns: [/\bninth\b/i, /\b9th\b/i, /\bca[\s._-]*9\b/i, /\bcircuit[\s._-]*9\b/i] },
  { label: 'Tenth Circuit', patterns: [/\btenth\b/i, /\b10th\b/i, /\bca[\s._-]*10\b/i, /\bcircuit[\s._-]*10\b/i] },
  { label: 'Eleventh Circuit', patterns: [/\beleventh\b/i, /\b11th\b/i, /\bca[\s._-]*11\b/i, /\bcircuit[\s._-]*11\b/i] },
  { label: 'D.C. Circuit', patterns: [/\bd\.?c\.?\b/i, /\bcadc\b/i, /\bdistrict of columbia\b/i] }
];

function inferJurisdictionLabelFromVaultPath(vaultPath) {
  const base = String(path.basename(vaultPath || '') || '').trim();
  const normalized = base.replace(/[_-]+/g, ' ');
  if (/supreme\s*court/i.test(normalized) || /\bscotus\b/i.test(normalized)) {
    return 'Supreme Court';
  }
  for (const item of CIRCUIT_NAME_PATTERNS) {
    if (item.patterns.some((pattern) => pattern.test(normalized))) {
      return item.label;
    }
  }
  return normalized || vaultPath;
}

function discoverCaselawVaultJurisdictions(activeVaultRoot = '') {
  const candidates = [];
  if (activeVaultRoot) candidates.push(path.resolve(activeVaultRoot));
  for (const vaultDir of listObsidianVaultDirectories()) {
    candidates.push(path.resolve(vaultDir));
  }

  const uniqueRoots = [];
  for (const candidate of candidates) {
    if (!candidate || uniqueRoots.includes(candidate)) continue;
    if (!looksLikeCaselawVault(candidate)) continue;
    uniqueRoots.push(candidate);
  }

  const entries = uniqueRoots.map((vaultRoot) => ({
    id: vaultRoot,
    label: inferJurisdictionLabelFromVaultPath(vaultRoot),
    vaultRoot
  }));

  const priority = (label) => (String(label || '').toLowerCase() === 'supreme court' ? 0 : 1);
  entries.sort((a, b) => {
    const p = priority(a.label) - priority(b.label);
    if (p) return p;
    return String(a.label).localeCompare(String(b.label));
  });

  return entries;
}

function normalizeCaselawVaultRoots(vaultRoots = [], fallbackRoot = '') {
  const roots = [];
  for (const raw of Array.isArray(vaultRoots) ? vaultRoots : []) {
    const trimmed = String(raw || '').trim();
    if (!trimmed) continue;
    const resolved = path.resolve(trimmed);
    if (!resolved || roots.includes(resolved)) continue;
    if (!pathIsDirectory(resolved)) continue;
    if (!looksLikeCaselawVault(resolved)) continue;
    roots.push(resolved);
  }

  if (!roots.length) {
    const fallback = String(fallbackRoot || '').trim();
    if (fallback) {
      const resolvedFallback = path.resolve(fallback);
      if (pathIsDirectory(resolvedFallback) && looksLikeCaselawVault(resolvedFallback)) {
        roots.push(resolvedFallback);
      }
    }
  }

  return roots;
}

function getVaultAccess(rootPath) {
  const access = {
    exists: false,
    isDirectory: false,
    readable: false,
    writable: false,
    casefilePresent: false,
    markerPresent: false,
    caselawPresent: false,
    vaultKind: '',
    error: ''
  };

  if (!rootPath) {
    access.error = 'Vault root is not configured.';
    return access;
  }

  let stat = null;
  try {
    stat = fs.statSync(rootPath);
  } catch {
    access.error = 'Vault path does not exist.';
    return access;
  }

  access.exists = true;
  access.isDirectory = stat.isDirectory();
  if (!access.isDirectory) {
    access.error = 'Vault path is not a directory.';
    return access;
  }

  try {
    fs.accessSync(rootPath, fs.constants.R_OK);
    access.readable = true;
  } catch {
    access.error = 'Vault path is not readable.';
  }

  try {
    fs.accessSync(rootPath, fs.constants.W_OK);
    access.writable = true;
  } catch {
    access.error = access.error || 'Vault path is read-only.';
  }

  access.markerPresent = looksLikeAcquittifyVault(rootPath);
  access.casefilePresent = looksLikeCasefileWorkspace(rootPath);
  access.caselawPresent = looksLikeCaselawVault(rootPath);
  // Prefer editable casefile mode when both casefile and caselaw structures exist.
  if (access.casefilePresent) {
    access.vaultKind = 'casefile';
  } else if (access.caselawPresent) {
    access.vaultKind = 'caselaw';
  } else {
    access.vaultKind = 'casefile';
  }
  return access;
}

function resolveVaultPath(settings = {}) {
  if (process.env.ACQUITTIFY_OBSIDIAN_VAULT) {
    return path.resolve(process.env.ACQUITTIFY_OBSIDIAN_VAULT);
  }
  if (process.env.ACQUITTIFY_SKIP_VAULT_DISCOVERY === '1') {
    const fallback = settings?.vaultRoot ? path.resolve(settings.vaultRoot) : '';
    logStartup(`resolveVaultPath: skipped discovery; fallback=${fallback || 'none'}`);
    return fallback;
  }
  if (settings?.vaultRoot) {
    const preferred = path.resolve(settings.vaultRoot);
    try {
      if (fs.existsSync(preferred) && fs.statSync(preferred).isDirectory()) {
        return preferred;
      }
    } catch {
      // continue to auto-resolution
    }
  }

  const home = os.homedir();
  const obsidianVaults = listObsidianVaultDirectories();
  const candidates = [
    ...obsidianVaults,
    path.join(home, 'Library', 'Mobile Documents', 'iCloud~md~obsidian', 'Documents', 'Acquittify'),
    path.join(home, 'Library', 'Mobile Documents', 'iCloud~md~obsidian', 'Documents', 'Supreme Court'),
    path.join(home, 'Desktop', 'Acquittify'),
    path.join(home, 'Desktop', 'Acquittify', 'vault')
  ];

  const uniqueCandidates = [];
  for (const c of candidates) {
    if (!c) continue;
    const normalized = path.resolve(c);
    if (!uniqueCandidates.includes(normalized)) uniqueCandidates.push(normalized);
  }

  const existingDirs = [];
  for (const c of uniqueCandidates) {
    try {
      if (fs.existsSync(c) && fs.statSync(c).isDirectory()) {
        existingDirs.push(c);
      }
    } catch {
      // ignore
    }
  }

  const matchingVault = existingDirs.find((c) => looksLikeAcquittifyVault(c));
  if (matchingVault) return matchingVault;
  const matchingCaselawVault = existingDirs.find((c) => looksLikeCaselawVault(c));
  if (matchingCaselawVault) return matchingCaselawVault;
  if (existingDirs.length) return existingDirs[0];
  return path.resolve(__dirname, '..');
}

function hasLocalDevAppDir(dirPath = LOCAL_DEV_APP_DIR) {
  const abs = path.resolve(dirPath);
  try {
    return (
      fs.existsSync(path.join(abs, 'package.json')) &&
      fs.existsSync(path.join(abs, 'node_modules')) &&
      fs.statSync(path.join(abs, 'node_modules')).isDirectory()
    );
  } catch {
    return false;
  }
}

function launchLocalDevApp(dirPath = LOCAL_DEV_APP_DIR) {
  const abs = path.resolve(dirPath);
  const cmd = `cd ${JSON.stringify(abs)} && nohup npm run start >/tmp/acquittify-dev.log 2>&1 &`;
  const child = spawn('bash', ['-lc', cmd], {
    detached: true,
    stdio: 'ignore'
  });
  child.unref();
}

function ensureInsideVault(vaultRoot, targetPath) {
  const absRoot = path.resolve(vaultRoot);
  const absTarget = path.resolve(targetPath);
  if (absTarget === absRoot || absTarget.startsWith(absRoot + path.sep)) {
    return absTarget;
  }
  throw new Error('Path outside vault boundary');
}

function toRel(vaultRoot, absPath) {
  return path.relative(vaultRoot, absPath).replaceAll('\\', '/');
}

function normalizeVaultLeafName(name, label = 'Name') {
  const cleaned = String(name || '').trim();
  if (!cleaned) throw new Error(`${label} is required.`);
  if (cleaned === '.' || cleaned === '..') throw new Error(`${label} cannot be '.' or '..'.`);
  if (cleaned.includes('/') || cleaned.includes('\\')) throw new Error(`${label} cannot include path separators.`);
  return cleaned;
}

function resolveVaultParentDirectory(vaultRoot, parentRelPath = '') {
  const rel = String(parentRelPath || '').trim().replaceAll('\\', '/').replace(/^\/+/, '');
  const abs = ensureInsideVault(vaultRoot, path.join(vaultRoot, rel));
  let stat = null;
  try {
    stat = fs.statSync(abs);
  } catch {
    throw new Error('Parent folder does not exist.');
  }
  if (!stat.isDirectory()) throw new Error('Parent path must be a folder.');
  return { abs, rel: toRel(vaultRoot, abs) };
}

function resolveVaultEntity(vaultRoot, relPath, label = 'Path') {
  const rel = String(relPath || '').trim().replaceAll('\\', '/').replace(/^\/+/, '');
  if (!rel) throw new Error(`${label} is required.`);
  const abs = ensureInsideVault(vaultRoot, path.join(vaultRoot, rel));
  let stat = null;
  try {
    stat = fs.statSync(abs);
  } catch {
    throw new Error(`${label} does not exist.`);
  }
  return {
    abs,
    rel: toRel(vaultRoot, abs),
    stat
  };
}

function listDirSafe(vaultRoot, relPath = '') {
  if (!vaultRoot) return [];
  let absRoot = '';
  try {
    absRoot = path.resolve(vaultRoot);
  } catch {
    return [];
  }
  try {
    if (!fs.existsSync(absRoot)) return [];
  } catch {
    return [];
  }

  let abs = '';
  try {
    abs = ensureInsideVault(absRoot, path.join(absRoot, relPath));
  } catch {
    return [];
  }

  let entries = [];
  try {
    entries = fs.readdirSync(abs, { withFileTypes: true });
  } catch (err) {
    logStartup(`listDirSafe: failed ${err?.message || err}`);
    return [];
  }
  return entries
    .filter((e) => !e.name.startsWith('.'))
    .map((e) => {
      const full = path.join(abs, e.name);
      const rel = toRel(absRoot, full);
      return {
        name: e.name,
        path: rel,
        type: e.isDirectory() ? 'directory' : 'file'
      };
    })
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
}

function getExtensionLower(filePath = '') {
  return path.extname(String(filePath || '')).toLowerCase();
}

function classifyExtension(ext = '') {
  if (PDF_EXTENSIONS.has(ext)) return 'pdf';
  if (WORD_EXTENSIONS.has(ext)) return 'word';
  if (SPREADSHEET_EXTENSIONS.has(ext)) return 'spreadsheet';
  if (EMAIL_EXTENSIONS.has(ext)) return 'email';
  if (IMAGE_EXTENSIONS.has(ext)) return 'image';
  if (AUDIO_EXTENSIONS.has(ext)) return 'audio';
  if (PRESENTATION_EXTENSIONS.has(ext)) return 'presentation';
  if (TEXT_EXTENSIONS.has(ext)) return 'text';
  return 'binary';
}

function normalizeText(value = '') {
  return String(value || '')
    .replace(/\u0000/g, '')
    .replace(/\r\n?/g, '\n')
    .trim();
}

function truncateText(value, warnings, label = 'Extracted text') {
  const normalized = normalizeText(value);
  if (normalized.length <= MAX_EXTRACTED_TEXT_CHARS) return normalized;
  warnings.push(`${label} truncated to ${MAX_EXTRACTED_TEXT_CHARS.toLocaleString()} characters.`);
  return normalized.slice(0, MAX_EXTRACTED_TEXT_CHARS);
}

function sanitizeFileStem(stem = '') {
  const cleaned = String(stem || '')
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\.+$/g, '');
  return cleaned || 'Document';
}

function stripHtml(value = '') {
  return String(value || '')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeInlineMarkdown(value = '') {
  return String(value || '').replace(/[\r\n]+/g, ' ').replace(/\|/g, '\\|').trim();
}

function extractTextWithTextutil(absPath) {
  const result = spawnSync('textutil', ['-convert', 'txt', '-stdout', absPath], {
    encoding: 'utf-8',
    maxBuffer: 32 * 1024 * 1024
  });
  if (result.error) {
    throw new Error(`textutil unavailable: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const stderr = normalizeText(result.stderr || '');
    throw new Error(stderr || `textutil exited with status ${result.status}`);
  }
  const text = normalizeText(result.stdout || '');
  if (!text) {
    throw new Error('textutil returned empty output.');
  }
  return text;
}

async function extractPdfText(absPath) {
  const fileBuffer = fs.readFileSync(absPath);
  const parserWarnings = [];

  try {
    const pdfParseModule = loadPdfParseModule();

    if (typeof pdfParseModule?.PDFParse === 'function') {
      const parser = new pdfParseModule.PDFParse({ data: fileBuffer });
      try {
        const parsed = await parser.getText({ parsePageInfo: true });
        const pageCount = Array.isArray(parsed?.pages) ? parsed.pages.length : Number(parsed?.total) || 0;
        return {
          extractor: 'pdf-parse',
          category: 'pdf',
          metadata: { pageCount },
          text: normalizeText(parsed?.text || ''),
          markdown: '',
          warnings: parserWarnings
        };
      } finally {
        if (typeof parser.destroy === 'function') {
          try {
            await parser.destroy();
          } catch {
            // no-op
          }
        }
      }
    }

    if (typeof pdfParseModule === 'function') {
      const parsed = await pdfParseModule(fileBuffer);
      const pageCount = Number(parsed?.numpages) || 0;
      return {
        extractor: 'pdf-parse',
        category: 'pdf',
        metadata: { pageCount },
        text: normalizeText(parsed?.text || ''),
        markdown: '',
        warnings: parserWarnings
      };
    }

    throw new Error('Unsupported pdf-parse module interface.');
  } catch (pdfErr) {
    parserWarnings.push(`pdf-parse unavailable: ${pdfErr.message}`);
  }

  // Fallback: try pdftotext if available in PATH.
  const fallback = spawnSync('pdftotext', ['-layout', absPath, '-'], {
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024
  });
  if (!fallback.error && fallback.status === 0) {
    return {
      extractor: 'pdftotext',
      category: 'pdf',
      metadata: {},
      text: normalizeText(fallback.stdout || ''),
      markdown: '',
      warnings: parserWarnings
    };
  }

  const fallbackDetail = fallback.error
    ? fallback.error.message
    : normalizeText(fallback.stderr || '') || `exit code ${fallback.status}`;
  throw new Error(`Unable to extract PDF text (${parserWarnings.join(' ; ')} ; pdftotext: ${fallbackDetail})`);
}

async function extractWordText(absPath, ext) {
  if (ext === '.docx') {
    const result = await mammoth.extractRawText({ path: absPath });
    const warnings = Array.isArray(result.messages)
      ? result.messages.map((m) => normalizeText(m.message || m.value || '')).filter(Boolean)
      : [];
    return {
      extractor: 'mammoth',
      category: 'word',
      metadata: {},
      text: normalizeText(result.value || ''),
      markdown: '',
      warnings
    };
  }
  return {
    extractor: 'textutil',
    category: 'word',
    metadata: {},
    text: extractTextWithTextutil(absPath),
    markdown: '',
    warnings: []
  };
}

function extractSpreadsheetText(absPath) {
  const workbook = xlsx.readFile(absPath, { cellDates: true, raw: false, dense: true });
  const warnings = [];
  const sections = [];
  const MAX_ROWS_PER_SHEET = 1500;
  const MAX_COLS_PER_ROW = 40;

  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    const rows = xlsx.utils.sheet_to_json(sheet, { header: 1, defval: '', blankrows: false, raw: false });
    sections.push(`### Sheet: ${escapeInlineMarkdown(sheetName) || 'Untitled'}`);
    if (!rows.length) {
      sections.push('_No rows found._');
      continue;
    }

    const cappedRows = rows.slice(0, MAX_ROWS_PER_SHEET);
    const tsvRows = cappedRows.map((row) =>
      row
        .slice(0, MAX_COLS_PER_ROW)
        .map((cell) => escapeInlineMarkdown(cell))
        .join('\t')
    );

    sections.push('```tsv');
    sections.push(tsvRows.join('\n'));
    sections.push('```');

    if (rows.length > MAX_ROWS_PER_SHEET || cappedRows.some((row) => row.length > MAX_COLS_PER_ROW)) {
      warnings.push(
        `${sheetName}: table truncated to ${MAX_ROWS_PER_SHEET} rows and ${MAX_COLS_PER_ROW} columns for display.`
      );
    }
  }

  return {
    extractor: 'xlsx',
    category: 'spreadsheet',
    metadata: { sheetCount: workbook.SheetNames.length },
    text: '',
    markdown: sections.join('\n\n'),
    warnings
  };
}

async function extractEmailText(absPath, ext) {
  if (ext === '.eml') {
    const parsed = await simpleParser(fs.readFileSync(absPath));
    const body = normalizeText(parsed.text || stripHtml(parsed.html || ''));
    const lines = [
      `- Subject: ${escapeInlineMarkdown(parsed.subject || '(none)')}`,
      `- From: ${escapeInlineMarkdown(parsed.from?.text || '(none)')}`,
      `- To: ${escapeInlineMarkdown(parsed.to?.text || '(none)')}`,
      `- Cc: ${escapeInlineMarkdown(parsed.cc?.text || '(none)')}`,
      `- Date: ${escapeInlineMarkdown(parsed.date ? parsed.date.toISOString() : '(none)')}`,
      ''
    ];
    lines.push('### Body');
    lines.push('');
    lines.push(body || '_No body text found._');
    return {
      extractor: 'mailparser',
      category: 'email',
      metadata: { attachments: Array.isArray(parsed.attachments) ? parsed.attachments.length : 0 },
      text: '',
      markdown: lines.join('\n'),
      warnings: []
    };
  }

  const msg = new MsgReader(fs.readFileSync(absPath));
  const data = msg.getFileData();
  const recipients = Array.isArray(data?.recipients)
    ? data.recipients.map((r) => r.email || r.name || '').filter(Boolean).join(', ')
    : '';
  const body = normalizeText(data?.body || '');
  const headers = normalizeText(data?.headers || '');
  const lines = [
    `- Subject: ${escapeInlineMarkdown(data?.subject || '(none)')}`,
    `- From: ${escapeInlineMarkdown(data?.senderEmail || data?.senderName || '(none)')}`,
    `- To: ${escapeInlineMarkdown(recipients || '(none)')}`,
    `- Date: ${escapeInlineMarkdown(data?.messageDeliveryTime || data?.creationTime || '(none)')}`,
    ''
  ];
  lines.push('### Body');
  lines.push('');
  lines.push(body || '_No body text found._');
  if (headers) {
    lines.push('');
    lines.push('### Headers');
    lines.push('');
    lines.push('```text');
    lines.push(headers);
    lines.push('```');
  }
  return {
    extractor: 'msgreader',
    category: 'email',
    metadata: { attachments: Array.isArray(data?.attachments) ? data.attachments.length : 0 },
    text: '',
    markdown: lines.join('\n'),
    warnings: []
  };
}

function extractTextDocument(absPath) {
  return {
    extractor: 'utf-8',
    category: 'text',
    metadata: {},
    text: normalizeText(fs.readFileSync(absPath, 'utf-8')),
    markdown: '',
    warnings: []
  };
}

function extractPresentationText(absPath) {
  return {
    extractor: 'textutil',
    category: 'presentation',
    metadata: {},
    text: extractTextWithTextutil(absPath),
    markdown: '',
    warnings: []
  };
}

async function extractNativeFile(absPath) {
  const ext = getExtensionLower(absPath);
  const category = classifyExtension(ext);
  const warnings = [];

  try {
    if (category === 'pdf') {
      const extracted = await extractPdfText(absPath);
      extracted.text = truncateText(extracted.text, extracted.warnings);
      return extracted;
    }
    if (category === 'word') {
      const extracted = await extractWordText(absPath, ext);
      extracted.text = truncateText(extracted.text, extracted.warnings);
      return extracted;
    }
    if (category === 'spreadsheet') {
      const extracted = extractSpreadsheetText(absPath);
      extracted.markdown = truncateText(extracted.markdown, extracted.warnings, 'Spreadsheet extract');
      return extracted;
    }
    if (category === 'email') {
      const extracted = await extractEmailText(absPath, ext);
      extracted.markdown = truncateText(extracted.markdown, extracted.warnings, 'Email extract');
      return extracted;
    }
    if (category === 'presentation') {
      const extracted = extractPresentationText(absPath);
      extracted.text = truncateText(extracted.text, extracted.warnings);
      return extracted;
    }
    if (category === 'text') {
      const extracted = extractTextDocument(absPath);
      extracted.text = truncateText(extracted.text, extracted.warnings);
      return extracted;
    }
    if (category === 'image' || category === 'audio') {
      return {
        extractor: 'native-media',
        category,
        metadata: {},
        text: '',
        markdown: '',
        warnings
      };
    }

    try {
      const fallbackText = extractTextWithTextutil(absPath);
      return {
        extractor: 'textutil',
        category: 'binary',
        metadata: {},
        text: truncateText(fallbackText, warnings),
        markdown: '',
        warnings
      };
    } catch (fallbackErr) {
      warnings.push(`No text extraction available for this file type (${ext || 'unknown extension'}).`);
      warnings.push(`Fallback extraction attempt failed: ${fallbackErr.message}`);
      return {
        extractor: 'none',
        category: 'binary',
        metadata: {},
        text: '',
        markdown: '',
        warnings
      };
    }
  } catch (err) {
    warnings.push(`Extraction error: ${err.message}`);
    return {
      extractor: 'none',
      category,
      metadata: {},
      text: '',
      markdown: '',
      warnings
    };
  }
}

function yamlQuoted(value) {
  return JSON.stringify(String(value ?? ''));
}

function deriveExtractedFileNameForNative(nativeFileName = '') {
  const ext = path.extname(nativeFileName);
  const stem = path.basename(nativeFileName, ext);
  const match = stem.match(/^(.*)\s+native(\s+\(\d+\))?$/i);
  if (match) {
    const base = sanitizeFileStem(match[1]);
    const suffix = match[2] || '';
    return `${base} extracted${suffix}.md`;
  }
  return `${sanitizeFileStem(stem)} extracted.md`;
}

function buildExtractedNoteMarkdown({
  originalFilename,
  importedAt,
  sourceAbsolutePath,
  nativeRelPath,
  extractedRelPath,
  extraction
}) {
  const nativeFileName = path.basename(nativeRelPath);
  const extractedTitle = path.basename(extractedRelPath, path.extname(extractedRelPath));
  const frontmatter = [
    '---',
    'acquittify_import: true',
    `original_filename: ${yamlQuoted(originalFilename || nativeFileName)}`,
    `imported_at: ${yamlQuoted(importedAt || new Date().toISOString())}`,
    `source_category: ${yamlQuoted(extraction.category)}`,
    `extractor: ${yamlQuoted(extraction.extractor)}`,
    `native_file: ${yamlQuoted(nativeRelPath)}`,
    `linked_native: ${yamlQuoted(`[[${nativeFileName}]]`)}`,
    `source_path: ${yamlQuoted(sourceAbsolutePath || '')}`,
    '---',
    ''
  ];

  const lines = [...frontmatter];
  lines.push(`# ${extractedTitle}`);
  lines.push('');
  lines.push(`Native file: [[${nativeFileName}]]`);
  lines.push('');
  lines.push(`Category: ${extraction.category}`);
  lines.push(`Extractor: ${extraction.extractor}`);
  lines.push('');

  if (extraction.category === 'audio') {
    lines.push('## Audio Player');
    lines.push('');
    lines.push(`![[${nativeFileName}]]`);
    lines.push('');
  } else if (extraction.category === 'image' || extraction.category === 'pdf') {
    lines.push('## Native Preview');
    lines.push('');
    lines.push(`![[${nativeFileName}]]`);
    lines.push('');
  }

  if (Array.isArray(extraction.warnings) && extraction.warnings.length) {
    lines.push('## Extraction Notes');
    lines.push('');
    for (const warning of extraction.warnings) {
      if (!warning) continue;
      lines.push(`- ${warning}`);
    }
    lines.push('');
  }

  lines.push('## Extracted Text');
  lines.push('');
  if (extraction.markdown) {
    lines.push(extraction.markdown);
  } else if (extraction.text) {
    lines.push(extraction.text);
  } else {
    lines.push('_No extractable text detected for this file type._');
  }
  lines.push('');
  return lines.join('\n');
}

function resolvePairedImportPaths(targetDirAbs, safeStem, ext) {
  for (let attempt = 0; attempt < 5000; attempt++) {
    const suffix = attempt === 0 ? '' : ` (${attempt + 1})`;
    const nativeFileName = `${safeStem} native${suffix}${ext}`;
    const extractedFileName = `${safeStem} extracted${suffix}.md`;
    const nativeAbs = path.join(targetDirAbs, nativeFileName);
    const extractedAbs = path.join(targetDirAbs, extractedFileName);
    if (!fs.existsSync(nativeAbs) && !fs.existsSync(extractedAbs)) {
      return { nativeAbs, extractedAbs, nativeFileName, extractedFileName };
    }
  }
  throw new Error('Unable to allocate unique import filenames.');
}

async function ensureExtractedNoteForVaultFile(vaultRoot, relPath, options = {}) {
  const nativeAbs = ensureInsideVault(vaultRoot, path.join(vaultRoot, relPath));
  const stat = fs.statSync(nativeAbs);
  if (!stat.isFile()) {
    throw new Error('Expected a file path to generate extracted note.');
  }

  const ext = getExtensionLower(nativeAbs);
  const nativeRelPath = toRel(vaultRoot, nativeAbs);
  const category = classifyExtension(ext);

  if (category === 'text' && (ext === '.md' || ext === '.markdown' || ext === '.yaml' || ext === '.yml')) {
    return {
      path: nativeRelPath,
      category,
      extractor: 'none',
      warnings: [],
      created: false,
      skipped: true
    };
  }

  const hintedRel = options.extractedRelPathHint ? String(options.extractedRelPathHint) : '';
  const hintedAbs = hintedRel
    ? ensureInsideVault(vaultRoot, path.join(vaultRoot, hintedRel))
    : path.join(path.dirname(nativeAbs), deriveExtractedFileNameForNative(path.basename(nativeAbs)));
  const extractedAbs = ensureInsideVault(vaultRoot, hintedAbs);
  const extractedRelPath = toRel(vaultRoot, extractedAbs);
  const existed = fs.existsSync(extractedAbs);

  if (existed && !options.force) {
    return {
      path: extractedRelPath,
      category,
      extractor: 'existing',
      warnings: [],
      created: false,
      skipped: true
    };
  }

  const extraction = await extractNativeFile(nativeAbs);
  const markdown = buildExtractedNoteMarkdown({
    originalFilename: options.originalFilename || path.basename(nativeAbs),
    importedAt: options.importedAt || new Date().toISOString(),
    sourceAbsolutePath: options.sourcePath || '',
    nativeRelPath,
    extractedRelPath,
    extraction
  });

  fs.mkdirSync(path.dirname(extractedAbs), { recursive: true });
  fs.writeFileSync(extractedAbs, markdown, 'utf-8');

  return {
    path: extractedRelPath,
    category: extraction.category,
    extractor: extraction.extractor,
    warnings: extraction.warnings,
    created: !existed,
    skipped: false
  };
}

async function importFilesIntoVault(vaultRoot, sourcePaths = [], options = {}) {
  const requestedTarget = String(options.targetDir || VAULT_IMPORT_RELATIVE_DIR)
    .replace(/^[/\\]+/, '')
    .replace(/\\/g, '/');
  const targetDirAbs = ensureInsideVault(vaultRoot, path.join(vaultRoot, requestedTarget));
  fs.mkdirSync(targetDirAbs, { recursive: true });

  const results = [];
  for (const sourcePath of sourcePaths) {
    const sourceAbs = path.resolve(String(sourcePath || ''));
    const filename = path.basename(sourceAbs);
    try {
      const stat = fs.statSync(sourceAbs);
      if (!stat.isFile()) {
        throw new Error('Path is not a file.');
      }

      const ext = getExtensionLower(filename);
      const stem = sanitizeFileStem(path.basename(filename, path.extname(filename)));
      const pair = resolvePairedImportPaths(targetDirAbs, stem, ext);

      fs.copyFileSync(sourceAbs, pair.nativeAbs);
      const nativeRelPath = toRel(vaultRoot, pair.nativeAbs);
      const extracted = await ensureExtractedNoteForVaultFile(vaultRoot, nativeRelPath, {
        force: true,
        extractedRelPathHint: toRel(vaultRoot, pair.extractedAbs),
        originalFilename: filename,
        sourcePath: sourceAbs,
        importedAt: new Date().toISOString()
      });

      results.push({
        status: 'imported',
        filename,
        nativePath: nativeRelPath,
        extractedPath: extracted.path,
        category: extracted.category,
        warnings: extracted.warnings
      });
    } catch (err) {
      results.push({
        status: 'failed',
        filename: filename || String(sourcePath || ''),
        message: err.message
      });
    }
  }

  return {
    canceled: false,
    targetDir: toRel(vaultRoot, targetDirAbs),
    results
  };
}

function walkMarkdownFiles(root, limit = 3000) {
  const allowedExt = new Set(['.md', '.markdown', '.yml', '.yaml']);
  const out = [];
  const stack = [root];
  const seenDirs = new Set();

  while (stack.length && out.length < limit) {
    const cur = stack.pop();
    if (!cur) continue;

    let realDir = cur;
    try {
      realDir = fs.realpathSync.native(cur);
    } catch {
      // ignore and continue with unresolved path
    }

    if (seenDirs.has(realDir)) continue;
    seenDirs.add(realDir);

    let entries = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const e of entries) {
      if (e.name === '.' || e.name === '..') continue;
      if (e.isSymbolicLink()) continue;
      const full = path.join(cur, e.name);
      if (e.isDirectory()) {
        stack.push(full);
      } else if (e.isFile()) {
        const ext = path.extname(e.name).toLowerCase();
        if (allowedExt.has(ext)) {
          out.push(full);
          if (out.length >= limit) break;
        }
      }
    }
  }
  return out;
}

function slugifyNodeToken(value = '', fallback = 'node') {
  const slug = String(value || '')
    .normalize('NFKD')
    .replace(/[^\w\s-]/g, ' ')
    .replace(/[_\s-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
  return slug || fallback;
}

function readJsonFileSafe(absPath, fallbackValue) {
  try {
    const raw = fs.readFileSync(absPath, 'utf-8');
    return JSON.parse(raw);
  } catch {
    return fallbackValue;
  }
}

function writeJsonFile(absPath, value) {
  fs.mkdirSync(path.dirname(absPath), { recursive: true });
  fs.writeFileSync(absPath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function deriveBootstrapSchemaSidecarPath(absJsonPath) {
  if (/\.json$/i.test(absJsonPath)) return absJsonPath.replace(/\.json$/i, '.md');
  return `${absJsonPath}.md`;
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

function buildBootstrapSchemaSidecarMarkdown(caseRoot, absJsonPath, value, schemaInfo = {}) {
  const sidecarMarker = `<!-- ACQUITTIFY_BOOTSTRAP_SCHEMA_SIDECAR_VERSION:${BOOTSTRAP_SCHEMA_VERSION} -->`;
  const relJsonPath = toRel(caseRoot, absJsonPath);
  const nodeType = String(value?.node_type || '').trim();
  const nodeId = String(value?.node_id || '').trim();
  const nodeBootstrapVersion = String(value?.bootstrap_version || '').trim() || BOOTSTRAP_SCHEMA_VERSION;
  const schemaSourcePath = String(schemaInfo?.path || '').trim();
  const schemaText = String(schemaInfo?.text || '').trim();
  const establishedSchemaMarkdown =
    schemaText ||
    [
      '# Bootstrap Schema',
      '',
      `Schema file not found. Expected filename: ${BOOTSTRAP_SCHEMA_FILENAME}`,
      '',
      `Required bootstrap schema version: ${BOOTSTRAP_SCHEMA_VERSION}`
    ].join('\n');

  return [
    '# Bootstrap Schema Sidecar',
    sidecarMarker,
    '',
    `- JSON file: \`${relJsonPath}\``,
    `- Bootstrap schema version: \`${BOOTSTRAP_SCHEMA_VERSION}\``,
    `- Node bootstrap version: \`${nodeBootstrapVersion}\``,
    `- Node type: \`${nodeType || 'n/a'}\``,
    `- Node id: \`${nodeId || 'n/a'}\``,
    `- Generated at: \`${new Date().toISOString()}\``,
    `- Schema source: \`${schemaSourcePath || BOOTSTRAP_SCHEMA_FILENAME}\``,
    '',
    '## File Shape',
    ...summarizeBootstrapJsonTopLevel(value),
    '',
    '## Established Bootstrap Schema',
    '',
    establishedSchemaMarkdown,
    ''
  ].join('\n');
}

function writeBootstrapJsonWithSchemaMarkdown(caseRoot, absJsonPath, value, schemaInfo = {}) {
  writeJsonFile(absJsonPath, value);
  const sidecarPath = deriveBootstrapSchemaSidecarPath(absJsonPath);
  const sidecarMarkdown = buildBootstrapSchemaSidecarMarkdown(caseRoot, absJsonPath, value, schemaInfo);
  fs.mkdirSync(path.dirname(sidecarPath), { recursive: true });
  fs.writeFileSync(sidecarPath, `${sidecarMarkdown.trimEnd()}\n`, 'utf-8');
}

function loadBootstrapSchemaPromptText() {
  const candidates = [
    path.resolve(__dirname, '..', BOOTSTRAP_SCHEMA_FILENAME),
    path.resolve(__dirname, BOOTSTRAP_SCHEMA_FILENAME)
  ];
  for (const candidate of candidates) {
    try {
      if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) continue;
      const content = fs.readFileSync(candidate, 'utf-8');
      if (String(content || '').trim()) {
        return { path: candidate, text: content.trim() };
      }
    } catch {
      // ignore and try next candidate
    }
  }
  return { path: '', text: '' };
}

function buildPeregrineBootstrapPromptMarkdown() {
  const marker = `<!-- ACQUITTIFY_BOOTSTRAP_PROMPT_VERSION:${PEREGRINE_BOOTSTRAP_PROMPT_VERSION} -->`;
  const schema = loadBootstrapSchemaPromptText();
  const schemaLabel = schema.path ? path.basename(schema.path) : BOOTSTRAP_SCHEMA_FILENAME;
  const lines = [
    '# Peregrine Bootstrap Prompt',
    marker,
    '',
    '## Quick Start Commands (Deep Only)',
    '- `/bootstrap`',
    '- `/bootstrap --case "."`',
    '- `/bootstrap refresh`',
    '- `/bootstrap refresh --case "."`',
    '',
    '## Full Ontology Development Prompt (Paste Into OpenClaw/Peregrine)',
    '```text',
    'You are Peregrine inside Acquittify. Execute a FULL case bootstrap for ontology development.',
    '',
    'Critical routing:',
    '- This request is NOT OpenClaw workspace initialization.',
    '- Do NOT respond with AGENTS.md / BOOTSTRAP.md / SOUL.md startup ritual summaries.',
    '- Treat `/bootstrap` as Acquittify deep case bootstrap.',
    '',
    'Execution target:',
    '- Mode: deep',
    '- Case root: active vault root (`.` unless user supplied --case path).',
    '- Schema contract: Acquittify Ontology Schema v1.2.',
    '- Output directory contract: /Casefile.',
    '',
    'Required ontology outputs (idempotent + merge-safe):',
    '1) Create/refresh /Casefile structure and metadata files.',
    '2) Parse indictment and create one indictment node plus one count node per count.',
    '3) For each count node, extract statutes, elements, alleged conduct, mens rea, date range, locations, linked witnesses, linked exhibits, linked transcripts, rule_29_vulnerability_score.',
    '4) Build witness nodes with:',
    '   - aliases',
    '   - related docs/appears_in',
    '   - testimony or statement excerpts',
    '   - witness appearance chart (document path/link, document type, role in document, involvement summary, excerpt, linked counts)',
    '   - top-level overall witness summary',
    '   - impeachment flags/material',
    '   - credibility risk score',
    '   - witness name extraction contract (required):',
    '     a) From transcripts: only extract names from explicit witness-introduction text (for example: "THE WITNESS: <Name>", "A. My name is <Name>", "DIRECT EXAMINATION OF <Name>").',
    '     b) Never create witness nodes from generic transcript prose, Q/A fragments, or sentence snippets.',
    '     c) If transcripts are unavailable or lack explicit witness-introduction text, use interviewee names from law-enforcement interview/statement documents and names listed in government/defense witness lists.',
    '     d) After witness identities are established, scan every extracted document for those witness names and attach each matching document to that witness with role analysis.',
    '     e) Witness nodes must summarize actual testimony (from transcripts) and potential testimony (from statements/affidavits/witness lists) and link each summary point back to source documents.',
    '5) Build attorney nodes from explicit counsel identifiers (for example: "For the United States:", "For the Defendant:", "AUSA", "ESQ"), and exclude attorney names from witness-node creation.',
    '6) Build transcript nodes and exhibit nodes with links to counts and witnesses.',
    '7) Build canonical entity registry entries (persons/entities/statutes/attorneys) and connect them.',
    '8) Build /06_Link_Graph/relationships.json edges using allowed relationship types.',
    '9) Score discovery relevance for exhibits/documents and initialize discovery review queue.',
    '',
    'Edge requirements:',
    '- Every count must connect to at least one witness, statute, or exhibit where evidence exists.',
    '- Every witness should connect to transcripts/exhibits where they appear.',
    '- Every witness node should include a non-empty appearance chart when source references exist.',
    '- No duplicate nodes for same canonical entity.',
    '',
    'Allowed relationship types:',
    '- charged_in',
    '- testifies_about',
    '- authored',
    '- received',
    '- mentioned',
    '- relates_to_count',
    '- relates_to_statute',
    '- co_conspirator_with',
    '- contradicted_by',
    '- impeached_by',
    '- supports_element',
    '- fails_to_support_element',
    '- references',
    '- part_of_scheme',
    '- represented_by',
    '',
    'Completion response format:',
    '- Bootstrap completed.',
    '- Case root:',
    '- Mode:',
    '- Counts:',
    '- Witnesses:',
    '- Attorneys:',
    '- Documents:',
    '- Discovery queue items:',
    '- Workspace note:',
    '- Bootstrap prompt (root):',
    '- Bootstrap prompt:',
    '- Bootstrap refresh prompt (root):',
    '- Bootstrap refresh prompt:',
    '- Schema root:',
    '- Ontology index:',
    '- Relationships:',
    '- Warnings: <if any>',
    '',
    'If OpenClaw still drifts to startup-routine output, immediately comply by running:',
    '/bootstrap --case "."',
    '```',
    '',
    `## Schema Contract Source (${schemaLabel})`
  ];
  if (schema.text) {
    lines.push('```md');
    lines.push(schema.text);
    lines.push('```');
  } else {
    lines.push(`Schema file not found. Expected filename: ${BOOTSTRAP_SCHEMA_FILENAME}`);
  }
  lines.push('');
  return lines.join('\n');
}

function buildPeregrineBootstrapRefreshPromptMarkdown() {
  const marker = `<!-- ACQUITTIFY_BOOTSTRAP_REFRESH_PROMPT_VERSION:${PEREGRINE_BOOTSTRAP_PROMPT_VERSION} -->`;
  const lines = [
    '# Peregrine Bootstrap Refresh Prompt',
    marker,
    '',
    '## Refresh Commands',
    '- `/bootstrap refresh`',
    '- `/bootstrap refresh --case "."`',
    '',
    '## Additions-Only Delta Analysis Prompt (Paste Into OpenClaw/Peregrine)',
    '```text',
    'You are Peregrine inside Acquittify. Execute a BOOTSTRAP REFRESH for the active case root.',
    '',
    'Critical routing:',
    '- This request is NOT OpenClaw workspace initialization.',
    '- Do NOT respond with AGENTS.md / BOOTSTRAP.md / SOUL.md startup ritual summaries.',
    '- Treat `/bootstrap refresh` as Acquittify deep bootstrap refresh.',
    '',
    'Execution target:',
    '- Mode: deep',
    '- Operation: refresh',
    '- Case root: active vault root (`.` unless user supplied --case path).',
    '- Schema contract: Acquittify Ontology Schema v1.2.',
    '',
    'Refresh requirements:',
    '1) Load prior source index from /Casefile/00_Metadata/bootstrap_source_index.json.',
    '2) Scan the current source casefile and build a new source index snapshot.',
    '3) Compute deltas: new documents, updated documents, removed documents.',
    '4) Analyze each new/updated document for ontology impact:',
    '   - likely document type',
    '   - count references',
    '   - explicit transcript witness-identification hits',
    '   - witness-list/interviewee signals',
    '   - attorney/counsel signals',
    '5) Re-run deep ontology synthesis so all impacted witness/count/exhibit/relationship nodes are current.',
    '6) Write refresh delta report to /Casefile/00_Metadata/bootstrap_refresh_report.json.',
    '',
    'Completion response format:',
    '- Bootstrap refresh completed.',
    '- Case root:',
    '- Mode: deep',
    '- New documents:',
    '- Updated documents:',
    '- Removed documents:',
    '- Delta report:',
    '- Source index:',
    '- Workspace note:',
    '- Warnings: <if any>',
    '',
    'If OpenClaw drifts to startup-routine output, immediately comply by running:',
    '/bootstrap refresh --case "."',
    '```',
    ''
  ];
  return lines.join('\n');
}

function ensurePeregrineBootstrapPromptNotes(caseRoot = '') {
  const resolvedRoot = path.resolve(String(caseRoot || '').trim() || '.');
  const bootstrapMarker = `<!-- ACQUITTIFY_BOOTSTRAP_PROMPT_VERSION:${PEREGRINE_BOOTSTRAP_PROMPT_VERSION} -->`;
  const refreshMarker = `<!-- ACQUITTIFY_BOOTSTRAP_REFRESH_PROMPT_VERSION:${PEREGRINE_BOOTSTRAP_PROMPT_VERSION} -->`;
  const bootstrapMarkdown = buildPeregrineBootstrapPromptMarkdown();
  const refreshMarkdown = buildPeregrineBootstrapRefreshPromptMarkdown();

  const ensureTarget = (targetAbs) => {
    const { markdown, marker, contentChecks } = targetAbs;
    fs.mkdirSync(path.dirname(targetAbs.path), { recursive: true });
    if (!fs.existsSync(targetAbs.path) || !fs.statSync(targetAbs.path).isFile()) {
      fs.writeFileSync(targetAbs.path, markdown, 'utf-8');
      return;
    }
    const current = fs.readFileSync(targetAbs.path, 'utf-8');
    const text = String(current || '');
    const hasVersion = text.includes(marker);
    const hasContent = Array.isArray(contentChecks) ? contentChecks.every((check) => text.includes(check)) : true;
    if (!hasVersion || !hasContent) {
      fs.writeFileSync(targetAbs.path, markdown, 'utf-8');
    }
  };
  try {
    ensureTarget({
      path: path.join(resolvedRoot, PEREGRINE_BOOTSTRAP_PROMPT_ROOT_REL),
      markdown: bootstrapMarkdown,
      marker: bootstrapMarker,
      contentChecks: ['## Schema Contract Source (', '## Quick Start Commands (Deep Only)']
    });
    ensureTarget({
      path: path.join(resolvedRoot, PEREGRINE_BOOTSTRAP_PROMPT_NOTE_REL),
      markdown: bootstrapMarkdown,
      marker: bootstrapMarker,
      contentChecks: ['## Schema Contract Source (', '## Quick Start Commands (Deep Only)']
    });
    ensureTarget({
      path: path.join(resolvedRoot, PEREGRINE_BOOTSTRAP_REFRESH_PROMPT_ROOT_REL),
      markdown: refreshMarkdown,
      marker: refreshMarker,
      contentChecks: ['## Additions-Only Delta Analysis Prompt']
    });
    ensureTarget({
      path: path.join(resolvedRoot, PEREGRINE_BOOTSTRAP_REFRESH_PROMPT_NOTE_REL),
      markdown: refreshMarkdown,
      marker: refreshMarker,
      contentChecks: ['## Additions-Only Delta Analysis Prompt']
    });
  } catch (err) {
    logStartup(`[bootstrap] ensure prompt note failed root=${resolvedRoot} err=${err?.message || err}`);
  }
  return {
    bootstrapPromptNoteRel: PEREGRINE_BOOTSTRAP_PROMPT_NOTE_REL,
    bootstrapRefreshPromptNoteRel: PEREGRINE_BOOTSTRAP_REFRESH_PROMPT_NOTE_REL
  };
}

function walkCasefileDocuments(root, limit = 1200) {
  const out = [];
  const stack = [root];
  const seenDirs = new Set();
  while (stack.length && out.length < limit) {
    const cur = stack.pop();
    if (!cur) continue;
    let realDir = cur;
    try {
      realDir = fs.realpathSync.native(cur);
    } catch {
      // continue with unresolved path
    }
    if (seenDirs.has(realDir)) continue;
    seenDirs.add(realDir);

    let entries = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (!entry || entry.name === '.' || entry.name === '..') continue;
      if (entry.name.startsWith('.')) continue;
      const absPath = path.join(cur, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) {
        if (BOOTSTRAP_SKIP_DIRS.has(entry.name)) continue;
        stack.push(absPath);
        continue;
      }
      if (!entry.isFile()) continue;
      out.push(absPath);
      if (out.length >= limit) break;
    }
  }
  return out;
}

function resolveBootstrapCaseRoot(vaultRoot, payload = {}) {
  const requested = String(
    payload?.casePath || payload?.caseRoot || payload?.path || payload?.root || ''
  ).trim();
  const resolvedVaultRoot = path.resolve(String(vaultRoot || '').trim() || '.');
  const candidates = [];
  if (requested) {
    if (path.isAbsolute(requested)) {
      candidates.push(path.resolve(requested));
    } else {
      candidates.push(path.resolve(resolvedVaultRoot, requested));
      candidates.push(path.resolve(resolvedVaultRoot, 'Casefiles', requested));
    }
  }
  candidates.push(resolvedVaultRoot);

  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) {
        return candidate;
      }
    } catch {
      // continue
    }
  }
  return resolvedVaultRoot;
}

function normalizeStatuteCitation(rawValue = '') {
  let normalized = String(rawValue || '')
    .replace(/\s+/g, ' ')
    .replace(/\bU\s*\.\s*S\s*\.\s*C\s*\.?/gi, 'U.S.C.')
    .replace(/\bSection\b/gi, '§')
    .replace(/\bSec\.?\b/gi, '§')
    .replace(/§\s*§+/g, '§§')
    .replace(/\s*-\s*/g, '-')
    .replace(/\s+/g, ' ')
    .trim();

  normalized = normalized.replace(/§\s*([0-9A-Za-z().-]+)/g, (_match, sectionRaw) => {
    const fixedSection = String(sectionRaw || '')
      .replace(/[lI](?=[0-9)(.-]|$)/g, '1')
      .replace(/(?<=\d)[oO](?=\d)/g, '0');
    return `§ ${fixedSection}`;
  });
  normalized = normalized.replace(/[.,;:]+$/g, '');
  return normalized;
}

function extractStatutesFromText(text = '') {
  const statutes = new Map();
  const regex = /\b\d+\s*U\.?\s*S\.?\s*C\.?\s*(?:(?:§{1,2}|Section|Sec\.?)\s*)?\d+[A-Za-z0-9().-]*/gi;
  let match = regex.exec(String(text || ''));
  while (match) {
    const normalized = normalizeStatuteCitation(match[0]);
    if (!normalized) {
      match = regex.exec(String(text || ''));
      continue;
    }
    const key = normalized.toLowerCase().replace(/\s+/g, ' ');
    if (!statutes.has(key)) statutes.set(key, normalized);
    match = regex.exec(String(text || ''));
  }
  return Array.from(statutes.values());
}

function parseCountTokenToNumber(token = '') {
  const normalized = String(token || '').trim().toLowerCase();
  if (!normalized) return null;
  if (normalized === 'l' || normalized === 'i') return 1;
  if (/^\d+$/.test(normalized)) {
    const parsed = Number(normalized);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }

  const wordToNumber = {
    one: 1,
    two: 2,
    three: 3,
    four: 4,
    five: 5,
    six: 6,
    seven: 7,
    eight: 8,
    nine: 9,
    ten: 10,
    eleven: 11,
    twelve: 12
  };
  if (wordToNumber[normalized]) return wordToNumber[normalized];

  const romanValues = { i: 1, v: 5, x: 10, l: 50, c: 100 };
  if (!/^[ivxlc]+$/.test(normalized)) return null;
  let total = 0;
  let previous = 0;
  for (let i = normalized.length - 1; i >= 0; i -= 1) {
    const current = romanValues[normalized[i]] || 0;
    if (!current) return null;
    if (current < previous) total -= current;
    else {
      total += current;
      previous = current;
    }
  }
  return total > 0 ? total : null;
}

function extractCountSegmentsFromText(text = '') {
  const source = String(text || '');
  if (!source.trim()) return [];

  const markerRegex = /(^|\n)\s*(?:count|ct)\s*([0-9]+|[ivxlc]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|l)\b[^\n]*/gi;
  const markers = [];
  let match = markerRegex.exec(source);
  while (match) {
    const countNumber = parseCountTokenToNumber(match[2] || '');
    if (countNumber) {
      markers.push({
        countNumber,
        index: match.index + (match[1] ? match[1].length : 0)
      });
    }
    match = markerRegex.exec(source);
  }

  if (!markers.length) return [];

  markers.sort((a, b) => a.index - b.index);
  const deduped = [];
  for (const marker of markers) {
    const last = deduped[deduped.length - 1];
    if (last && last.index === marker.index) continue;
    deduped.push(marker);
  }

  const out = [];
  for (let i = 0; i < deduped.length; i += 1) {
    const start = deduped[i].index;
    const end = deduped[i + 1] ? deduped[i + 1].index : source.length;
    const fullText = source.slice(start, end).trim();
    if (!fullText) continue;
    out.push({
      countNumber: deduped[i].countNumber,
      fullText
    });
  }
  return out;
}

function extractCountReferencesFromText(text = '', limit = 24) {
  const references = [];
  const seen = new Set();
  const regex = /\b(?:count|ct)\s*([0-9]+|[ivxlc]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|l)\b/gi;
  let match = regex.exec(String(text || ''));
  while (match && references.length < limit) {
    const countNumber = parseCountTokenToNumber(match[1] || '');
    if (countNumber && !seen.has(countNumber)) {
      seen.add(countNumber);
      references.push(countNumber);
    }
    match = regex.exec(String(text || ''));
  }
  return references.sort((a, b) => a - b);
}

function toNameCaseToken(token = '') {
  const source = String(token || '').trim();
  if (!source) return '';
  if (/^[A-Z]\.?$/.test(source)) return source.replace('.', '').toUpperCase();

  const lower = source.toLowerCase();
  const chunks = lower.split(/([-'`])/);
  return chunks
    .map((chunk) => {
      if (!chunk) return '';
      if (chunk === '-' || chunk === '\'' || chunk === '`') return chunk;
      return chunk.charAt(0).toUpperCase() + chunk.slice(1);
    })
    .join('');
}

function normalizePersonName(rawName = '') {
  let name = String(rawName || '')
    .replace(/[“”"]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!name) return '';

  name = name
    .replace(/^(?:mr|mrs|ms|miss|dr|judge|hon|honorable|attorney|ausa|agent|officer)\.?\s+/i, '')
    .replace(/[,:;.]+$/g, '')
    .trim();
  if (!name) return '';

  let tokens = name
    .split(/\s+/)
    .map((token) => {
      let cleaned = token.replace(/[^A-Za-z'.-]/g, '');
      if (/^[A-Za-z]{2,}\.$/.test(cleaned)) cleaned = cleaned.slice(0, -1);
      return cleaned;
    })
    .filter(Boolean)
    .slice(0, 4);
  while (tokens.length) {
    const last = String(tokens[tokens.length - 1] || '').toLowerCase();
    if (!last) break;
    const connector = last === 'and' || last === 'or' || last === 'but';
    const spelledOut = /^[a-z](?:-[a-z]){2,}$/i.test(last);
    if (!connector && !spelledOut) break;
    tokens = tokens.slice(0, -1);
  }
  if (!tokens.length) return '';

  return tokens.map((token) => toNameCaseToken(token)).join(' ').trim();
}

const BOOTSTRAP_PERSON_STOP_PHRASES = [
  'united states',
  'the court',
  'district court',
  'case no',
  'page id',
  'jury trial',
  'direct examination',
  'cross examination',
  'redirect examination',
  'recross examination',
  'government exhibit',
  'peregrine startup workspace',
  'next steps',
  'certificate of service',
  'respectfully submitted',
  'supreme court'
];

const BOOTSTRAP_PERSON_STOP_TOKENS = new Set([
  'the',
  'and',
  'or',
  'of',
  'to',
  'for',
  'from',
  'in',
  'on',
  'at',
  'by',
  'with',
  'through',
  'q',
  'a',
  'okay',
  'yes',
  'no',
  'good',
  'morning',
  'afternoon',
  'thank',
  'you',
  'sir',
  'maam',
  'hello',
  'hi',
  'your',
  'before',
  'office',
  'respectfully',
  'requests',
  'presumed',
  'innocent',
  'guilty',
  'legal',
  'standard',
  'impeachment',
  'again',
  'against',
  'begun',
  'concluded',
  'anybody',
  'there',
  'because',
  'going',
  'will',
  'have',
  'scribe',
  'must',
  'identify',
  'date',
  'capitol',
  'view',
  'madam',
  'clerk',
  'diversion',
  'investigator',
  'monitoring',
  'program',
  'stand',
  'waiting',
  'area',
  'chapman',
  'law',
  'group',
  'plf',
  'def',
  'tune',
  'entrekin',
  'an',
  'has',
  'court',
  'judge',
  'jury',
  'page',
  'id',
  'case',
  'count',
  'district',
  'division',
  'transcript',
  'trial',
  'examination',
  'government',
  'exhibit',
  'superseding',
  'indictment',
  'indictiment',
  'entry',
  'motion',
  'order',
  'docket',
  'states',
  'united',
  'kentucky',
  'tennessee',
  'county',
  'london',
  'gateway',
  'medical',
  'associates',
  'street',
  'lane',
  'suite',
  'avenue',
  'bank',
  'account',
  'business',
  'property',
  'license',
  'practice',
  'judgment',
  'money',
  'schedule',
  'relevant',
  'entities',
  'individuals',
  'beginning',
  'drug',
  'doc',
  'rew',
  'hai',
  'honor',
  'background',
  'conclusion',
  'argument',
  'forfeiture',
  'allegation',
  'section',
  'paragraph',
  'declaration',
  'response',
  'brief'
]);

function isLikelyPersonName(name = '') {
  const normalized = normalizePersonName(name);
  if (!normalized) return false;
  if (normalized.length < 5) return false;

  const lowered = normalized.toLowerCase();
  if (BOOTSTRAP_PERSON_STOP_PHRASES.some((phrase) => lowered.includes(phrase))) return false;

  const tokens = normalized.split(' ').filter(Boolean);
  const primaryCleanTokens = tokens
    .map((token) => token.toLowerCase().replace(/[^a-z]/g, ''))
    .filter(Boolean);
  const cleanedTokens = tokens
    .flatMap((token) => token.toLowerCase().split(/[-'.`]/g))
    .map((token) => token.replace(/[^a-z]/g, ''))
    .filter(Boolean);
  if (tokens.length < 2 || tokens.length > 3) return false;
  if (tokens.filter((token) => token.length > 1).length < 2) return false;
  if (tokens.some((token) => /^\d/.test(token))) return false;
  if (tokens.some((token) => /^[A-Za-z](?:-[A-Za-z]){2,}$/.test(token))) return false;
  if (primaryCleanTokens.length < 2) return false;
  const first = primaryCleanTokens[0];
  const last = primaryCleanTokens[primaryCleanTokens.length - 1];
  if (first.length < 3 || last.length < 3) return false;
  if (BOOTSTRAP_PERSON_STOP_TOKENS.has(first) || BOOTSTRAP_PERSON_STOP_TOKENS.has(last)) return false;
  if (!cleanedTokens.length) return false;
  if (cleanedTokens.some((token) => BOOTSTRAP_PERSON_STOP_TOKENS.has(token))) return false;
  if (!tokens.every((token) => /^[A-Za-z][A-Za-z'.-]*$/.test(token))) return false;
  if (cleanedTokens.length >= 2 && cleanedTokens[cleanedTokens.length - 1].length < 3) return false;

  return true;
}

function extractWitnessNamesFromText(text = '', limit = 120) {
  const source = String(text || '');
  if (!source.trim()) return [];

  const results = [];
  const seen = new Set();
  const push = (candidate) => {
    const normalized = normalizePersonName(candidate);
    if (!isLikelyPersonName(normalized)) return;
    const key = normalized.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    results.push(normalized);
  };

  const lines = source.split(/\r?\n/);
  for (const rawLine of lines) {
    if (results.length >= limit) break;
    let line = String(rawLine || '')
      .replace(/\s+/g, ' ')
      .replace(/^[\-\*\u2022\d.()]+/, '')
      .replace(/^(?:Q|A|BY)\.\s*/i, '')
      .trim();
    if (!line || line.length < 5 || line.length > 90) continue;

    let match = line.match(/^([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})$/);
    if (match) {
      push(match[1]);
      continue;
    }

    match = line.match(/(?:witness|testimony\s+of|defendant)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/i);
    if (match) {
      push(match[1]);
      continue;
    }

    match = line.match(/^([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})[,)]/);
    if (match) {
      push(match[1]);
    }
  }

  return results;
}

function collectDistinctPersonNames(sourceText = '', patterns = [], limit = 120) {
  const source = String(sourceText || '');
  if (!source.trim()) return [];

  const results = [];
  const seen = new Set();
  const push = (candidate) => {
    if (results.length >= limit) return;
    const normalized = normalizePersonName(candidate);
    if (!isLikelyPersonName(normalized)) return;
    const key = normalized.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    results.push(normalized);
  };

  for (const pattern of patterns) {
    if (!(pattern instanceof RegExp)) continue;
    const flags = pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`;
    const regex = new RegExp(pattern.source, flags);
    let match = regex.exec(source);
    while (match && results.length < limit) {
      push(match[1] || match[0] || '');
      match = regex.exec(source);
    }
    if (results.length >= limit) break;
  }

  return results;
}

function extractExplicitWitnessNamesFromTranscript(text = '', limit = 120) {
  const source = String(text || '');
  if (!source.trim()) return [];

  const patterns = [
    /\b(?:THE\s+WITNESS|WITNESS)\s*:\s*(?:my name is\s+|i am\s+|it's\s+)?([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})(?=\s*[.,;:]|\s*$)/gi,
    /\bA\.\s*(?:my name is|i am)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})(?=\s*[.,;:]|\s*$)/gi,
    /\b(?:direct|cross|redirect|recross)[ -]examination\s+of\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
    /\btestimony\s+of\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
    /\bcalled\s+(?:as\s+)?(?:the\s+|its\s+)?(?:next\s+)?witness[,:]?\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi
  ];
  const base = collectDistinctPersonNames(source, patterns, limit);
  if (base.length >= limit) return base.slice(0, limit);

  const results = [...base];
  const seen = new Set(results.map((name) => name.toLowerCase()));
  const push = (candidate) => {
    const normalized = normalizePersonName(candidate);
    if (!isLikelyPersonName(normalized)) return;
    const key = normalized.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    results.push(normalized);
  };

  const lines = source.split(/\r?\n/);
  for (const rawLine of lines) {
    if (results.length >= limit) break;
    const line = String(rawLine || '').replace(/\s+/g, ' ').trim();
    if (!line || line.length > 160) continue;
    const witnessLine = line.match(/^(?:THE\s+WITNESS|WITNESS)\s*:\s*(.+)$/i);
    if (!witnessLine) continue;
    const nameMatch = witnessLine[1].match(
      /(?:my name is\s+|i am\s+|it's\s+)?([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})(?=\s*[.,;:]|\s*$)/
    );
    if (nameMatch) push(nameMatch[1]);
  }

  return results.slice(0, limit);
}

function extractWitnessNamesFromWitnessList(text = '', limit = 120) {
  const source = String(text || '');
  if (!source.trim()) return [];

  const results = [];
  const seen = new Set();
  const push = (candidate) => {
    if (results.length >= limit) return;
    const normalized = normalizePersonName(candidate);
    if (!isLikelyPersonName(normalized)) return;
    const key = normalized.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    results.push(normalized);
  };

  const lines = source.split(/\r?\n/);
  for (const rawLine of lines) {
    if (results.length >= limit) break;
    let line = String(rawLine || '')
      .replace(/\s+/g, ' ')
      .replace(/^[\-\*\u2022]+/, '')
      .replace(/^\(?\d{1,3}[.)-]?\s+/, '')
      .trim();
    if (!line || line.length < 4 || line.length > 180) continue;
    if (/^(?:witness(?:es)?|government|defen[cs]e|plaintiff|defendant)\s*$/i.test(line)) continue;
    line = line.replace(
      /^(?:witness(?:es)?|government witnesses?|defen[cs]e witnesses?|defendant witnesses?)\s*[:\-]\s*/i,
      ''
    );

    const directName = line.match(/^([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})(?:\s*[-,;:].*)?$/);
    if (directName) {
      push(directName[1]);
      continue;
    }

    const segments = line.split(/(?:,|;|\band\b)/i);
    for (const segment of segments) {
      if (results.length >= limit) break;
      const cleaned = segment.trim();
      if (!cleaned || cleaned.length > 120) continue;
      const candidate = cleaned.match(/([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/);
      if (candidate) push(candidate[1]);
    }
  }

  return results;
}

function extractIntervieweeNamesFromText(text = '', limit = 120) {
  const source = String(text || '');
  if (!source.trim()) return [];

  const patterns = [
    /\binterview(?:ed|s)?(?:\s+of|\s+with|\s+by)?\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
    /\bstatement(?:\s+of|\s+from|\s+by)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
    /\baffidavit(?:\s+of|\s+by)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
    /\bdeclaration(?:\s+of|\s+by)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
    /\bI,\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})\s*,\s*(?:being duly sworn|declare|state|depose)\b/g,
    /\b([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})\s+was interviewed\b/gi,
    /\b(?:my name is|i am)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi
  ];
  return collectDistinctPersonNames(source, patterns, limit);
}

function isWitnessListDocument(doc = {}) {
  const lower = String(doc?.lower || '');
  const textLower = String(doc?.text || '').slice(0, 22000).toLowerCase();
  return (
    /\bwitness(?:es)?(?:\s+and\s+exhibit(?:s)?)?\s+list\b/.test(lower) ||
    /\bgovernment witnesses?\b|\bdefen[cs]e witnesses?\b|\bdefendant witnesses?\b/.test(lower) ||
    /\bwitness(?:es)?(?:\s+and\s+exhibit(?:s)?)?\s+list\b/.test(textLower) ||
    /\bproposed witnesses?\b/.test(textLower)
  );
}

function isInterviewSourceDocument(doc = {}) {
  const lower = String(doc?.lower || '');
  const textLower = String(doc?.text || '').slice(0, 26000).toLowerCase();
  return (
    /\binterview\b|\bdebrief\b|\bstatement\b|\b302\b|\baffidavit\b|\bdeclaration\b/.test(lower) ||
    /\binterview(?:ed| of| with)\b/.test(textLower) ||
    /\bstatement(?: of| from| by)\b/.test(textLower) ||
    /\bi,\s*[a-z][a-z'.-]+(?:\s+[a-z][a-z'.-]+){1,3}\s*,\s*(?:being duly sworn|declare|state|depose)\b/.test(textLower)
  );
}

function inferAttorneySideFromContext(context = '') {
  const lower = String(context || '').toLowerCase();
  if (
    /\bfor the united states\b|\bfor the government\b|\bgovernment counsel\b|\bprosecution\b|\bausa\b|\bassistant united states attorney\b/.test(
      lower
    )
  ) {
    return 'prosecution';
  }
  if (/\bfor the defendant\b|\bfor defendant\b|\bdefen[cs]e\b|\bdefendant counsel\b|\bcounsel for defendant\b/.test(lower)) {
    return 'defense';
  }
  return '';
}

function extractAttorneyObservationsFromText(text = '', limit = 80) {
  const source = String(text || '');
  if (!source.trim()) return [];

  const observationsByKey = new Map();
  const push = (rawName, side = '', context = '') => {
    const normalizedName = normalizePersonName(rawName);
    if (!isLikelyPersonName(normalizedName)) return;
    const key = normalizedName.toLowerCase();
    if (!key) return;
    let entry = observationsByKey.get(key);
    if (!entry) {
      entry = {
        name: normalizedName,
        sideCounts: {
          prosecution: 0,
          defense: 0
        },
        contexts: []
      };
      observationsByKey.set(key, entry);
    }
    const inferredSide = side === 'prosecution' || side === 'defense' ? side : inferAttorneySideFromContext(context);
    if (inferredSide === 'prosecution' || inferredSide === 'defense') {
      entry.sideCounts[inferredSide] += 1;
    }
    const trimmedContext = String(context || '').replace(/\s+/g, ' ').trim();
    if (trimmedContext && entry.contexts.length < 6) entry.contexts.push(trimmedContext.slice(0, 220));
  };

  const patterns = [
    {
      regex: /\bfor the united states:\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
      side: 'prosecution'
    },
    {
      regex: /\bfor the government:\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
      side: 'prosecution'
    },
    {
      regex: /\bfor the defendant:\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
      side: 'defense'
    },
    {
      regex: /\bfor the defen[cs]e:\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
      side: 'defense'
    },
    {
      regex: /\bcounsel for (?:the )?(?:defendant|defen[cs]e)\s*:\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
      side: 'defense'
    },
    {
      regex: /\bcounsel for (?:the )?(?:government|united states|prosecution)\s*:\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})/gi,
      side: 'prosecution'
    },
    {
      regex: /\b([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})\s*,\s*(?:AUSA|Assistant United States Attorney)\b/gi,
      side: 'prosecution'
    },
    {
      regex: /\b([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})\s*,\s*(?:ESQ\.?|Esq\.?)\b/g,
      side: ''
    }
  ];

  for (const patternSpec of patterns) {
    const baseRegex = patternSpec.regex instanceof RegExp ? patternSpec.regex : null;
    if (!baseRegex) continue;
    const flags = baseRegex.flags.includes('g') ? baseRegex.flags : `${baseRegex.flags}g`;
    const regex = new RegExp(baseRegex.source, flags);
    let match = regex.exec(source);
    while (match) {
      const context = source.slice(Math.max(0, match.index - 120), Math.min(source.length, match.index + 240));
      push(match[1] || '', patternSpec.side, context);
      if (observationsByKey.size >= limit) break;
      match = regex.exec(source);
    }
    if (observationsByKey.size >= limit) break;
  }

  return Array.from(observationsByKey.values())
    .sort((a, b) => {
      const scoreA = a.sideCounts.prosecution + a.sideCounts.defense + a.contexts.length * 0.25;
      const scoreB = b.sideCounts.prosecution + b.sideCounts.defense + b.contexts.length * 0.25;
      return scoreB - scoreA;
    })
    .slice(0, limit)
    .map((entry) => {
      const side =
        entry.sideCounts.prosecution > entry.sideCounts.defense
          ? 'prosecution'
          : entry.sideCounts.defense > entry.sideCounts.prosecution
            ? 'defense'
            : null;
      return {
        name: entry.name,
        side,
        context: entry.contexts[0] || ''
      };
    });
}

function extractDefendantNamesFromIndictment(text = '') {
  const source = String(text || '');
  if (!source.trim()) return [];

  const names = new Set();
  const push = (rawName) => {
    const normalized = normalizePersonName(rawName);
    if (isLikelyPersonName(normalized)) names.add(normalized);
  };

  const top = source.slice(0, 24000);
  const captionMatch = top.match(/\nV\.\s+([\s\S]{0,900}?)(?:\*+\s*\*+\s*\*+|THE GRAND JURY CHARGES)/i);
  if (captionMatch) {
    for (const line of captionMatch[1].split(/\r?\n/)) {
      const cleaned = line.replace(/[^A-Za-z'.\s,-]/g, ' ').replace(/\s+/g, ' ').trim();
      if (!cleaned) continue;
      const lineMatch = cleaned.match(/^([A-Za-z'.-]+(?:\s+[A-Za-z'.-]+){1,3})/);
      if (lineMatch) push(lineMatch[1]);
    }
  }

  const countBlockRegex = /\n\s*([A-Z][A-Z'.-]+(?:\s+[A-Z][A-Z'.-]+){1,3})\s*,/g;
  let match = countBlockRegex.exec(top);
  while (match) {
    push(match[1]);
    match = countBlockRegex.exec(top);
  }

  return Array.from(names);
}

function extractContextAroundTerm(text = '', term = '', radius = 220) {
  const source = String(text || '');
  const needle = String(term || '').trim();
  if (!source || !needle) return '';
  const lowerSource = source.toLowerCase();
  const lowerNeedle = needle.toLowerCase();
  let index = lowerSource.indexOf(lowerNeedle);
  if (index < 0) {
    const firstToken = lowerNeedle.split(' ')[0];
    index = firstToken ? lowerSource.indexOf(firstToken) : -1;
  }
  if (index < 0) return '';

  const start = Math.max(0, index - radius);
  const end = Math.min(source.length, index + needle.length + radius);
  return source.slice(start, end).replace(/\s+/g, ' ').trim();
}

function escapeRegexLiteral(value = '') {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeBootstrapSourcePath(value = '') {
  return String(value || '')
    .trim()
    .replaceAll('\\', '/')
    .replace(/^\.?\//, '');
}

function classifyWitnessReferenceDocumentType(doc = {}) {
  const lower = String(doc?.lower || '');
  const textLower = String(doc?.text || '').slice(0, 28000).toLowerCase();
  if (String(doc?.docType || '') === 'transcript') return 'transcript';
  if (String(doc?.docType || '') === 'exhibit') return 'exhibit';
  if (String(doc?.docType || '') === 'indictment') return 'indictment';
  if (isWitnessListDocument(doc)) return 'witness_list';
  if (/\baffidavit\b|\bdeclaration\b/.test(lower) || /\bbeing duly sworn\b|\baffiant\b|\bdeclarant\b/.test(textLower)) {
    return 'affidavit';
  }
  if (String(doc?.docType || '') === 'statement' || isInterviewSourceDocument(doc)) return 'statement';
  return 'document';
}

function buildWitnessSearchProfile(witnessNode = {}) {
  const nodeId = String(witnessNode?.node_id || '').trim();
  if (!nodeId) return null;
  const aliases = Array.isArray(witnessNode?.aliases)
    ? witnessNode.aliases
    : witnessNode?.aliases === undefined || witnessNode?.aliases === null
      ? []
      : [witnessNode.aliases];
  const nameValues = [String(witnessNode?.canonical_name || ''), ...aliases.map((value) => String(value || ''))];
  const names = Array.from(
    new Set(
      nameValues
        .map((rawName) => normalizePersonName(rawName))
        .filter((name) => isLikelyPersonName(name))
    )
  );
  if (!names.length) return null;

  const namePatternSources = new Set();
  const transcriptIntroPatterns = [];
  const statementSubjectPatterns = [];
  const nameSegments = [];
  const lastNameSet = new Set();

  for (const name of names) {
    const tokens = String(name || '').split(' ').filter(Boolean);
    if (tokens.length < 2) continue;
    const first = tokens[0];
    const last = tokens[tokens.length - 1];
    const nameSegment = tokens.map(escapeRegexLiteral).join('\\s+');
    if (!nameSegment) continue;
    nameSegments.push(nameSegment);
    lastNameSet.add(last.toLowerCase());
    namePatternSources.add(`\\b${nameSegment}\\b`);
    namePatternSources.add(`\\b${escapeRegexLiteral(first)}(?:\\s+[A-Z]\\.?|\\s+[A-Za-z'.-]+){0,2}\\s+${escapeRegexLiteral(last)}\\b`);
    try {
      transcriptIntroPatterns.push(
        new RegExp(`\\b(?:direct|cross|redirect|recross)[ -]examination\\s+of\\s+${nameSegment}\\b`, 'i'),
        new RegExp(`\\btestimony\\s+of\\s+${nameSegment}\\b`, 'i'),
        new RegExp(`\\b(?:the\\s+)?witness\\s*:\\s*(?:my name is\\s+|i am\\s+|it's\\s+)?${nameSegment}\\b`, 'i'),
        new RegExp(`\\bA\\.\\s*(?:my name is|i am)\\s+${nameSegment}\\b`, 'i'),
        new RegExp(`\\bcalled\\s+(?:as\\s+)?(?:the\\s+|its\\s+)?(?:next\\s+)?witness[,:]?\\s+${nameSegment}\\b`, 'i')
      );
      statementSubjectPatterns.push(
        new RegExp(
          `\\b(?:interview(?:ed| of| with)|statement(?: of| from| by)|affidavit(?: of| by)|declaration(?: of| by))\\s+${nameSegment}\\b`,
          'i'
        ),
        new RegExp(`\\bi,\\s*${nameSegment}\\s*,\\s*(?:being duly sworn|declare|state|depose)\\b`, 'i')
      );
    } catch {
      // Skip malformed dynamic regex inputs.
    }
  }

  const namePatterns = [];
  for (const source of namePatternSources) {
    try {
      namePatterns.push(new RegExp(source, 'i'));
    } catch {
      // Skip malformed dynamic regex inputs.
    }
  }
  if (!namePatterns.length) return null;

  const canonicalTokens = normalizePersonName(String(witnessNode?.canonical_name || '')).split(' ').filter(Boolean);
  const canonicalLastName = canonicalTokens.length ? canonicalTokens[canonicalTokens.length - 1].toLowerCase() : '';
  const lastNames = Array.from(new Set([canonicalLastName, ...Array.from(lastNameSet)])).filter(Boolean);
  let honorificPattern = null;
  if (lastNames.length) {
    try {
      honorificPattern = new RegExp(
        `\\b(?:mr|mrs|ms|miss|dr|agent|officer|detective|special agent)\\.?\\s+(?:${lastNames.map(escapeRegexLiteral).join('|')})\\b`,
        'i'
      );
    } catch {
      honorificPattern = null;
    }
  }

  return {
    nodeId,
    canonicalName: String(witnessNode?.canonical_name || '').trim(),
    names,
    lastNames,
    namePatterns,
    nameSegments,
    honorificPattern,
    transcriptIntroPatterns,
    statementSubjectPatterns
  };
}

function findWitnessMentionInDocument(text = '', profile = {}, radius = 220) {
  const source = String(text || '');
  if (!source || !profile || !Array.isArray(profile.namePatterns)) return null;

  let best = null;
  for (const regex of profile.namePatterns) {
    if (!(regex instanceof RegExp)) continue;
    const match = regex.exec(source);
    if (!match) continue;
    if (!best || match.index < best.index) {
      best = {
        index: match.index,
        matchedText: String(match[0] || ''),
        matchType: 'name',
        confidence: 0.84
      };
    }
  }

  if (!best && profile.honorificPattern instanceof RegExp) {
    const match = profile.honorificPattern.exec(source);
    if (match) {
      best = {
        index: match.index,
        matchedText: String(match[0] || ''),
        matchType: 'honorific',
        confidence: 0.66
      };
    }
  }
  if (!best) return null;

  const start = Math.max(0, best.index - radius);
  const end = Math.min(source.length, best.index + Math.max(best.matchedText.length, 1) + radius);
  const excerpt = source
    .slice(start, end)
    .replace(/\s+/g, ' ')
    .trim();

  return {
    ...best,
    excerpt
  };
}

function inferWitnessInvolvementFromDocument(doc = {}, profile = {}, mention = {}) {
  const docType = classifyWitnessReferenceDocumentType(doc);
  const source = String(doc?.text || '');
  const hasTranscriptCue = Array.isArray(profile.transcriptIntroPatterns)
    ? profile.transcriptIntroPatterns.some((regex) => regex instanceof RegExp && regex.test(source))
    : false;
  const hasStatementCue = Array.isArray(profile.statementSubjectPatterns)
    ? profile.statementSubjectPatterns.some((regex) => regex instanceof RegExp && regex.test(source))
    : false;

  const mentionConfidence = Number.isFinite(Number(mention?.confidence)) ? Number(mention.confidence) : 0.58;
  if (docType === 'transcript') {
    if (hasTranscriptCue) {
      return {
        documentType: 'transcript',
        role: 'testifying_witness',
        description: 'Witness appears as a testifying witness in this transcript.',
        confidence: Math.max(mentionConfidence, 0.9)
      };
    }
    return {
      documentType: 'transcript',
      role: 'mentioned_in_transcript',
      description: 'Witness is referenced during transcript proceedings.',
      confidence: Math.max(mentionConfidence, 0.74)
    };
  }

  if (docType === 'witness_list') {
    return {
      documentType: 'witness_list',
      role: 'listed_witness',
      description: 'Witness appears on a witness list and is a potential trial witness.',
      confidence: Math.max(mentionConfidence, 0.86)
    };
  }

  if (docType === 'affidavit') {
    if (hasStatementCue) {
      return {
        documentType: 'affidavit',
        role: 'affiant_or_declarant',
        description: 'Witness appears as an affiant/declarant or primary statement subject.',
        confidence: Math.max(mentionConfidence, 0.88)
      };
    }
    return {
      documentType: 'affidavit',
      role: 'referenced_in_affidavit',
      description: 'Witness is referenced in affidavit/declaration materials.',
      confidence: Math.max(mentionConfidence, 0.72)
    };
  }

  if (docType === 'statement') {
    if (hasStatementCue) {
      return {
        documentType: 'statement',
        role: 'interviewee_or_declarant',
        description: 'Witness appears as an interviewee/declarant for potential testimony.',
        confidence: Math.max(mentionConfidence, 0.84)
      };
    }
    return {
      documentType: 'statement',
      role: 'referenced_in_statement',
      description: 'Witness is referenced in statement/interview materials.',
      confidence: Math.max(mentionConfidence, 0.71)
    };
  }

  if (docType === 'exhibit') {
    return {
      documentType: 'exhibit',
      role: 'mentioned_in_exhibit',
      description: 'Witness is referenced or implicated by this exhibit.',
      confidence: Math.max(mentionConfidence, 0.69)
    };
  }

  if (docType === 'indictment') {
    return {
      documentType: 'indictment',
      role: 'named_in_charging_document',
      description: 'Witness is named or described in charging allegations.',
      confidence: Math.max(mentionConfidence, 0.8)
    };
  }

  return {
    documentType: 'document',
    role: 'referenced_in_document',
    description: 'Witness is referenced in case materials.',
    confidence: Math.max(mentionConfidence, 0.6)
  };
}

function buildWitnessOverallSummary(appearsIn = {}, chart = []) {
  const rows = Array.isArray(chart) ? chart : [];
  const counts = {
    transcript: 0,
    statement: 0,
    affidavit: 0,
    witness_list: 0,
    exhibit: 0,
    indictment: 0,
    document: 0
  };
  let testifyingCount = 0;
  for (const row of rows) {
    const docType = String(row?.document_type || 'document');
    if (docType in counts) counts[docType] += 1;
    else counts.document += 1;
    if (String(row?.role_in_document || '') === 'testifying_witness') testifyingCount += 1;
  }
  const countRefs = Array.isArray(appearsIn?.counts) ? appearsIn.counts.length : 0;
  if (!rows.length) {
    return countRefs
      ? `Linked to ${countRefs} count(s). Document appearance chart is pending source matches.`
      : 'Document appearance chart is pending source matches.';
  }

  const statementLikeTotal = counts.statement + counts.affidavit + counts.witness_list;
  const otherTotal = counts.document + counts.indictment;
  return `Appears in ${rows.length} document(s): ${counts.transcript} transcript(s) (${testifyingCount} as testifying witness), ${statementLikeTotal} statement/affidavit/witness-list document(s), ${counts.exhibit} exhibit(s), and ${otherTotal} additional document(s). Linked to ${countRefs} count(s).`;
}

function classifyBootstrapDocument(relPath = '', text = '') {
  const lower = String(relPath || '').toLowerCase();
  const textLower = String(text || '').slice(0, 12000).toLowerCase();
  if (lower.endsWith('peregrine startup workspace.md')) return 'generated';
  if (
    /\bindict|indictment|indictiment|information\b/.test(lower) ||
    /\bthe grand jury charges\b/.test(textLower)
  ) {
    return 'indictment';
  }
  if (
    /\btranscript\b|\btrial\b|\bvoir dire\b|\btestimony\b/.test(lower) ||
    /\bdirect examination\b|\bcross[- ]examination\b/.test(textLower)
  ) {
    return 'transcript';
  }
  if (/\bexhibit\b|\bgx[\s_-]*\d+\b|\bdx[\s_-]*\d+\b/.test(lower)) return 'exhibit';
  if (/\baffidavit\b|\bdeclaration\b/.test(lower) || /\bsworn statement\b/.test(textLower)) return 'statement';
  return 'other';
}

function scoreIndictmentCandidate(doc = {}) {
  const lower = String(doc?.lower || '').toLowerCase();
  const text = String(doc?.text || '');
  const textLower = text.toLowerCase();
  let score = 0;

  if (/\bindict|indictment|indictiment\b/.test(lower)) score += 70;
  if (/\bsupersed/.test(lower)) score += 24;
  if (/\binformation\b/.test(lower)) score += 14;
  if (/\bgrand jury charges\b/.test(textLower)) score += 220;
  if (/\bforfeiture allegation\b/.test(textLower)) score += 40;
  if (/\bdid\s+conspire\b|\ball in violation of\b/.test(textLower)) score += 36;
  if (/\bcharged\b/.test(textLower)) score += 18;

  if (/\bmotion\b|\border\b|\bjudgment\b|\bopinion\b|\bbrief\b|\bresponse\b|\bnotice\b/.test(lower)) score -= 110;
  if (/\bmotion of defendant\b|\bmemorandum of law\b|\bcertificate of service\b/.test(textLower)) score -= 140;

  const countMarkers = extractCountSegmentsFromText(text).length;
  const statuteCount = extractStatutesFromText(text).length;
  score += Math.min(180, countMarkers * 58);
  score += Math.min(90, statuteCount * 7);

  return {
    score,
    countMarkers,
    statuteCount,
    isSuperseding: /\bsupersed/.test(lower) || /\bsuperseding indictment\b/.test(textLower)
  };
}

function selectIndictmentDocuments(docs = []) {
  const candidates = docs
    .filter((doc) => {
      if (!doc) return false;
      if (doc.docType === 'indictment') return true;
      const lower = String(doc.lower || '');
      return /\bindict|indictment|indictiment|information\b/.test(lower);
    })
    .map((doc) => ({
      doc,
      ...scoreIndictmentCandidate(doc)
    }))
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (b.countMarkers !== a.countMarkers) return b.countMarkers - a.countMarkers;
      if (b.statuteCount !== a.statuteCount) return b.statuteCount - a.statuteCount;
      return String(a.doc.relPath || '').localeCompare(String(b.doc.relPath || ''));
    });

  const bestOverall = candidates[0]?.doc || null;
  const bestNonSuperseding = candidates.find(
    (entry) => !entry.isSuperseding && entry.score >= 120 && entry.countMarkers > 0
  )?.doc;
  const primary = bestNonSuperseding || bestOverall;
  const superseding = candidates.find((entry) => entry.isSuperseding)?.doc || null;

  const forCounts =
    candidates
      .slice()
      .sort((a, b) => {
        if (b.countMarkers !== a.countMarkers) return b.countMarkers - a.countMarkers;
        return b.score - a.score;
      })[0]?.doc || primary || superseding || null;

  return {
    primary,
    superseding,
    forCounts,
    scoredCandidates: candidates
  };
}

function roundTo(value = 0, places = 2) {
  const factor = 10 ** places;
  return Math.round(Number(value || 0) * factor) / factor;
}

function isBootstrapTrialTranscriptDoc(doc = {}) {
  const lower = String(doc?.lower || '');
  const normalizedPath = lower.replaceAll('\\', '/');
  const baseName = path.basename(normalizedPath);
  const textSample = String(doc?.text || '').slice(0, 12000).toLowerCase();
  const inTranscriptDir = /(?:^|\/)transcripts?(?:\/|$)/.test(normalizedPath);
  const fileSignal =
    /\btranscript\b|\btrial day\b|\bvoir dire\b|\bsentencing hearing\b|\brearraignment\b/.test(baseName) ||
    /\btranscript of proceedings\b/.test(baseName);
  const headingSignal = /\btranscript of (?:jury trial|proceedings)\b|\bproceedings commenced\b/.test(textSample);
  if (!inTranscriptDir && !fileSignal && !headingSignal) return false;

  const witnessSignal =
    /\bthe witness:\b|\bdirect examination\b|\bcross[- ]examination\b|\bredirect examination\b|\brecross[- ]examination\b/.test(
      textSample
    );
  const trialSignal =
    /\btrial day\b|\bvoir dire\b|\bjury trial\b|\brearraignment\b|\bsentencing hearing\b/.test(normalizedPath) ||
    /\btranscript of proceedings\b/.test(textSample);
  if (!witnessSignal && !trialSignal) return false;

  const proceduralDoc = /\bmotion\b|\border\b|\bnotice\b|\bresponse\b|\bbrief\b|\bmemorandum\b/.test(baseName);
  if (proceduralDoc && !/transcript/.test(baseName) && !witnessSignal) return false;

  return true;
}

function deriveWitnessCredibilitySignals(excerpts = []) {
  const credibilityFlags = new Set();
  const impeachmentMaterial = [];
  const pushMaterial = (label, excerpt) => {
    if (!excerpt || impeachmentMaterial.length >= 8) return;
    impeachmentMaterial.push(`${label}: ${String(excerpt).slice(0, 220)}`);
  };

  for (const excerpt of excerpts) {
    const lower = String(excerpt || '').toLowerCase();
    if (!lower) continue;

    if (/\binconsisten|contradict|changed (?:his|her|their) (?:story|statement)\b/.test(lower)) {
      credibilityFlags.add('inconsistent_statements');
      pushMaterial('Inconsistency signal', excerpt);
    }
    if (/\bimpeach|impeachment\b/.test(lower)) {
      credibilityFlags.add('impeachment_mentioned');
      pushMaterial('Impeachment mention', excerpt);
    }
    if (/\bplea\b|\bcooperat(?:e|ing|ion)\b|\bimmunity\b|\binformant\b/.test(lower)) {
      credibilityFlags.add('cooperation_bias');
      pushMaterial('Cooperation/benefit signal', excerpt);
    }
    if (/\bprior conviction\b|\bfelony\b|\bcrime of dishonesty\b/.test(lower)) {
      credibilityFlags.add('prior_conviction_risk');
      pushMaterial('Prior conviction signal', excerpt);
    }
    if (/\blie[sd]?\b|\bfalse\b|\bfabricat(?:e|ed|ion)\b|\buntruth\b/.test(lower)) {
      credibilityFlags.add('truthfulness_challenge');
      pushMaterial('Truthfulness challenge', excerpt);
    }
  }

  return {
    credibilityFlags: Array.from(credibilityFlags),
    impeachmentMaterial
  };
}

async function extractBootstrapText(absPath, maxChars = 140000) {
  const ext = getExtensionLower(absPath);
  const category = classifyExtension(ext);
  if (category === 'text') {
    const text = normalizeText(fs.readFileSync(absPath, 'utf-8'));
    return text.length > maxChars ? text.slice(0, maxChars) : text;
  }
  if (['pdf', 'word', 'spreadsheet', 'email', 'presentation'].includes(category)) {
    const extracted = await extractNativeFile(absPath);
    const text = normalizeText(extracted.markdown || extracted.text || '');
    return text.length > maxChars ? text.slice(0, maxChars) : text;
  }
  return '';
}

async function bootstrapCasefileWorkspace(vaultRoot, payload = {}) {
  const mode = 'deep';
  const actionToken = String(payload?.action || payload?.operation || payload?.command || '').trim().toLowerCase();
  const requestedModeToken = String(payload?.mode || payload?.bootstrapMode || payload?.depth || '').trim().toLowerCase();
  const isRefresh =
    Boolean(payload?.refresh || payload?.bootstrapRefresh) ||
    actionToken === 'refresh' ||
    requestedModeToken === 'refresh';
  const caseRoot = resolveBootstrapCaseRoot(vaultRoot, payload || {});
  const startedAt = new Date().toISOString();
  const fileLimit = 1800;
  const textLimit = 180000;
  logStartup(
    `[bootstrap] start mode=${mode} refresh=${isRefresh ? 'yes' : 'no'} requestedMode=${requestedModeToken || ''} vaultRoot=${vaultRoot || ''} resolved=${caseRoot}`
  );

  const schemaRoot = path.join(caseRoot, 'Casefile');
  const metadataRoot = path.join(schemaRoot, '00_Metadata');
  const chargingRoot = path.join(schemaRoot, '01_Charging_Documents');
  const countsRoot = path.join(schemaRoot, '02_Counts');
  const witnessesRoot = path.join(schemaRoot, '03_Witnesses');
  const transcriptsRoot = path.join(schemaRoot, '04_Transcripts');
  const exhibitsRoot = path.join(schemaRoot, '05_Exhibits');
  const graphRoot = path.join(schemaRoot, '06_Link_Graph');
  const attorneysRoot = path.join(schemaRoot, '07_Attorneys');
  [
    metadataRoot,
    chargingRoot,
    countsRoot,
    witnessesRoot,
    transcriptsRoot,
    exhibitsRoot,
    graphRoot,
    attorneysRoot
  ].forEach((dir) => fs.mkdirSync(dir, { recursive: true }));

  const allFiles = walkCasefileDocuments(caseRoot, fileLimit);
  logStartup(`[bootstrap] scan caseRoot=${caseRoot} files=${allFiles.length} limit=${fileLimit}`);

  const docs = [];
  for (const absPath of allFiles) {
    const relPath = toRel(caseRoot, absPath);
    const lower = relPath.toLowerCase();
    const isInteresting =
      /\.(md|markdown|txt|json|yaml|yml|pdf|doc|docx|odt|rtf|eml|msg|xls|xlsx|csv|tsv|ppt|pptx|odp)$/i.test(relPath) ||
      /\bindictment\b|\btranscript\b|\btrial\b|\bexhibit\b|\baffidavit\b|\bwitness\b/.test(lower);
    if (!isInteresting) continue;
    let text = '';
    try {
      text = await extractBootstrapText(absPath, textLimit);
    } catch {
      text = '';
    }
    const docType = classifyBootstrapDocument(relPath, text);
    if (docType === 'generated') continue;

    docs.push({
      absPath,
      relPath,
      fileName: path.basename(absPath),
      lower,
      text,
      docType
    });
  }
  logStartup(`[bootstrap] extracted documents=${docs.length}`);

  const sourceIndexPath = path.join(metadataRoot, 'bootstrap_source_index.json');
  const refreshReportPath = path.join(metadataRoot, 'bootstrap_refresh_report.json');
  const previousSourceIndex = readJsonFileSafe(sourceIndexPath, {
    version: 1,
    generated_at: '',
    mode: 'deep',
    documents: []
  });
  const previousDocs = Array.isArray(previousSourceIndex?.documents) ? previousSourceIndex.documents : [];
  const previousByPath = new Map();
  for (const entry of previousDocs) {
    const normalizedPath = normalizeBootstrapSourcePath(entry?.path || entry?.document_path || '');
    if (!normalizedPath) continue;
    previousByPath.set(normalizedPath, {
      path: normalizedPath,
      file_name: String(entry?.file_name || path.basename(normalizedPath)),
      doc_type: String(entry?.doc_type || entry?.document_type || 'document'),
      text_hash: String(entry?.text_hash || ''),
      size_bytes: Number.isFinite(Number(entry?.size_bytes)) ? Number(entry.size_bytes) : null,
      mtime_ms: Number.isFinite(Number(entry?.mtime_ms)) ? Number(entry.mtime_ms) : null,
      scanned_chars: Number.isFinite(Number(entry?.scanned_chars)) ? Number(entry.scanned_chars) : 0
    });
  }

  const currentEntries = [];
  const currentByPath = new Map();
  const docsBySourcePath = new Map();
  for (const doc of docs) {
    const normalizedPath = normalizeBootstrapSourcePath(doc.relPath);
    if (!normalizedPath) continue;
    docsBySourcePath.set(normalizedPath, doc);
    let sizeBytes = null;
    let mtimeMs = null;
    try {
      const stat = fs.statSync(doc.absPath);
      sizeBytes = Number.isFinite(Number(stat?.size)) ? Number(stat.size) : null;
      mtimeMs = Number.isFinite(Number(stat?.mtimeMs)) ? Number(stat.mtimeMs) : null;
    } catch {
      sizeBytes = null;
      mtimeMs = null;
    }
    const textHash = crypto
      .createHash('sha1')
      .update(String(doc.text || ''), 'utf8')
      .digest('hex');
    const entry = {
      path: normalizedPath,
      file_name: String(doc.fileName || path.basename(normalizedPath)),
      doc_type: String(doc.docType || classifyWitnessReferenceDocumentType(doc)),
      text_hash: textHash,
      size_bytes: sizeBytes,
      mtime_ms: mtimeMs,
      scanned_chars: Number(String(doc.text || '').length),
      scanned_at: new Date().toISOString()
    };
    currentEntries.push(entry);
    currentByPath.set(normalizedPath, entry);
  }

  const newDocuments = [];
  const updatedDocuments = [];
  const removedDocuments = [];
  for (const entry of currentEntries) {
    const prior = previousByPath.get(entry.path);
    if (!prior) {
      newDocuments.push(entry);
      continue;
    }
    if (String(prior.text_hash || '') !== String(entry.text_hash || '')) {
      updatedDocuments.push({
        ...entry,
        previous_text_hash: String(prior.text_hash || '')
      });
    }
  }
  for (const previousEntry of previousByPath.values()) {
    if (currentByPath.has(previousEntry.path)) continue;
    removedDocuments.push(previousEntry);
  }

  const analyzeDeltaDocument = (entry = {}) => {
    const sourcePath = normalizeBootstrapSourcePath(entry?.path || '');
    const doc = docsBySourcePath.get(sourcePath);
    const text = String(doc?.text || '');
    const countRefs = extractCountReferencesFromText(text, 12).map((countNumber) => `count_${countNumber}`);
    const explicitWitnessNames = doc?.docType === 'transcript' ? extractExplicitWitnessNamesFromTranscript(text, 24) : [];
    const witnessListNames = isWitnessListDocument(doc || {}) ? extractWitnessNamesFromWitnessList(text, 24) : [];
    const intervieweeNames = isInterviewSourceDocument(doc || {}) ? extractIntervieweeNamesFromText(text, 24) : [];
    const attorneyNames = extractAttorneyObservationsFromText(text, 20).map((item) => String(item?.name || '')).filter(Boolean);
    const impactFlags = [];
    if (countRefs.length) impactFlags.push(`count_refs=${countRefs.length}`);
    if (explicitWitnessNames.length) impactFlags.push(`explicit_witnesses=${explicitWitnessNames.length}`);
    if (witnessListNames.length) impactFlags.push(`witness_list_names=${witnessListNames.length}`);
    if (intervieweeNames.length) impactFlags.push(`interviewees=${intervieweeNames.length}`);
    if (attorneyNames.length) impactFlags.push(`attorneys=${attorneyNames.length}`);
    return {
      path: sourcePath,
      file_name: String(entry?.file_name || path.basename(sourcePath)),
      document_type: String(entry?.doc_type || 'document'),
      count_refs: Array.from(new Set(countRefs)).slice(0, 24),
      explicit_witness_names: explicitWitnessNames.slice(0, 24),
      witness_list_names: witnessListNames.slice(0, 24),
      interviewee_names: intervieweeNames.slice(0, 24),
      attorney_names: attorneyNames.slice(0, 24),
      impact_summary: impactFlags.length ? impactFlags.join('; ') : 'No high-signal ontology indicators detected.'
    };
  };
  const analyzedDeltaDocuments = [...newDocuments, ...updatedDocuments]
    .map((entry) => analyzeDeltaDocument(entry))
    .slice(0, 400);
  const refreshSummary = {
    requested: isRefresh,
    new_documents: newDocuments.length,
    updated_documents: updatedDocuments.length,
    removed_documents: removedDocuments.length,
    analyzed_documents: analyzedDeltaDocuments.length
  };

  const indictmentSelection = selectIndictmentDocuments(docs);
  const primaryIndictment = indictmentSelection.primary;
  const supersedingIndictment = indictmentSelection.superseding;
  const indictmentForCounts = indictmentSelection.forCounts || primaryIndictment || supersedingIndictment;
  const indictmentText = String(
    indictmentForCounts?.text || primaryIndictment?.text || supersedingIndictment?.text || ''
  );
  const defendantNames = extractDefendantNamesFromIndictment(indictmentText);
  const rawCountSegments = extractCountSegmentsFromText(indictmentText);
  const dedupedCountSegments = new Map();
  for (const segment of rawCountSegments) {
    const countNumber = Number(segment?.countNumber || 0);
    if (!Number.isFinite(countNumber) || countNumber <= 0) continue;
    const existing = dedupedCountSegments.get(countNumber);
    if (!existing || String(segment.fullText || '').length > String(existing.fullText || '').length) {
      dedupedCountSegments.set(countNumber, segment);
    }
  }
  const countSegments = Array.from(dedupedCountSegments.values()).sort((a, b) => a.countNumber - b.countNumber);
  logStartup(
    `[bootstrap] indictment primary=${primaryIndictment?.relPath || ''} superseding=${supersedingIndictment?.relPath || ''} forCounts=${indictmentForCounts?.relPath || ''} parsedCounts=${countSegments.length}`
  );
  const counts = countSegments.length
    ? countSegments
    : indictmentText
      ? [{ countNumber: 1, fullText: indictmentText }]
      : [];

  const countWitnessesByNumber = new Map();
  const countNodes = [];
  for (const segment of counts) {
    const nodeId = `count_${segment.countNumber}`;
    const countWitnesses = [];
    countWitnessesByNumber.set(segment.countNumber, new Set(countWitnesses));
    countNodes.push({
      node_id: nodeId,
      node_type: 'Count',
      canonical_name: `Count ${segment.countNumber}`,
      count_number: segment.countNumber,
      statutes: extractStatutesFromText(segment.fullText),
      statutory_elements: [],
      full_text: String(segment.fullText || '').slice(0, 15000),
      defendant_conduct_alleged: String(segment.fullText || '').slice(0, 900),
      mens_rea_alleged: /\bknowingly|willfully|intent/i.test(segment.fullText) ? String(segment.fullText || '').slice(0, 500) : '',
      financial_exposure: null,
      forfeiture_alleged: /\bforfeiture|forfeit/i.test(segment.fullText) ? true : null,
      date_range: '',
      locations: [],
      named_witnesses: countWitnesses,
      linked_exhibits: [],
      linked_transcripts: [],
      elements_status: {
        element_1: {
          text: '',
          supporting_witnesses: [],
          supporting_exhibits: [],
          defense_gaps: [],
          confidence_score: 0
        }
      },
      rule_29_vulnerability_score: null,
      created_at: startedAt,
      last_updated: new Date().toISOString(),
      source_files: indictmentForCounts ? [indictmentForCounts.relPath] : [],
      bootstrap_version: BOOTSTRAP_SCHEMA_VERSION
    });
  }
  const countIdSet = new Set(countNodes.map((node) => node.node_id));
  const countNodeByNumber = new Map(countNodes.map((node) => [node.count_number, node]));

  const transcriptDocs = docs.filter((doc) => doc.docType === 'transcript' && isBootstrapTrialTranscriptDoc(doc));
  const exhibitDocs = docs.filter((doc) => doc.docType === 'exhibit');
  const statementDocs = docs.filter((doc) => doc.docType === 'statement');

  const transcriptData = transcriptDocs.slice(0, 1200).map((doc) => {
    const token = slugifyNodeToken(path.basename(doc.fileName, path.extname(doc.fileName)), 'transcript');
    const linkedCountNumbers = extractCountReferencesFromText(doc.text || '', 24);
    const linkedCountIds = linkedCountNumbers
      .map((countNumber) => `count_${countNumber}`)
      .filter((countId) => countIdSet.has(countId));
    const referencedPersons = extractExplicitWitnessNamesFromTranscript(doc.text || '', 180);
    const referencedEntities = extractStatutesFromText(doc.text || '');
    const node = {
      node_id: `transcript_${token}`,
      node_type: 'Transcript',
      canonical_name: path.basename(doc.fileName, path.extname(doc.fileName)),
      date: '',
      proceeding_type: 'Trial Transcript',
      witness_on_stand: referencedPersons[0] || '',
      direct_exam: [],
      cross_exam: [],
      redirect_exam: [],
      recross_exam: [],
      linked_counts: linkedCountIds,
      linked_exhibits: [],
      referenced_persons: referencedPersons,
      referenced_entities: referencedEntities,
      created_at: startedAt,
      last_updated: new Date().toISOString(),
      source_files: [doc.relPath],
      bootstrap_version: BOOTSTRAP_SCHEMA_VERSION
    };
    return {
      doc,
      node,
      linkedCountNumbers,
      linkedCountIds,
      referencedPersons,
      referencedEntities
    };
  });
  const transcriptNodes = transcriptData.map((entry) => entry.node);

  const exhibitData = exhibitDocs.slice(0, 2000).map((doc) => {
    const token = slugifyNodeToken(path.basename(doc.fileName, path.extname(doc.fileName)), 'exhibit');
    const linkedCountNumbers = extractCountReferencesFromText(doc.text || '', 18);
    const linkedCountIds = linkedCountNumbers
      .map((countNumber) => `count_${countNumber}`)
      .filter((countId) => countIdSet.has(countId));
    const mentionedEntities = extractStatutesFromText(doc.text || '');
    const witnessListDoc = isWitnessListDocument(doc);
    const interviewDoc = isInterviewSourceDocument(doc);
    const mentionedPersons = Array.from(
      new Set([
        ...(witnessListDoc ? extractWitnessNamesFromWitnessList(doc.text || '', 90) : []),
        ...(interviewDoc ? extractIntervieweeNamesFromText(doc.text || '', 70) : [])
      ])
    );
    const node = {
      node_id: `exhibit_${token}`,
      node_type: 'Exhibit',
      canonical_name: path.basename(doc.fileName, path.extname(doc.fileName)),
      exhibit_id: path.basename(doc.fileName, path.extname(doc.fileName)),
      type: getExtensionLower(doc.fileName).replace('.', '').toUpperCase(),
      date: '',
      authors: [],
      recipients: [],
      mentioned_entities: mentionedEntities,
      linked_witnesses: [],
      linked_counts: linkedCountIds,
      summary: String(doc.text || '').slice(0, 1000),
      full_text: String(doc.text || '').slice(0, 20000),
      bates_range: '',
      file_path: doc.relPath,
      relevance_score: null,
      created_at: startedAt,
      last_updated: new Date().toISOString(),
      source_files: [doc.relPath],
      bootstrap_version: BOOTSTRAP_SCHEMA_VERSION
    };
    return {
      doc,
      node,
      linkedCountNumbers,
      linkedCountIds,
      mentionedEntities,
      mentionedPersons,
      witnessListDoc,
      interviewDoc
    };
  });
  const exhibitNodes = exhibitData.map((entry) => entry.node);

  const attorneyStatsByKey = new Map();
  const attorneyNameParts = (rawName) => {
    const normalized = normalizePersonName(rawName);
    if (!normalized) {
      return {
        normalized: '',
        firstName: '',
        lastName: ''
      };
    }
    const tokens = normalized.toLowerCase().split(' ').filter(Boolean);
    if (tokens.length < 2) {
      return {
        normalized,
        firstName: tokens[0] || '',
        lastName: tokens[0] || ''
      };
    }
    return {
      normalized,
      firstName: tokens[0],
      lastName: tokens[tokens.length - 1]
    };
  };
  const addAttorneyObservation = (rawName, payload = {}) => {
    const parts = attorneyNameParts(rawName);
    const normalized = parts.normalized;
    if (!isLikelyPersonName(normalized)) return;
    const key = parts.firstName && parts.lastName ? `${parts.firstName}_${parts.lastName}` : '';
    if (!key) return;
    let stat = attorneyStatsByKey.get(key);
    if (!stat) {
      stat = {
        key,
        firstName: parts.firstName,
        lastName: parts.lastName,
        variantCounts: new Map(),
        sourceFiles: new Set(),
        transcriptIds: new Set(),
        countNumbers: new Set(),
        sideCounts: {
          prosecution: 0,
          defense: 0
        },
        contexts: []
      };
      attorneyStatsByKey.set(key, stat);
    }
    stat.variantCounts.set(normalized, (stat.variantCounts.get(normalized) || 0) + 1);
    if (payload.sourceFile) stat.sourceFiles.add(String(payload.sourceFile));
    if (payload.transcriptId) stat.transcriptIds.add(String(payload.transcriptId));
    if (Array.isArray(payload.countNumbers)) {
      for (const countNumber of payload.countNumbers) {
        const parsed = Number(countNumber);
        if (Number.isFinite(parsed) && parsed > 0) stat.countNumbers.add(parsed);
      }
    }
    if (payload.side === 'prosecution' || payload.side === 'defense') {
      stat.sideCounts[payload.side] += 1;
    }
    if (payload.excerpt) {
      const excerpt = String(payload.excerpt).replace(/\s+/g, ' ').trim();
      if (excerpt && stat.contexts.length < 8) stat.contexts.push(excerpt.slice(0, 220));
    }
  };

  for (const entry of transcriptData) {
    const attorneyObservations = extractAttorneyObservationsFromText(entry.doc.text || '', 80);
    for (const observation of attorneyObservations) {
      addAttorneyObservation(observation.name, {
        sourceFile: entry.doc.relPath,
        transcriptId: entry.node.node_id,
        countNumbers: entry.linkedCountNumbers,
        side: observation.side,
        excerpt: observation.context || extractContextAroundTerm(entry.doc.text || '', observation.name, 190)
      });
    }
  }
  for (const doc of docs) {
    if (doc.docType === 'transcript' && isBootstrapTrialTranscriptDoc(doc)) continue;
    const attorneyObservations = extractAttorneyObservationsFromText(doc.text || '', 80);
    for (const observation of attorneyObservations) {
      addAttorneyObservation(observation.name, {
        sourceFile: doc.relPath,
        side: observation.side,
        excerpt: observation.context || extractContextAroundTerm(doc.text || '', observation.name, 170)
      });
    }
  }

  const attorneyStats = Array.from(attorneyStatsByKey.values()).filter((stat) => stat.sourceFiles.size >= 1);
  attorneyStats.sort((a, b) => {
    const scoreA =
      a.transcriptIds.size * 4 +
      a.sourceFiles.size * 2 +
      a.countNumbers.size * 2 +
      a.sideCounts.prosecution +
      a.sideCounts.defense;
    const scoreB =
      b.transcriptIds.size * 4 +
      b.sourceFiles.size * 2 +
      b.countNumbers.size * 2 +
      b.sideCounts.prosecution +
      b.sideCounts.defense;
    return scoreB - scoreA;
  });

  const attorneyNodes = attorneyStats.slice(0, 260).map((stat) => {
    const variants = Array.from(stat.variantCounts.entries())
      .sort((a, b) => {
        if (b[1] !== a[1]) return b[1] - a[1];
        return b[0].length - a[0].length;
      })
      .map(([name]) => name);
    const canonicalName = variants[0] || 'Unknown Attorney';
    const attorneyId = `attorney_${slugifyNodeToken(canonicalName, 'attorney')}`;
    const countIds = Array.from(stat.countNumbers)
      .sort((a, b) => a - b)
      .map((countNumber) => `count_${countNumber}`)
      .filter((countId) => countIdSet.has(countId));
    const transcriptIds = Array.from(stat.transcriptIds).sort();
    const side =
      stat.sideCounts.prosecution > stat.sideCounts.defense
        ? 'prosecution'
        : stat.sideCounts.defense > stat.sideCounts.prosecution
          ? 'defense'
          : null;
    return {
      node_id: attorneyId,
      node_type: 'Attorney',
      canonical_name: canonicalName,
      aliases: variants.slice(1, 6),
      side,
      represents: side === 'defense' ? defendantNames : side === 'prosecution' ? ['United States'] : [],
      appears_in: {
        counts: countIds,
        transcripts: transcriptIds
      },
      statements: stat.contexts.map((excerpt) => ({ excerpt })),
      created_at: startedAt,
      last_updated: new Date().toISOString(),
      source_files: Array.from(stat.sourceFiles).sort(),
      bootstrap_version: BOOTSTRAP_SCHEMA_VERSION
    };
  });

  const attorneyNormalizedNames = new Set();
  for (const attorneyNode of attorneyNodes) {
    const names = [attorneyNode.canonical_name, ...(attorneyNode.aliases || [])];
    for (const name of names) {
      const normalized = normalizePersonName(name).toLowerCase();
      if (normalized) attorneyNormalizedNames.add(normalized);
    }
  }

  const witnessStatsByKey = new Map();
  const witnessNameParts = (rawName) => {
    const normalized = normalizePersonName(rawName);
    if (!normalized) {
      return {
        normalized: '',
        firstName: '',
        lastName: ''
      };
    }
    const tokens = normalized.toLowerCase().split(' ').filter(Boolean);
    if (tokens.length < 2) {
      return {
        normalized,
        firstName: tokens[0] || '',
        lastName: tokens[0] || ''
      };
    }
    return {
      normalized,
      firstName: tokens[0],
      lastName: tokens[tokens.length - 1]
    };
  };

  const fuzzyFirstNameMatch = (first, candidateFirst) => {
    const a = String(first || '').trim();
    const b = String(candidateFirst || '').trim();
    if (!a || !b) return false;
    if (a === b) return true;
    if (a.includes(b) || b.includes(a)) return true;
    const stripVowels = (value) => value.replace(/[aeiou]/g, '');
    const av = stripVowels(a);
    const bv = stripVowels(b);
    if (!av || !bv) return false;
    return av === bv || av.includes(bv) || bv.includes(av);
  };

  const addWitnessObservation = (rawName, payload = {}) => {
    const parts = witnessNameParts(rawName);
    const normalized = parts.normalized;
    if (!isLikelyPersonName(normalized)) return;
    if (attorneyNormalizedNames.has(normalized.toLowerCase())) return;
    const key = parts.firstName && parts.lastName ? `${parts.firstName}_${parts.lastName}` : '';
    if (!key) return;

    let stat = witnessStatsByKey.get(key);
    if (!stat) {
      for (const candidate of witnessStatsByKey.values()) {
        if (candidate.lastName !== parts.lastName) continue;
        if (!fuzzyFirstNameMatch(parts.firstName, candidate.firstName)) continue;
        stat = candidate;
        break;
      }
    }
    if (!stat) {
      stat = {
        key,
        firstName: parts.firstName,
        lastName: parts.lastName,
        variantCounts: new Map(),
        sourceFiles: new Set(),
        transcriptIds: new Set(),
        exhibitIds: new Set(),
        countNumbers: new Set(),
        contexts: [],
        role: null,
        fromWitnessList: false,
        fromInterview: false,
        appearsInIndictment: false
      };
      witnessStatsByKey.set(key, stat);
    }

    stat.variantCounts.set(normalized, (stat.variantCounts.get(normalized) || 0) + 1);

    if (payload.sourceFile) stat.sourceFiles.add(String(payload.sourceFile));
    if (payload.transcriptId) stat.transcriptIds.add(String(payload.transcriptId));
    if (payload.exhibitId) stat.exhibitIds.add(String(payload.exhibitId));
    if (payload.role === 'defendant') stat.role = 'defendant';
    if (payload.fromWitnessList) stat.fromWitnessList = true;
    if (payload.fromInterview) stat.fromInterview = true;
    if (payload.fromIndictment) stat.appearsInIndictment = true;

    if (Array.isArray(payload.countNumbers)) {
      for (const countNumber of payload.countNumbers) {
        const parsed = Number(countNumber);
        if (Number.isFinite(parsed) && parsed > 0) stat.countNumbers.add(parsed);
      }
    }

    if (payload.excerpt) {
      const excerpt = String(payload.excerpt).trim();
      if (excerpt) {
        stat.contexts.push({
          sourceFile: payload.sourceFile || '',
          sourceType: payload.sourceType || '',
          excerpt
        });
      }
    }
  };

  for (const defendantName of defendantNames) {
    addWitnessObservation(defendantName, {
      sourceFile: indictmentForCounts?.relPath || '',
      fromIndictment: true,
      role: 'defendant'
    });
  }
  for (const [countNumber, names] of countWitnessesByNumber.entries()) {
    for (const name of names) {
      addWitnessObservation(name, {
        sourceFile: indictmentForCounts?.relPath || '',
        countNumbers: [countNumber],
        fromIndictment: true,
        sourceType: 'indictment',
        excerpt: extractContextAroundTerm(indictmentText, name, 180)
      });
    }
  }

  for (const entry of transcriptData) {
    for (const name of entry.referencedPersons) {
      addWitnessObservation(name, {
        sourceFile: entry.doc.relPath,
        sourceType: 'transcript',
        transcriptId: entry.node.node_id,
        countNumbers: entry.linkedCountNumbers,
        excerpt: extractContextAroundTerm(entry.doc.text || '', name, 210),
        fromWitnessList: false
      });
    }
  }
  for (const entry of exhibitData) {
    for (const name of entry.mentionedPersons) {
      addWitnessObservation(name, {
        sourceFile: entry.doc.relPath,
        sourceType: 'exhibit',
        exhibitId: entry.node.node_id,
        countNumbers: entry.linkedCountNumbers,
        excerpt: extractContextAroundTerm(entry.doc.text || '', name, 180),
        fromWitnessList: entry.witnessListDoc,
        fromInterview: entry.interviewDoc
      });
    }
  }
  for (const doc of statementDocs) {
    const witnessListDoc = isWitnessListDocument(doc);
    const interviewDoc = isInterviewSourceDocument(doc);
    const names = Array.from(
      new Set([
        ...(witnessListDoc ? extractWitnessNamesFromWitnessList(doc.text || '', 120) : []),
        ...(interviewDoc ? extractIntervieweeNamesFromText(doc.text || '', 120) : [])
      ])
    );
    const countNumbers = extractCountReferencesFromText(doc.text || '', 12);
    for (const name of names) {
      addWitnessObservation(name, {
        sourceFile: doc.relPath,
        sourceType: 'statement',
        countNumbers,
        excerpt: extractContextAroundTerm(doc.text || '', name, 170),
        fromWitnessList: witnessListDoc,
        fromInterview: interviewDoc
      });
    }
  }

  let witnessStats = Array.from(witnessStatsByKey.values()).filter((stat) => {
    if (stat.role === 'defendant') return true;
    if (stat.fromWitnessList) return true;
    if (stat.fromInterview) return true;
    if (stat.transcriptIds.size >= 1) return true;
    return false;
  });

  witnessStats.sort((a, b) => {
    const scoreA =
      a.transcriptIds.size * 6 +
      a.exhibitIds.size * 3 +
      a.countNumbers.size * 5 +
      a.sourceFiles.size +
      (a.fromWitnessList ? 3 : 0) +
      (a.fromInterview ? 2 : 0) +
      (a.role === 'defendant' ? 3 : 0);
    const scoreB =
      b.transcriptIds.size * 6 +
      b.exhibitIds.size * 3 +
      b.countNumbers.size * 5 +
      b.sourceFiles.size +
      (b.fromWitnessList ? 3 : 0) +
      (b.fromInterview ? 2 : 0) +
      (b.role === 'defendant' ? 3 : 0);
    return scoreB - scoreA;
  });

  const witnessLimit = 900;
  const witnessNodesRaw = witnessStats.slice(0, witnessLimit).map((stat) => {
    const variants = Array.from(stat.variantCounts.entries())
      .sort((a, b) => {
        if (b[1] !== a[1]) return b[1] - a[1];
        const tokenDiff = b[0].split(' ').length - a[0].split(' ').length;
        if (tokenDiff !== 0) return tokenDiff;
        return b[0].length - a[0].length;
      })
      .map(([name]) => name);

    const canonicalName = variants[0] || 'Unknown Witness';
    const aliases = variants.slice(1, 6);
    const witnessId = `witness_${slugifyNodeToken(canonicalName, 'witness')}`;
    const countIds = Array.from(stat.countNumbers)
      .sort((a, b) => a - b)
      .map((countNumber) => `count_${countNumber}`)
      .filter((countId) => countIdSet.has(countId));

    const transcriptIds = Array.from(stat.transcriptIds).sort();
    const exhibitIds = Array.from(stat.exhibitIds).sort();
    const contexts = stat.contexts
      .filter((entry) => entry.excerpt)
      .sort((a, b) => {
        const rank = (sourceType) => {
          if (sourceType === 'transcript') return 0;
          if (sourceType === 'statement') return 1;
          if (sourceType === 'exhibit') return 2;
          return 3;
        };
        return rank(a.sourceType) - rank(b.sourceType);
      })
      .slice(0, 8);

    const testimonyExcerpts = contexts.map((entry) => entry.excerpt).slice(0, 3);
    const credibilitySignals = deriveWitnessCredibilitySignals(testimonyExcerpts);
    const strategicValueScore = roundTo(
      Math.min(
        1,
        transcriptIds.length * 0.14 +
          countIds.length * 0.24 +
          exhibitIds.length * 0.08 +
          (stat.role === 'defendant' ? 0.2 : 0)
      ),
      2
    );
    const impeachmentValueScore = roundTo(
      Math.min(1, credibilitySignals.impeachmentMaterial.length * 0.22 + (stat.role === 'defendant' ? 0.1 : 0)),
      2
    );
    const credibilityRiskScore = roundTo(
      Math.min(1, credibilitySignals.credibilityFlags.length * 0.2 + credibilitySignals.impeachmentMaterial.length * 0.12),
      2
    );

    return {
      node_id: witnessId,
      node_type: 'Witness',
      canonical_name: canonicalName,
      aliases,
      role: stat.role || null,
      overall_summary: '',
      appears_in: {
        indictment: stat.appearsInIndictment || indictmentText.toLowerCase().includes(canonicalName.toLowerCase()),
        counts: countIds,
        transcripts: transcriptIds,
        exhibits: exhibitIds,
        statements: [],
        affidavits: [],
        documents: []
      },
      testimony_text: testimonyExcerpts.join('\n\n'),
      testimony_summary:
        transcriptIds.length || exhibitIds.length || countIds.length
          ? `Referenced in ${transcriptIds.length} transcript(s), ${exhibitIds.length} exhibit(s), and linked to ${countIds.length} count(s).`
          : '',
      potential_testimony_summary: '',
      document_appearance_chart: [],
      linked_documents: [],
      statements: contexts.map((entry) => ({
        source_file: entry.sourceFile,
        source_type: entry.sourceType || '',
        source_node_id: '',
        role_in_document: '',
        involvement_summary: '',
        link: entry.sourceFile ? `[[${String(entry.sourceFile).replace(/\\/g, '/')}]]` : '',
        excerpt: entry.excerpt
      })),
      linked_witnesses: [],
      linked_entities: [],
      internal_inconsistencies: credibilitySignals.credibilityFlags.includes('inconsistent_statements')
        ? ['Potential inconsistency markers detected in source excerpts.']
        : [],
      cross_witness_conflicts: [],
      credibility_flags: credibilitySignals.credibilityFlags,
      impeachment_material: credibilitySignals.impeachmentMaterial,
      timeline_events: [],
      strategic_value_score: strategicValueScore,
      impeachment_value_score: impeachmentValueScore,
      credibility_risk_score: credibilityRiskScore,
      created_at: startedAt,
      last_updated: new Date().toISOString(),
      source_files: Array.from(stat.sourceFiles).sort(),
      bootstrap_version: BOOTSTRAP_SCHEMA_VERSION
    };
  });

  const witnessNodeById = new Map();
  const mergeUnique = (left = [], right = []) => Array.from(new Set([...(left || []), ...(right || [])]));
  for (const node of witnessNodesRaw) {
    if (!node || !node.node_id) continue;
    const existing = witnessNodeById.get(node.node_id);
    if (!existing) {
      witnessNodeById.set(node.node_id, node);
      continue;
    }

    existing.aliases = mergeUnique(existing.aliases, [node.canonical_name, ...(node.aliases || [])])
      .filter((alias) => alias && alias !== existing.canonical_name)
      .slice(0, 8);
    existing.source_files = mergeUnique(existing.source_files, node.source_files).slice(0, 120);
    existing.appears_in = {
      indictment: Boolean(existing.appears_in?.indictment || node.appears_in?.indictment),
      counts: mergeUnique(existing.appears_in?.counts, node.appears_in?.counts),
      transcripts: mergeUnique(existing.appears_in?.transcripts, node.appears_in?.transcripts),
      exhibits: mergeUnique(existing.appears_in?.exhibits, node.appears_in?.exhibits),
      statements: mergeUnique(existing.appears_in?.statements, node.appears_in?.statements),
      affidavits: mergeUnique(existing.appears_in?.affidavits, node.appears_in?.affidavits),
      documents: mergeUnique(existing.appears_in?.documents, node.appears_in?.documents)
    };
    const statementKey = (entry = {}) =>
      `${String(entry?.source_file || '').toLowerCase()}|${String(entry?.excerpt || '').slice(0, 120).toLowerCase()}`;
    const mergedStatements = [];
    const seenStatementKeys = new Set();
    for (const entry of [...(existing.statements || []), ...(node.statements || [])]) {
      const key = statementKey(entry);
      if (!key || seenStatementKeys.has(key)) continue;
      seenStatementKeys.add(key);
      mergedStatements.push(entry);
      if (mergedStatements.length >= 24) break;
    }
    existing.statements = mergedStatements;
    const mergeChartRows = [];
    const seenChartKeys = new Set();
    for (const row of [...(existing.document_appearance_chart || []), ...(node.document_appearance_chart || [])]) {
      const key = `${String(row?.document_path || '').toLowerCase()}|${String(row?.role_in_document || '').toLowerCase()}`;
      if (!key || seenChartKeys.has(key)) continue;
      seenChartKeys.add(key);
      mergeChartRows.push(row);
      if (mergeChartRows.length >= 80) break;
    }
    existing.document_appearance_chart = mergeChartRows;
    const mergeLinkedDocs = [];
    const seenLinkedDocKeys = new Set();
    for (const row of [...(existing.linked_documents || []), ...(node.linked_documents || [])]) {
      const key = `${String(row?.document_path || '').toLowerCase()}|${String(row?.source_node_id || '').toLowerCase()}`;
      if (!key || seenLinkedDocKeys.has(key)) continue;
      seenLinkedDocKeys.add(key);
      mergeLinkedDocs.push(row);
      if (mergeLinkedDocs.length >= 120) break;
    }
    existing.linked_documents = mergeLinkedDocs;
    if (!existing.overall_summary || String(existing.overall_summary || '').length < String(node.overall_summary || '').length) {
      existing.overall_summary = String(node.overall_summary || '');
    }
    if (
      !existing.potential_testimony_summary ||
      String(existing.potential_testimony_summary || '').length < String(node.potential_testimony_summary || '').length
    ) {
      existing.potential_testimony_summary = String(node.potential_testimony_summary || '');
    }
    existing.credibility_flags = mergeUnique(existing.credibility_flags, node.credibility_flags);
    existing.impeachment_material = mergeUnique(existing.impeachment_material, node.impeachment_material).slice(0, 10);
    existing.strategic_value_score = Math.max(Number(existing.strategic_value_score || 0), Number(node.strategic_value_score || 0));
    existing.impeachment_value_score = Math.max(Number(existing.impeachment_value_score || 0), Number(node.impeachment_value_score || 0));
    existing.credibility_risk_score = Math.max(Number(existing.credibility_risk_score || 0), Number(node.credibility_risk_score || 0));
    if (existing.testimony_text.length < node.testimony_text.length) {
      existing.testimony_text = node.testimony_text;
    }
  }
  const witnessNodes = Array.from(witnessNodeById.values());

  const witnessIdByNormalizedName = new Map();
  for (const witnessNode of witnessNodes) {
    const names = [witnessNode.canonical_name, ...(witnessNode.aliases || [])];
    for (const name of names) {
      const normalized = normalizePersonName(name).toLowerCase();
      if (normalized && !witnessIdByNormalizedName.has(normalized)) {
        witnessIdByNormalizedName.set(normalized, witnessNode.node_id);
      }
    }
  }
  const defendantWitnessIds = defendantNames
    .map((name) => {
      const normalized = normalizePersonName(name).toLowerCase();
      return witnessIdByNormalizedName.get(normalized) || '';
    })
    .filter(Boolean);

  const transcriptDataBySourcePath = new Map();
  const transcriptDataByNodeId = new Map();
  for (const entry of transcriptData) {
    const sourcePath = normalizeBootstrapSourcePath(entry?.doc?.relPath || '');
    if (sourcePath) transcriptDataBySourcePath.set(sourcePath, entry);
    if (entry?.node?.node_id) transcriptDataByNodeId.set(entry.node.node_id, entry);
  }
  const exhibitDataBySourcePath = new Map();
  const exhibitDataByNodeId = new Map();
  for (const entry of exhibitData) {
    const sourcePath = normalizeBootstrapSourcePath(entry?.doc?.relPath || '');
    if (sourcePath) exhibitDataBySourcePath.set(sourcePath, entry);
    if (entry?.node?.node_id) exhibitDataByNodeId.set(entry.node.node_id, entry);
  }

  const docCountIdsBySourcePath = new Map();
  for (const doc of docs) {
    const sourcePath = normalizeBootstrapSourcePath(doc.relPath);
    if (!sourcePath) continue;
    if (transcriptDataBySourcePath.has(sourcePath)) {
      docCountIdsBySourcePath.set(sourcePath, transcriptDataBySourcePath.get(sourcePath).linkedCountIds || []);
      continue;
    }
    if (exhibitDataBySourcePath.has(sourcePath)) {
      docCountIdsBySourcePath.set(sourcePath, exhibitDataBySourcePath.get(sourcePath).linkedCountIds || []);
      continue;
    }
    const inferredCountIds = extractCountReferencesFromText(doc.text || '', 20)
      .map((countNumber) => `count_${countNumber}`)
      .filter((countId) => countIdSet.has(countId));
    docCountIdsBySourcePath.set(sourcePath, inferredCountIds);
  }

  const witnessProfiles = witnessNodes.map((node) => buildWitnessSearchProfile(node)).filter(Boolean);
  const witnessProfileById = new Map(witnessProfiles.map((profile) => [profile.nodeId, profile]));
  const witnessProfilesByLastName = new Map();
  for (const profile of witnessProfiles) {
    for (const lastName of profile.lastNames || []) {
      if (!lastName) continue;
      if (!witnessProfilesByLastName.has(lastName)) witnessProfilesByLastName.set(lastName, []);
      witnessProfilesByLastName.get(lastName).push(profile);
    }
  }

  const witnessAppearanceByNodeId = new Map(witnessNodes.map((node) => [node.node_id, new Map()]));
  const pushWitnessAppearance = (witnessId, appearance = {}) => {
    const map = witnessAppearanceByNodeId.get(witnessId);
    if (!map) return;
    const documentPath = normalizeBootstrapSourcePath(appearance.document_path || '');
    if (!documentPath) return;
    const sourceNodeId = String(appearance.source_node_id || '').trim();
    const role = String(appearance.role_in_document || '').trim().toLowerCase();
    const key = `${documentPath}|${sourceNodeId}|${role}`;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        ...appearance,
        document_path: documentPath
      });
      return;
    }
    if (Number(appearance.confidence || 0) > Number(existing.confidence || 0)) {
      map.set(key, {
        ...existing,
        ...appearance,
        document_path: documentPath
      });
      return;
    }
    if (!existing.excerpt && appearance.excerpt) existing.excerpt = appearance.excerpt;
    if (!existing.involvement_summary && appearance.involvement_summary) existing.involvement_summary = appearance.involvement_summary;
    if (!existing.link && appearance.link) existing.link = appearance.link;
  };

  const collectWordSet = (text = '', maxTokens = 18000) => {
    const set = new Set();
    const source = String(text || '').toLowerCase();
    const regex = /[a-z]{3,}/g;
    let match = regex.exec(source);
    while (match) {
      set.add(match[0]);
      if (set.size >= maxTokens) break;
      match = regex.exec(source);
    }
    return set;
  };

  for (const doc of docs) {
    const sourcePath = normalizeBootstrapSourcePath(doc.relPath);
    const sourceText = String(doc.text || '');
    if (!sourceText.trim()) continue;
    const wordSet = collectWordSet(sourceText, 22000);
    if (!wordSet.size) continue;

    const candidateProfiles = new Set();
    for (const token of wordSet) {
      const profiles = witnessProfilesByLastName.get(token);
      if (!profiles) continue;
      for (const profile of profiles) candidateProfiles.add(profile);
    }
    if (!candidateProfiles.size) continue;

    for (const profile of candidateProfiles) {
      const mention = findWitnessMentionInDocument(sourceText, profile, 240);
      if (!mention) continue;
      const involvement = inferWitnessInvolvementFromDocument(doc, profile, mention);
      const transcriptEntry = transcriptDataBySourcePath.get(sourcePath) || null;
      const exhibitEntry = exhibitDataBySourcePath.get(sourcePath) || null;
      const sourceNodeId = transcriptEntry?.node?.node_id || exhibitEntry?.node?.node_id || '';
      const linkedCountIds = Array.from(
        new Set([
          ...(transcriptEntry?.linkedCountIds || []),
          ...(exhibitEntry?.linkedCountIds || []),
          ...(docCountIdsBySourcePath.get(sourcePath) || [])
        ])
      );
      pushWitnessAppearance(profile.nodeId, {
        document_path: doc.relPath,
        document_name: doc.fileName,
        document_type: involvement.documentType,
        source_node_id: sourceNodeId,
        role_in_document: involvement.role,
        involvement_summary: involvement.description,
        excerpt: mention.excerpt || '',
        linked_counts: linkedCountIds,
        link: `[[${String(doc.relPath || '').replace(/\\/g, '/')}]]`,
        confidence: roundTo(involvement.confidence, 2)
      });
    }
  }

  const fallbackWitnessSourcePaths = (witnessNode = {}) => {
    const paths = new Set();
    for (const sourcePath of witnessNode.source_files || []) {
      const normalized = normalizeBootstrapSourcePath(sourcePath);
      if (normalized) paths.add(normalized);
    }
    for (const row of witnessNode.statements || []) {
      const normalized = normalizeBootstrapSourcePath(row?.source_file || '');
      if (normalized) paths.add(normalized);
    }
    const transcriptIds = Array.isArray(witnessNode.appears_in?.transcripts) ? witnessNode.appears_in.transcripts : [];
    for (const transcriptId of transcriptIds) {
      const sourcePath = normalizeBootstrapSourcePath(transcriptDataByNodeId.get(transcriptId)?.doc?.relPath || '');
      if (sourcePath) paths.add(sourcePath);
    }
    const exhibitIds = Array.isArray(witnessNode.appears_in?.exhibits) ? witnessNode.appears_in.exhibits : [];
    for (const exhibitId of exhibitIds) {
      const sourcePath = normalizeBootstrapSourcePath(exhibitDataByNodeId.get(exhibitId)?.doc?.relPath || '');
      if (sourcePath) paths.add(sourcePath);
    }
    return Array.from(paths);
  };

  for (const witnessNode of witnessNodes) {
    const profile = witnessProfileById.get(witnessNode.node_id) || null;
    if (!profile) continue;
    for (const sourcePath of fallbackWitnessSourcePaths(witnessNode)) {
      const doc = docsBySourcePath.get(sourcePath);
      if (!doc) continue;
      const involvement = inferWitnessInvolvementFromDocument(doc, profile, { confidence: 0.52 });
      const transcriptEntry = transcriptDataBySourcePath.get(sourcePath) || null;
      const exhibitEntry = exhibitDataBySourcePath.get(sourcePath) || null;
      const sourceNodeId = transcriptEntry?.node?.node_id || exhibitEntry?.node?.node_id || '';
      const linkedCountIds = Array.from(
        new Set([
          ...(transcriptEntry?.linkedCountIds || []),
          ...(exhibitEntry?.linkedCountIds || []),
          ...(docCountIdsBySourcePath.get(sourcePath) || [])
        ])
      );
      pushWitnessAppearance(witnessNode.node_id, {
        document_path: doc.relPath,
        document_name: doc.fileName,
        document_type: involvement.documentType,
        source_node_id: sourceNodeId,
        role_in_document: involvement.role,
        involvement_summary: involvement.description,
        excerpt: '',
        linked_counts: linkedCountIds,
        link: `[[${String(doc.relPath || '').replace(/\\/g, '/')}]]`,
        confidence: roundTo(involvement.confidence, 2)
      });
    }
  }

  const witnessDocTypeRank = {
    transcript: 0,
    witness_list: 1,
    statement: 2,
    affidavit: 3,
    exhibit: 4,
    indictment: 5,
    document: 6
  };
  const dedupeStatementRows = (rows = [], limit = 28) => {
    const output = [];
    const seen = new Set();
    for (const row of rows) {
      const key = `${String(row?.source_file || '').toLowerCase()}|${String(row?.excerpt || '').slice(0, 120).toLowerCase()}`;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      output.push(row);
      if (output.length >= limit) break;
    }
    return output;
  };

  for (const witnessNode of witnessNodes) {
    const appearanceRows = Array.from(witnessAppearanceByNodeId.get(witnessNode.node_id)?.values() || [])
      .sort((a, b) => {
        const rankA = witnessDocTypeRank[String(a?.document_type || 'document')] ?? 99;
        const rankB = witnessDocTypeRank[String(b?.document_type || 'document')] ?? 99;
        if (rankA !== rankB) return rankA - rankB;
        const confidenceDelta = Number(b?.confidence || 0) - Number(a?.confidence || 0);
        if (Math.abs(confidenceDelta) > 0.0001) return confidenceDelta;
        return String(a?.document_path || '').localeCompare(String(b?.document_path || ''));
      })
      .slice(0, 120);

    const transcriptIds = new Set(Array.isArray(witnessNode.appears_in?.transcripts) ? witnessNode.appears_in.transcripts : []);
    const exhibitIds = new Set(Array.isArray(witnessNode.appears_in?.exhibits) ? witnessNode.appears_in.exhibits : []);
    const countIds = new Set(Array.isArray(witnessNode.appears_in?.counts) ? witnessNode.appears_in.counts : []);
    const statementPaths = new Set(Array.isArray(witnessNode.appears_in?.statements) ? witnessNode.appears_in.statements : []);
    const affidavitPaths = new Set(Array.isArray(witnessNode.appears_in?.affidavits) ? witnessNode.appears_in.affidavits : []);
    const documentPaths = new Set(Array.isArray(witnessNode.appears_in?.documents) ? witnessNode.appears_in.documents : []);

    for (const row of appearanceRows) {
      if (row?.source_node_id && String(row.source_node_id).startsWith('transcript_')) transcriptIds.add(row.source_node_id);
      if (row?.source_node_id && String(row.source_node_id).startsWith('exhibit_')) exhibitIds.add(row.source_node_id);
      for (const countId of row?.linked_counts || []) {
        if (countIdSet.has(countId)) countIds.add(countId);
      }
      const sourcePath = normalizeBootstrapSourcePath(row?.document_path || '');
      if (sourcePath) documentPaths.add(sourcePath);
      if (row?.document_type === 'statement' || row?.document_type === 'witness_list') {
        if (sourcePath) statementPaths.add(sourcePath);
      } else if (row?.document_type === 'affidavit') {
        if (sourcePath) affidavitPaths.add(sourcePath);
      }
    }

    witnessNode.appears_in = {
      indictment: Boolean(witnessNode.appears_in?.indictment),
      counts: Array.from(countIds).sort(),
      transcripts: Array.from(transcriptIds).sort(),
      exhibits: Array.from(exhibitIds).sort(),
      statements: Array.from(statementPaths).sort(),
      affidavits: Array.from(affidavitPaths).sort(),
      documents: Array.from(documentPaths).sort()
    };

    const normalizedChart = appearanceRows.map((row) => ({
      document_path: normalizeBootstrapSourcePath(row.document_path || ''),
      document_name: String(row.document_name || path.basename(String(row.document_path || ''))),
      document_type: String(row.document_type || 'document'),
      source_node_id: String(row.source_node_id || ''),
      role_in_document: String(row.role_in_document || ''),
      involvement_summary: String(row.involvement_summary || ''),
      excerpt: String(row.excerpt || ''),
      linked_counts: Array.from(new Set((row.linked_counts || []).filter((countId) => countIdSet.has(countId)))).sort(),
      link: String(row.link || ''),
      confidence: roundTo(Number(row.confidence || 0), 2)
    }));
    witnessNode.document_appearance_chart = normalizedChart;
    witnessNode.linked_documents = normalizedChart.map((row) => ({
      document_path: row.document_path,
      document_type: row.document_type,
      source_node_id: row.source_node_id || '',
      role_in_document: row.role_in_document,
      involvement_summary: row.involvement_summary,
      linked_counts: row.linked_counts,
      link: row.link
    }));

    const transcriptRows = normalizedChart.filter((row) => row.document_type === 'transcript');
    const statementLikeRows = normalizedChart.filter((row) =>
      row.document_type === 'statement' || row.document_type === 'affidavit' || row.document_type === 'witness_list'
    );
    const testimonyExcerpts = transcriptRows
      .map((row) => row.excerpt)
      .filter(Boolean)
      .slice(0, 4);
    const potentialSummaryPoints = Array.from(
      new Set(
        statementLikeRows
          .map((row) => row.involvement_summary)
          .filter(Boolean)
      )
    ).slice(0, 4);
    witnessNode.potential_testimony_summary = potentialSummaryPoints.join(' ');
    witnessNode.testimony_text = testimonyExcerpts.join('\n\n') || witnessNode.testimony_text || '';
    const highSignalRows = normalizedChart
      .map((row) => row.involvement_summary)
      .filter(Boolean)
      .slice(0, 3);
    const topLine = buildWitnessOverallSummary(witnessNode.appears_in, normalizedChart);
    witnessNode.overall_summary = topLine;
    witnessNode.testimony_summary = [topLine, ...highSignalRows].filter(Boolean).join(' ');

    const statementRowsFromChart = normalizedChart
      .map((row) => ({
        source_file: row.document_path,
        source_type: row.document_type,
        source_node_id: row.source_node_id || '',
        role_in_document: row.role_in_document,
        involvement_summary: row.involvement_summary,
        link: row.link,
        excerpt: row.excerpt
      }))
      .filter((row) => row.excerpt || row.involvement_summary);
    witnessNode.statements = dedupeStatementRows([...(witnessNode.statements || []), ...statementRowsFromChart], 30);
    witnessNode.last_updated = new Date().toISOString();
  }

  for (const entry of transcriptData) {
    const linkedWitnessNames = [];
    for (const rawName of entry.referencedPersons) {
      const normalized = normalizePersonName(rawName);
      const id = witnessIdByNormalizedName.get(normalized.toLowerCase());
      if (!id) continue;
      linkedWitnessNames.push(normalized);
    }
    entry.node.referenced_persons = Array.from(new Set(linkedWitnessNames)).slice(0, 120);
  }

  for (const entry of exhibitData) {
    const linkedWitnessIds = [];
    for (const rawName of entry.mentionedPersons) {
      const normalized = normalizePersonName(rawName);
      const witnessId = witnessIdByNormalizedName.get(normalized.toLowerCase());
      if (witnessId) linkedWitnessIds.push(witnessId);
    }
    entry.node.linked_witnesses = Array.from(new Set(linkedWitnessIds));

    const relevanceScore = Math.min(
      1,
      0.12 +
        (entry.node.linked_counts.length ? 0.35 : 0) +
        Math.min(0.25, entry.node.linked_witnesses.length * 0.06) +
        Math.min(0.2, entry.node.mentioned_entities.length * 0.05) +
        (/\bforfeiture\b|\bcontrolled substance\b|\bprescription\b/i.test(entry.node.summary || '') ? 0.1 : 0)
    );
    entry.node.relevance_score = roundTo(relevanceScore, 2);
  }

  const witnessNamesByCountId = new Map(countNodes.map((countNode) => [countNode.node_id, new Set()]));
  for (const witnessNode of witnessNodes) {
    const countIds = Array.isArray(witnessNode.appears_in?.counts) ? witnessNode.appears_in.counts : [];
    for (const countId of countIds) {
      if (!witnessNamesByCountId.has(countId)) continue;
      witnessNamesByCountId.get(countId).add(witnessNode.canonical_name);
    }
  }
  for (const countNode of countNodes) {
    const namesForCount = Array.from(witnessNamesByCountId.get(countNode.node_id) || []).sort();
    countNode.named_witnesses = namesForCount;
    countNode.elements_status.element_1.supporting_witnesses = namesForCount.slice(0, 20);
  }

  const relationships = [];
  const relationshipIds = new Set();
  const pushRelationship = (source, target, type, context = '', confidence = 0.7) => {
    if (!source || !target || !type) return;
    const idSeed = `${source}|${target}|${type}|${context.slice(0, 120)}`;
    const relationshipId = `rel_${crypto.createHash('sha1').update(idSeed).digest('hex').slice(0, 16)}`;
    if (relationshipIds.has(relationshipId)) return;
    relationshipIds.add(relationshipId);
    relationships.push({
      relationship_id: relationshipId,
      source_node: source,
      target_node: target,
      relationship_type: type,
      context_excerpt: context,
      confidence,
      created_at: new Date().toISOString()
    });
  };

  const normalizeSourcePath = normalizeBootstrapSourcePath;
  const transcriptIdsBySourcePath = new Map();
  const exhibitIdsBySourcePath = new Map();
  const registerNodeSourcePaths = (indexMap, nodeId, values = []) => {
    const entries = Array.isArray(values) ? values : [values];
    for (const value of entries) {
      const normalized = normalizeSourcePath(value);
      if (!normalized || !nodeId) continue;
      indexMap.set(normalized, nodeId);
      const base = path.basename(normalized).toLowerCase();
      if (base) indexMap.set(base, nodeId);
    }
  };
  for (const entry of transcriptData) {
    registerNodeSourcePaths(transcriptIdsBySourcePath, entry?.node?.node_id, [
      entry?.doc?.relPath,
      ...(entry?.node?.source_files || [])
    ]);
  }
  for (const entry of exhibitData) {
    registerNodeSourcePaths(exhibitIdsBySourcePath, entry?.node?.node_id, [
      entry?.doc?.relPath,
      ...(entry?.node?.source_files || []),
      entry?.node?.file_path || ''
    ]);
  }
  const transcriptLinkedCountsById = new Map(
    transcriptNodes.map((node) => [node.node_id, new Set(node.linked_counts || [])])
  );
  const exhibitLinkedCountsById = new Map(
    exhibitNodes.map((node) => [node.node_id, new Set(node.linked_counts || [])])
  );

  for (const countNode of countNodes) {
    pushRelationship('indictment_primary', countNode.node_id, 'charged_in', countNode.canonical_name, 0.95);
    if (supersedingIndictment) {
      pushRelationship('indictment_superseding', countNode.node_id, 'charged_in', countNode.canonical_name, 0.88);
    }
    for (const statute of countNode.statutes) {
      pushRelationship(countNode.node_id, `statute_${slugifyNodeToken(statute, 'statute')}`, 'relates_to_statute', statute, 0.85);
    }
  }

  for (const transcriptNode of transcriptNodes) {
    for (const countId of transcriptNode.linked_counts || []) {
      pushRelationship(transcriptNode.node_id, countId, 'relates_to_count', transcriptNode.canonical_name, 0.74);
    }
  }

  for (const exhibitNode of exhibitNodes) {
    for (const countId of exhibitNode.linked_counts || []) {
      pushRelationship(exhibitNode.node_id, countId, 'relates_to_count', exhibitNode.canonical_name, 0.72);
    }
    for (const witnessId of exhibitNode.linked_witnesses || []) {
      pushRelationship(exhibitNode.node_id, witnessId, 'mentioned', exhibitNode.canonical_name, 0.66);
    }
  }

  for (const witnessNode of witnessNodes) {
    const explicitCountIds = new Set();
    const inferredCountIds = new Set();
    for (const countId of witnessNode.appears_in?.counts || []) {
      pushRelationship(witnessNode.node_id, countId, 'testifies_about', witnessNode.canonical_name, 0.71);
      explicitCountIds.add(String(countId));
      inferredCountIds.add(String(countId));
    }
    for (const transcriptId of witnessNode.appears_in?.transcripts || []) {
      pushRelationship(witnessNode.node_id, transcriptId, 'references', witnessNode.canonical_name, 0.67);
      for (const countId of transcriptLinkedCountsById.get(transcriptId) || []) {
        inferredCountIds.add(String(countId));
      }
    }
    for (const exhibitId of witnessNode.appears_in?.exhibits || []) {
      pushRelationship(witnessNode.node_id, exhibitId, 'mentioned', witnessNode.canonical_name, 0.63);
      for (const countId of exhibitLinkedCountsById.get(exhibitId) || []) {
        inferredCountIds.add(String(countId));
      }
    }

    for (const sourceFileRaw of witnessNode.source_files || []) {
      const normalizedSource = normalizeSourcePath(sourceFileRaw);
      if (!normalizedSource) continue;

      const transcriptId =
        transcriptIdsBySourcePath.get(normalizedSource) ||
        transcriptIdsBySourcePath.get(path.basename(normalizedSource).toLowerCase()) ||
        '';
      if (transcriptId) {
        pushRelationship(witnessNode.node_id, transcriptId, 'references', witnessNode.canonical_name, 0.58);
        for (const countId of transcriptLinkedCountsById.get(transcriptId) || []) {
          inferredCountIds.add(String(countId));
        }
      }

      const exhibitId =
        exhibitIdsBySourcePath.get(normalizedSource) ||
        exhibitIdsBySourcePath.get(path.basename(normalizedSource).toLowerCase()) ||
        '';
      if (exhibitId) {
        pushRelationship(witnessNode.node_id, exhibitId, 'mentioned', witnessNode.canonical_name, 0.56);
        for (const countId of exhibitLinkedCountsById.get(exhibitId) || []) {
          inferredCountIds.add(String(countId));
        }
      }
    }

    if (!explicitCountIds.size && inferredCountIds.size) {
      for (const countId of inferredCountIds) {
        pushRelationship(witnessNode.node_id, countId, 'testifies_about', witnessNode.canonical_name, 0.57);
      }
    }
  }

  for (const attorneyNode of attorneyNodes) {
    for (const transcriptId of attorneyNode.appears_in?.transcripts || []) {
      pushRelationship(attorneyNode.node_id, transcriptId, 'references', attorneyNode.canonical_name, 0.64);
    }
    for (const countId of attorneyNode.appears_in?.counts || []) {
      pushRelationship(attorneyNode.node_id, countId, 'relates_to_count', attorneyNode.canonical_name, 0.58);
    }
    if (attorneyNode.side === 'defense') {
      for (const defendantWitnessId of defendantWitnessIds) {
        pushRelationship(defendantWitnessId, attorneyNode.node_id, 'represented_by', attorneyNode.canonical_name, 0.82);
      }
    }
  }

  const statutes = Array.from(
    new Set([
      ...extractStatutesFromText(indictmentText),
      ...countNodes.flatMap((node) => node.statutes || []),
      ...transcriptNodes.flatMap((node) => node.referenced_entities || []),
      ...exhibitNodes.flatMap((node) => node.mentioned_entities || [])
    ])
  );
  const statuteLinkedCounts = new Map();
  for (const countNode of countNodes) {
    for (const statute of countNode.statutes || []) {
      const key = normalizeStatuteCitation(statute);
      if (!statuteLinkedCounts.has(key)) statuteLinkedCounts.set(key, new Set());
      statuteLinkedCounts.get(key).add(countNode.node_id);
    }
  }

  const caseCaption = path.basename(caseRoot);
  const defenseCounselNames = attorneyNodes
    .filter((node) => node.side === 'defense')
    .map((node) => node.canonical_name);
  const prosecutionCounselNames = attorneyNodes
    .filter((node) => node.side === 'prosecution')
    .map((node) => node.canonical_name);
  const caseConfig = {
    case_id: slugifyNodeToken(caseCaption, 'case'),
    jurisdiction: /united states/i.test(caseCaption) ? 'United States' : '',
    court: '',
    judge: '',
    defendants: defendantNames,
    lead_defense_counsel: defenseCounselNames[0] || '',
    defense_counsel: defenseCounselNames,
    prosecution_counsel: prosecutionCounselNames,
    trial_status: isRefresh ? `bootstrapped_refresh_${mode}` : `bootstrapped_${mode}`,
    bootstrap_version: BOOTSTRAP_SCHEMA_VERSION,
    created_at: startedAt,
    last_updated: new Date().toISOString()
  };
  const ontologyIndex = {
    indictments: ['indictment_primary', 'indictment_superseding'],
    counts: countNodes.map((n) => n.node_id),
    witnesses: witnessNodes.map((n) => n.node_id),
    attorneys: attorneyNodes.map((n) => n.node_id),
    transcripts: transcriptNodes.map((n) => n.node_id),
    exhibits: exhibitNodes.map((n) => n.node_id),
    entities: [],
    relationships_total: relationships.length,
    last_updated: new Date().toISOString()
  };
  const personRegistry = new Map();
  const addPersonRegistryEntry = (node, entityType = 'person') => {
    if (!node || !node.canonical_name || !node.node_id) return;
    const key = String(node.canonical_name || '').replace(/[^\w]+/g, '_');
    const existing = personRegistry.get(key);
    if (!existing) {
      personRegistry.set(key, {
        canonical_name: node.canonical_name,
        aliases: Array.from(new Set(node.aliases || [])),
        entity_type: entityType,
        linked_nodes: [node.node_id],
        created_at: startedAt,
        last_updated: new Date().toISOString()
      });
      return;
    }
    existing.aliases = Array.from(new Set([...(existing.aliases || []), ...(node.aliases || [])]));
    existing.linked_nodes = Array.from(new Set([...(existing.linked_nodes || []), node.node_id]));
    if (entityType === 'attorney') existing.entity_type = 'attorney';
    existing.last_updated = new Date().toISOString();
  };
  for (const node of witnessNodes) addPersonRegistryEntry(node, 'person');
  for (const node of attorneyNodes) addPersonRegistryEntry(node, 'attorney');

  const entityRegistry = {
    persons: Object.fromEntries(personRegistry.entries()),
    attorneys: Object.fromEntries(
      attorneyNodes.map((node) => [
        node.canonical_name.replace(/[^\w]+/g, '_'),
        {
          canonical_name: node.canonical_name,
          aliases: node.aliases || [],
          side: node.side || null,
          represents: node.represents || [],
          linked_nodes: [node.node_id],
          created_at: startedAt,
          last_updated: new Date().toISOString()
        }
      ])
    ),
    organizations: {},
    corporations: {},
    government_agents: {},
    statutes: Object.fromEntries(
      statutes.map((statute) => [
        statute.replace(/[^\w]+/g, '_'),
        {
          canonical_name: statute,
          title: '',
          elements: [],
          linked_counts: Array.from(statuteLinkedCounts.get(normalizeStatuteCitation(statute)) || []).sort()
        }
      ])
    )
  };
  const primaryIndictmentDoc = primaryIndictment || indictmentForCounts || supersedingIndictment;
  const supersedingIndictmentDoc =
    supersedingIndictment ||
    (primaryIndictmentDoc && /\bsupersed/.test(String(primaryIndictmentDoc.lower || ''))
      ? primaryIndictmentDoc
      : null);
  const indictmentNamedPersons = Array.from(
    new Set([
      ...defendantNames,
      ...extractWitnessNamesFromText(indictmentText, 120)
    ])
  ).slice(0, 140);

  const indictmentPrimary = {
    node_id: 'indictment_primary',
    node_type: 'Indictment',
    canonical_name: 'Primary Indictment',
    superseding: false,
    version_number: 1,
    file_path: primaryIndictmentDoc ? primaryIndictmentDoc.relPath : '',
    full_text: String(primaryIndictmentDoc?.text || indictmentText).slice(0, 250000),
    counts_detected: countNodes.map((n) => n.count_number),
    defendants: defendantNames,
    statutes_cited: extractStatutesFromText(String(primaryIndictmentDoc?.text || indictmentText)),
    named_persons: indictmentNamedPersons,
    named_entities: statutes,
    overt_acts: [],
    date_filed: '',
    created_at: startedAt,
    last_updated: new Date().toISOString(),
    source_files: primaryIndictmentDoc ? [primaryIndictmentDoc.relPath] : [],
    bootstrap_version: BOOTSTRAP_SCHEMA_VERSION
  };
  const indictmentSuperseding = {
    node_id: 'indictment_superseding',
    node_type: 'Indictment',
    canonical_name: 'Superseding Indictment',
    superseding: true,
    overrides: 'indictment_primary',
    version_number: 2,
    file_path: supersedingIndictmentDoc ? supersedingIndictmentDoc.relPath : '',
    full_text: String(supersedingIndictmentDoc?.text || '').slice(0, 250000),
    counts_detected: countNodes.map((n) => n.count_number),
    defendants: defendantNames,
    statutes_cited: extractStatutesFromText(String(supersedingIndictmentDoc?.text || '')),
    named_persons: extractWitnessNamesFromText(String(supersedingIndictmentDoc?.text || ''), 80),
    named_entities: extractStatutesFromText(String(supersedingIndictmentDoc?.text || '')),
    overt_acts: [],
    date_filed: '',
    created_at: startedAt,
    last_updated: new Date().toISOString(),
    source_files: supersedingIndictmentDoc ? [supersedingIndictmentDoc.relPath] : [],
    bootstrap_version: BOOTSTRAP_SCHEMA_VERSION
  };
  const discoveryQueueItems = exhibitNodes.filter((node) => !Number.isFinite(node.relevance_score) || node.relevance_score < 0.55).length;
  const sourceIndexPayload = {
    version: 1,
    generated_at: new Date().toISOString(),
    mode,
    operation: isRefresh ? 'refresh' : 'bootstrap',
    documents: currentEntries.sort((a, b) => String(a.path || '').localeCompare(String(b.path || '')))
  };
  const refreshReportPayload = {
    timestamp: new Date().toISOString(),
    operation: isRefresh ? 'refresh' : 'bootstrap',
    mode,
    summary: refreshSummary,
    new_documents: newDocuments
      .map((entry) => ({
        path: entry.path,
        file_name: entry.file_name,
        document_type: entry.doc_type
      }))
      .slice(0, 1200),
    updated_documents: updatedDocuments
      .map((entry) => ({
        path: entry.path,
        file_name: entry.file_name,
        document_type: entry.doc_type
      }))
      .slice(0, 1200),
    removed_documents: removedDocuments
      .map((entry) => ({
        path: entry.path,
        file_name: entry.file_name,
        document_type: entry.doc_type
      }))
      .slice(0, 1200),
    analyzed_documents: analyzedDeltaDocuments
  };
  const bootstrapLog = [
    {
      timestamp: new Date().toISOString(),
      action: isRefresh ? 'bootstrap_refresh_completed' : 'bootstrap_completed',
      node_affected: 'casefile',
      details: `mode=${mode}; refresh=${isRefresh ? 'yes' : 'no'}; docs=${docs.length}; indictment=${indictmentForCounts?.relPath || 'none'}; counts=${countNodes.length}; witnesses=${witnessNodes.length}; attorneys=${attorneyNodes.length}; exhibits=${exhibitNodes.length}; new_docs=${refreshSummary.new_documents}; updated_docs=${refreshSummary.updated_documents}; removed_docs=${refreshSummary.removed_documents}`,
      confidence: 0.9
    }
  ];

  const bootstrapSchemaInfo = loadBootstrapSchemaPromptText();
  const writeBootstrapFile = (absPath, value) =>
    writeBootstrapJsonWithSchemaMarkdown(caseRoot, absPath, value, bootstrapSchemaInfo);

  writeBootstrapFile(path.join(metadataRoot, 'case_config.json'), caseConfig);
  writeBootstrapFile(path.join(metadataRoot, 'ontology_index.json'), ontologyIndex);
  writeBootstrapFile(path.join(metadataRoot, 'entity_registry.json'), entityRegistry);
  writeBootstrapFile(path.join(metadataRoot, 'case_timeline.json'), []);
  writeBootstrapFile(path.join(metadataRoot, 'bootstrap_log.json'), bootstrapLog);
  writeBootstrapFile(sourceIndexPath, sourceIndexPayload);
  writeBootstrapFile(refreshReportPath, refreshReportPayload);
  writeBootstrapFile(path.join(chargingRoot, 'indictment_primary.json'), indictmentPrimary);
  writeBootstrapFile(path.join(chargingRoot, 'indictment_superseding.json'), indictmentSuperseding);
  for (const node of countNodes) writeBootstrapFile(path.join(countsRoot, `${node.node_id}.json`), node);
  for (const node of witnessNodes) writeBootstrapFile(path.join(witnessesRoot, `${node.node_id}.json`), node);
  for (const node of transcriptNodes) writeBootstrapFile(path.join(transcriptsRoot, `${node.node_id}.json`), node);
  for (const node of exhibitNodes) writeBootstrapFile(path.join(exhibitsRoot, `${node.node_id}.json`), node);
  for (const node of attorneyNodes) writeBootstrapFile(path.join(attorneysRoot, `${node.node_id}.json`), node);
  writeBootstrapFile(path.join(graphRoot, 'relationships.json'), relationships);

  const workspaceNoteRel = path.join('Trial', 'Peregrine Startup Workspace.md').replace(/\\/g, '/');
  const workspaceNoteAbs = path.join(caseRoot, workspaceNoteRel);
  const promptNotes = ensurePeregrineBootstrapPromptNotes(caseRoot);
  const bootstrapPromptNoteRel = promptNotes.bootstrapPromptNoteRel;
  const bootstrapRefreshPromptNoteRel = promptNotes.bootstrapRefreshPromptNoteRel;
  fs.mkdirSync(path.dirname(workspaceNoteAbs), { recursive: true });
  fs.writeFileSync(
    workspaceNoteAbs,
    [
      '# Peregrine Startup Workspace',
      '',
      `- Case root: .`,
      `- Operation: ${isRefresh ? 'refresh' : 'bootstrap'}`,
      `- Mode: ${mode}`,
      `- Counts: ${countNodes.length}`,
      `- Witnesses: ${witnessNodes.length}`,
      `- Attorneys: ${attorneyNodes.length}`,
      `- Documents: ${docs.length}`,
      `- Discovery queue items: ${discoveryQueueItems}`,
      `- Delta new docs: ${refreshSummary.new_documents}`,
      `- Delta updated docs: ${refreshSummary.updated_documents}`,
      `- Delta removed docs: ${refreshSummary.removed_documents}`,
      `- Indictment source: ${indictmentForCounts?.relPath || 'not found'}`,
      `- Bootstrap prompt (root): [[${PEREGRINE_BOOTSTRAP_PROMPT_ROOT_REL}]]`,
      `- Bootstrap prompt: [[${bootstrapPromptNoteRel}]]`,
      `- Bootstrap refresh prompt (root): [[${PEREGRINE_BOOTSTRAP_REFRESH_PROMPT_ROOT_REL}]]`,
      `- Bootstrap refresh prompt: [[${bootstrapRefreshPromptNoteRel}]]`,
      `- Source index: [[Casefile/00_Metadata/bootstrap_source_index.json]]`,
      `- Refresh delta report: [[Casefile/00_Metadata/bootstrap_refresh_report.json]]`,
      ''
    ].join('\n'),
    'utf-8'
  );

  const schemaPromptPath = String(bootstrapSchemaInfo?.path || '').trim();

  logStartup(
    `[bootstrap] complete caseRoot=${caseRoot} operation=${isRefresh ? 'refresh' : 'bootstrap'} mode=${mode} counts=${countNodes.length} witnesses=${witnessNodes.length} attorneys=${attorneyNodes.length} documents=${docs.length} relationships=${relationships.length} new=${refreshSummary.new_documents} updated=${refreshSummary.updated_documents} removed=${refreshSummary.removed_documents}`
  );

  const warnings = [];
  if (!docs.length) warnings.push('No documents were extractable for bootstrap analysis.');
  if (!indictmentForCounts) warnings.push('No charging document was identified as an indictment.');
  if (!countNodes.length) warnings.push('No counts detected from indictment text.');
  if (!witnessNodes.length) warnings.push('No witness nodes were extracted from transcripts/exhibits/statements.');
  if (!attorneyNodes.length) warnings.push('No attorney nodes were extracted from counsel identifiers.');
  if (isRefresh && !refreshSummary.new_documents && !refreshSummary.updated_documents && !refreshSummary.removed_documents) {
    warnings.push('Bootstrap refresh found no source-document deltas compared to the prior source index.');
  }
  if (indictmentSelection.scoredCandidates.length && indictmentSelection.scoredCandidates[0].score < 120) {
    warnings.push('Indictment confidence score is low; verify charging document selection.');
  }

  return {
    ok: true,
    caseRoot,
    operation: isRefresh ? 'refresh' : 'bootstrap',
    mode,
    counts: countNodes.length,
    witnesses: witnessNodes.length,
    attorneys: attorneyNodes.length,
    documents: docs.length,
    discoveryQueueItems,
    newDocuments: refreshSummary.new_documents,
    updatedDocuments: refreshSummary.updated_documents,
    removedDocuments: refreshSummary.removed_documents,
    analyzedDeltaDocuments: refreshSummary.analyzed_documents,
    workspaceNote: workspaceNoteRel,
    bootstrapPromptRoot: PEREGRINE_BOOTSTRAP_PROMPT_ROOT_REL,
    bootstrapPromptNote: bootstrapPromptNoteRel,
    bootstrapRefreshPromptRoot: PEREGRINE_BOOTSTRAP_REFRESH_PROMPT_ROOT_REL,
    bootstrapRefreshPromptNote: bootstrapRefreshPromptNoteRel,
    schemaRoot: 'Casefile',
    ontologyIndexPath: 'Casefile/00_Metadata/ontology_index.json',
    relationshipsPath: 'Casefile/06_Link_Graph/relationships.json',
    sourceIndexPath: 'Casefile/00_Metadata/bootstrap_source_index.json',
    refreshReportPath: 'Casefile/00_Metadata/bootstrap_refresh_report.json',
    schemaPromptPath,
    resolutionNote: '',
    warnings
  };
}

function buildGraph(vaultRoot, limit = 1000) {
  const files = walkMarkdownFiles(vaultRoot, limit);
  const nodeSet = new Map();
  const basenameIndex = new Map();
  const edgeSet = new Set();
  const linkRegex = /\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]/g;

  const toNodeId = (relPath) =>
    relPath.replace(/\.(md|markdown|yaml|yml)$/i, '');

  for (const file of files) {
    const srcRel = toRel(vaultRoot, file);
    const srcId = toNodeId(srcRel);
    if (!nodeSet.has(srcId)) {
      nodeSet.set(srcId, { id: srcId, label: path.basename(srcId), path: srcRel });
    }
    const basenameKey = path.basename(srcId).toLowerCase();
    if (!basenameIndex.has(basenameKey)) basenameIndex.set(basenameKey, new Set());
    basenameIndex.get(basenameKey).add(srcId);
  }

  const resolveLinkedNodeId = (srcId, rawTarget) => {
    let target = String(rawTarget || '').trim();
    if (!target) return '';
    target = target.replace(/\\/g, '/').replace(/\.(md|markdown|yaml|yml)$/i, '');
    if (target.startsWith('/')) target = target.slice(1);
    if (!target) return '';

    if (target.includes('/')) {
      return path.posix.normalize(target);
    }

    const sourceDir = path.posix.dirname(srcId);
    const sameDirCandidate = path.posix.normalize(path.posix.join(sourceDir, target));
    if (nodeSet.has(sameDirCandidate)) return sameDirCandidate;

    if (nodeSet.has(target)) return target;
    const basenameMatches = basenameIndex.get(target.toLowerCase());
    if (basenameMatches && basenameMatches.size === 1) {
      return Array.from(basenameMatches)[0];
    }
    return target;
  };

  for (const file of files) {
    const srcRel = toRel(vaultRoot, file);
    const srcId = toNodeId(srcRel);
    if (!nodeSet.has(srcId)) nodeSet.set(srcId, { id: srcId, label: path.basename(srcId), path: srcRel });
    let text = '';
    try {
      text = fs.readFileSync(file, 'utf-8');
    } catch {
      continue;
    }
    linkRegex.lastIndex = 0;
    let m;
    while ((m = linkRegex.exec(text)) !== null) {
      const targetId = resolveLinkedNodeId(srcId, m[1]);
      if (!targetId) continue;
      if (!nodeSet.has(targetId)) nodeSet.set(targetId, { id: targetId, label: path.basename(targetId) });
      edgeSet.add(`${srcId}=>${targetId}`);
    }
  }

  const edges = Array.from(edgeSet).map((key) => {
    const [source, target] = key.split('=>');
    return { source, target };
  });

  return {
    nodes: Array.from(nodeSet.values()),
    edges,
    meta: {
      scannedFiles: files.length,
      truncated: files.length >= limit
    }
  };
}

function normalizeEnumSuffix(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (raw.includes('.')) return raw.split('.').pop().toLowerCase();
  return raw.toLowerCase();
}

function normalizeOriginatingCircuit(value) {
  const raw = String(value || '')
    .trim()
    .toLowerCase();
  if (!raw) return '';

  const compact = raw.replace(/[^a-z0-9]+/g, '');
  if (!compact) return '';
  if (ORIGINATING_CIRCUIT_CODES.has(compact)) return compact;
  if (compact === 'dc' || compact === 'dccircuit' || compact === 'districtofcolumbia') return 'cadc';

  if (/^ca(?:[1-9]|10|11)$/.test(compact)) return compact;
  if (/^(?:[1-9]|10|11)(?:st|nd|rd|th)?$/.test(compact)) {
    const match = compact.match(/^([1-9]|10|11)/);
    if (match) return `ca${match[1]}`;
  }
  if (compact.includes('districtofcolumbia')) return 'cadc';
  if (compact.includes('first')) return 'ca1';
  if (compact.includes('second')) return 'ca2';
  if (compact.includes('third')) return 'ca3';
  if (compact.includes('fourth')) return 'ca4';
  if (compact.includes('fifth')) return 'ca5';
  if (compact.includes('sixth')) return 'ca6';
  if (compact.includes('seventh')) return 'ca7';
  if (compact.includes('eighth')) return 'ca8';
  if (compact.includes('ninth')) return 'ca9';
  if (compact.includes('tenth')) return 'ca10';
  if (compact.includes('eleventh')) return 'ca11';

  const token = raw.replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ');
  if (token.includes('district of columbia')) return 'cadc';
  if (/\bfirst\b/.test(token)) return 'ca1';
  if (/\bsecond\b/.test(token)) return 'ca2';
  if (/\bthird\b/.test(token)) return 'ca3';
  if (/\bfourth\b/.test(token)) return 'ca4';
  if (/\bfifth\b/.test(token)) return 'ca5';
  if (/\bsixth\b/.test(token)) return 'ca6';
  if (/\bseventh\b/.test(token)) return 'ca7';
  if (/\beighth\b/.test(token)) return 'ca8';
  if (/\bninth\b/.test(token)) return 'ca9';
  if (/\btenth\b/.test(token)) return 'ca10';
  if (/\beleventh\b/.test(token)) return 'ca11';
  return '';
}

function originatingCircuitLabel(value) {
  const normalized = normalizeOriginatingCircuit(value);
  return ORIGINATING_CIRCUIT_LABELS[normalized] || '';
}

function parseYamlScalar(rawValue) {
  const value = String(rawValue || '').trim();
  if (!value) return '';

  const unquoted =
    (value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))
      ? value.slice(1, -1)
      : value;
  const compact = unquoted.trim();
  if (!compact) return '';
  if (compact.toLowerCase() === 'true') return true;
  if (compact.toLowerCase() === 'false') return false;
  if (compact.toLowerCase() === 'null') return null;
  if (/^-?\d+(?:\.\d+)?$/.test(compact)) {
    const parsed = Number(compact);
    if (!Number.isNaN(parsed)) return parsed;
  }
  if (compact.startsWith('[') && compact.endsWith(']')) {
    const inner = compact.slice(1, -1).trim();
    if (!inner) return [];
    return inner
      .split(',')
      .map((item) => parseYamlScalar(item))
      .filter((item) => item !== '');
  }
  return compact;
}

function splitFrontmatter(text) {
  const source = String(text || '');
  const lines = source.split(/\r?\n/);
  if (!lines.length || lines[0].trim() !== '---') {
    return { frontmatter: '', body: source };
  }
  let i = 1;
  const frontmatterLines = [];
  while (i < lines.length && lines[i].trim() !== '---') {
    frontmatterLines.push(lines[i]);
    i += 1;
  }
  if (i >= lines.length) {
    return { frontmatter: '', body: source };
  }
  return { frontmatter: frontmatterLines.join('\n'), body: lines.slice(i + 1).join('\n') };
}

function parseFrontmatterObject(text) {
  const { frontmatter, body } = splitFrontmatter(text);
  if (!frontmatter) return { data: {}, body };

  // Prefer a real YAML parser so nested arrays/maps (anchors, interpretive edges)
  // are preserved exactly; fall back to the legacy parser if unavailable.
  if (yaml && typeof yaml.load === 'function') {
    try {
      const parsed = yaml.load(frontmatter);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return { data: parsed, body };
      }
    } catch {
      // Fall through to legacy parser below.
    }
  }

  const data = {};
  const lines = frontmatter.split(/\r?\n/);
  let topKey = '';
  let nestedKey = '';
  let listObjectKey = '';

  for (const rawLine of lines) {
    if (!rawLine || !rawLine.trim() || rawLine.trim().startsWith('#')) continue;

    if (!rawLine.startsWith(' ')) {
      const idx = rawLine.indexOf(':');
      if (idx <= 0) {
        topKey = '';
        nestedKey = '';
        listObjectKey = '';
        continue;
      }
      const key = rawLine.slice(0, idx).trim();
      const valuePart = rawLine.slice(idx + 1).trim();
      if (!valuePart) {
        data[key] = data[key] ?? {};
        topKey = key;
        nestedKey = '';
        listObjectKey = '';
      } else {
        data[key] = parseYamlScalar(valuePart);
        topKey = '';
        nestedKey = '';
        listObjectKey = '';
      }
      continue;
    }

    if (!topKey) continue;

    const nestedListObjectMatch = rawLine.match(/^ {2}-\s+([A-Za-z0-9_.-]+):\s*(.*)$/);
    if (nestedListObjectMatch) {
      const listKey = topKey;
      if (!Array.isArray(data[listKey])) data[listKey] = [];
      const obj = {};
      obj[nestedListObjectMatch[1]] = parseYamlScalar(nestedListObjectMatch[2]);
      data[listKey].push(obj);
      listObjectKey = listKey;
      continue;
    }

    const nestedListMatch = rawLine.match(/^ {2}-\s+(.+)$/);
    if (nestedListMatch) {
      if (!Array.isArray(data[topKey])) data[topKey] = [];
      data[topKey].push(parseYamlScalar(nestedListMatch[1]));
      listObjectKey = '';
      continue;
    }

    const nestedSectionMatch = rawLine.match(/^ {2}([A-Za-z0-9_.-]+):\s*$/);
    if (nestedSectionMatch) {
      const key = nestedSectionMatch[1];
      if (typeof data[topKey] !== 'object' || data[topKey] === null || Array.isArray(data[topKey])) {
        data[topKey] = {};
      }
      data[topKey][key] = data[topKey][key] ?? [];
      nestedKey = key;
      listObjectKey = '';
      continue;
    }

    const nestedValueMatch = rawLine.match(/^ {2}([A-Za-z0-9_.-]+):\s*(.+)$/);
    if (nestedValueMatch) {
      const key = nestedValueMatch[1];
      if (typeof data[topKey] !== 'object' || data[topKey] === null || Array.isArray(data[topKey])) {
        data[topKey] = {};
      }
      data[topKey][key] = parseYamlScalar(nestedValueMatch[2]);
      nestedKey = '';
      listObjectKey = '';
      continue;
    }

    const deepListMatch = rawLine.match(/^ {4}-\s+(.+)$/);
    if (deepListMatch) {
      if (listObjectKey === topKey && Array.isArray(data[topKey]) && data[topKey].length) {
        const tail = data[topKey][data[topKey].length - 1];
        if (tail && typeof tail === 'object' && !Array.isArray(tail)) {
          tail._items = tail._items || [];
          tail._items.push(parseYamlScalar(deepListMatch[1]));
          continue;
        }
      }
      if (nestedKey && typeof data[topKey] === 'object' && data[topKey] !== null) {
        if (!Array.isArray(data[topKey][nestedKey])) data[topKey][nestedKey] = [];
        data[topKey][nestedKey].push(parseYamlScalar(deepListMatch[1]));
      }
      continue;
    }

    const deepValueMatch = rawLine.match(/^ {4}([A-Za-z0-9_.-]+):\s*(.+)$/);
    if (deepValueMatch) {
      if (listObjectKey === topKey && Array.isArray(data[topKey]) && data[topKey].length) {
        const tail = data[topKey][data[topKey].length - 1];
        if (tail && typeof tail === 'object' && !Array.isArray(tail)) {
          tail[deepValueMatch[1]] = parseYamlScalar(deepValueMatch[2]);
          continue;
        }
      }
      if (nestedKey && typeof data[topKey] === 'object' && data[topKey] !== null) {
        if (
          typeof data[topKey][nestedKey] !== 'object' ||
          data[topKey][nestedKey] === null ||
          Array.isArray(data[topKey][nestedKey])
        ) {
          data[topKey][nestedKey] = {};
        }
        data[topKey][nestedKey][deepValueMatch[1]] = parseYamlScalar(deepValueMatch[2]);
      }
    }
  }

  return { data, body };
}

function toNumberOrNull(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function pathIsDirectory(targetPath) {
  try {
    return fs.existsSync(targetPath) && fs.statSync(targetPath).isDirectory();
  } catch {
    return false;
  }
}

function looksLikeOntologyVaultRoot(candidate) {
  const abs = path.resolve(candidate || '');
  if (!pathIsDirectory(abs)) return false;
  return (
    pathIsDirectory(path.join(abs, 'holdings')) &&
    pathIsDirectory(path.join(abs, 'issues')) &&
    pathIsDirectory(path.join(abs, 'relations'))
  );
}

function discoverObsidianOntologyCandidates(vaultRoot) {
  const discovered = [];
  const docsRoots = new Set();
  const activeRoot = path.resolve(vaultRoot || '');
  const activeParent = activeRoot ? path.dirname(activeRoot) : '';
  if (activeParent && /iCloud~md~obsidian[\\/]Documents$/i.test(activeParent)) {
    docsRoots.add(activeParent);
  }

  const defaultDocsRoot = path.join(os.homedir(), 'Library', 'Mobile Documents', 'iCloud~md~obsidian', 'Documents');
  if (pathIsDirectory(defaultDocsRoot)) {
    docsRoots.add(defaultDocsRoot);
  }

  for (const docsRoot of docsRoots) {
    let entries = [];
    try {
      entries = fs.readdirSync(docsRoot, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (!entry?.isDirectory?.()) continue;
      const vaultDir = path.join(docsRoot, entry.name);
      discovered.push(path.join(vaultDir, 'Ontology', 'precedent_vault'));
      discovered.push(path.join(vaultDir, 'precedent_vault'));
    }
  }

  return discovered;
}

function resolveOntologyVaultRoot(vaultRoot) {
  const explicit = ONTOLOGY_VAULT_ENV ? path.resolve(ONTOLOGY_VAULT_ENV) : '';
  const activeVaultCandidates = [
    path.join(vaultRoot, 'Ontology', 'precedent_vault'),
    path.join(vaultRoot, 'precedent_vault'),
    vaultRoot
  ];
  const discoveredCandidates = discoverObsidianOntologyCandidates(vaultRoot);
  const candidates = [explicit, ...activeVaultCandidates, ...discoveredCandidates].filter(Boolean).map((entry) => path.resolve(entry));

  const unique = [];
  for (const candidate of candidates) {
    if (!unique.includes(candidate)) unique.push(candidate);
  }

  const activeCandidateSet = new Set(activeVaultCandidates.map((entry) => path.resolve(entry)));
  for (const candidate of unique) {
    if (looksLikeOntologyVaultRoot(candidate)) {
      const source =
        explicit && candidate === explicit
          ? 'env'
          : activeCandidateSet.has(candidate)
            ? 'active_vault'
            : 'obsidian_discovery';
      return {
        root: candidate,
        exists: true,
        inferred: candidate !== explicit,
        source,
        checkedCandidates: unique.length
      };
    }
  }

  return {
    root: unique[0] || path.join(vaultRoot, 'Ontology', 'precedent_vault'),
    exists: false,
    inferred: true,
    source: explicit ? 'env_missing' : 'not_found',
    checkedCandidates: unique.length
  };
}

function inferCourtLevelFromPathLike(value) {
  const raw = String(value || '').toLowerCase();
  if (!raw) return '';
  if (raw.includes('/scotus') || raw.includes('supreme')) return 'supreme';
  if (raw.includes('/circuit') || raw.includes('circuit') || /(^|[._/-])ca\d{1,2}([._/-]|$)/.test(raw)) return 'circuit';
  if (raw.includes('/district') || raw.includes('district')) return 'district';
  return '';
}

function sanitizeSingleLine(value, maxLen = 280) {
  const compact = String(value || '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!compact) return '';
  if (compact.length <= maxLen) return compact;
  return `${compact.slice(0, Math.max(0, maxLen - 1)).trimEnd()}…`;
}

function extractYearFromDate(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const direct = raw.match(/^(\d{4})/);
  if (direct) return direct[1];
  return '';
}

function looksLikeDocketNumber(value) {
  const token = String(value || '').trim();
  if (!token) return false;
  return /^\d{1,2}-\d{1,6}[a-z]*$/i.test(token);
}

function extractReporterCaseCitation(value) {
  const raw = sanitizeSingleLine(value, 220);
  if (!raw) return '';
  const usMatch = raw.match(/\b(\d+)\s*U\.?\s*S\.?\s*([0-9_]+)\b/i);
  if (usMatch) {
    return `${Number(usMatch[1])} U.S. ${usMatch[2]}`;
  }
  const sctMatch = raw.match(/\b(\d+)\s*S\.?\s*Ct\.?\s*([0-9_]+)\b/i);
  if (sctMatch) {
    return `${Number(sctMatch[1])} S. Ct. ${sctMatch[2]}`;
  }
  const ledMatch = raw.match(/\b(\d+)\s*L\.?\s*Ed\.?\s*2d\s*([0-9_]+)\b/i);
  if (ledMatch) {
    return `${Number(ledMatch[1])} L. Ed. 2d ${ledMatch[2]}`;
  }
  return '';
}

function normalizeCaseCitation(value) {
  const raw = sanitizeSingleLine(value, 140);
  if (!raw) return '';
  if (/^unknown citation$/i.test(raw)) return '';
  if (/citation unavailable|^unknown$/i.test(raw)) return '';
  if (looksLikeDocketNumber(raw)) return '';
  const reporter = extractReporterCaseCitation(raw);
  if (reporter) return reporter;
  return raw;
}

function normalizeCaseDomain(value) {
  const raw = String(value || '')
    .trim()
    .toLowerCase();
  if (!raw) return '';

  if (
    raw === 'criminal' ||
    raw === 'crim' ||
    raw === 'crime' ||
    raw === 'criminal_law' ||
    raw === 'criminal-law' ||
    raw.includes('criminal')
  ) {
    return 'criminal';
  }

  if (
    raw === 'civil' ||
    raw === 'civ' ||
    raw === 'civil_law' ||
    raw === 'civil-law' ||
    raw.includes('civil')
  ) {
    return 'civil';
  }

  return '';
}

function toBooleanOrNull(value) {
  if (value === true || value === false) return value;
  const raw = String(value || '')
    .trim()
    .toLowerCase();
  if (!raw) return null;
  if (['true', 'yes', 'y', '1'].includes(raw)) return true;
  if (['false', 'no', 'n', '0'].includes(raw)) return false;
  return null;
}

function keywordScore(text, keywords = []) {
  const haystack = String(text || '').toLowerCase();
  if (!haystack) return 0;
  let score = 0;
  for (const keyword of keywords) {
    const token = String(keyword || '').toLowerCase().trim();
    if (!token) continue;
    if (!haystack.includes(token)) continue;
    score += token.includes(' ') ? 2 : 1;
  }
  return score;
}

function inferCaseDomainFromInputs(input = {}) {
  const normalizedExplicitValues = [];
  const explicitCandidates = [
    input.caseDomain,
    input.caseType,
    input.domain,
    input.matterType,
    input.practiceArea
  ];
  for (const candidate of explicitCandidates) {
    if (Array.isArray(candidate)) {
      normalizedExplicitValues.push(...candidate);
    } else {
      normalizedExplicitValues.push(candidate);
    }
  }
  if (Array.isArray(input.tags)) normalizedExplicitValues.push(...input.tags);

  for (const candidate of normalizedExplicitValues) {
    const normalized = normalizeCaseDomain(candidate);
    if (normalized === 'criminal' || normalized === 'civil') return normalized;
  }

  const criminalFlag = toBooleanOrNull(
    input.isCriminalCase ?? input.criminalCase ?? input.isCriminal ?? input.criminal
  );
  if (criminalFlag === true) return 'criminal';
  const civilFlag = toBooleanOrNull(input.isCivilCase ?? input.civilCase ?? input.isCivil ?? input.civil);
  if (civilFlag === true) return 'civil';

  const ruleType = String(input.ruleType || '').toLowerCase();
  if (ruleType.includes('crim')) return 'criminal';
  if (ruleType.includes('civ')) return 'civil';

  const authorityAnchors = Array.isArray(input.authorityAnchors) ? input.authorityAnchors : [];
  let structuralCriminal = 0;
  let structuralCivil = 0;
  for (const anchor of authorityAnchors) {
    if (!anchor || typeof anchor !== 'object') continue;
    const sourceId = String(anchor.source_id || anchor.sourceId || '').toLowerCase();
    const normalizedText = String(anchor.normalized_text || anchor.normalizedText || '').toLowerCase();
    if (sourceId.includes('rule.federal.crim.') || normalizedText.includes('fed. r. crim. p.')) {
      structuralCriminal += 3;
    }
    if (sourceId.includes('rule.federal.civ.') || normalizedText.includes('fed. r. civ. p.')) {
      structuralCivil += 3;
    }
  }

  const title = String(input.title || '').trim();
  const pathLike = String(input.pathLike || '').trim();
  const summary = String(input.summary || '').trim();
  const holding = String(input.holding || '').trim();
  const bodyExcerpt = String(input.bodyExcerpt || '').slice(0, 16000);
  const combined = [pathLike, title, summary, holding, bodyExcerpt].filter(Boolean).join(' ').toLowerCase();
  if (!combined) return 'civil';

  let criminalScore = keywordScore(combined, CRIMINAL_CASE_KEYWORDS) + structuralCriminal;
  let civilScore = keywordScore(combined, CIVIL_CASE_KEYWORDS) + structuralCivil;

  const caption = title.toLowerCase();
  if (
    /^\s*(united states|people|commonwealth)\b.*\bv\.?\b/.test(caption) ||
    /\bv\.?\s*(united states|people|commonwealth)\b/.test(caption)
  ) {
    criminalScore += 3;
  }
  if (/\bv\.?\b/.test(caption)) {
    civilScore += 1;
  }
  if (/^\s*in re\b/.test(caption)) {
    civilScore += 1;
  }
  if (pathLike.toLowerCase().includes('/criminal/')) criminalScore += 2;
  if (pathLike.toLowerCase().includes('/civil/')) civilScore += 2;

  if (criminalScore > civilScore) return 'criminal';
  return 'civil';
}

function citationFromCaseFilename(filePath) {
  const base = path.basename(String(filePath || ''), path.extname(String(filePath || '')));
  if (!base) return '';
  const normalized = sanitizeSingleLine(base.replace(/\[[^\]]+\]/g, ' '), 260);
  if (!normalized || /unknown citation/i.test(normalized)) return '';
  return extractReporterCaseCitation(normalized);
}

function citationFromOpinionHeaderText(opinionText) {
  const header = String(opinionText || '').slice(0, 16000);
  if (!header) return '';
  const citeAsMatch = header.match(/\bCite\s+as:\s*([0-9_]+\s*U\.?\s*S\.?\s*[0-9_]+)/i);
  if (citeAsMatch) {
    const normalized = normalizeCaseCitation(citeAsMatch[1]);
    if (normalized) return normalized;
  }
  return '';
}

function buildCaseDisplayLabel(title, decisionDate, caseId) {
  const caseName = sanitizeSingleLine(title || caseId || 'Case', 140);
  const year = extractYearFromDate(decisionDate);
  return year ? `${caseName} (${year})` : caseName;
}

function looksLikeVsCaseCaption(value) {
  const compact = sanitizeSingleLine(value, 220);
  if (!compact) return false;
  return /\bv\.?\b/i.test(compact);
}

function extractFirstMarkdownHeading(body) {
  const lines = String(body || '').split(/\r?\n/);
  for (const line of lines) {
    const match = line.match(/^#\s+(.+?)\s*$/);
    if (match && match[1]) return sanitizeSingleLine(match[1], 220);
  }
  return '';
}

function caseNameFromCaseNoteFilename(filePath) {
  const base = path.basename(String(filePath || ''), path.extname(String(filePath || '')));
  if (!base) return '';
  let cleaned = base;
  cleaned = cleaned.replace(/\s*\[[^\]]+\]\s*/g, ' ');
  cleaned = cleaned.replace(/^(?:case\s+)+/i, '');
  cleaned = cleaned.replace(/,\s*unknown citation\s*\(\d{4}\).*$/i, '');
  cleaned = cleaned.replace(/,\s*\d+\s*U\.?\s*S\.?\s*[0-9_]+\s*\(\d{4}\).*$/i, '');
  cleaned = cleaned.replace(/\s{2,}/g, ' ');
  return sanitizeSingleLine(cleaned.trim(' ,.;'), 220);
}

function resolvePreferredCaseTitle(frontmatterTitle, headingTitle, filenameTitle, caseId) {
  const ordered = [frontmatterTitle, headingTitle, filenameTitle]
    .map((value) => sanitizeSingleLine(value, 220))
    .map((value) => value.replace(/^(?:case\s+)+/i, '').trim())
    .filter(Boolean);
  const captionCandidate = ordered.find((item) => looksLikeVsCaseCaption(item));
  if (captionCandidate) return captionCandidate;
  const nonDocket = ordered.find((item) => !looksLikeDocketNumber(item));
  return nonDocket || sanitizeSingleLine(caseId, 220);
}

function buildFallbackCaseSummary(title, decisionDate, caseCitation) {
  const caseName = sanitizeSingleLine(title || 'This case', 120);
  const year = extractYearFromDate(decisionDate);
  const yearPhrase = year ? ` (${year})` : '';
  if (caseCitation) {
    return `${caseName}${yearPhrase} at ${caseCitation}. Structured holdings are not yet extracted for this case.`;
  }
  return `${caseName}${yearPhrase}. Structured holdings are not yet extracted for this case.`;
}

function citationTokenFromText(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const match = raw.match(/\b(\d+)\s*U\.?\s*S\.?\s*([0-9_]+)\b/i);
  if (!match) return '';
  return `${Number(match[1])}us${String(match[2] || '').toLowerCase()}`;
}

function normalizeDocketKey(value) {
  let token = String(value || '').trim().toLowerCase();
  if (!token) return '';
  token = token.replace(/^scotus-/, '');
  token = token.replace(/\.(txt|pdf|xml|md)$/g, '');
  token = token.replace(/_/g, '-');
  token = token.replace(/[^a-z0-9-]/g, '');
  if (!token) return '';

  const withSuffix = token.match(/^(\d{1,2}-\d+)([a-z]+)$/);
  if (withSuffix) return withSuffix[1];
  if (/^\d{1,2}-\d+$/.test(token)) return token;
  const compactDigits = token.match(/^(\d{1,2})(\d{3,6})$/);
  if (compactDigits) return `${Number(compactDigits[1])}-${Number(compactDigits[2])}`;
  if (/^\d{1,2}[a-z]\d+$/.test(token)) return token;
  return '';
}

function extractDocketKeysFromValue(value) {
  const raw = String(value || '').trim();
  if (!raw) return [];
  const normalized = raw.replaceAll('\\', '/');
  const keys = new Set();

  for (const segment of normalized.split(/[\/\s]+/g)) {
    const key = normalizeDocketKey(segment);
    if (key) keys.add(key);
  }

  const scotusRegex = /SCOTUS-([0-9A-Za-z-]+)/gi;
  let match;
  while ((match = scotusRegex.exec(normalized)) !== null) {
    const key = normalizeDocketKey(match[1]);
    if (key) keys.add(key);
  }

  return Array.from(keys);
}

function looksLikeHoldingNodeId(value) {
  const token = String(value || '').trim().toLowerCase();
  if (!token) return false;
  return /^us\.scotus\.\d{4}\.[a-z0-9_]+\.h\d+$/.test(token) || /\.h\d+$/.test(token);
}

function buildOntologyFallbackFromVault(vaultRoot, ontologyInfo, limit = 10000, fallbackReason = 'ontology_vault_not_found') {
  const fallbackGraph = buildGraph(vaultRoot, limit);
  const nodesById = new Map();
  const edgeKeys = new Set();
  const edges = [];

  const ensureCaseNode = (id, seed = {}) => {
    const nodeId = String(id || '').trim();
    if (!nodeId) return null;
    const existing = nodesById.get(nodeId);
    if (existing) {
      for (const [key, value] of Object.entries(seed || {})) {
        if (value === undefined || value === null || value === '') continue;
        existing[key] = value;
      }
      return existing;
    }
    const guessedPath = String(seed.path || '').trim();
    const courtLevel = inferCourtLevelFromPathLike(`${nodeId} ${guessedPath}`);
    const caseDomain =
      normalizeCaseDomain(seed.caseDomain || '') ||
      inferCaseDomainFromInputs({
        caseDomain: seed.caseDomain,
        pathLike: `${nodeId} ${guessedPath}`,
        title: String(seed.label || ''),
        summary: String(seed.caseSummary || ''),
        holding: String(seed.essentialHolding || '')
      });
    const created = {
      id: nodeId,
      label: String(seed.label || path.basename(nodeId)).trim() || nodeId,
      nodeType: 'case',
      path: guessedPath,
      caseId: nodeId,
      courtLevel,
      caseDomain: caseDomain || 'civil'
    };
    nodesById.set(nodeId, created);
    return created;
  };

  for (const node of Array.isArray(fallbackGraph.nodes) ? fallbackGraph.nodes : []) {
    ensureCaseNode(node?.id, {
      label: node?.label,
      path: node?.path
    });
  }

  for (const edge of Array.isArray(fallbackGraph.edges) ? fallbackGraph.edges : []) {
    const source = String(edge?.source || '').trim();
    const target = String(edge?.target || '').trim();
    if (!source || !target) continue;
    ensureCaseNode(source);
    ensureCaseNode(target);
    const key = `${source}=>${target}`;
    if (edgeKeys.has(key)) continue;
    edgeKeys.add(key);
    edges.push({
      source,
      target,
      edgeType: 'precedent_relation',
      relationType: '',
      citationType: '',
      confidence: null
    });
  }

  const nodes = Array.from(nodesById.values()).map((node) => {
    const inferredDomain = inferCaseDomainFromInputs({
      caseDomain: node.caseDomain,
      pathLike: `${node.path || ''} ${node.id || ''}`,
      title: String(node.label || node.caseTitle || node.caseId || ''),
      summary: String(node.caseSummary || ''),
      holding: String(node.essentialHolding || '')
    });
    const caseDomain = inferredDomain || 'civil';
    const searchParts = [node.id, node.label, 'case', node.path, node.courtLevel, caseDomain]
      .filter(Boolean)
      .map((part) => String(part).toLowerCase());
    return {
      ...node,
      caseDomain,
      domain: node.domain || caseDomain,
      searchText: Array.from(new Set(searchParts)).join(' ')
    };
  });

  const edgeTypeCounts = edges.length ? { precedent_relation: edges.length } : {};
  const nodeTypeCounts = nodes.length ? { case: nodes.length } : {};
  const caseDomainCounts = {};
  for (const node of nodes) {
    const nodeType = String(node.nodeType || '').toLowerCase();
    if (nodeType !== 'case') continue;
    const domain = normalizeCaseDomain(node.caseDomain || '') || 'civil';
    caseDomainCounts[domain] = (caseDomainCounts[domain] || 0) + 1;
  }

  return {
    nodes,
    edges,
    meta: {
      ontologyRoot: ontologyInfo?.root || '',
      exists: Boolean(ontologyInfo?.exists),
      source: ontologyInfo?.source || '',
      checkedCandidates: ontologyInfo?.checkedCandidates || 0,
      scannedFiles: Number(fallbackGraph?.meta?.scannedFiles || 0),
      truncated: Boolean(fallbackGraph?.meta?.truncated),
      nodeTypeCounts,
      edgeTypeCounts,
      relationTypes: [],
      citationTypes: [],
      caseDomainCounts,
      originatingCircuitCounts: {},
      fallbackFromVault: true,
      fallbackReason
    }
  };
}

function resolveCasefileOntologyRoot(vaultRoot) {
  const candidates = [path.join(vaultRoot, 'Casefile'), vaultRoot];
  for (const candidate of candidates) {
    const metadataPath = path.join(candidate, '00_Metadata', 'ontology_index.json');
    const relationshipsPath = path.join(candidate, '06_Link_Graph', 'relationships.json');
    const hasMetadata = fs.existsSync(metadataPath);
    const hasRelationships = fs.existsSync(relationshipsPath);
    if (hasMetadata || hasRelationships) {
      return {
        exists: true,
        root: candidate,
        metadataPath,
        relationshipsPath
      };
    }
  }
  return {
    exists: false,
    root: '',
    metadataPath: '',
    relationshipsPath: ''
  };
}

function mapCasefileNodeType(rawNodeType = '', nodeId = '') {
  const raw = String(rawNodeType || '').trim().toLowerCase();
  if (raw === 'statute') return 'statute';
  if (raw === 'constitution') return 'constitution';
  if (raw === 'indictment') return 'indictment';
  if (raw === 'count') return 'count';
  if (raw === 'witness') return 'witness';
  if (raw === 'attorney') return 'attorney';
  if (raw === 'transcript') return 'transcript';
  if (raw === 'exhibit') return 'exhibit';
  const id = String(nodeId || '').trim().toLowerCase();
  if (id.startsWith('statute_')) return 'statute';
  if (id.startsWith('constitution_')) return 'constitution';
  if (id.startsWith('indictment_')) return 'indictment';
  if (id.startsWith('count_')) return 'count';
  if (id.startsWith('witness_')) return 'witness';
  if (id.startsWith('attorney_')) return 'attorney';
  if (id.startsWith('transcript_')) return 'transcript';
  if (id.startsWith('exhibit_')) return 'exhibit';
  return 'case';
}

function canonicalOntologyRelationTypeFromCasefileRelationship(rawType = '') {
  const normalized = String(rawType || '').trim().toLowerCase();
  if (!normalized) return '';
  if (
    normalized === 'charged_in' ||
    normalized === 'testifies_about' ||
    normalized === 'supports_element' ||
    normalized === 'references' ||
    normalized === 'mentioned' ||
    normalized === 'relates_to_count' ||
    normalized === 'relates_to_statute' ||
    normalized === 'part_of_scheme' ||
    normalized === 'authored' ||
    normalized === 'received' ||
    normalized === 'represented_by'
  ) {
    return 'applies';
  }
  if (normalized === 'contradicted_by' || normalized === 'impeached_by') return 'questions';
  if (normalized === 'fails_to_support_element') return 'limits';
  if (normalized === 'co_conspirator_with') return 'extends';
  return '';
}

function buildCasefileOntologyGraph(vaultRoot, limit = 10000) {
  const casefileInfo = resolveCasefileOntologyRoot(vaultRoot);
  if (!casefileInfo.exists) return null;

  const root = casefileInfo.root;
  const nodesById = new Map();
  const nodePayloadById = new Map();
  const edgesByKey = new Map();
  const relationTypeSet = new Set();
  const sourcePathToNodeIds = new Map();
  const sourceBasenameToNodeIds = new Map();
  const witnessIdByName = new Map();
  const attorneyIdByName = new Map();
  const nodeTypeCounts = {};
  const edgeTypeCounts = {};
  let scannedFiles = 0;

  const normalizeSourcePath = (value = '') =>
    String(value || '')
      .trim()
      .replaceAll('\\', '/')
      .replace(/^\.?\//, '');

  const makeGraphPath = (absPath) => {
    const relToVault = path.relative(vaultRoot, absPath).replaceAll('\\', '/');
    if (!relToVault.startsWith('..')) return relToVault;
    return path.relative(root, absPath).replaceAll('\\', '/');
  };

  const registerSourcePath = (rawPath, nodeId) => {
    const normalized = normalizeSourcePath(rawPath);
    if (!normalized || !nodeId) return;
    if (!sourcePathToNodeIds.has(normalized)) sourcePathToNodeIds.set(normalized, new Set());
    sourcePathToNodeIds.get(normalized).add(nodeId);
    const base = path.basename(normalized).toLowerCase();
    if (base) {
      if (!sourceBasenameToNodeIds.has(base)) sourceBasenameToNodeIds.set(base, new Set());
      sourceBasenameToNodeIds.get(base).add(nodeId);
    }
  };

  const lookupNodeIdsBySourcePath = (rawPath) => {
    const normalized = normalizeSourcePath(rawPath);
    if (!normalized) return [];
    const out = new Set();
    const direct = sourcePathToNodeIds.get(normalized);
    if (direct) {
      for (const value of direct) out.add(value);
    }
    const base = path.basename(normalized).toLowerCase();
    const byBase = sourceBasenameToNodeIds.get(base);
    if (byBase) {
      for (const value of byBase) out.add(value);
    }
    return Array.from(out);
  };

  const asStringArray = (value) => {
    if (!Array.isArray(value)) return [];
    const out = [];
    for (const item of value) {
      if (item === null || item === undefined) continue;
      if (typeof item === 'string' || typeof item === 'number') {
        const text = String(item).trim();
        if (text) out.push(text);
        continue;
      }
      if (typeof item === 'object') {
        const candidate = String(
          item.node_id ||
            item.id ||
            item.canonical_name ||
            item.name ||
            item.source_file ||
            item.file_path ||
            ''
        ).trim();
        if (candidate) out.push(candidate);
      }
    }
    return out;
  };

  const normalizeCountId = (value = '') => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    if (/^count_\d+$/i.test(raw)) return raw.toLowerCase();
    const directNumber = Number(raw);
    if (Number.isFinite(directNumber) && directNumber > 0) return `count_${Math.round(directNumber)}`;
    const embedded = raw.match(/count[_\s-]*([0-9]+)/i);
    if (embedded) return `count_${embedded[1]}`;
    return '';
  };

  const ensureNode = (id, seed = {}) => {
    const nodeId = String(id || '').trim();
    if (!nodeId) return null;
    if (nodesById.has(nodeId)) {
      const existing = nodesById.get(nodeId);
      for (const [key, value] of Object.entries(seed || {})) {
        if (value === undefined || value === null || value === '') continue;
        existing[key] = value;
      }
      return existing;
    }
    const nodeType = mapCasefileNodeType(seed.nodeType || '', nodeId);
    const created = {
      id: nodeId,
      label: seed.label || nodeId,
      nodeType,
      path: seed.path || '',
      caseDomain: seed.caseDomain || 'criminal',
      domain: seed.domain || 'criminal',
      courtLevel: seed.courtLevel || 'district',
      citationType: seed.citationType || 'background',
      caseImportance: Number(seed.caseImportance ?? 0.45),
      searchText: String(seed.searchText || `${seed.label || nodeId} ${nodeType}`).toLowerCase()
    };
    nodesById.set(nodeId, created);
    nodeTypeCounts[nodeType] = (nodeTypeCounts[nodeType] || 0) + 1;
    return created;
  };

  const addEdge = (source, target, attrs = {}) => {
    const src = String(source || '').trim();
    const dst = String(target || '').trim();
    if (!src || !dst) return;
    ensureNode(src, { label: src });
    ensureNode(dst, { label: dst });
    const edgeType = String(attrs.edgeType || 'relation_effect').trim().toLowerCase();
    const relationType = String(attrs.relationType || '').trim().toLowerCase();
    const key = `${src}=>${dst}=>${edgeType}=>${relationType}`;
    if (edgesByKey.has(key)) return;
    const edge = {
      source: src,
      target: dst,
      edgeType,
      relationType,
      confidence: Number.isFinite(Number(attrs.confidence)) ? Number(attrs.confidence) : null
    };
    edgesByKey.set(key, edge);
    edgeTypeCounts[edgeType] = (edgeTypeCounts[edgeType] || 0) + 1;
    if (relationType) relationTypeSet.add(relationType);
  };

  const nodeDirs = [
    path.join(root, '01_Charging_Documents'),
    path.join(root, '02_Counts'),
    path.join(root, '03_Witnesses'),
    path.join(root, '04_Transcripts'),
    path.join(root, '05_Exhibits'),
    path.join(root, '07_Attorneys')
  ];
  for (const dir of nodeDirs) {
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (!entry || !entry.isFile() || !entry.name.toLowerCase().endsWith('.json')) continue;
      const absPath = path.join(dir, entry.name);
      scannedFiles += 1;
      if (scannedFiles > limit) break;
      let parsed = null;
      try {
        parsed = JSON.parse(fs.readFileSync(absPath, 'utf-8'));
      } catch {
        continue;
      }
      if (!parsed || typeof parsed !== 'object') continue;
      const nodeId = String(parsed.node_id || parsed.id || '').trim();
      if (!nodeId) continue;
      nodePayloadById.set(nodeId, parsed);
      const label = String(parsed.canonical_name || parsed.name || nodeId).trim();
      const nodeType = mapCasefileNodeType(parsed.node_type || parsed.nodeType || '', nodeId);
      const searchText = [
        label,
        String(parsed.node_type || ''),
        String(parsed.full_text || '').slice(0, 800),
        String(parsed.summary || ''),
        String(parsed.overall_summary || ''),
        String(parsed.testimony_summary || ''),
        String(parsed.potential_testimony_summary || ''),
        Array.isArray(parsed.document_appearance_chart)
          ? parsed.document_appearance_chart
              .slice(0, 24)
              .map((entry) =>
                [
                  String(entry?.document_name || ''),
                  String(entry?.document_path || ''),
                  String(entry?.role_in_document || ''),
                  String(entry?.involvement_summary || '')
                ]
                  .filter(Boolean)
                  .join(' ')
              )
              .join(' ')
          : '',
        String(parsed.testimony_text || '').slice(0, 600)
      ]
        .join(' ')
        .toLowerCase();
      ensureNode(nodeId, {
        label,
        nodeType,
        path: makeGraphPath(absPath),
        searchText,
        caseImportance: nodeType === 'statute' ? 0.3 : 0.55
      });
      registerSourcePath(makeGraphPath(absPath), nodeId);
      for (const sourceFile of asStringArray(parsed.source_files)) {
        registerSourcePath(sourceFile, nodeId);
      }
      registerSourcePath(parsed.file_path, nodeId);

      if (nodeType === 'witness') {
        const names = [String(parsed.canonical_name || ''), ...asStringArray(parsed.aliases)];
        for (const rawName of names) {
          const normalized = normalizePersonName(rawName).toLowerCase();
          if (!normalized || witnessIdByName.has(normalized)) continue;
          witnessIdByName.set(normalized, nodeId);
        }
      }
      if (nodeType === 'attorney') {
        const names = [String(parsed.canonical_name || ''), ...asStringArray(parsed.aliases)];
        for (const rawName of names) {
          const normalized = normalizePersonName(rawName).toLowerCase();
          if (!normalized || attorneyIdByName.has(normalized)) continue;
          attorneyIdByName.set(normalized, nodeId);
        }
      }
    }
  }

  const entityRegistryPath = path.join(root, '00_Metadata', 'entity_registry.json');
  const entityRegistry = readJsonFileSafe(entityRegistryPath, {});
  const statutes = entityRegistry?.statutes && typeof entityRegistry.statutes === 'object' ? entityRegistry.statutes : {};
  for (const [key, value] of Object.entries(statutes)) {
    const canonicalName = String(value?.canonical_name || key || '').trim();
    if (!canonicalName) continue;
    const nodeId = `statute_${slugifyNodeToken(canonicalName, 'statute')}`;
    ensureNode(nodeId, {
      label: canonicalName,
      nodeType: 'statute',
      path: makeGraphPath(entityRegistryPath),
      searchText: `${canonicalName} statute`,
      caseImportance: 0.25
    });
  }

  const relationships = readJsonFileSafe(casefileInfo.relationshipsPath, []);
  for (const rel of Array.isArray(relationships) ? relationships : []) {
    if (!rel || typeof rel !== 'object') continue;
    const sourceNode = String(rel.source_node || rel.source || '').trim();
    const targetNode = String(rel.target_node || rel.target || '').trim();
    if (!sourceNode || !targetNode) continue;
    ensureNode(sourceNode, { label: sourceNode });
    ensureNode(targetNode, { label: targetNode });
    const canonicalRelationType = canonicalOntologyRelationTypeFromCasefileRelationship(
      rel.relationship_type || rel.relationType || ''
    );
    addEdge(sourceNode, targetNode, {
      edgeType: 'relation_effect',
      relationType: canonicalRelationType,
      confidence: rel.confidence
    });
  }

  const resolveWitnessNodeId = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    if (nodesById.has(raw)) return raw;
    const bySlug = `witness_${slugifyNodeToken(raw, 'witness')}`;
    if (nodesById.has(bySlug)) return bySlug;
    const normalized = normalizePersonName(raw).toLowerCase();
    if (!normalized) return '';
    return witnessIdByName.get(normalized) || '';
  };

  const resolveAttorneyNodeId = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    if (nodesById.has(raw)) return raw;
    const bySlug = `attorney_${slugifyNodeToken(raw, 'attorney')}`;
    if (nodesById.has(bySlug)) return bySlug;
    const normalized = normalizePersonName(raw).toLowerCase();
    if (!normalized) return '';
    return attorneyIdByName.get(normalized) || '';
  };

  const resolveNodeIdWithPrefix = (value, prefix = '') => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    if (nodesById.has(raw)) return raw;
    if (prefix === 'count') {
      const normalizedCountId = normalizeCountId(raw);
      if (normalizedCountId) return normalizedCountId;
      return '';
    }
    if (prefix === 'witness') {
      return resolveWitnessNodeId(raw);
    }
    if (prefix === 'attorney') {
      return resolveAttorneyNodeId(raw);
    }
    const normalizedPrefix = String(prefix || '').trim().toLowerCase();
    if (!normalizedPrefix) return raw;
    if (raw.toLowerCase().startsWith(`${normalizedPrefix}_`)) return raw.toLowerCase();
    return `${normalizedPrefix}_${slugifyNodeToken(raw, normalizedPrefix)}`;
  };

  const appendCountLinksFromNode = (nodeId, targetSet) => {
    if (!targetSet || !(targetSet instanceof Set)) return;
    const payload = nodePayloadById.get(String(nodeId || '').trim());
    if (!payload || typeof payload !== 'object') return;
    const countRefs = asStringArray(payload.linked_counts || payload.appears_in?.counts || []);
    for (const countRef of countRefs) {
      const countId = normalizeCountId(countRef);
      if (countId) targetSet.add(countId);
    }
  };

  for (const [nodeId, payload] of nodePayloadById.entries()) {
    const nodeType = mapCasefileNodeType(payload?.node_type || payload?.nodeType || '', nodeId);

    if (nodeType === 'indictment') {
      for (const countRef of asStringArray(payload.counts_detected || payload.counts || [])) {
        const countId = normalizeCountId(countRef);
        if (!countId) continue;
        addEdge(nodeId, countId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('charged_in'),
          confidence: 0.88
        });
      }
      for (const statuteRef of asStringArray(payload.statutes_cited)) {
        const statuteId = resolveNodeIdWithPrefix(statuteRef, 'statute');
        if (!statuteId) continue;
        ensureNode(statuteId, {
          label: statuteRef,
          nodeType: 'statute',
          caseImportance: 0.25,
          searchText: `${statuteRef} statute`
        });
        addEdge(nodeId, statuteId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('relates_to_statute'),
          confidence: 0.84
        });
      }
      continue;
    }

    if (nodeType === 'count') {
      for (const statuteRef of asStringArray(payload.statutes)) {
        const statuteId = resolveNodeIdWithPrefix(statuteRef, 'statute');
        if (!statuteId) continue;
        ensureNode(statuteId, {
          label: statuteRef,
          nodeType: 'statute',
          caseImportance: 0.25,
          searchText: `${statuteRef} statute`
        });
        addEdge(nodeId, statuteId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('relates_to_statute'),
          confidence: 0.84
        });
      }

      for (const transcriptRef of asStringArray(payload.linked_transcripts)) {
        const transcriptId = resolveNodeIdWithPrefix(transcriptRef, 'transcript');
        if (!transcriptId) continue;
        addEdge(transcriptId, nodeId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('relates_to_count'),
          confidence: 0.72
        });
      }
      for (const exhibitRef of asStringArray(payload.linked_exhibits)) {
        const exhibitId = resolveNodeIdWithPrefix(exhibitRef, 'exhibit');
        if (!exhibitId) continue;
        addEdge(exhibitId, nodeId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('relates_to_count'),
          confidence: 0.7
        });
      }
      for (const witnessRef of asStringArray(payload.named_witnesses)) {
        const witnessId = resolveWitnessNodeId(witnessRef);
        if (!witnessId) continue;
        addEdge(witnessId, nodeId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('testifies_about'),
          confidence: 0.69
        });
      }
      continue;
    }

    if (nodeType === 'transcript') {
      for (const countRef of asStringArray(payload.linked_counts)) {
        const countId = normalizeCountId(countRef);
        if (!countId) continue;
        addEdge(nodeId, countId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('relates_to_count'),
          confidence: 0.74
        });
      }
      for (const exhibitRef of asStringArray(payload.linked_exhibits)) {
        const exhibitId = resolveNodeIdWithPrefix(exhibitRef, 'exhibit');
        if (!exhibitId) continue;
        addEdge(nodeId, exhibitId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('references'),
          confidence: 0.63
        });
      }
      const witnessRefs = asStringArray(payload.referenced_persons);
      if (payload.witness_on_stand) witnessRefs.push(String(payload.witness_on_stand));
      for (const witnessRef of witnessRefs) {
        const witnessId = resolveWitnessNodeId(witnessRef);
        if (!witnessId) continue;
        addEdge(witnessId, nodeId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('references'),
          confidence: 0.66
        });
      }
      continue;
    }

    if (nodeType === 'exhibit') {
      for (const countRef of asStringArray(payload.linked_counts)) {
        const countId = normalizeCountId(countRef);
        if (!countId) continue;
        addEdge(nodeId, countId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('relates_to_count'),
          confidence: 0.72
        });
      }
      for (const witnessRef of asStringArray(payload.linked_witnesses)) {
        const witnessId = resolveWitnessNodeId(witnessRef) || resolveNodeIdWithPrefix(witnessRef, 'witness');
        if (!witnessId) continue;
        addEdge(nodeId, witnessId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('mentioned'),
          confidence: 0.66
        });
      }
      continue;
    }

    if (nodeType === 'attorney') {
      for (const countRef of asStringArray(payload.appears_in?.counts || payload.linked_counts || [])) {
        const countId = normalizeCountId(countRef);
        if (!countId) continue;
        addEdge(nodeId, countId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('relates_to_count'),
          confidence: 0.58
        });
      }
      for (const transcriptRef of asStringArray(payload.appears_in?.transcripts || [])) {
        const transcriptId = resolveNodeIdWithPrefix(transcriptRef, 'transcript');
        if (!transcriptId) continue;
        addEdge(nodeId, transcriptId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('references'),
          confidence: 0.62
        });
      }
      for (const representedRef of asStringArray(payload.represents || [])) {
        const witnessId = resolveWitnessNodeId(representedRef);
        if (!witnessId) continue;
        addEdge(witnessId, nodeId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('represented_by'),
          confidence: 0.79
        });
      }
      continue;
    }

    if (nodeType !== 'witness') continue;

    const inferredCountIds = new Set();
    const explicitCountIds = new Set();
    for (const countRef of asStringArray(payload.appears_in?.counts)) {
      const countId = normalizeCountId(countRef);
      if (!countId) continue;
      explicitCountIds.add(countId);
      inferredCountIds.add(countId);
      addEdge(nodeId, countId, {
        edgeType: 'relation_effect',
        relationType: canonicalOntologyRelationTypeFromCasefileRelationship('testifies_about'),
        confidence: 0.74
      });
    }

    for (const transcriptRef of asStringArray(payload.appears_in?.transcripts)) {
      const transcriptId = resolveNodeIdWithPrefix(transcriptRef, 'transcript');
      if (!transcriptId) continue;
      addEdge(nodeId, transcriptId, {
        edgeType: 'relation_effect',
        relationType: canonicalOntologyRelationTypeFromCasefileRelationship('references'),
        confidence: 0.68
      });
      appendCountLinksFromNode(transcriptId, inferredCountIds);
    }
    for (const exhibitRef of asStringArray(payload.appears_in?.exhibits)) {
      const exhibitId = resolveNodeIdWithPrefix(exhibitRef, 'exhibit');
      if (!exhibitId) continue;
      addEdge(nodeId, exhibitId, {
        edgeType: 'relation_effect',
        relationType: canonicalOntologyRelationTypeFromCasefileRelationship('mentioned'),
        confidence: 0.64
      });
      appendCountLinksFromNode(exhibitId, inferredCountIds);
    }

    const sourceFiles = new Set([
      ...asStringArray(payload.source_files),
      String(payload.file_path || '').trim()
    ]);
    for (const sourceFile of sourceFiles) {
      if (!sourceFile) continue;
      const relatedNodeIds = lookupNodeIdsBySourcePath(sourceFile);
      for (const relatedNodeId of relatedNodeIds) {
        if (!relatedNodeId || relatedNodeId === nodeId) continue;
        const relatedType = mapCasefileNodeType(
          nodePayloadById.get(relatedNodeId)?.node_type || nodePayloadById.get(relatedNodeId)?.nodeType || '',
          relatedNodeId
        );
        if (relatedType === 'transcript') {
          addEdge(nodeId, relatedNodeId, {
            edgeType: 'relation_effect',
            relationType: canonicalOntologyRelationTypeFromCasefileRelationship('references'),
            confidence: 0.58
          });
          appendCountLinksFromNode(relatedNodeId, inferredCountIds);
        } else if (relatedType === 'exhibit') {
          addEdge(nodeId, relatedNodeId, {
            edgeType: 'relation_effect',
            relationType: canonicalOntologyRelationTypeFromCasefileRelationship('mentioned'),
            confidence: 0.56
          });
          appendCountLinksFromNode(relatedNodeId, inferredCountIds);
        } else if (relatedType === 'count') {
          inferredCountIds.add(relatedNodeId);
        }
      }
    }

    if (!explicitCountIds.size && inferredCountIds.size) {
      for (const countId of inferredCountIds) {
        addEdge(nodeId, countId, {
          edgeType: 'relation_effect',
          relationType: canonicalOntologyRelationTypeFromCasefileRelationship('testifies_about'),
          confidence: 0.57
        });
      }
    }
  }

  const nodes = Array.from(nodesById.values());
  const edges = Array.from(edgesByKey.values());
  const caseDomainCounts = {
    criminal: nodes.filter((node) => !['statute', 'constitution'].includes(String(node?.nodeType || '').toLowerCase())).length
  };

  return {
    nodes,
    edges,
    meta: {
      ontologyRoot: root,
      exists: true,
      source: 'casefile_schema',
      checkedCandidates: 2,
      scannedFiles,
      truncated: false,
      nodeTypeCounts,
      edgeTypeCounts,
      relationTypes: Array.from(relationTypeSet).sort(),
      citationTypes: [],
      caseDomainCounts,
      originatingCircuitCounts: {},
      fallbackFromVault: false,
      fallbackReason: ''
    }
  };
}

function buildOntologyGraph(vaultRoot, limit = 10000) {
  const casefileGraph = buildCasefileOntologyGraph(vaultRoot, limit);
  if (casefileGraph) return casefileGraph;

  const ontologyInfo = resolveOntologyVaultRoot(vaultRoot);
  const ontologyRoot = ontologyInfo.root;
  if (!ontologyInfo.exists) {
    return buildOntologyFallbackFromVault(vaultRoot, ontologyInfo, limit, 'ontology_vault_not_found');
  }

  const nodesById = new Map();
  const edgesByKey = new Map();
  const relationTypeSet = new Set();
  const citationTypeSet = new Set();
  const caseAliasById = new Map();
  const localCaseIdSet = new Set();
  const caseCitationTokensById = new Map();
  const docketIndex = new Map();
  const caseSlugIndex = new Map();
  const pendingCaseCitationEdges = [];
  const pendingCaseAuthorityEdges = [];
  const pendingInterpretiveEdges = [];
  const interpretiveAuthorityCaseIndex = new Map();
  const interpretiveAuthorityTypeBySourceId = new Map();
  const authorityCaseIndex = new Map();
  const constitutionCaseIndex = new Map();
  const authorityFamilyBySourceId = new Map();
  const caseCitationClusterIndex = new Map();
  const caseAuthorityIdsByCase = new Map();
  const caseCitationLabelsByCase = new Map();
  const groupedAuthorityRefsByCase = new Map();
  const groupedAuthorityCaseIndex = new Map();
  const groupedAuthorityMetaByKey = new Map();

  const nodeTypeCounts = {};
  const edgeTypeCounts = {};
  let scannedFiles = 0;

  const makeGraphPath = (absPath) => {
    const rel = path.relative(vaultRoot, absPath).replaceAll('\\', '/');
    return rel.startsWith('..') ? '' : rel;
  };

  const rememberCaseAlias = (aliasId, canonicalCaseId) => {
    const alias = String(aliasId || '').trim();
    const canonical = String(canonicalCaseId || '').trim();
    if (!alias || !canonical || alias === canonical) return;
    if (!caseAliasById.has(alias)) caseAliasById.set(alias, canonical);
  };

  const registerCaseDocket = (decisionYear, docketKey, caseId) => {
    const year = String(decisionYear || '').trim();
    const docket = String(docketKey || '').trim();
    const canonicalCaseId = String(caseId || '').trim();
    if (!year || !docket || !canonicalCaseId) return;
    const key = `${year}:${docket}`;
    if (!docketIndex.has(key)) docketIndex.set(key, new Set());
    docketIndex.get(key).add(canonicalCaseId);
  };

  const registerCaseSlug = (decisionYear, slugTokenRaw, caseId) => {
    const year = String(decisionYear || '').trim();
    const slugToken = String(slugTokenRaw || '').trim().toLowerCase();
    const canonicalCaseId = String(caseId || '').trim();
    if (!year || !slugToken || !canonicalCaseId) return;
    const key = `${year}:${slugToken}`;
    if (!caseSlugIndex.has(key)) caseSlugIndex.set(key, new Set());
    caseSlugIndex.get(key).add(canonicalCaseId);
  };

  const normalizeCaseAliasToken = (value) =>
    String(value || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, '');

  const aliasTokenVariants = (value) => {
    const token = normalizeCaseAliasToken(value);
    if (!token) return [];
    const variants = new Set([token]);
    if (token.includes('_')) variants.add(token.replaceAll('_', '-'));
    if (token.includes('-')) variants.add(token.replaceAll('-', '_'));
    return Array.from(variants).filter(Boolean);
  };

  const registerCaseAliases = ({ caseId, decisionDate, caseCitation, opinionUrl, opinionPdfPath, filePath }) => {
    const canonicalCaseId = String(caseId || '').trim();
    if (!canonicalCaseId) return;
    caseAliasById.set(canonicalCaseId, canonicalCaseId);

    const decisionYear =
      extractYearFromDate(decisionDate) ||
      (String(canonicalCaseId).match(/^us\.scotus\.(\d{4})\./i)?.[1] || '');
    if (!decisionYear) return;

    const citationTokens = new Set();
    const citationToken = citationTokenFromText(caseCitation);
    if (citationToken) citationTokens.add(citationToken);
    const canonicalParts = canonicalCaseId.split('.');
    const canonicalSlug = normalizeCaseAliasToken(canonicalParts[3] || '');
    const canonicalTailToken = normalizeCaseAliasToken(canonicalParts[4] || '');
    if (canonicalTailToken) citationTokens.add(canonicalTailToken);
    caseCitationTokensById.set(canonicalCaseId, citationTokens);
    if (canonicalSlug) registerCaseSlug(decisionYear, canonicalSlug, canonicalCaseId);

    const docketKeys = new Set();
    for (const sourceValue of [opinionUrl, opinionPdfPath, filePath]) {
      for (const docketKey of extractDocketKeysFromValue(sourceValue)) {
        docketKeys.add(docketKey);
      }
    }
    const slugVariants = aliasTokenVariants(canonicalSlug);
    for (const docketKey of docketKeys) {
      registerCaseDocket(decisionYear, docketKey, canonicalCaseId);
      const docketVariants = aliasTokenVariants(docketKey).concat(aliasTokenVariants(String(docketKey).replaceAll('-', '')));
      for (const docketVariant of new Set(docketVariants)) {
        for (const slugVariant of slugVariants) {
          rememberCaseAlias(`us.scotus.${decisionYear}.${slugVariant}.${docketVariant}`, canonicalCaseId);
          rememberCaseAlias(`us.scotus.${decisionYear}.${docketVariant}.${slugVariant}`, canonicalCaseId);
        }
      }
      for (const citationValue of citationTokens) {
        const legacyAlias = `us.scotus.${decisionYear}.${docketKey.replaceAll('-', '_')}.${citationValue}`;
        rememberCaseAlias(legacyAlias, canonicalCaseId);
        for (const docketVariant of aliasTokenVariants(docketKey).concat(aliasTokenVariants(String(docketKey).replaceAll('-', '')))) {
          rememberCaseAlias(`us.scotus.${decisionYear}.${docketVariant}.${citationValue}`, canonicalCaseId);
          rememberCaseAlias(`us.scotus.${decisionYear}.${citationValue}.${docketVariant}`, canonicalCaseId);
        }
      }
    }
  };

  const resolveCaseAlias = (caseIdRaw) => {
    const raw = String(caseIdRaw || '').trim();
    if (!raw) return raw;
    const directAlias = caseAliasById.get(raw);
    if (directAlias) return directAlias;

    const match = raw.match(/^us\.scotus\.(\d{4})\.([a-z0-9_]+)\.([a-z0-9_]+)$/i);
    if (!match) return raw;
    const decisionYear = String(match[1] || '').trim();
    const segmentA = normalizeCaseAliasToken(match[2] || '');
    const segmentB = normalizeCaseAliasToken(match[3] || '');
    if (!decisionYear) return raw;

    const scoringForCandidate = (candidateCaseId, lookupToken = '', citationToken = '') => {
      let score = 0;
      const candidate = String(candidateCaseId || '').toLowerCase();
      if (lookupToken && candidate.includes(`.${lookupToken}.`)) score += 3;
      if (citationToken && candidate.includes(`.${citationToken}.`)) score += 2;
      const tokenSet = caseCitationTokensById.get(candidateCaseId);
      if (tokenSet && citationToken && tokenSet.has(citationToken)) score += 4;
      if (tokenSet && lookupToken && tokenSet.has(lookupToken)) score += 2;
      return score;
    };

    let resolved = '';
    let bestScore = -1;
    const docketCandidatesToTry = [];
    const docketA = normalizeDocketKey(segmentA);
    const docketB = normalizeDocketKey(segmentB);
    if (docketA) docketCandidatesToTry.push({ docketKey: docketA, lookupToken: segmentA, citationToken: segmentB });
    if (docketB) docketCandidatesToTry.push({ docketKey: docketB, lookupToken: segmentB, citationToken: segmentA });

    for (const item of docketCandidatesToTry) {
      const docketCandidates = docketIndex.get(`${decisionYear}:${item.docketKey}`);
      if (!docketCandidates || !docketCandidates.size) continue;
      for (const candidate of docketCandidates) {
        const score = scoringForCandidate(candidate, item.lookupToken, item.citationToken);
        if (score > bestScore || (score === bestScore && String(candidate).localeCompare(String(resolved)) < 0)) {
          bestScore = score;
          resolved = candidate;
        }
      }
    }

    if (!resolved) {
      const slugCandidates = new Set();
      const slugKeyA = `${decisionYear}:${segmentA}`;
      const slugKeyB = `${decisionYear}:${segmentB}`;
      for (const candidate of caseSlugIndex.get(slugKeyA) || []) slugCandidates.add(candidate);
      for (const candidate of caseSlugIndex.get(slugKeyB) || []) slugCandidates.add(candidate);
      for (const candidate of slugCandidates) {
        const score = scoringForCandidate(candidate, segmentA, segmentB);
        if (score > bestScore || (score === bestScore && String(candidate).localeCompare(String(resolved)) < 0)) {
          bestScore = score;
          resolved = candidate;
        }
      }
    }

    if (resolved) {
      rememberCaseAlias(raw, resolved);
      return resolved;
    }
    return raw;
  };

  const hasLocalCaseNode = (caseIdRaw) => {
    const raw = String(caseIdRaw || '').trim();
    if (!raw) return false;
    const canonical = resolveCaseAlias(raw);
    if (!canonical) return false;
    return localCaseIdSet.has(canonical);
  };

  const ensureNode = (id, seed = {}) => {
    const seedType = String(seed?.nodeType || '').toLowerCase();
    const rawId = String(id || '').trim();
    const nodeId = seedType === 'case' ? resolveCaseAlias(rawId) : rawId;
    if (!nodeId) return null;
    const existing = nodesById.get(nodeId);
    if (existing) {
      for (const [key, value] of Object.entries(seed || {})) {
        if (value === undefined || value === null || value === '') continue;
        if (Array.isArray(value) && value.length === 0) continue;
        existing[key] = value;
      }
      return existing;
    }
    const created = {
      id: nodeId,
      label: seed.label || path.basename(nodeId),
      nodeType: seed.nodeType || 'unknown',
      ...seed
    };
    nodesById.set(nodeId, created);
    return created;
  };

  const addEdge = (source, target, attrs = {}) => {
    const src = String(source || '').trim();
    const dst = String(target || '').trim();
    if (!src || !dst) return;
    const edgeType = attrs.edgeType || 'link';
    const relationType = normalizeEnumSuffix(attrs.relationType || '');
    const citationType = normalizeEnumSuffix(attrs.citationType || '');
    const key = `${src}=>${dst}=>${edgeType}=>${relationType}=>${citationType}`;
    if (!edgesByKey.has(key)) {
      edgesByKey.set(key, {
        source: src,
        target: dst,
        edgeType,
        ...attrs,
        relationType,
        citationType
      });
      edgeTypeCounts[edgeType] = (edgeTypeCounts[edgeType] || 0) + 1;
      if (relationType) relationTypeSet.add(relationType);
      if (citationType) citationTypeSet.add(citationType);
    }
  };

  const authorityFamilyPriority = {
    authority: 0,
    guideline: 1,
    regulation: 2,
    rule: 3,
    statute: 4,
    constitution: 5
  };

  const classifyAuthorityFamily = (sourceIdRaw, sourceTypeRaw = '') => {
    const sourceId = String(sourceIdRaw || '').trim().toLowerCase();
    const sourceType = normalizeEnumSuffix(sourceTypeRaw || '');
    if (!sourceId && !sourceType) return 'authority';

    if (sourceId.startsWith('constitution.') || sourceType === 'constitution' || sourceType === 'amendment') {
      return 'constitution';
    }

    if (
      sourceId.startsWith('statute.') ||
      sourceId.startsWith('public_law.') ||
      sourceId.startsWith('statutes_at_large.') ||
      sourceType === 'statute' ||
      sourceType === 'statutes_at_large' ||
      sourceType === 'public_law'
    ) {
      return 'statute';
    }

    if (
      sourceId.startsWith('reg.') ||
      sourceType === 'reg' ||
      sourceType === 'regulation' ||
      sourceType === 'cfr'
    ) {
      return 'regulation';
    }

    if (sourceId.startsWith('rule.') || sourceType === 'rule' || sourceType === 'federal_rule') {
      return 'rule';
    }

    if (sourceId.startsWith('guideline.') || sourceType === 'guideline' || sourceType === 'ussg') {
      return 'guideline';
    }

    return 'authority';
  };

  const rememberAuthorityFamily = (sourceIdRaw, sourceTypeRaw = '') => {
    const sourceId = String(sourceIdRaw || '').trim();
    if (!sourceId) return 'authority';
    const nextFamily = classifyAuthorityFamily(sourceId, sourceTypeRaw);
    const currentFamily = authorityFamilyBySourceId.get(sourceId) || '';
    if (
      !currentFamily ||
      (authorityFamilyPriority[nextFamily] || 0) > (authorityFamilyPriority[currentFamily] || 0)
    ) {
      authorityFamilyBySourceId.set(sourceId, nextFamily);
      return nextFamily;
    }
    return currentFamily;
  };

  const addCaseAuthorityReference = (caseIdRaw, sourceIdRaw) => {
    const caseId = resolveCaseAlias(caseIdRaw);
    const sourceId = String(sourceIdRaw || '').trim();
    if (!caseId || !sourceId) return;
    if (!caseAuthorityIdsByCase.has(caseId)) caseAuthorityIdsByCase.set(caseId, new Set());
    caseAuthorityIdsByCase.get(caseId).add(sourceId);
  };

  const addCaseCitationReference = (caseIdRaw, citationRaw) => {
    const caseId = resolveCaseAlias(caseIdRaw);
    const citationLabel = normalizeCaseCitation(String(citationRaw || '').trim());
    if (!caseId || !citationLabel) return;
    if (!caseCitationLabelsByCase.has(caseId)) caseCitationLabelsByCase.set(caseId, new Set());
    caseCitationLabelsByCase.get(caseId).add(citationLabel);
  };

  const authorityGroupInfo = (sourceIdRaw, authorityFamilyRaw = '', normalizedAuthorityRaw = '') => {
    const sourceId = String(sourceIdRaw || '').trim().toLowerCase();
    const authorityFamily = String(authorityFamilyRaw || '').trim().toLowerCase();
    if (!sourceId || !authorityFamily) return null;
    const tokens = sourceId.split('.').filter(Boolean);
    const first = tokens[0] || '';
    const second = tokens[1] || '';
    const third = tokens[2] || '';
    const fourth = tokens[3] || '';
    const fifth = tokens[4] || '';
    const compactToken = (value) =>
      String(value || '')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_]+/g, '');
    const sectionRootFrom = (value) => {
      const compact = compactToken(value);
      if (!compact) return '';
      return compact.split('_')[0] || compact;
    };
    const numericDisplay = (value) => {
      const compact = compactToken(value);
      return compact ? String(Number.isFinite(Number(compact)) ? Number(compact) : compact) : '';
    };
    const fallbackLabel =
      sanitizeSingleLine(String(normalizedAuthorityRaw || ''), 120) ||
      sanitizeSingleLine(sourceId, 120);

    if (authorityFamily === 'statute' && first === 'statute' && second === 'usc') {
      const title = compactToken(third);
      if (!title) return null;
      const sectionRoot = sectionRootFrom(fourth);
      if (sectionRoot) {
        return {
          family: 'statute',
          key: `statute.usc.${title}.${sectionRoot}`,
          label: `${numericDisplay(title)} U.S.C. § ${sectionRoot}`
        };
      }
      return {
        family: 'statute',
        key: `statute.usc.${title}`,
        label: `${numericDisplay(title)} U.S.C.`
      };
    }

    if (authorityFamily === 'statute' && first === 'statute' && second === 'statutes_at_large') {
      const volume = compactToken(third);
      if (!volume) {
        return {
          family: 'statute',
          key: 'statute.statutes_at_large',
          label: fallbackLabel
        };
      }
      return {
        family: 'statute',
        key: `statute.statutes_at_large.${volume}`,
        label: `${numericDisplay(volume)} Stat.`
      };
    }

    if (authorityFamily === 'statute' && first === 'statute' && second === 'public_law') {
      const plToken = compactToken(third).replaceAll('_', '-');
      if (!plToken) {
        return {
          family: 'statute',
          key: 'statute.public_law',
          label: fallbackLabel
        };
      }
      return {
        family: 'statute',
        key: `statute.public_law.${plToken}`,
        label: `Pub. L. No. ${plToken}`
      };
    }

    if (authorityFamily === 'regulation' && first === 'reg' && second === 'cfr') {
      const title = compactToken(third);
      if (!title) return null;
      const partRaw = fourth === 'pt' ? fifth : fourth;
      const partRoot = sectionRootFrom(partRaw);
      if (partRoot) {
        return {
          family: 'regulation',
          key: `reg.cfr.${title}.pt.${partRoot}`,
          label: `${numericDisplay(title)} C.F.R. pt. ${partRoot}`
        };
      }
      return {
        family: 'regulation',
        key: `reg.cfr.${title}`,
        label: `${numericDisplay(title)} C.F.R.`
      };
    }

    if (authorityFamily === 'regulation' && first === 'reg' && second === 'ussg') {
      const sectionRoot = sectionRootFrom(third);
      if (sectionRoot) {
        return {
          family: 'guideline',
          key: `guideline.ussg.${sectionRoot}`,
          label: `U.S.S.G. § ${sectionRoot}`
        };
      }
      return {
        family: 'guideline',
        key: 'guideline.ussg',
        label: 'U.S.S.G.'
      };
    }

    if (authorityFamily === 'guideline' && first === 'guideline' && second === 'ussg') {
      const sectionRoot = sectionRootFrom(third);
      if (sectionRoot) {
        return {
          family: 'guideline',
          key: `guideline.ussg.${sectionRoot}`,
          label: `U.S.S.G. § ${sectionRoot}`
        };
      }
      return {
        family: 'guideline',
        key: 'guideline.ussg',
        label: 'U.S.S.G.'
      };
    }

    if (authorityFamily === 'rule' && first === 'rule') {
      const namespace = compactToken(second);
      const ruleSet = compactToken(third);
      const number = sectionRootFrom(fourth);
      const key = `rule.${namespace || 'general'}.${ruleSet || 'general'}.${number || 'general'}`;
      const ruleSetLabelMap = {
        civ: 'Civ. P.',
        crim: 'Crim. P.',
        evid: 'Evid.',
        app: 'App. P.'
      };
      const namespaceLabel = namespace === 'fedr' ? 'Fed. R.' : String(namespace || 'Rule').toUpperCase();
      const ruleSetLabel = ruleSetLabelMap[ruleSet] || String(ruleSet || '').toUpperCase();
      const numberLabel = number ? ` ${number}` : '';
      const label = sanitizeSingleLine(`${namespaceLabel} ${ruleSetLabel}${numberLabel}`.trim(), 120) || fallbackLabel;
      return {
        family: 'rule',
        key,
        label
      };
    }

    if (authorityFamily === 'statute' || authorityFamily === 'regulation' || authorityFamily === 'rule' || authorityFamily === 'guideline') {
      const fallbackKey = tokens.slice(0, Math.min(tokens.length, 4)).join('.');
      return {
        family: authorityFamily,
        key: fallbackKey || `${authorityFamily}.other`,
        label: fallbackLabel
      };
    }

    return null;
  };

  const authorityTitleInfo = (sourceIdRaw, authorityFamilyRaw = '', normalizedAuthorityRaw = '') => {
    const sourceId = String(sourceIdRaw || '').trim().toLowerCase();
    const family = String(authorityFamilyRaw || '').trim().toLowerCase();
    if (!sourceId || !family) return null;
    const parts = sourceId.split('.').filter(Boolean);
    if (family === 'statute' && parts[0] === 'statute' && parts[1] === 'usc') {
      const title = String(parts[2] || '').trim();
      if (!title) return null;
      const titleLabel = Number.isFinite(Number(title)) ? Number(title) : title;
      return {
        nodeId: `statute.usc.${title}`,
        label: `${titleLabel} U.S.C.`,
        edgeType: 'usc_title_citation'
      };
    }
    if (family === 'regulation' && parts[0] === 'reg' && parts[1] === 'cfr') {
      const title = String(parts[2] || '').trim();
      if (!title) return null;
      const titleLabel = Number.isFinite(Number(title)) ? Number(title) : title;
      return {
        nodeId: `reg.cfr.${title}`,
        label: `${titleLabel} C.F.R.`,
        edgeType: 'cfr_title_citation'
      };
    }
    return null;
  };

  const registerGroupedAuthorityReference = (
    caseIdRaw,
    sourceIdRaw,
    authorityFamilyRaw = '',
    normalizedAuthorityRaw = '',
    confidenceRaw = null
  ) => {
    const caseId = resolveCaseAlias(caseIdRaw);
    const sourceId = String(sourceIdRaw || '').trim();
    const authorityFamily = String(authorityFamilyRaw || '').trim().toLowerCase();
    if (!caseId || !sourceId || !authorityFamily) return null;
    const grouped = authorityGroupInfo(sourceId, authorityFamily, normalizedAuthorityRaw);
    if (!grouped || !grouped.key) return null;

    if (!groupedAuthorityMetaByKey.has(grouped.key)) {
      groupedAuthorityMetaByKey.set(grouped.key, {
        family: grouped.family,
        label: grouped.label
      });
    }

    if (!groupedAuthorityCaseIndex.has(grouped.key)) groupedAuthorityCaseIndex.set(grouped.key, new Set());
    groupedAuthorityCaseIndex.get(grouped.key).add(caseId);

    if (!groupedAuthorityRefsByCase.has(caseId)) groupedAuthorityRefsByCase.set(caseId, new Map());
    const refMap = groupedAuthorityRefsByCase.get(caseId);
    const existing = refMap.get(grouped.key);
    const nextConfidence = toNumberOrNull(confidenceRaw);
    if (!existing) {
      refMap.set(grouped.key, {
        family: grouped.family,
        label: grouped.label,
        confidence: nextConfidence,
        count: 1
      });
    } else {
      existing.count = Number(existing.count || 0) + 1;
      if (!existing.label && grouped.label) existing.label = grouped.label;
      if (!existing.family && grouped.family) existing.family = grouped.family;
      if (Number.isFinite(nextConfidence)) {
        const currentConfidence = Number(existing.confidence);
        if (!Number.isFinite(currentConfidence) || nextConfidence > currentConfidence) {
          existing.confidence = nextConfidence;
        }
      }
    }
    return grouped;
  };

  const normalizeAuthorityToken = (value) =>
    String(value || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, '');

  const amendmentNumberByWord = new Map([
    ['first', 1],
    ['second', 2],
    ['third', 3],
    ['fourth', 4],
    ['fourt', 4],
    ['fifth', 5],
    ['sixth', 6],
    ['seventh', 7],
    ['eighth', 8],
    ['ninth', 9],
    ['tenth', 10],
    ['eleventh', 11],
    ['twelfth', 12],
    ['thirteenth', 13],
    ['fourteenth', 14],
    ['fifteenth', 15],
    ['sixteenth', 16],
    ['seventeenth', 17],
    ['eighteenth', 18],
    ['nineteenth', 19],
    ['twentieth', 20],
    ['twentyfirst', 21],
    ['twentysecond', 22],
    ['twentythird', 23],
    ['twentyfourth', 24],
    ['twentyfifth', 25],
    ['twentysixth', 26],
    ['twentyseventh', 27]
  ]);

  const ordinalWordPattern =
    'first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|twenty(?:-|\\s*)first|twenty(?:-|\\s*)second|twenty(?:-|\\s*)third|twenty(?:-|\\s*)fourth|twenty(?:-|\\s*)fifth|twenty(?:-|\\s*)sixth|twenty(?:-|\\s*)seventh';

  const parseRomanNumeral = (valueRaw) => {
    const value = String(valueRaw || '').trim().toUpperCase();
    if (!value || !/^[IVXLCDM]+$/.test(value)) return null;
    const map = { I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000 };
    let total = 0;
    for (let idx = 0; idx < value.length; idx += 1) {
      const current = map[value[idx]] || 0;
      const next = map[value[idx + 1]] || 0;
      total += current < next ? -current : current;
    }
    return total > 0 ? total : null;
  };

  const toRomanNumeral = (valueRaw) => {
    let value = Number(valueRaw);
    if (!Number.isFinite(value) || value <= 0 || value >= 4000) return '';
    value = Math.floor(value);
    const pairs = [
      [1000, 'M'],
      [900, 'CM'],
      [500, 'D'],
      [400, 'CD'],
      [100, 'C'],
      [90, 'XC'],
      [50, 'L'],
      [40, 'XL'],
      [10, 'X'],
      [9, 'IX'],
      [5, 'V'],
      [4, 'IV'],
      [1, 'I']
    ];
    let out = '';
    for (const [numeric, roman] of pairs) {
      while (value >= numeric) {
        out += roman;
        value -= numeric;
      }
      if (!value) break;
    }
    return out;
  };

  const parseAmendmentTokenToNumber = (tokenRaw) => {
    const token = String(tokenRaw || '')
      .trim()
      .toLowerCase()
      .replace(/[.,;:()]/g, '')
      .replace(/-/g, '')
      .replace(/\s+/g, '');
    if (!token) return null;
    const numeric = token.match(/^(\d{1,2})(?:st|nd|rd|th)?$/i);
    if (numeric) return Number.parseInt(numeric[1], 10);
    if (amendmentNumberByWord.has(token)) return amendmentNumberByWord.get(token);
    const roman = parseRomanNumeral(token);
    if (roman !== null) return roman;
    return null;
  };

  const canonicalConstitutionSourceId = (sourceIdRaw = '') => {
    const sourceId = String(sourceIdRaw || '').trim();
    if (!sourceId) return '';
    const lower = sourceId.toLowerCase();
    const match = lower.match(/^constitution\.us\.amendment\.([a-z0-9_-]+)$/i);
    if (!match) return sourceId;
    const number = parseAmendmentTokenToNumber(match[1]);
    if (!Number.isFinite(number) || number < 1 || number > 27) return sourceId;
    return `constitution.us.amendment.${number}`;
  };

  const constitutionLabelFromSourceId = (sourceIdRaw = '') => {
    const sourceId = canonicalConstitutionSourceId(sourceIdRaw);
    const match = sourceId.match(/^constitution\.us\.amendment\.(\d{1,2})$/i);
    if (!match) return sourceId || 'U.S. Const. amend.';
    const number = Number.parseInt(match[1], 10);
    const roman = toRomanNumeral(number);
    return roman ? `U.S. Const. amend. ${roman}` : `U.S. Const. amend. ${number}`;
  };

  const extractConstitutionSourceIdsFromText = (textRaw = '') => {
    const text = String(textRaw || '');
    if (!text) return [];
    const sourceIds = new Set();
    const addToken = (tokenRaw) => {
      const number = parseAmendmentTokenToNumber(tokenRaw);
      if (!Number.isFinite(number) || number < 1 || number > 27) return;
      sourceIds.add(`constitution.us.amendment.${number}`);
    };

    const explicitConstRegex = new RegExp(
      `\\b(?:u\\.?\\s*s\\.?\\s*const\\.?|const\\.?)\\s*,?\\s*(?:amend(?:ment)?s?\\.?)\\s*(${ordinalWordPattern}|\\d{1,2}(?:st|nd|rd|th)?|[ivxlcdm]+)\\b`,
      'gi'
    );
    for (const match of text.matchAll(explicitConstRegex)) {
      addToken(match[1] || '');
    }

    const amendmentSuffixRegex = new RegExp(
      `\\b(${ordinalWordPattern}|\\d{1,2}(?:st|nd|rd|th)?|[ivxlcdm]+)\\s+amendments?\\b`,
      'gi'
    );
    for (const match of text.matchAll(amendmentSuffixRegex)) {
      addToken(match[1] || '');
    }

    const amendmentPrefixRegex = new RegExp(
      `\\bamend(?:ment)?s?\\.?\\s*(${ordinalWordPattern}|\\d{1,2}(?:st|nd|rd|th)?|[ivxlcdm]+)\\b`,
      'gi'
    );
    for (const match of text.matchAll(amendmentPrefixRegex)) {
      addToken(match[1] || '');
    }

    return Array.from(sourceIds).sort((a, b) => a.localeCompare(b));
  };

  const tokenCore = (value) => {
    const token = normalizeAuthorityToken(value);
    if (!token) return '';
    const head = token.split('_')[0];
    return head || token;
  };

  const deriveAuthoritySharedKeys = (sourceIdRaw, familyRaw = '') => {
    const sourceId = String(sourceIdRaw || '').trim().toLowerCase();
    if (!sourceId) return [];
    const family = String(familyRaw || '').trim() || classifyAuthorityFamily(sourceId, '');
    const parts = sourceId.split('.').map((part) => String(part || '').trim()).filter(Boolean);
    const keys = new Set();

    if (family === 'statute' && parts[0] === 'statute' && parts[1] === 'usc') {
      const title = normalizeAuthorityToken(parts[2] || '');
      const section = tokenCore(parts[3] || '');
      if (title && section) keys.add(`statute.usc.${title}.${section}`);
    } else if (family === 'regulation' && parts[0] === 'reg' && parts[1] === 'cfr') {
      const title = normalizeAuthorityToken(parts[2] || '');
      const section = tokenCore(parts[3] || '');
      if (title && section) keys.add(`reg.cfr.${title}.${section}`);
    } else if (family === 'rule' && parts[0] === 'rule') {
      const namespace = normalizeAuthorityToken(parts[1] || 'federal') || 'federal';
      const ruleSet = normalizeAuthorityToken(parts[2] || 'unknown') || 'unknown';
      const ruleNumber = tokenCore(parts[3] || '');
      if (namespace && ruleSet && ruleNumber) keys.add(`rule.${namespace}.${ruleSet}.${ruleNumber}`);
    } else if (family === 'guideline' && parts[0] === 'guideline' && parts[1] === 'ussg') {
      const section = tokenCore(parts[2] || '');
      if (section) keys.add(`guideline.ussg.${section}`);
    }

    return Array.from(keys).filter((key) => key && key !== sourceId);
  };

  const registerAuthorityForCase = (caseIdRaw, sourceIdRaw, sourceTypeRaw = '', includeDerived = true) => {
    const caseId = resolveCaseAlias(caseIdRaw);
    const sourceId = String(sourceIdRaw || '').trim();
    if (!caseId || !sourceId) {
      return { caseId: '', sourceId: '', authorityFamily: 'authority', sharedKeys: [] };
    }

    const authorityFamily = rememberAuthorityFamily(sourceId, sourceTypeRaw || '');
    const sharedKeys = new Set([sourceId]);

    if (includeDerived) {
      for (const derivedSourceId of deriveAuthoritySharedKeys(sourceId, authorityFamily)) {
        sharedKeys.add(derivedSourceId);
        rememberAuthorityFamily(derivedSourceId, authorityFamily);
      }
    }

    if (!caseAuthorityIdsByCase.has(caseId)) caseAuthorityIdsByCase.set(caseId, new Set());
    const authorityRefs = caseAuthorityIdsByCase.get(caseId);

    for (const key of sharedKeys) {
      authorityRefs.add(key);
      if (!authorityCaseIndex.has(key)) authorityCaseIndex.set(key, new Set());
      authorityCaseIndex.get(key).add(caseId);
      const family = authorityFamilyBySourceId.get(key) || classifyAuthorityFamily(key, authorityFamily);
      if (family === 'constitution' || String(key).startsWith('constitution.')) {
        if (!constitutionCaseIndex.has(key)) constitutionCaseIndex.set(key, new Set());
        constitutionCaseIndex.get(key).add(caseId);
      }
    }

    return {
      caseId,
      sourceId,
      authorityFamily,
      sharedKeys: Array.from(sharedKeys)
    };
  };

  const noteFilesIn = (relativeDir, localLimit = limit) => {
    const dir = path.join(ontologyRoot, relativeDir);
    if (!fs.existsSync(dir)) return [];
    const files = walkMarkdownFiles(dir, Math.max(100, localLimit));
    return files.filter((file) => /\.(md|markdown)$/i.test(file));
  };
  const readTextSafe = (file) => {
    try {
      return fs.readFileSync(file, 'utf-8');
    } catch {
      return '';
    }
  };

  const processCaseFiles = () => {
    const dirs = ['cases/scotus', 'cases/circuits', 'cases/districts'];
    for (const dir of dirs) {
      const files = noteFilesIn(dir, limit);
      for (const file of files) {
        scannedFiles += 1;
        const raw = readTextSafe(file);
        if (!raw) continue;
        const { data, body } = parseFrontmatterObject(raw);
        const caseId = String(data.case_id || '').trim() || toRel(ontologyRoot, file).replace(/\.md$/i, '');
        const frontmatterTitle = String(data.title || '').trim();
        const headingTitle = extractFirstMarkdownHeading(body);
        const filenameTitle = caseNameFromCaseNoteFilename(file);
        const title = resolvePreferredCaseTitle(frontmatterTitle, headingTitle, filenameTitle, caseId);
        const decisionDate = String(data.date_decided || '').trim();
        const sourceMap = data.sources && typeof data.sources === 'object' && !Array.isArray(data.sources) ? data.sources : {};
        const primaryCitation = String(sourceMap.primary_citation || data.primary_citation || data.citation || '').trim();
        const fileCitation = citationFromCaseFilename(file);
        const headingCitation = extractReporterCaseCitation(headingTitle);
        const titleCitation = extractReporterCaseCitation(frontmatterTitle);
        const citeAsCitation = citationFromOpinionHeaderText(body);
        let caseCitation =
          normalizeCaseCitation(primaryCitation) ||
          normalizeCaseCitation(fileCitation) ||
          normalizeCaseCitation(headingCitation) ||
          normalizeCaseCitation(titleCitation) ||
          normalizeCaseCitation(citeAsCitation);
        const displayLabel = buildCaseDisplayLabel(title, decisionDate, caseId);
        const opinionUrl = String(sourceMap.opinion_url || data.opinion_url || '').trim();
        const opinionPdfPathRaw = String(
          sourceMap.opinion_pdf_path || sourceMap.pdf_path || data.opinion_pdf_path || data.pdf_path || ''
        ).trim();
        const opinionPdfPath =
          opinionPdfPathRaw ||
          (/\.pdf(?:[#?]|$)/i.test(opinionUrl) ? opinionUrl : '');
        const caseDomain = inferCaseDomainFromInputs({
          caseDomain: data.case_domain,
          caseType: data.case_type,
          domain: data.domain,
          matterType: data.matter_type,
          practiceArea: data.practice_area,
          ruleType: data.rule_type,
          tags: Array.isArray(data.tags) ? data.tags : [],
          isCriminalCase: data.is_criminal_case,
          criminalCase: data.criminal_case,
          isCivilCase: data.is_civil_case,
          civilCase: data.civil_case,
          authorityAnchors: Array.isArray(data.authority_anchors) ? data.authority_anchors : [],
          pathLike: `${dir}/${toRel(ontologyRoot, file)}`,
          title: `${title} ${displayLabel}`,
          summary: String(data.case_summary || ''),
          holding: String(data.essential_holding || ''),
          bodyExcerpt: body
        });
        const originatingCircuit =
          normalizeOriginatingCircuit(data.originating_circuit) ||
          normalizeOriginatingCircuit(data.originating_circuit_label);
        const node = ensureNode(caseId, {
          nodeType: 'case',
          label: displayLabel || title || caseId,
          path: makeGraphPath(file),
          caseId,
          isPrimaryCase: true,
          caseTitle: title,
          caseDisplayLabel: displayLabel,
          caseCitation,
          courtLevel: String(data.court_level || '').toLowerCase(),
          court: String(data.court || ''),
          jurisdiction: String(data.jurisdiction || ''),
          decisionDate,
          decisionYear: extractYearFromDate(decisionDate),
          caseSummary: sanitizeSingleLine(String(data.case_summary || ''), 650),
          essentialHolding: sanitizeSingleLine(String(data.essential_holding || ''), 420),
          caseDomain: caseDomain || 'civil',
          opinionUrl,
          pdfPath: opinionPdfPath,
          originatingCircuit,
          originatingCircuitLabel:
            String(data.originating_circuit_label || '').trim() ||
            originatingCircuitLabel(originatingCircuit)
        });
        registerCaseAliases({
          caseId,
          decisionDate,
          caseCitation,
          opinionUrl,
          opinionPdfPath,
          filePath: file
        });
        const caseTaxonomies = Array.isArray(data.case_taxonomies) ? data.case_taxonomies : [];
        for (const entry of caseTaxonomies) {
          const code =
            typeof entry === 'string'
              ? String(entry || '').trim()
              : String(entry?.code || entry?.taxonomy_code || entry?.id || '').trim();
          if (!code) continue;
          const label =
            typeof entry === 'string'
              ? code
              : String(entry?.label || entry?.name || code).trim();
          const taxonomyId = `taxonomy.${code}`;
          ensureNode(taxonomyId, {
            nodeType: 'taxonomy',
            taxonomyCode: code,
            label: sanitizeSingleLine(label || code, 160)
          });
          addEdge(caseId, taxonomyId, { edgeType: 'taxonomy_edge' });
        }
        localCaseIdSet.add(resolveCaseAlias(caseId) || caseId);
        const queuedAuthoritySourceIds = new Set();
        const queueCaseAuthorityAnchor = ({
          sourceIdRaw = '',
          sourceTypeRaw = '',
          normalizedAuthorityRaw = '',
          confidenceRaw = null
        }) => {
          let sourceId = String(sourceIdRaw || '').trim();
          if (!sourceId) return;
          sourceId = canonicalConstitutionSourceId(sourceId);
          const sourceType = String(sourceTypeRaw || '').trim();
          const authorityFamily = rememberAuthorityFamily(sourceId, sourceType);
          if (queuedAuthoritySourceIds.has(sourceId)) {
            registerAuthorityForCase(caseId, sourceId, sourceType || authorityFamily, true);
            return;
          }
          queuedAuthoritySourceIds.add(sourceId);
          const normalizedAuthority =
            sanitizeSingleLine(String(normalizedAuthorityRaw || ''), 200) ||
            (authorityFamily === 'constitution' ? constitutionLabelFromSourceId(sourceId) : '');
          pendingCaseAuthorityEdges.push({
            caseId,
            sourceId,
            sourceType: authorityFamily,
            confidence: toNumberOrNull(confidenceRaw),
            normalizedAuthority
          });
          registerAuthorityForCase(caseId, sourceId, sourceType || authorityFamily, true);
        };
        const citationAnchors = Array.isArray(data.citation_anchors) ? data.citation_anchors : [];
        for (const anchorRaw of citationAnchors) {
          if (!anchorRaw || typeof anchorRaw !== 'object' || Array.isArray(anchorRaw)) continue;
          const normalizedCitation = normalizeCaseCitation(String(anchorRaw.normalized_text || anchorRaw.raw_text || '').trim());
          if (!normalizedCitation) continue;
          const targetRef = String(anchorRaw.resolved_case_id || '').trim();
          pendingCaseCitationEdges.push({
            sourceCaseId: caseId,
            targetCaseRef: targetRef,
            citationType: normalizeEnumSuffix(anchorRaw.role || ''),
            confidence: toNumberOrNull(anchorRaw.confidence),
            normalizedCitation: sanitizeSingleLine(normalizedCitation, 120)
          });
          addCaseCitationReference(caseId, normalizedCitation);
          if (!caseCitationClusterIndex.has(normalizedCitation)) caseCitationClusterIndex.set(normalizedCitation, new Set());
          caseCitationClusterIndex.get(normalizedCitation).add(caseId);
        }
        const authorityAnchors = Array.isArray(data.authority_anchors) ? data.authority_anchors : [];
        for (const anchorRaw of authorityAnchors) {
          if (!anchorRaw || typeof anchorRaw !== 'object' || Array.isArray(anchorRaw)) continue;
          const sourceId = String(anchorRaw.source_id || '').trim();
          if (!sourceId) continue;
          queueCaseAuthorityAnchor({
            sourceIdRaw: sourceId,
            sourceTypeRaw: String(anchorRaw.source_type || '').trim(),
            normalizedAuthorityRaw: String(anchorRaw.normalized_text || ''),
            confidenceRaw: anchorRaw.confidence
          });
        }

        // Backfill constitutional amendment anchors from opinion text variants
        // (e.g., "Fourth Amendment", "4th Amendment", "Const. amend. IV").
        const constitutionText = [frontmatterTitle, headingTitle, String(data.case_summary || ''), body]
          .filter(Boolean)
          .join('\n');
        for (const sourceId of extractConstitutionSourceIdsFromText(constitutionText)) {
          queueCaseAuthorityAnchor({
            sourceIdRaw: sourceId,
            sourceTypeRaw: 'constitution',
            normalizedAuthorityRaw: constitutionLabelFromSourceId(sourceId),
            confidenceRaw: 0.72
          });
        }
        const interpretiveEdges = Array.isArray(data.interpretive_edges) ? data.interpretive_edges : [];
        for (const edgeRaw of interpretiveEdges) {
          if (!edgeRaw || typeof edgeRaw !== 'object' || Array.isArray(edgeRaw)) continue;
          const authorityType = String(edgeRaw.authority_type || '').trim().toUpperCase();
          const edgeType = String(edgeRaw.edge_type || '').trim().toUpperCase();
          if (!authorityType || !edgeType) continue;
          pendingInterpretiveEdges.push({
            sourceCaseId: String(edgeRaw.source_case || caseId).trim() || caseId,
            targetAuthority: sanitizeSingleLine(String(edgeRaw.target_authority || ''), 220),
            authorityType,
            edgeType,
            confidence: toNumberOrNull(edgeRaw.confidence),
            textSpan: sanitizeSingleLine(String(edgeRaw.text_span || ''), 420),
            targetSourceId: String(edgeRaw.target_source_id || '').trim(),
            targetCaseId: String(edgeRaw.target_case_id || '').trim()
          });
        }
        if (node) nodeTypeCounts.case = (nodeTypeCounts.case || 0) + 1;
      }
    }
  };

  const processCaseCitationEdges = () => {
    for (const item of pendingCaseCitationEdges) {
      const sourceCaseId = resolveCaseAlias(item?.sourceCaseId || '');
      const targetCaseId = resolveCaseAlias(item?.targetCaseRef || '');
      const normalizedCitation = normalizeCaseCitation(String(item?.normalizedCitation || '').trim());
      if (!sourceCaseId || sourceCaseId === targetCaseId) continue;
      if (!hasLocalCaseNode(sourceCaseId)) continue;
      ensureNode(sourceCaseId, { nodeType: 'case' });
      if (targetCaseId && targetCaseId !== sourceCaseId && hasLocalCaseNode(targetCaseId)) {
        ensureNode(targetCaseId, { nodeType: 'case' });
        addEdge(sourceCaseId, targetCaseId, {
          edgeType: 'case_citation',
          citationType: item?.citationType || '',
          confidence: toNumberOrNull(item?.confidence),
          normalizedCitation: normalizedCitation || String(item?.normalizedCitation || '')
        });
        continue;
      }
    }
  };

  const processSharedCaseCitationEdges = () => {
    const maxCasesPerCitation = 18;
    for (const [citationLabelRaw, caseSet] of caseCitationClusterIndex.entries()) {
      const citationLabel = normalizeCaseCitation(String(citationLabelRaw || '').trim());
      const caseIds = Array.from(caseSet || [])
        .map((caseId) => resolveCaseAlias(caseId))
        .filter((caseId) => Boolean(caseId) && hasLocalCaseNode(caseId));
      const unique = Array.from(new Set(caseIds)).sort((a, b) => String(a).localeCompare(String(b)));
      if (unique.length < 2) continue;

      if (unique.length <= maxCasesPerCitation) {
        for (let i = 0; i < unique.length; i += 1) {
          for (let j = i + 1; j < unique.length; j += 1) {
            addEdge(unique[i], unique[j], {
              edgeType: 'shared_case_citation',
              citationType: 'persuasive',
              confidence: 0.72,
              normalizedCitation: citationLabel || citationLabelRaw
            });
          }
        }
        continue;
      }

      const maxHop = unique.length <= 60 ? 3 : 2;
      for (let i = 0; i < unique.length; i += 1) {
        for (let hop = 1; hop <= maxHop; hop += 1) {
          const j = i + hop;
          if (j >= unique.length) break;
          addEdge(unique[i], unique[j], {
            edgeType: 'shared_case_citation',
            citationType: 'persuasive',
            confidence: 0.66,
            normalizedCitation: citationLabel || citationLabelRaw
          });
        }
      }
    }
  };

  const processCaseAuthorityEdges = () => {
    const isCitationAuthorityFamily = (family) =>
      family === 'statute' || family === 'regulation' || family === 'constitution' || family === 'rule' || family === 'guideline';
    for (const item of pendingCaseAuthorityEdges) {
      const sourceCaseId = resolveCaseAlias(item?.caseId || '');
      const sourceIdRaw = String(item?.sourceId || '').trim();
      const sourceId = canonicalConstitutionSourceId(sourceIdRaw);
      if (!sourceCaseId || !sourceId) continue;
      if (!hasLocalCaseNode(sourceCaseId)) continue;
      const authorityFamily = rememberAuthorityFamily(sourceId, item?.sourceType || '');
      if (!isCitationAuthorityFamily(authorityFamily)) continue;
      registerAuthorityForCase(sourceCaseId, sourceId, authorityFamily, true);
      ensureNode(sourceCaseId, { nodeType: 'case' });
      if (authorityFamily === 'constitution') {
        ensureNode(sourceId, {
          nodeType: 'constitution',
          sourceId,
          sourceType: authorityFamily,
          label:
            sanitizeSingleLine(String(item?.normalizedAuthority || ''), 200) ||
            constitutionLabelFromSourceId(sourceId)
        });
        addEdge(sourceCaseId, sourceId, {
          edgeType: 'constitution_citation',
          citationType: 'controlling',
          confidence: toNumberOrNull(item?.confidence) ?? 0.86,
          normalizedCitation: String(item?.normalizedAuthority || '')
        });
        continue;
      }
      if (authorityFamily === 'statute' || authorityFamily === 'regulation') {
        const titleInfo = authorityTitleInfo(sourceId, authorityFamily, item?.normalizedAuthority || '');
        if (!titleInfo) continue;
        ensureNode(titleInfo.nodeId, {
          nodeType: authorityFamily === 'statute' ? 'statute' : 'regulation',
          sourceId: titleInfo.nodeId,
          sourceType: authorityFamily,
          label: titleInfo.label
        });
        addEdge(sourceCaseId, titleInfo.nodeId, {
          edgeType: titleInfo.edgeType,
          citationType: 'controlling',
          confidence: toNumberOrNull(item?.confidence) ?? 0.82,
          normalizedCitation: String(item?.normalizedAuthority || '')
        });
      }
    }
  };

  const processGroupedAuthorityPairEdges = () => {
    const localCases = Array.from(localCaseIdSet)
      .map((caseId) => resolveCaseAlias(caseId))
      .filter((caseId) => caseId && hasLocalCaseNode(caseId));
    const totalCaseCount = Math.max(1, localCases.length);
    if (totalCaseCount < 2) return;

    const familyBaseWeight = {
      statute: 0.64,
      regulation: 0.52,
      rule: 0.56,
      guideline: 0.48
    };
    const groupTooBroadThreshold = 180;
    const minPairScore = 0.22;
    const maxEdgesPerCase = 26;

    const pairKey = (leftRaw, rightRaw) => {
      const left = String(leftRaw || '').trim();
      const right = String(rightRaw || '').trim();
      if (!left || !right || left === right) return '';
      return left < right ? `${left}::${right}` : `${right}::${left}`;
    };

    const pairByKey = new Map();
    const appendLabel = (setRef, labelRaw, maxSize = 8) => {
      const label = sanitizeSingleLine(String(labelRaw || '').trim(), 120);
      if (!label) return;
      if (setRef.size >= maxSize && !setRef.has(label)) return;
      setRef.add(label);
    };

    const addPairContribution = (sourceCaseId, targetCaseId, groupMeta, contribution) => {
      const key = pairKey(sourceCaseId, targetCaseId);
      if (!key || contribution <= 0) return;
      const source = key.split('::')[0];
      const target = key.split('::')[1];
      let record = pairByKey.get(key);
      if (!record) {
        record = {
          key,
          source,
          target,
          score: 0,
          sharedAuthorityCount: 0,
          sharedStatuteCount: 0,
          sharedRegulationCount: 0,
          sharedRuleCount: 0,
          sharedGuidelineCount: 0,
          statuteLabels: new Set(),
          regulationLabels: new Set(),
          ruleLabels: new Set(),
          guidelineLabels: new Set()
        };
        pairByKey.set(key, record);
      }
      record.score += contribution;
      record.sharedAuthorityCount += 1;
      const family = String(groupMeta?.family || '').toLowerCase();
      const label = String(groupMeta?.label || '');
      if (family === 'statute') {
        record.sharedStatuteCount += 1;
        appendLabel(record.statuteLabels, label, 8);
      } else if (family === 'regulation') {
        record.sharedRegulationCount += 1;
        appendLabel(record.regulationLabels, label, 8);
      } else if (family === 'rule') {
        record.sharedRuleCount += 1;
        appendLabel(record.ruleLabels, label, 8);
      } else if (family === 'guideline') {
        record.sharedGuidelineCount += 1;
        appendLabel(record.guidelineLabels, label, 8);
      }
    };

    for (const [groupKey, caseSetRaw] of groupedAuthorityCaseIndex.entries()) {
      const groupMeta = groupedAuthorityMetaByKey.get(groupKey) || {};
      const family = String(groupMeta.family || '').toLowerCase();
      if (!familyBaseWeight[family]) continue;
      const caseIds = Array.from(caseSetRaw || [])
        .map((caseId) => resolveCaseAlias(caseId))
        .filter((caseId) => caseId && hasLocalCaseNode(caseId));
      const uniqueCaseIds = Array.from(new Set(caseIds)).sort((a, b) => String(a).localeCompare(String(b)));
      const caseCount = uniqueCaseIds.length;
      if (caseCount < 2) continue;
      if (caseCount > groupTooBroadThreshold) continue;

      const idf = Math.log1p(totalCaseCount / caseCount);
      const idfNorm = Math.max(0.2, Math.min(1, idf / 4.5));
      const specificityBoost = groupKey.split('.').length > 4 ? 1 : 0.8;
      const contribution = familyBaseWeight[family] * idfNorm * specificityBoost;
      if (contribution <= 0) continue;

      if (caseCount <= 28) {
        for (let i = 0; i < caseCount; i += 1) {
          for (let j = i + 1; j < caseCount; j += 1) {
            addPairContribution(uniqueCaseIds[i], uniqueCaseIds[j], groupMeta, contribution);
          }
        }
        continue;
      }

      const maxHop = caseCount <= 72 ? 4 : caseCount <= 120 ? 3 : 2;
      for (let i = 0; i < caseCount; i += 1) {
        for (let hop = 1; hop <= maxHop; hop += 1) {
          const j = i + hop;
          if (j >= caseCount) break;
          addPairContribution(uniqueCaseIds[i], uniqueCaseIds[j], groupMeta, contribution);
        }
      }
    }

    const pairRows = Array.from(pairByKey.values()).sort((left, right) => {
      const scoreDelta = Number(right.score || 0) - Number(left.score || 0);
      if (scoreDelta) return scoreDelta;
      const sharedDelta = Number(right.sharedAuthorityCount || 0) - Number(left.sharedAuthorityCount || 0);
      if (sharedDelta) return sharedDelta;
      return String(left.key || '').localeCompare(String(right.key || ''));
    });
    const caseEdgeBudget = new Map();
    const bumpBudget = (caseId) => caseEdgeBudget.set(caseId, (caseEdgeBudget.get(caseId) || 0) + 1);

    for (const row of pairRows) {
      const sourceCaseId = String(row.source || '').trim();
      const targetCaseId = String(row.target || '').trim();
      if (!sourceCaseId || !targetCaseId || sourceCaseId === targetCaseId) continue;
      if (Number(row.score || 0) < minPairScore && Number(row.sharedAuthorityCount || 0) < 2) continue;
      if ((caseEdgeBudget.get(sourceCaseId) || 0) >= maxEdgesPerCase) continue;
      if ((caseEdgeBudget.get(targetCaseId) || 0) >= maxEdgesPerCase) continue;

      const statuteLabels = Array.from(row.statuteLabels || []).slice(0, 6);
      const regulationLabels = Array.from(row.regulationLabels || []).slice(0, 6);
      const ruleLabels = Array.from(row.ruleLabels || []).slice(0, 6);
      const guidelineLabels = Array.from(row.guidelineLabels || []).slice(0, 6);
      const sharedAuthorityLabels = []
        .concat(statuteLabels)
        .concat(regulationLabels)
        .concat(ruleLabels)
        .concat(guidelineLabels)
        .slice(0, 8);
      const score = Number(row.score || 0);
      const confidence = Number((0.35 + 0.6 * (1 - Math.exp(-Math.max(0, score)))).toFixed(2));

      addEdge(sourceCaseId, targetCaseId, {
        edgeType: 'shared_authority_bundle',
        citationType: 'persuasive',
        confidence,
        authorityScore: Number(score.toFixed(4)),
        sharedAuthorityCount: Number(row.sharedAuthorityCount || 0),
        sharedStatuteCount: Number(row.sharedStatuteCount || 0),
        sharedRegulationCount: Number(row.sharedRegulationCount || 0),
        sharedRuleCount: Number(row.sharedRuleCount || 0),
        sharedGuidelineCount: Number(row.sharedGuidelineCount || 0),
        sharedAuthorityLabels,
        sharedStatuteLabels: statuteLabels,
        sharedRegulationLabels: regulationLabels,
        sharedRuleLabels: ruleLabels,
        sharedGuidelineLabels: guidelineLabels,
        normalizedCitation: sharedAuthorityLabels[0] || ''
      });
      bumpBudget(sourceCaseId);
      bumpBudget(targetCaseId);
    }
  };

  const processCaseCitationBackfillEdges = () => {
    const localCaseIds = Array.from(localCaseIdSet)
      .map((caseId) => resolveCaseAlias(caseId))
      .filter((caseId) => caseId && hasLocalCaseNode(caseId))
      .sort((a, b) => String(a).localeCompare(String(b)));
    if (localCaseIds.length < 2) return;

    const localCaseSet = new Set(localCaseIds);
    const minCaseDegree = 2;

    const pairKey = (leftRaw, rightRaw) => {
      const left = String(leftRaw || '').trim();
      const right = String(rightRaw || '').trim();
      if (!left || !right || left === right) return '';
      return left < right ? `${left}::${right}` : `${right}::${left}`;
    };

    const existingPairs = new Set();
    const degreeByCaseId = new Map(localCaseIds.map((caseId) => [caseId, 0]));
    const bumpDegree = (caseId) => degreeByCaseId.set(caseId, (degreeByCaseId.get(caseId) || 0) + 1);
    for (const edge of edgesByKey.values()) {
      const edgeType = String(edge?.edgeType || '').trim().toLowerCase();
      if (edgeType !== 'case_citation' && edgeType !== 'shared_case_citation') continue;
      const sourceCaseId = resolveCaseAlias(String(edge?.source || '').trim());
      const targetCaseId = resolveCaseAlias(String(edge?.target || '').trim());
      if (!sourceCaseId || !targetCaseId || sourceCaseId === targetCaseId) continue;
      if (!localCaseSet.has(sourceCaseId) || !localCaseSet.has(targetCaseId)) continue;
      const key = pairKey(sourceCaseId, targetCaseId);
      if (!key || existingPairs.has(key)) continue;
      existingPairs.add(key);
      bumpDegree(sourceCaseId);
      bumpDegree(targetCaseId);
    }

    const overlapCount = (leftSetRaw, rightSetRaw) => {
      const leftSet = leftSetRaw instanceof Set ? leftSetRaw : new Set();
      const rightSet = rightSetRaw instanceof Set ? rightSetRaw : new Set();
      if (!leftSet.size || !rightSet.size) return 0;
      const small = leftSet.size <= rightSet.size ? leftSet : rightSet;
      const large = small === leftSet ? rightSet : leftSet;
      let count = 0;
      for (const value of small) {
        if (large.has(value)) count += 1;
      }
      return count;
    };

    const caseMeta = (caseId) => {
      const node = nodesById.get(caseId) || {};
      const circuit = normalizeOriginatingCircuit(node.originatingCircuit || node.originatingCircuitLabel || '');
      const yearValue = parseInt(String(extractYearFromDate(node.decisionDate || node.decisionYear || '')), 10);
      const year = Number.isFinite(yearValue) ? yearValue : null;
      return { circuit, year };
    };

    const metaCache = new Map();
    const metaFor = (caseId) => {
      if (!metaCache.has(caseId)) metaCache.set(caseId, caseMeta(caseId));
      return metaCache.get(caseId);
    };

    const scoredCandidatesFor = (sourceCaseId) => {
      const sourceCitations = caseCitationLabelsByCase.get(sourceCaseId) || new Set();
      const sourceMeta = metaFor(sourceCaseId);

      const rows = [];
      if (sourceCitations.size) {
        for (const targetCaseId of localCaseIds) {
          if (targetCaseId === sourceCaseId) continue;
          const pair = pairKey(sourceCaseId, targetCaseId);
          if (!pair || existingPairs.has(pair)) continue;
          const targetCitations = caseCitationLabelsByCase.get(targetCaseId) || new Set();
          const sharedCount = overlapCount(sourceCitations, targetCitations);
          if (sharedCount <= 0) continue;

          const targetMeta = metaFor(targetCaseId);
          let score = sharedCount * 10;
          if (sourceMeta.circuit && targetMeta.circuit && sourceMeta.circuit === targetMeta.circuit) score += 1.25;
          if (sourceMeta.year !== null && targetMeta.year !== null) {
            const delta = Math.abs(sourceMeta.year - targetMeta.year);
            if (delta <= 1) score += 1.0;
            else if (delta <= 3) score += 0.6;
            else if (delta <= 6) score += 0.3;
          }
          rows.push({
            targetCaseId,
            pair,
            sharedCount,
            score,
            mode: 'citation'
          });
        }
      }
      if (!rows.length) {
        const sourceAuthorities = caseAuthorityIdsByCase.get(sourceCaseId) || new Set();
        if (sourceAuthorities.size) {
          for (const targetCaseId of localCaseIds) {
            if (targetCaseId === sourceCaseId) continue;
            const pair = pairKey(sourceCaseId, targetCaseId);
            if (!pair || existingPairs.has(pair)) continue;
            const targetAuthorities = caseAuthorityIdsByCase.get(targetCaseId) || new Set();
            const sharedCount = overlapCount(sourceAuthorities, targetAuthorities);
            if (sharedCount <= 0) continue;

            const targetMeta = metaFor(targetCaseId);
            let score = sharedCount * 6;
            if (sourceMeta.circuit && targetMeta.circuit && sourceMeta.circuit === targetMeta.circuit) score += 1.0;
            if (sourceMeta.year !== null && targetMeta.year !== null) {
              const delta = Math.abs(sourceMeta.year - targetMeta.year);
              if (delta <= 1) score += 0.75;
              else if (delta <= 3) score += 0.4;
            }
            rows.push({
              targetCaseId,
              pair,
              sharedCount,
              score,
              mode: 'authority'
            });
          }
        }
      }
      if (!rows.length) {
        for (const targetCaseId of localCaseIds) {
          if (targetCaseId === sourceCaseId) continue;
          const pair = pairKey(sourceCaseId, targetCaseId);
          if (!pair || existingPairs.has(pair)) continue;
          const targetMeta = metaFor(targetCaseId);
          let score = 0.01;
          if (sourceMeta.circuit && targetMeta.circuit && sourceMeta.circuit === targetMeta.circuit) score += 1.2;
          if (sourceMeta.year !== null && targetMeta.year !== null) {
            const delta = Math.abs(sourceMeta.year - targetMeta.year);
            score += Math.max(0, 1 - Math.min(1, delta / 10));
          }
          rows.push({
            targetCaseId,
            pair,
            sharedCount: 0,
            score,
            mode: 'fallback'
          });
        }
      }

      rows.sort((left, right) => {
        const scoreDelta = Number(right.score || 0) - Number(left.score || 0);
        if (scoreDelta) return scoreDelta;
        const sharedDelta = Number(right.sharedCount || 0) - Number(left.sharedCount || 0);
        if (sharedDelta) return sharedDelta;
        return String(left.targetCaseId || '').localeCompare(String(right.targetCaseId || ''));
      });
      return rows;
    };

    const underlinked = localCaseIds
      .slice()
      .sort((left, right) => {
        const leftDegree = Number(degreeByCaseId.get(left) || 0);
        const rightDegree = Number(degreeByCaseId.get(right) || 0);
        if (leftDegree !== rightDegree) return leftDegree - rightDegree;
        return String(left).localeCompare(String(right));
      });

    for (const sourceCaseId of underlinked) {
      if ((degreeByCaseId.get(sourceCaseId) || 0) >= minCaseDegree) continue;
      const candidates = scoredCandidatesFor(sourceCaseId);
      for (const candidate of candidates) {
        if ((degreeByCaseId.get(sourceCaseId) || 0) >= minCaseDegree) break;
        const targetCaseId = String(candidate.targetCaseId || '').trim();
        if (!targetCaseId || targetCaseId === sourceCaseId) continue;
        if (!localCaseSet.has(targetCaseId)) continue;
        if (existingPairs.has(candidate.pair)) continue;
        const confidenceBase =
          candidate.mode === 'authority'
            ? 0.5
            : candidate.mode === 'fallback'
              ? 0.46
              : 0.52;
        const confidence = Math.max(0.58, Math.min(0.9, confidenceBase + Number(candidate.sharedCount || 0) * 0.08));
        addEdge(sourceCaseId, targetCaseId, {
          edgeType: 'shared_case_citation',
          citationType: 'persuasive',
          confidence: Number(confidence.toFixed(2)),
          normalizedCitation:
            candidate.mode === 'authority'
              ? 'authority_overlap_backfill'
              : candidate.mode === 'fallback'
                ? 'minimal_connectivity_backfill'
                : 'citation_overlap_backfill',
          sharedCitationCount: Number(candidate.sharedCount || 0),
          citationBackfill: true
        });
        existingPairs.add(candidate.pair);
        bumpDegree(sourceCaseId);
        bumpDegree(targetCaseId);
      }
    }

    const forcedScoreForTarget = (sourceCaseId, targetCaseId) => {
      const sourceMeta = metaFor(sourceCaseId);
      const targetMeta = metaFor(targetCaseId);
      let score = 0.01;
      if (sourceMeta.circuit && targetMeta.circuit && sourceMeta.circuit === targetMeta.circuit) score += 1.2;
      if (sourceMeta.year !== null && targetMeta.year !== null) {
        const delta = Math.abs(sourceMeta.year - targetMeta.year);
        score += Math.max(0, 1 - Math.min(1, delta / 10));
      }
      return score;
    };

    for (const sourceCaseId of localCaseIds) {
      let attempts = 0;
      while ((degreeByCaseId.get(sourceCaseId) || 0) < minCaseDegree && attempts < localCaseIds.length * 2) {
        attempts += 1;
        let chosenTarget = '';
        let chosenPair = '';
        let bestScore = -1;
        for (const targetCaseId of localCaseIds) {
          if (targetCaseId === sourceCaseId) continue;
          const pair = pairKey(sourceCaseId, targetCaseId);
          if (!pair || existingPairs.has(pair)) continue;
          const score = forcedScoreForTarget(sourceCaseId, targetCaseId);
          if (score > bestScore || (score === bestScore && String(targetCaseId).localeCompare(String(chosenTarget)) < 0)) {
            bestScore = score;
            chosenTarget = targetCaseId;
            chosenPair = pair;
          }
        }
        if (!chosenTarget || !chosenPair) break;
        addEdge(sourceCaseId, chosenTarget, {
          edgeType: 'shared_case_citation',
          citationType: 'persuasive',
          confidence: 0.58,
          normalizedCitation: 'forced_connectivity_backfill',
          sharedCitationCount: 0,
          citationBackfill: true
        });
        existingPairs.add(chosenPair);
        bumpDegree(sourceCaseId);
        bumpDegree(chosenTarget);
      }
    }
  };

  const processInterpretiveEdges = () => {
    const interpretiveAuthorityTypeFromFamily = (familyRaw) => {
      const family = String(familyRaw || '').trim().toLowerCase();
      if (family === 'constitution') return 'CONSTITUTION';
      if (family === 'statute') return 'STATUTE';
      if (family === 'rule') return 'FEDERAL_RULE';
      if (family === 'regulation') return 'REGULATION';
      if (family === 'guideline') return 'GUIDELINE';
      return 'AUTHORITY';
    };

    const addInterpretiveAuthorityCasePairs = (sourceIdRaw, caseIdsRaw = [], authorityTypeRaw = 'AUTHORITY') => {
      const sourceId = String(sourceIdRaw || '').trim();
      const authorityType = String(authorityTypeRaw || '').trim().toUpperCase() || 'AUTHORITY';
      const caseIds = Array.from(
        new Set(
          caseIdsRaw
            .map((id) => resolveCaseAlias(id))
            .filter((id) => Boolean(id) && hasLocalCaseNode(id))
        )
      ).sort((a, b) => String(a).localeCompare(String(b)));
      if (caseIds.length < 2) return;

      if (caseIds.length <= 24) {
        for (let i = 0; i < caseIds.length; i += 1) {
          for (let j = i + 1; j < caseIds.length; j += 1) {
            addEdge(caseIds[i], caseIds[j], {
              edgeType: 'interpretive_authority',
              citationType: 'controlling',
              confidence: 0.92,
              normalizedCitation: sourceId,
              authorityType,
              interpretiveEdgeType: 'INTERPRETS_AUTHORITY'
            });
          }
        }
        return;
      }

      // Keep high-frequency interpretive authorities sparse but connected.
      const maxHop = caseIds.length <= 96 ? 5 : caseIds.length <= 260 ? 4 : 3;
      for (let i = 0; i < caseIds.length; i += 1) {
        for (let hop = 1; hop <= maxHop; hop += 1) {
          const j = i + hop;
          if (j >= caseIds.length) break;
          addEdge(caseIds[i], caseIds[j], {
            edgeType: 'interpretive_authority',
            citationType: 'controlling',
            confidence: 0.84,
            normalizedCitation: sourceId,
            authorityType,
            interpretiveEdgeType: 'INTERPRETS_AUTHORITY'
          });
        }
      }
    };

    for (const item of pendingInterpretiveEdges) {
      const sourceCaseId = resolveCaseAlias(item?.sourceCaseId || '');
      if (!sourceCaseId) continue;
      if (!hasLocalCaseNode(sourceCaseId)) continue;
      const localSourceCaseId = resolveCaseAlias(sourceCaseId);
      ensureNode(localSourceCaseId, { nodeType: 'case' });

      const targetCaseId = resolveCaseAlias(item?.targetCaseId || '');
      if (targetCaseId && targetCaseId !== localSourceCaseId && hasLocalCaseNode(targetCaseId)) {
        const localTargetCaseId = resolveCaseAlias(targetCaseId);
        ensureNode(localTargetCaseId, { nodeType: 'case' });
        addEdge(localSourceCaseId, localTargetCaseId, {
          edgeType: 'interpretive_prior_case',
          citationType: 'controlling',
          confidence: toNumberOrNull(item?.confidence),
          normalizedCitation: String(item?.targetAuthority || ''),
          authorityType: String(item?.authorityType || ''),
          interpretiveEdgeType: String(item?.edgeType || ''),
          textSpan: String(item?.textSpan || '')
        });
      }

      const targetSourceId = String(item?.targetSourceId || '').trim();
      if (!targetSourceId) continue;
      const authorityType = String(item?.authorityType || '').trim().toUpperCase();
      const sourceType =
        authorityType === 'CONSTITUTION'
          ? 'constitution'
          : authorityType === 'STATUTE'
            ? 'statute'
            : authorityType === 'FEDERAL_RULE'
              ? 'rule'
              : authorityType === 'REGULATION'
                ? 'reg'
                : authorityType === 'GUIDELINE'
                  ? 'guideline'
              : 'other';
      const registered = registerAuthorityForCase(localSourceCaseId, targetSourceId, sourceType, true);
      if (!interpretiveAuthorityCaseIndex.has(targetSourceId)) {
        interpretiveAuthorityCaseIndex.set(targetSourceId, new Set());
      }
      interpretiveAuthorityCaseIndex.get(targetSourceId).add(localSourceCaseId);
      const authorityFamily = registered.authorityFamily || rememberAuthorityFamily(targetSourceId, sourceType);
      const normalizedAuthorityType = authorityType || interpretiveAuthorityTypeFromFamily(authorityFamily);
      const priorType = String(interpretiveAuthorityTypeBySourceId.get(targetSourceId) || '').trim();
      if (!priorType || priorType === 'AUTHORITY') {
        interpretiveAuthorityTypeBySourceId.set(targetSourceId, normalizedAuthorityType);
      }
    }

    for (const [sourceId, caseSet] of interpretiveAuthorityCaseIndex.entries()) {
      const authorityType = interpretiveAuthorityTypeBySourceId.get(sourceId) || 'AUTHORITY';
      addInterpretiveAuthorityCasePairs(sourceId, Array.from(caseSet || []), authorityType);
    }
  };

  const processHoldingFiles = () => {
    const files = noteFilesIn('holdings', limit);
    for (const file of files) {
      scannedFiles += 1;
      const raw = readTextSafe(file);
      if (!raw) continue;
      const { data } = parseFrontmatterObject(raw);
      const holdingId = String(data.holding_id || '').trim() || toRel(ontologyRoot, file).replace(/\.md$/i, '');
      const rawCaseId = String(data.case_id || '').trim();
      const caseId = resolveCaseAlias(rawCaseId);
      const caseNode = caseId && hasLocalCaseNode(caseId) ? nodesById.get(caseId) : null;
      const originatingCircuit = normalizeOriginatingCircuit(caseNode?.originatingCircuit);
      const holdingText = sanitizeSingleLine(String(data.holding_text || ''), 420);
      const pfHolding = toNumberOrNull(data.metrics?.PF_holding);
      const factDimensions = Array.isArray(data.fact_vector)
        ? data.fact_vector
            .map((item) => {
              if (item && typeof item === 'object' && !Array.isArray(item)) return item.dimension;
              return item;
            })
            .map((item) => String(item || '').trim())
            .filter(Boolean)
        : [];
      const node = ensureNode(holdingId, {
        nodeType: 'holding',
        label: String(holdingId.split('.').pop() || holdingId),
        path: makeGraphPath(file),
        holdingId,
        caseId,
        holdingText,
        normativeStrength: normalizeEnumSuffix(data.normative_strength),
        pfHolding,
        factDimensions,
        courtLevel: String(caseId.split('.')[1] || '').toLowerCase(),
        originatingCircuit,
        originatingCircuitLabel: originatingCircuitLabel(originatingCircuit)
      });
      if (node) nodeTypeCounts.holding = (nodeTypeCounts.holding || 0) + 1;

      if (caseId && hasLocalCaseNode(caseId)) {
        const linkedCaseId = resolveCaseAlias(caseId);
        const linkedCase = ensureNode(linkedCaseId, {
          nodeType: 'case',
          courtLevel: String(linkedCaseId.split('.')[1] || '').toLowerCase()
        });
        if (linkedCase && holdingText) {
          if (!linkedCase.essentialHolding) linkedCase.essentialHolding = holdingText;
          if (!Array.isArray(linkedCase._holdingSnippets)) linkedCase._holdingSnippets = [];
          if (!linkedCase._holdingSnippets.includes(holdingText) && linkedCase._holdingSnippets.length < 4) {
            linkedCase._holdingSnippets.push(holdingText);
          }
        }
        addEdge(holdingId, linkedCaseId, { edgeType: 'holding_case' });
      }

      const normativeSources = Array.isArray(data.normative_source) ? data.normative_source : [];
      for (const sourceIdRaw of normativeSources) {
        const sourceId = String(sourceIdRaw || '').trim();
        if (!sourceId) continue;
        ensureNode(sourceId, { nodeType: sourceId.startsWith('secondary.') ? 'secondary' : 'source', label: sourceId });
        addEdge(holdingId, sourceId, { edgeType: 'normative_source' });
      }

      const supportingCites = Array.isArray(data.citations_supporting) ? data.citations_supporting : [];
      for (const citationIdRaw of supportingCites) {
        const citationId = resolveCaseAlias(String(citationIdRaw || '').trim());
        if (!citationId) continue;
        if (hasLocalCaseNode(citationId)) {
          const localCitationId = resolveCaseAlias(citationId);
          ensureNode(localCitationId, { nodeType: 'case' });
          addEdge(holdingId, localCitationId, { edgeType: 'holding_citation' });
        }
      }
    }
  };

  const processIssueFiles = () => {
    const files = noteFilesIn('issues/taxonomy', limit);
    for (const file of files) {
      scannedFiles += 1;
      const raw = readTextSafe(file);
      if (!raw) continue;
      const { data } = parseFrontmatterObject(raw);
      const issueId = String(data.issue_id || '').trim() || toRel(ontologyRoot, file).replace(/\.md$/i, '');
      const metrics = data.metrics || {};
      const taxonomy = data.taxonomy || {};
      const issueDimensions = Array.isArray(data.dimensions?.required_fact_dimensions)
        ? data.dimensions.required_fact_dimensions.map((item) => String(item || '').trim()).filter(Boolean)
        : [];
      const node = ensureNode(issueId, {
        nodeType: 'issue',
        label: String(data.normalized_form || issueId).slice(0, 180),
        path: makeGraphPath(file),
        issueId,
        domain: String(taxonomy.domain || ''),
        doctrine: String(taxonomy.doctrine || ''),
        ruleType: String(taxonomy.rule_type || ''),
        pfIssue: toNumberOrNull(metrics.PF_issue),
        consensus: toNumberOrNull(metrics.consensus),
        drift: toNumberOrNull(metrics.drift),
        factDimensions: issueDimensions
      });
      if (node) nodeTypeCounts.issue = (nodeTypeCounts.issue || 0) + 1;

      const linkedHoldings = Array.isArray(data.linked_holdings) ? data.linked_holdings : [];
      for (const linkedRaw of linkedHoldings) {
        const holdingId = String(linkedRaw || '').trim();
        if (!holdingId) continue;
        ensureNode(holdingId, { nodeType: 'holding', label: holdingId });
        addEdge(issueId, holdingId, { edgeType: 'issue_holding' });
      }

      const canonicalCitations = Array.isArray(data.anchors?.canonical_citations) ? data.anchors.canonical_citations : [];
      for (const citeRaw of canonicalCitations) {
        const citationRef = String(citeRaw || '').trim();
        if (!citationRef) continue;
        if (looksLikeHoldingNodeId(citationRef)) {
          ensureNode(citationRef, { nodeType: 'holding', label: String(citationRef.split('.').pop() || citationRef) });
          addEdge(issueId, citationRef, { edgeType: 'issue_holding' });
          continue;
        }
        const caseId = resolveCaseAlias(citationRef);
        if (!caseId) continue;
        if (hasLocalCaseNode(caseId)) {
          const localCaseId = resolveCaseAlias(caseId);
          ensureNode(localCaseId, { nodeType: 'case' });
          addEdge(issueId, localCaseId, { edgeType: 'issue_citation', citationType: 'controlling' });
        }
      }
    }
  };

  const processSourceFiles = () => {
    const sourceDirs = ['sources/constitution', 'sources/statutes', 'sources/regs', 'sources/secondary'];
    for (const dir of sourceDirs) {
      const files = noteFilesIn(dir, limit);
      for (const file of files) {
        scannedFiles += 1;
        const raw = readTextSafe(file);
        if (!raw) continue;
        const { data } = parseFrontmatterObject(raw);
        const sourceId = String(data.source_id || '').trim() || toRel(ontologyRoot, file).replace(/\.md$/i, '');
        const isSecondary = String(data.type || '').toLowerCase() === 'secondary' || sourceId.startsWith('secondary.');
        const sourceType = isSecondary ? 'secondary' : String(data.source_type || '').toLowerCase();
        ensureNode(sourceId, {
          nodeType: isSecondary ? 'secondary' : 'source',
          label: String(data.title || sourceId),
          path: makeGraphPath(file),
          sourceId,
          sourceType,
          authorityWeight: toNumberOrNull(data.authority_weight)
        });
        nodeTypeCounts[isSecondary ? 'secondary' : 'source'] =
          (nodeTypeCounts[isSecondary ? 'secondary' : 'source'] || 0) + 1;
      }
    }
  };

  const processEventFiles = () => {
    const files = noteFilesIn('events/interpretations', Math.min(limit, 6000));
    for (const file of files) {
      scannedFiles += 1;
      const raw = readTextSafe(file);
      if (!raw) continue;
      const { data, body } = parseFrontmatterObject(raw);
      const caseId = resolveCaseAlias(String(data.case_id || '').trim());
      if (!caseId || !hasLocalCaseNode(caseId)) continue;
      const eventId = `event.${caseId || path.basename(file, path.extname(file))}`;
      ensureNode(eventId, {
        nodeType: 'event',
        label: `Interpretation ${caseId || path.basename(file, path.extname(file))}`,
        path: makeGraphPath(file),
        caseId
      });
      nodeTypeCounts.event = (nodeTypeCounts.event || 0) + 1;

      const localCaseId = resolveCaseAlias(caseId);
      ensureNode(localCaseId, { nodeType: 'case' });
      addEdge(eventId, localCaseId, { edgeType: 'event_case' });

      for (const line of String(body || '').split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('- {') || !trimmed.endsWith('}')) continue;
        try {
          const event = JSON.parse(trimmed.slice(2).trim());
          const sourceHoldingId = String(event.source_holding_id || '').trim();
          const targetHoldingId = String(event.target_holding_id || '').trim();
          if (sourceHoldingId && targetHoldingId) {
            ensureNode(sourceHoldingId, { nodeType: 'holding', label: sourceHoldingId });
            ensureNode(targetHoldingId, { nodeType: 'holding', label: targetHoldingId });
            addEdge(sourceHoldingId, targetHoldingId, {
              edgeType: 'relation_effect',
              relationType: normalizeEnumSuffix(event.relation_type),
              confidence: toNumberOrNull(event.effect)
            });
          }
        } catch {
          // ignore malformed event lines
        }
      }
    }
  };

  const processRelationFiles = () => {
    const files = noteFilesIn('relations', limit);
    for (const file of files) {
      scannedFiles += 1;
      const raw = readTextSafe(file);
      if (!raw) continue;
      const { data } = parseFrontmatterObject(raw);
      const sourceHoldingId = String(data.source_holding_id || '').trim();
      const targetHoldingId = String(data.target_holding_id || '').trim();
      const relationId = String(data.relation_id || '').trim() || toRel(ontologyRoot, file).replace(/\.md$/i, '');
      const relationType = normalizeEnumSuffix(data.relation_type);
      const citationType = normalizeEnumSuffix(data.citation_type);

      ensureNode(relationId, {
        nodeType: 'relation',
        label: relationType || 'relation',
        path: makeGraphPath(file),
        relationType,
        citationType,
        confidence: toNumberOrNull(data.confidence)
      });
      nodeTypeCounts.relation = (nodeTypeCounts.relation || 0) + 1;

      if (sourceHoldingId) {
        ensureNode(sourceHoldingId, { nodeType: 'holding', label: sourceHoldingId });
        addEdge(sourceHoldingId, relationId, { edgeType: 'relation_source', relationType, citationType });
      }
      if (targetHoldingId) {
        ensureNode(targetHoldingId, { nodeType: 'holding', label: targetHoldingId });
        addEdge(relationId, targetHoldingId, { edgeType: 'relation_target', relationType, citationType });
      }
      if (sourceHoldingId && targetHoldingId) {
        addEdge(sourceHoldingId, targetHoldingId, {
          edgeType: 'precedent_relation',
          relationType,
          citationType,
          confidence: toNumberOrNull(data.confidence),
          weightModifier: toNumberOrNull(data.weight_modifier)
        });
      }
    }
  };

  let connectivityRepairs = 0;
  const ensureCaseConnectivity = () => {
    const localCaseIds = Array.from(localCaseIdSet)
      .map((caseId) => resolveCaseAlias(caseId))
      .filter((id) => id && nodesById.has(id))
      .sort((a, b) => String(a).localeCompare(String(b)));
    if (localCaseIds.length < 2) return;
    const localCaseUniverse = new Set(localCaseIds);

    const caseDegree = new Map();
    const bump = (id) => caseDegree.set(id, (caseDegree.get(id) || 0) + 1);
    for (const edge of edgesByKey.values()) {
      const src = String(edge?.source || '').trim();
      const dst = String(edge?.target || '').trim();
      if (!src || !dst) continue;
      if (!localCaseUniverse.has(src) || !localCaseUniverse.has(dst)) continue;
      bump(src);
      bump(dst);
    }

    const overlapCount = (leftSet, rightSet) => {
      const left = leftSet instanceof Set ? leftSet : new Set();
      const right = rightSet instanceof Set ? rightSet : new Set();
      if (!left.size || !right.size) return 0;
      const small = left.size <= right.size ? left : right;
      const large = small === left ? right : left;
      let count = 0;
      for (const item of small) {
        if (large.has(item)) count += 1;
      }
      return count;
    };

    const tokenizeCaseTitle = (value) => {
      const tokens = String(value || '')
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/g)
        .map((token) => token.trim())
        .filter((token) => token.length >= 4);
      const stop = new Set(['versus', 'petitioner', 'respondent', 'petitioners', 'respondents', 'et', 'al']);
      return new Set(tokens.filter((token) => !stop.has(token)));
    };

    const featureForCase = (caseId) => {
      const node = nodesById.get(caseId) || {};
      const authorityIds = caseAuthorityIdsByCase.get(caseId) || new Set();
      const constitution = new Set();
      const statute = new Set();
      const rule = new Set();
      const regulation = new Set();
      const guideline = new Set();
      const otherAuthority = new Set();

      for (const sourceId of authorityIds) {
        const family = authorityFamilyBySourceId.get(sourceId) || classifyAuthorityFamily(sourceId, '');
        if (family === 'constitution') constitution.add(sourceId);
        else if (family === 'statute') statute.add(sourceId);
        else if (family === 'rule') rule.add(sourceId);
        else if (family === 'regulation') regulation.add(sourceId);
        else if (family === 'guideline') guideline.add(sourceId);
        else otherAuthority.add(sourceId);
      }

      return {
        year: extractYearFromDate(node.decisionDate || node.decisionYear || ''),
        circuit: normalizeOriginatingCircuit(node.originatingCircuit || node.originatingCircuitLabel || ''),
        citations: caseCitationLabelsByCase.get(caseId) || new Set(),
        constitution,
        statute,
        rule,
        regulation,
        guideline,
        otherAuthority,
        titleTokens: tokenizeCaseTitle(node.caseTitle || node.label || caseId)
      };
    };

    const featureCache = new Map();
    const getFeature = (caseId) => {
      if (!featureCache.has(caseId)) featureCache.set(caseId, featureForCase(caseId));
      return featureCache.get(caseId);
    };

    const allCases = localCaseIds.slice().sort((a, b) => a.localeCompare(b));

    const casePairKey = (leftRaw, rightRaw) => {
      const left = String(leftRaw || '').trim();
      const right = String(rightRaw || '').trim();
      if (!left || !right || left === right) return '';
      return left < right ? `${left}::${right}` : `${right}::${left}`;
    };

    const existingCasePairs = new Set();
    for (const edge of edgesByKey.values()) {
      const src = String(edge?.source || '').trim();
      const dst = String(edge?.target || '').trim();
      if (!localCaseUniverse.has(src) || !localCaseUniverse.has(dst)) continue;
      const key = casePairKey(src, dst);
      if (key) existingCasePairs.add(key);
    }

    const pickFallbackCase = (sourceCaseId, blockedTargets = new Set()) => {
      const sourceFeature = getFeature(sourceCaseId);
      let bestCaseId = '';
      let bestScore = -1;
      let bestYearDelta = Number.POSITIVE_INFINITY;

      for (const targetCaseId of allCases) {
        if (targetCaseId === sourceCaseId) continue;
        if (blockedTargets.has(targetCaseId)) continue;
        const existingKey = casePairKey(sourceCaseId, targetCaseId);
        if (existingKey && existingCasePairs.has(existingKey)) continue;
        const targetFeature = getFeature(targetCaseId);

        const sharedConstitution = overlapCount(sourceFeature.constitution, targetFeature.constitution);
        const sharedStatute = overlapCount(sourceFeature.statute, targetFeature.statute);
        const sharedRule = overlapCount(sourceFeature.rule, targetFeature.rule);
        const sharedRegulation = overlapCount(sourceFeature.regulation, targetFeature.regulation);
        const sharedGuideline = overlapCount(sourceFeature.guideline, targetFeature.guideline);
        const sharedOtherAuthority = overlapCount(sourceFeature.otherAuthority, targetFeature.otherAuthority);
        const sharedCitation = overlapCount(sourceFeature.citations, targetFeature.citations);
        const sharedTitleTokens = overlapCount(sourceFeature.titleTokens, targetFeature.titleTokens);

        let score = 0;
        score += sharedConstitution * 120;
        score += sharedStatute * 52;
        score += sharedRule * 36;
        score += sharedRegulation * 30;
        score += sharedGuideline * 26;
        score += sharedOtherAuthority * 10;
        score += sharedCitation * 18;
        score += Math.min(3, sharedTitleTokens) * 3;
        if (sourceFeature.circuit && targetFeature.circuit && sourceFeature.circuit === targetFeature.circuit) score += 9;

        let yearDelta = Number.POSITIVE_INFINITY;
        if (sourceFeature.year && targetFeature.year) {
          yearDelta = Math.abs(Number(sourceFeature.year) - Number(targetFeature.year));
          if (Number.isFinite(yearDelta)) {
            if (yearDelta <= 1) score += 6;
            else if (yearDelta <= 3) score += 4;
            else if (yearDelta <= 6) score += 2;
          }
        }

        if (score > bestScore || (score === bestScore && yearDelta < bestYearDelta)) {
          bestScore = score;
          bestYearDelta = yearDelta;
          bestCaseId = targetCaseId;
        }
      }

      if (!bestCaseId) return null;
      return {
        targetCaseId: bestCaseId,
        confidence: bestScore > 0 ? Math.max(0.36, Math.min(0.93, Number((bestScore / 220).toFixed(2)))) : 0.34
      };
    };

    const targetMinDegree = 3;
    const underlinkedCases = allCases.filter((caseId) => (caseDegree.get(caseId) || 0) < targetMinDegree);
    if (!underlinkedCases.length) return;

    for (const sourceCaseId of underlinkedCases) {
      const blockedTargets = new Set();
      let attempts = 0;
      while ((caseDegree.get(sourceCaseId) || 0) < targetMinDegree && attempts < 8) {
        attempts += 1;
        const picked = pickFallbackCase(sourceCaseId, blockedTargets);
        if (!picked || !picked.targetCaseId || picked.targetCaseId === sourceCaseId) break;
        const pairKey = casePairKey(sourceCaseId, picked.targetCaseId);
        if (!pairKey || existingCasePairs.has(pairKey)) {
          blockedTargets.add(picked.targetCaseId);
          continue;
        }

        addEdge(sourceCaseId, picked.targetCaseId, {
          edgeType: 'case_similarity_fallback',
          citationType: 'persuasive',
          confidence: picked.confidence,
          normalizedCitation: 'connectivity_backfill'
        });
        existingCasePairs.add(pairKey);
        blockedTargets.add(picked.targetCaseId);
        bump(sourceCaseId);
        bump(picked.targetCaseId);
        connectivityRepairs += 1;
      }
    }
  };

  processCaseFiles();
  processCaseCitationEdges();
  processCaseAuthorityEdges();

  const nodes = Array.from(nodesById.values()).map((node) => {
    const nodeType = String(node.nodeType || '').toLowerCase();
    const finalized = { ...node };
    if (nodeType === 'case') {
      finalized.caseTitle = sanitizeSingleLine(finalized.caseTitle || finalized.label || finalized.caseId || '', 160);
      finalized.decisionYear = extractYearFromDate(finalized.decisionDate || finalized.decisionYear || '');
      finalized.caseDisplayLabel = buildCaseDisplayLabel(
        finalized.caseTitle || finalized.label || finalized.caseId || '',
        finalized.decisionDate || '',
        finalized.caseId || finalized.id || ''
      );
      finalized.caseCitation = normalizeCaseCitation(
        finalized.caseCitation || ''
      );
      if (!finalized.essentialHolding && Array.isArray(finalized._holdingSnippets) && finalized._holdingSnippets.length) {
        finalized.essentialHolding = sanitizeSingleLine(finalized._holdingSnippets[0], 420);
      } else {
        finalized.essentialHolding = sanitizeSingleLine(finalized.essentialHolding || '', 420);
      }
      if (!finalized.caseSummary) {
        if (Array.isArray(finalized._holdingSnippets) && finalized._holdingSnippets.length) {
          finalized.caseSummary = sanitizeSingleLine(finalized._holdingSnippets.slice(0, 2).join(' '), 680);
        } else {
          finalized.caseSummary = buildFallbackCaseSummary(
            finalized.caseTitle || finalized.label || finalized.caseId || '',
            finalized.decisionDate || '',
            finalized.caseCitation || ''
          );
        }
      } else {
        finalized.caseSummary = sanitizeSingleLine(finalized.caseSummary, 680);
      }
      finalized.caseDomain =
        inferCaseDomainFromInputs({
          caseDomain: finalized.caseDomain,
          caseType: finalized.caseType,
          domain: finalized.domain,
          matterType: finalized.matterType,
          practiceArea: finalized.practiceArea,
          ruleType: finalized.ruleType,
          tags: Array.isArray(finalized.tags) ? finalized.tags : [],
          pathLike: `${finalized.path || ''} ${finalized.caseId || ''}`,
          title: `${finalized.caseTitle || ''} ${finalized.caseDisplayLabel || ''}`,
          summary: finalized.caseSummary || '',
          holding: finalized.essentialHolding || ''
        }) || 'civil';
      finalized.pdfPath = sanitizeSingleLine(finalized.pdfPath || '', 900);
      finalized.label = finalized.caseDisplayLabel || finalized.label || finalized.caseId || finalized.id;
    }
    delete finalized._holdingSnippets;

    const searchParts = [
      finalized.id,
      finalized.label,
      finalized.nodeType,
      finalized.caseId,
      finalized.caseTitle,
      finalized.caseDisplayLabel,
      finalized.caseCitation,
      finalized.caseDomain,
      finalized.caseSummary,
      finalized.essentialHolding,
      finalized.holdingId,
      finalized.holdingText,
      finalized.issueId,
      finalized.sourceId,
      finalized.relationType,
      finalized.citationType,
      finalized.domain,
      finalized.doctrine,
      finalized.ruleType,
      finalized.courtLevel,
      finalized.originatingCircuit,
      finalized.originatingCircuitLabel,
      Array.isArray(finalized.factDimensions) ? finalized.factDimensions.join(' ') : ''
    ]
      .filter(Boolean)
      .map((part) => String(part).toLowerCase());
    return {
      ...finalized,
      searchText: Array.from(new Set(searchParts)).join(' ')
    };
  });

  const originatingCircuitCounts = {};
  const caseDomainCounts = {};
  for (const node of nodes) {
    if (String(node.nodeType || '').toLowerCase() !== 'case') continue;
    const circuitCode = normalizeOriginatingCircuit(node.originatingCircuit || node.originatingCircuitLabel || '');
    if (circuitCode) {
      originatingCircuitCounts[circuitCode] = (originatingCircuitCounts[circuitCode] || 0) + 1;
    }
    const caseDomain = normalizeCaseDomain(node.caseDomain || '') || 'civil';
    caseDomainCounts[caseDomain] = (caseDomainCounts[caseDomain] || 0) + 1;
  }

  const nodeIdSet = new Set(nodes.map((node) => String(node.id || '').trim()).filter(Boolean));
  const edges = Array.from(edgesByKey.values()).filter((edge) => {
    const src = String(edge?.source || '').trim();
    const dst = String(edge?.target || '').trim();
    return Boolean(src && dst && nodeIdSet.has(src) && nodeIdSet.has(dst));
  });

  const filteredNodeTypeCounts = {};
  for (const node of nodes) {
    const nodeType = String(node?.nodeType || 'unknown').toLowerCase() || 'unknown';
    filteredNodeTypeCounts[nodeType] = (filteredNodeTypeCounts[nodeType] || 0) + 1;
  }
  const filteredEdgeTypeCounts = {};
  const filteredRelationTypes = new Set();
  const filteredCitationTypes = new Set();
  for (const edge of edges) {
    const edgeType = String(edge?.edgeType || 'link').trim() || 'link';
    filteredEdgeTypeCounts[edgeType] = (filteredEdgeTypeCounts[edgeType] || 0) + 1;
    const relationType = normalizeEnumSuffix(edge?.relationType || '');
    if (relationType) filteredRelationTypes.add(relationType);
    const citationType = normalizeEnumSuffix(edge?.citationType || '');
    if (citationType) filteredCitationTypes.add(citationType);
  }
  if (!nodes.length && !edges.length) {
    return buildOntologyFallbackFromVault(vaultRoot, ontologyInfo, limit, 'ontology_dataset_empty');
  }
  return {
    nodes,
    edges,
    meta: {
      ontologyRoot,
      exists: true,
      source: ontologyInfo.source || '',
      checkedCandidates: ontologyInfo.checkedCandidates || 0,
      scannedFiles,
      truncated: scannedFiles >= limit,
      nodeTypeCounts: filteredNodeTypeCounts,
      edgeTypeCounts: filteredEdgeTypeCounts,
      relationTypes: Array.from(filteredRelationTypes).sort(),
      citationTypes: Array.from(filteredCitationTypes).sort(),
      caseDomainCounts,
      originatingCircuitCounts,
      connectivityRepairs
    }
  };
}

function mergeStringArraysUnique(values = []) {
  const out = [];
  for (const value of values) {
    const raw = String(value || '').trim();
    if (!raw) continue;
    if (!out.includes(raw)) out.push(raw);
  }
  return out;
}

function resolveCaselawDbDsn() {
  const primary = String(process.env.ACQ_CASELAW_DB_DSN || '').trim();
  if (primary) return primary;
  const secondary = String(process.env.COURTLISTENER_DB_DSN || '').trim();
  if (secondary) return secondary;
  return '';
}

function buildCaselawGraphFromDb(limit = CASELAW_DB_GRAPH_LIMIT) {
  const dsn = resolveCaselawDbDsn();
  if (!dsn) return null;
  if (!fs.existsSync(CASELAW_DB_GRAPH_SCRIPT)) return null;

  const pythonBin = String(process.env.ACQ_CASELAW_PYTHON || 'python3').trim() || 'python3';
  const env = { ...process.env, ACQ_CASELAW_DB_DSN: dsn };
  const args = [CASELAW_DB_GRAPH_SCRIPT, '--limit', String(Math.max(100, Number(limit) || CASELAW_DB_GRAPH_LIMIT))];
  const result = spawnSync(pythonBin, args, {
    encoding: 'utf-8',
    timeout: 120000,
    maxBuffer: 30 * 1024 * 1024,
    env
  });

  if (result.error || result.status !== 0) {
    const errText = String(result.error?.message || result.stderr || `status=${result.status}`).trim();
    logStartup(`[caselaw-db-graph] failed: ${errText}`);
    return null;
  }

  const stdout = String(result.stdout || '').trim();
  if (!stdout) return null;
  try {
    const payload = JSON.parse(stdout);
    if (!payload || !Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) return null;
    return payload;
  } catch (err) {
    logStartup(`[caselaw-db-graph] invalid JSON: ${err?.message || err}`);
    return null;
  }
}

function enrichCaselawDbGraphMeta(dbGraph = {}, roots = [], fallbackReason = '') {
  const nodes = Array.isArray(dbGraph?.nodes) ? dbGraph.nodes : [];
  const edges = Array.isArray(dbGraph?.edges) ? dbGraph.edges : [];
  const existingMeta = dbGraph?.meta && typeof dbGraph.meta === 'object' ? dbGraph.meta : {};
  return {
    nodes,
    edges,
    meta: {
      ...existingMeta,
      ontologyRoot: String(existingMeta.ontologyRoot || 'derived.caselaw_nightly_case'),
      exists: nodes.length > 0 || edges.length > 0,
      source: 'postgres_caselaw',
      selectedVaultRoots: roots,
      multiVault: true,
      perVault: Array.isArray(existingMeta.perVault) ? existingMeta.perVault : [],
      fallbackFromVault: false,
      fallbackReason: fallbackReason || String(existingMeta.fallbackReason || 'vault_ontology_empty_db_fallback'),
      checkedCandidates: Number(existingMeta.checkedCandidates || 0),
      scannedFiles: Number(existingMeta.scannedFiles || existingMeta.documents || 0)
    }
  };
}

function buildOntologyGraphMulti(vaultRoots = [], limit = 10000) {
  const roots = [];
  for (const raw of Array.isArray(vaultRoots) ? vaultRoots : []) {
    const resolved = path.resolve(String(raw || '').trim());
    if (!resolved || roots.includes(resolved)) continue;
    if (!pathIsDirectory(resolved)) continue;
    roots.push(resolved);
  }

  if (!roots.length) {
    const dbGraph = buildCaselawGraphFromDb(limit);
    if (dbGraph && (Array.isArray(dbGraph.nodes) ? dbGraph.nodes.length : 0)) {
      return enrichCaselawDbGraphMeta(dbGraph, [], 'no_caselaw_vault_roots');
    }
    return {
      nodes: [],
      edges: [],
      meta: {
        ontologyRoot: 'multiple vaults (0)',
        exists: false,
        source: 'multi_vault',
        selectedVaultRoots: [],
        scannedFiles: 0,
        nodeTypeCounts: {},
        edgeTypeCounts: {},
        relationTypes: [],
        citationTypes: [],
        caseDomainCounts: {},
        multiVault: true,
        perVault: []
      }
    };
  }

  const nodesById = new Map();
  const edgesByKey = new Map();
  const caseAliasById = new Map();
  const caseIdentityById = new Map();
  const caseIdentityToCanonicalId = new Map();
  const perVault = [];
  let scannedFiles = 0;
  let truncated = false;
  let mergedDuplicateCases = 0;

  const normalizeCaseIdentityTitle = (value) =>
    String(value || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();

  const caseIdentityKeys = (node = {}) => {
    const title = normalizeCaseIdentityTitle(node.caseTitle || node.label || '');
    if (!title) return [];
    const decisionDate = String(node.decisionDate || '').trim();
    const decisionYear = extractYearFromDate(decisionDate || node.decisionYear || '');
    const caseCitation = normalizeCaseCitation(node.caseCitation || '');
    const keys = [];
    if (decisionDate && caseCitation) keys.push(`${title}|date:${decisionDate}|cite:${caseCitation}`);
    if (decisionYear && caseCitation) keys.push(`${title}|year:${decisionYear}|cite:${caseCitation}`);
    if (!caseCitation && decisionDate) keys.push(`${title}|date:${decisionDate}|cite:no_citation`);
    if (!caseCitation && !decisionDate && decisionYear) keys.push(`${title}|year:${decisionYear}|cite:no_citation`);
    return Array.from(new Set(keys)).filter(Boolean);
  };

  const mergeNode = (incomingNode = {}) => {
    const id = String(incomingNode.id || '').trim();
    if (!id) return;
    const existing = nodesById.get(id);
    if (!existing) {
      nodesById.set(id, { ...incomingNode });
      return;
    }
    for (const [key, value] of Object.entries(incomingNode)) {
      if (value === undefined || value === null || value === '') continue;
      if (Array.isArray(value)) {
        const prior = Array.isArray(existing[key]) ? existing[key] : [];
        existing[key] = mergeStringArraysUnique([...prior, ...value]);
        continue;
      }
      if (key === 'caseDomain') {
        const current = normalizeCaseDomain(existing.caseDomain || '');
        const next = normalizeCaseDomain(value);
        if (!next) continue;
        if (!current) {
          existing.caseDomain = next;
          continue;
        }
        if (current !== 'criminal' && next === 'criminal') {
          existing.caseDomain = next;
        }
        continue;
      }
      if (key === 'searchText') {
        const merged = mergeStringArraysUnique(
          `${String(existing.searchText || '')} ${String(value || '')}`.split(/\s+/g)
        );
        existing.searchText = merged.join(' ');
        continue;
      }
      if (existing[key] === undefined || existing[key] === null || existing[key] === '') {
        existing[key] = value;
      }
    }
  };

  const addEdge = (edge = {}) => {
    const sourceRaw = String(edge.source || '').trim();
    const targetRaw = String(edge.target || '').trim();
    const source = caseAliasById.get(sourceRaw) || sourceRaw;
    const target = caseAliasById.get(targetRaw) || targetRaw;
    if (!source || !target) return;
    const edgeType = String(edge.edgeType || 'link').trim();
    const relationType = normalizeEnumSuffix(edge.relationType || '');
    const citationType = normalizeEnumSuffix(edge.citationType || '');
    const key = `${source}=>${target}=>${edgeType}=>${relationType}=>${citationType}`;
    if (edgesByKey.has(key)) return;
    edgesByKey.set(key, {
      ...edge,
      source,
      target,
      edgeType,
      relationType,
      citationType
    });
  };

  for (const root of roots) {
    const graph = buildOntologyGraph(root, limit);
    const meta = graph?.meta || {};
    perVault.push({
      vaultRoot: root,
      ontologyRoot: String(meta.ontologyRoot || ''),
      nodes: Array.isArray(graph?.nodes) ? graph.nodes.length : 0,
      edges: Array.isArray(graph?.edges) ? graph.edges.length : 0,
      exists: meta.exists !== false,
      fallbackFromVault: meta.fallbackFromVault === true
    });
    scannedFiles += Number(meta.scannedFiles || 0);
    truncated = truncated || Boolean(meta.truncated);

    for (const node of Array.isArray(graph?.nodes) ? graph.nodes : []) {
      const sourceVaultRoot = path.resolve(root);
      const priorRoots = Array.isArray(node?.sourceVaultRoots) ? node.sourceVaultRoots : [];
      const incoming = {
        ...node,
        sourceVaultRoot: String(node?.sourceVaultRoot || sourceVaultRoot),
        sourceVaultRoots: mergeStringArraysUnique([sourceVaultRoot, ...priorRoots, node?.sourceVaultRoot])
      };
      const incomingId = String(incoming.id || '').trim();
      if (String(incoming.nodeType || '').toLowerCase() === 'case' && incomingId) {
        const identities = caseIdentityKeys(incoming);
        let mapped = '';
        let matchedIdentity = '';
        for (const identity of identities) {
          const candidate = caseIdentityToCanonicalId.get(identity);
          if (candidate && candidate !== incomingId) {
            mapped = candidate;
            matchedIdentity = identity;
            break;
          }
        }
        if (mapped) {
          caseAliasById.set(incomingId, mapped);
          caseIdentityById.set(incomingId, matchedIdentity);
          incoming.id = mapped;
          if (!incoming.caseId) incoming.caseId = mapped;
          mergedDuplicateCases += 1;
        } else {
          for (const identity of identities) {
            caseIdentityToCanonicalId.set(identity, incomingId);
          }
          caseIdentityById.set(incomingId, identities[0] || '');
          caseAliasById.set(incomingId, incomingId);
        }
      }
      mergeNode(incoming);
    }
    for (const edge of Array.isArray(graph?.edges) ? graph.edges : []) {
      addEdge(edge);
    }
  }

  const nodes = Array.from(nodesById.values());
  const edges = Array.from(edgesByKey.values());
  const nodeTypeCounts = {};
  const edgeTypeCounts = {};
  const relationTypes = new Set();
  const citationTypes = new Set();
  const caseDomainCounts = {};

  for (const node of nodes) {
    const nodeType = String(node.nodeType || 'unknown').toLowerCase();
    nodeTypeCounts[nodeType] = (nodeTypeCounts[nodeType] || 0) + 1;
    if (nodeType === 'case') {
      const caseDomain = normalizeCaseDomain(node.caseDomain || '') || 'civil';
      caseDomainCounts[caseDomain] = (caseDomainCounts[caseDomain] || 0) + 1;
    }
  }
  for (const edge of edges) {
    const edgeType = String(edge.edgeType || 'link').toLowerCase();
    edgeTypeCounts[edgeType] = (edgeTypeCounts[edgeType] || 0) + 1;
    const relationType = normalizeEnumSuffix(edge.relationType || '');
    const citationType = normalizeEnumSuffix(edge.citationType || '');
    if (relationType) relationTypes.add(relationType);
    if (citationType) citationTypes.add(citationType);
  }

  if (!nodes.length && !edges.length) {
    const dbGraph = buildCaselawGraphFromDb(limit);
    if (dbGraph && (Array.isArray(dbGraph.nodes) ? dbGraph.nodes.length : 0)) {
      const enriched = enrichCaselawDbGraphMeta(dbGraph, roots, 'vault_ontology_empty');
      enriched.meta.perVault = perVault;
      enriched.meta.scannedFiles = Number(enriched.meta.scannedFiles || 0);
      return enriched;
    }
  }

  return {
    nodes,
    edges,
    meta: {
      ontologyRoot: roots.length === 1 ? roots[0] : `multiple vaults (${roots.length})`,
      exists: nodes.length > 0 || edges.length > 0,
      source: 'multi_vault',
      selectedVaultRoots: roots,
      scannedFiles,
      truncated,
      nodeTypeCounts,
      edgeTypeCounts,
      relationTypes: Array.from(relationTypes).sort(),
      citationTypes: Array.from(citationTypes).sort(),
      caseDomainCounts,
      multiVault: true,
      perVault,
      mergedDuplicateCases
    }
  };
}

function searchVault(vaultRoot, query, maxResults = 20) {
  return searchVaultScored(vaultRoot, query, maxResults).map((item) => ({
    path: item.path,
    snippet: item.snippet
  }));
}

function normalizeFederalCitation(value) {
  let text = sanitizeSingleLine(value, 180);
  if (!text) return '';

  text = text
    .replace(/\bU\s*\.?\s*S\s*\.?/gi, 'U.S.')
    .replace(/\bS\s*\.?\s*Ct\s*\.?/gi, 'S. Ct.')
    .replace(/\bL\s*\.?\s*Ed\s*\.?\s*2d\b/gi, 'L. Ed. 2d')
    .replace(/\bL\s*\.?\s*Ed\s*\.?/gi, 'L. Ed.')
    .replace(/\bF\s*\.?\s*Supp\s*\.?\s*3d\b/gi, 'F. Supp. 3d')
    .replace(/\bF\s*\.?\s*Supp\s*\.?\s*2d\b/gi, 'F. Supp. 2d')
    .replace(/\bF\s*\.?\s*Supp\s*\.?/gi, 'F. Supp.')
    .replace(/\bF\s*\.?\s*App(?:'|’)?x\b/gi, "F. App'x")
    .replace(/\bF\s*\.?\s*4th\b/gi, 'F.4th')
    .replace(/\bF\s*\.?\s*3d\b/gi, 'F.3d')
    .replace(/\bF\s*\.?\s*2d\b/gi, 'F.2d')
    .replace(/\.{2,}/g, '.')
    // Normalize nominative reporters like: 5 U.S. (1 Cranch) 137 -> 5 U.S. 137
    .replace(/\(\s*[^()\r\n]{1,80}\s*\)\s*(?=\d{1,5}\b)/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  const match = text.match(/^(\d{1,4})\s+(.+?)\s+(\d{1,5})$/);
  if (!match) return '';
  const volume = String(Number(match[1]));
  const reporter = String(match[2] || '')
    .replace(/\s+/g, ' ')
    .trim();
  const page = String(Number(match[3]));
  if (!reporter || reporter.toLowerCase() === 'f.') return '';
  return `${volume} ${reporter} ${page}`;
}

function extractFederalCitationsFromInput(value) {
  const raw = String(value || '');
  const collected = [];

  for (const match of raw.match(FEDERAL_CITATION_PATTERN) || []) {
    const normalized = normalizeFederalCitation(match);
    if (normalized) collected.push(normalized);
  }
  if (collected.length) return Array.from(new Set(collected));

  const fallbackChunks = raw
    .split(/[\r\n,;]+/g)
    .map((item) => sanitizeSingleLine(item, 180))
    .filter(Boolean);
  for (const chunk of fallbackChunks) {
    if (!/\d/.test(chunk) || !FEDERAL_CITATION_HINT_PATTERN.test(chunk)) continue;
    const normalized = normalizeFederalCitation(chunk);
    if (normalized) collected.push(normalized);
  }
  return Array.from(new Set(collected));
}

function resolveFederalCapCasesDirs() {
  const roots = [];
  for (const candidate of FEDERAL_CAP_CASES_CANDIDATE_DIRS) {
    const resolved = path.resolve(String(candidate || ''));
    if (!resolved || roots.includes(resolved)) continue;
    if (!pathIsDirectory(resolved)) continue;
    roots.push(resolved);
  }
  return roots;
}

function getFederalCapCitationFiles() {
  const files = [];
  for (const root of resolveFederalCapCasesDirs()) {
    let entries = [];
    try {
      entries = fs.readdirSync(root, { withFileTypes: true });
    } catch {
      entries = [];
    }
    for (const entry of entries) {
      if (!entry || !entry.isFile()) continue;
      if (!/^cases_.*\.jsonl$/i.test(entry.name)) continue;
      files.push(path.join(root, entry.name));
    }
  }
  files.sort((a, b) => a.localeCompare(b));
  if (files.length) {
    federalCapCitationFilesCache = files;
    return files;
  }
  if (Array.isArray(federalCapCitationFilesCache) && federalCapCitationFilesCache.length) {
    return federalCapCitationFilesCache;
  }
  return [];
}

function createFederalCapCitationFilesSignature(citationFiles = []) {
  const parts = [];
  for (const file of citationFiles) {
    if (!file) continue;
    try {
      const stat = fs.statSync(file);
      parts.push(`${file}:${Number(stat.size) || 0}:${Math.trunc(Number(stat.mtimeMs) || 0)}`);
    } catch {
      parts.push(`${file}:missing`);
    }
  }
  parts.sort((a, b) => a.localeCompare(b));
  return parts.join('|');
}

async function buildFederalCapCitationIndex(citationFiles = []) {
  const startedAt = Date.now();
  const entries = new Map();
  let scannedFiles = 0;
  let scannedLines = 0;

  for (const file of citationFiles) {
    if (!file) continue;
    scannedFiles += 1;
    const stream = fs.createReadStream(file, { encoding: 'utf-8' });
    const lineReader = readline.createInterface({ input: stream, crlfDelay: Infinity });

    try {
      for await (const line of lineReader) {
        scannedLines += 1;
        const trimmed = String(line || '').trim();
        if (!trimmed) continue;

        let record = null;
        try {
          record = JSON.parse(trimmed);
        } catch {
          record = null;
        }
        if (!record || typeof record !== 'object') continue;

        const rawCitations = Array.isArray(record.citations) ? record.citations : [];
        if (!rawCitations.length) continue;
        const summary = summarizeFederalCitationHit(record);
        for (const rawCitation of rawCitations) {
          const normalized = normalizeCapCitationEntry(rawCitation);
          if (!normalized || entries.has(normalized)) continue;
          entries.set(normalized, summary);
        }
      }
    } finally {
      lineReader.close();
      stream.destroy();
    }
  }

  return {
    signature: createFederalCapCitationFilesSignature(citationFiles),
    entries,
    scannedFiles,
    scannedLines,
    buildMs: Date.now() - startedAt
  };
}

async function getFederalCapCitationIndex(citationFiles = []) {
  const signature = createFederalCapCitationFilesSignature(citationFiles);
  if (
    federalCapCitationIndexCache &&
    typeof federalCapCitationIndexCache === 'object' &&
    federalCapCitationIndexCache.signature === signature &&
    federalCapCitationIndexCache.entries instanceof Map
  ) {
    return {
      entries: federalCapCitationIndexCache.entries,
      scannedFiles: 0,
      scannedLines: 0,
      buildMs: 0,
      rebuilt: false
    };
  }

  const built = await buildFederalCapCitationIndex(citationFiles);
  federalCapCitationIndexCache = built;
  return {
    entries: built.entries,
    scannedFiles: built.scannedFiles,
    scannedLines: built.scannedLines,
    buildMs: built.buildMs,
    rebuilt: true
  };
}

function normalizeCapCitationEntry(entry) {
  if (typeof entry === 'string') return normalizeFederalCitation(entry);
  if (!entry || typeof entry !== 'object') return '';
  return normalizeFederalCitation(entry.cite || entry.citation || '');
}

function summarizeFederalCitationHit(record = {}) {
  return {
    caseName: sanitizeSingleLine(record.case_name || record.name_abbreviation || record.name || '', 180),
    court: sanitizeSingleLine(record.court || '', 120),
    decisionDate: String(record.decision_date || '').trim(),
    jurisdiction: sanitizeSingleLine(record.jurisdiction || '', 80),
    reporterSlug: sanitizeSingleLine(record.reporter_slug || '', 40),
    source: 'cap_local'
  };
}

function extractNormalizedCitationsFromCourtListenerRecord(record = {}) {
  const values = Array.isArray(record?.citation) ? record.citation : [];
  const normalized = [];
  for (const value of values) {
    const parsed = normalizeFederalCitation(value);
    if (parsed) normalized.push(parsed);
  }
  return Array.from(new Set(normalized));
}

function summarizeCourtListenerCitationHit(record = {}) {
  return {
    caseName: sanitizeSingleLine(record.caseName || record.caseNameFull || '', 180),
    court: sanitizeSingleLine(record.court_citation_string || record.court || record.court_id || '', 120),
    decisionDate: String(record.dateFiled || record.dateArgued || '').trim(),
    jurisdiction: sanitizeSingleLine(record.court_jurisdiction || '', 80),
    reporterSlug: '',
    source: 'courtlistener'
  };
}

async function lookupFederalCitationViaCourtListener(citation) {
  if (!FEDERAL_CITATION_REMOTE_FALLBACK_ENABLED) return null;
  if (!citation) return null;
  if (federalCitationRemoteLookupCache.has(citation)) {
    return federalCitationRemoteLookupCache.get(citation) || null;
  }

  const url = new URL(COURTLISTENER_CITATION_SEARCH_URL);
  url.searchParams.set('type', 'o');
  url.searchParams.set('page_size', '5');
  url.searchParams.set('q', `citation:"${citation}"`);

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), FEDERAL_CITATION_REMOTE_TIMEOUT_MS);
  try {
    const resp = await fetch(url.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal
    });
    if (!resp.ok) {
      federalCitationRemoteLookupCache.set(citation, null);
      return null;
    }
    const payload = await resp.json().catch(() => null);
    const results = Array.isArray(payload?.results) ? payload.results : [];
    for (const result of results) {
      const citations = extractNormalizedCitationsFromCourtListenerRecord(result);
      if (!citations.includes(citation)) continue;
      const summary = summarizeCourtListenerCitationHit(result);
      federalCitationRemoteLookupCache.set(citation, summary);
      return summary;
    }
  } catch {
    // Network/API failures should not block local validation.
  } finally {
    clearTimeout(timeoutHandle);
  }

  federalCitationRemoteLookupCache.set(citation, null);
  return null;
}

async function lookupFederalCitations(citations = []) {
  const targets = Array.from(new Set((Array.isArray(citations) ? citations : []).map((c) => String(c || '').trim()).filter(Boolean)));
  const pending = new Set(targets);
  const found = new Map();
  let scannedFiles = 0;
  let scannedLines = 0;
  let indexBuildMs = 0;
  let remoteChecked = 0;
  let remoteFound = 0;

  for (const citation of targets) {
    if (!federalCitationLookupCache.has(citation)) continue;
    const cached = federalCitationLookupCache.get(citation);
    if (cached) {
      pending.delete(citation);
      found.set(citation, cached);
    }
  }

  if (!pending.size) {
    return {
      found,
      missing: [],
      scannedFiles: 0,
      scannedLines: 0,
      totalFiles: getFederalCapCitationFiles().length,
      indexBuildMs: 0,
      remoteChecked: 0,
      remoteFound: 0
    };
  }

  const citationFiles = getFederalCapCitationFiles();
  if (pending.size) {
    const localIndex = await getFederalCapCitationIndex(citationFiles);
    scannedFiles = Number(localIndex.scannedFiles) || 0;
    scannedLines = Number(localIndex.scannedLines) || 0;
    indexBuildMs = Number(localIndex.buildMs) || 0;
    const entries = localIndex.entries instanceof Map ? localIndex.entries : new Map();
    for (const citation of Array.from(pending)) {
      const summary = entries.get(citation) || null;
      if (!summary) continue;
      found.set(citation, summary);
      federalCitationLookupCache.set(citation, summary);
      pending.delete(citation);
    }
  }

  if (pending.size && FEDERAL_CITATION_REMOTE_FALLBACK_ENABLED && FEDERAL_CITATION_REMOTE_MAX_LOOKUPS > 0) {
    const remoteTargets = Array.from(pending).slice(0, FEDERAL_CITATION_REMOTE_MAX_LOOKUPS);
    for (const citation of remoteTargets) {
      remoteChecked += 1;
      const remoteHit = await lookupFederalCitationViaCourtListener(citation);
      if (!remoteHit) continue;
      remoteFound += 1;
      found.set(citation, remoteHit);
      federalCitationLookupCache.set(citation, remoteHit);
      pending.delete(citation);
    }
  }

  return {
    found,
    missing: Array.from(pending),
    scannedFiles,
    scannedLines,
    totalFiles: citationFiles.length,
    indexBuildMs,
    remoteChecked,
    remoteFound
  };
}

async function runFederalCitationCheck(inputText) {
  const rawInput = String(inputText || '').trim();
  const citations = extractFederalCitationsFromInput(rawInput);
  if (!citations.length) {
    return {
      ok: true,
      agentResponse:
        'Citation Checker: no recognizable federal reporter citations were found. Enter citations like "410 U.S. 113" or "792 F.3d 847".',
      citations: [],
      stats: {
        checked: 0,
        valid: 0,
        invalid: 0,
        scannedFiles: 0,
        scannedLines: 0,
        totalFiles: getFederalCapCitationFiles().length,
        indexBuildMs: 0,
        remoteChecked: 0,
        remoteFound: 0
      }
    };
  }

  const lookup = await lookupFederalCitations(citations);
  const citationResults = citations.map((citation) => {
    const hit = lookup.found.get(citation) || null;
    return {
      citation,
      valid: Boolean(hit),
      match: hit
    };
  });

  const validCount = citationResults.filter((item) => item.valid).length;
  const invalidCount = citationResults.length - validCount;
  const remoteChecked = Number(lookup.remoteChecked) || 0;
  const remoteFound = Number(lookup.remoteFound) || 0;
  const introSuffix = remoteChecked
    ? ` CourtListener fallback resolved ${remoteFound} of ${remoteChecked} CAP misses.`
    : '';
  const intro = `Citation Checker Agent: checked ${citationResults.length} federal citation${citationResults.length === 1 ? '' : 's'} against the CAP federal corpus. ${validCount} valid, ${invalidCount} invalid.${introSuffix}`;
  const details = citationResults.map((item) => {
    if (!item.valid) return `INVALID: ${item.citation}`;
    const namePart = item.match?.caseName ? ` (${item.match.caseName})` : '';
    const datePart = item.match?.decisionDate ? ` - ${item.match.decisionDate}` : '';
    const sourcePart = item.match?.source === 'courtlistener' ? ' [CourtListener]' : '';
    return `VALID: ${item.citation}${namePart}${datePart}${sourcePart}`;
  });

  return {
    ok: true,
    agentResponse: [intro, ...details].join('\n'),
    citations: citationResults,
    stats: {
      checked: citationResults.length,
      valid: validCount,
      invalid: invalidCount,
      scannedFiles: lookup.scannedFiles,
      scannedLines: lookup.scannedLines,
      totalFiles: lookup.totalFiles,
      indexBuildMs: lookup.indexBuildMs,
      remoteChecked,
      remoteFound
    }
  };
}

function searchVaultScored(vaultRoot, query, maxResults = 20) {
  const rawQuery = String(query || '').trim();
  const q = rawQuery.toLowerCase();
  if (!q) return [];

  const STOPWORDS = new Set([
    'a',
    'an',
    'and',
    'are',
    'as',
    'at',
    'be',
    'by',
    'for',
    'from',
    'how',
    'i',
    'in',
    'is',
    'it',
    'of',
    'on',
    'or',
    'that',
    'the',
    'this',
    'to',
    'was',
    'what',
    'when',
    'where',
    'who',
    'why',
    'with'
  ]);

  const tokens = Array.from(
    new Set(
      q
        .split(/[^a-z0-9_]+/)
        .map((t) => t.trim())
        .filter((t) => t.length >= 2 && !STOPWORDS.has(t))
    )
  );

  const files = walkMarkdownFiles(vaultRoot, 4000);
  const scored = [];

  for (const file of files) {
    const relPath = toRel(vaultRoot, file);
    const relLower = relPath.toLowerCase();
    const baseLower = path.basename(relPath).toLowerCase();

    let text = '';
    try {
      text = fs.readFileSync(file, 'utf-8');
    } catch {
      continue;
    }
    const textLower = text.toLowerCase();

    let score = 0;
    let snippetIdx = -1;

    const phraseIdx = q.length >= 4 ? textLower.indexOf(q) : -1;
    if (phraseIdx !== -1) {
      score += 80;
      snippetIdx = phraseIdx;
    }

    const phrasePathIdx = q.length >= 3 ? relLower.indexOf(q) : -1;
    if (phrasePathIdx !== -1) {
      score += 35;
      if (snippetIdx === -1) snippetIdx = 0;
    }

    for (const token of tokens) {
      const tokenInTextIdx = textLower.indexOf(token);
      if (tokenInTextIdx !== -1) {
        score += token.length >= 5 ? 12 : 8;
        if (snippetIdx === -1 || tokenInTextIdx < snippetIdx) snippetIdx = tokenInTextIdx;
      }
      if (relLower.includes(token)) score += 10;
      if (baseLower.includes(token)) score += 6;
    }

    if (score <= 0) continue;

    const idx = snippetIdx >= 0 ? snippetIdx : 0;
    const span = Math.max(120, q.length + 60);
    const start = Math.max(0, idx - span);
    const end = Math.min(text.length, idx + span);
    const snippet = text.slice(start, end).replace(/\s+/g, ' ').trim();

    scored.push({
      path: relPath,
      snippet,
      score
    });
  }

  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.path.localeCompare(b.path);
  });

  return scored.slice(0, maxResults);
}

function searchVaultAcrossRoots(vaultRoots = [], query, maxResults = 20) {
  const roots = [];
  for (const raw of Array.isArray(vaultRoots) ? vaultRoots : []) {
    const trimmed = String(raw || '').trim();
    if (!trimmed) continue;
    const resolved = path.resolve(trimmed);
    if (!resolved || roots.includes(resolved)) continue;
    if (!pathIsDirectory(resolved)) continue;
    roots.push(resolved);
  }
  if (!roots.length) return [];

  const perRootLimit = Math.max(8, Number(maxResults) || 20);
  const combined = [];
  for (const root of roots) {
    const matches = searchVaultScored(root, query, perRootLimit);
    for (const match of matches) {
      combined.push({
        vaultRoot: root,
        path: match.path,
        snippet: match.snippet,
        score: Number(match.score) || 0
      });
    }
  }

  combined.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    const pathCmp = String(a.path || '').localeCompare(String(b.path || ''));
    if (pathCmp) return pathCmp;
    return String(a.vaultRoot || '').localeCompare(String(b.vaultRoot || ''));
  });

  return combined.slice(0, maxResults).map((item) => ({
    vaultRoot: item.vaultRoot,
    path: item.path,
    snippet: item.snippet
  }));
}

function normalizeAgentViewKind(value = '') {
  const kind = String(value || '').trim().toLowerCase();
  return kind === 'caselaw' ? 'caselaw' : 'casefile';
}

function buildAgentContextPath(vaultRoot, relPath, multiVault = false, usedPaths = new Set()) {
  const normalizedRelPath = String(relPath || '')
    .replaceAll('\\', '/')
    .replace(/^\/+/, '');
  if (!multiVault) return normalizedRelPath;

  const label = inferJurisdictionLabelFromVaultPath(vaultRoot) || path.basename(vaultRoot) || vaultRoot;
  const primary = `${label} :: ${normalizedRelPath}`;
  if (!usedPaths.has(primary)) return primary;

  const withLeaf = `${label} (${path.basename(vaultRoot) || 'vault'}) :: ${normalizedRelPath}`;
  if (!usedPaths.has(withLeaf)) return withLeaf;

  const withRoot = `${path.resolve(vaultRoot)} :: ${normalizedRelPath}`;
  if (!usedPaths.has(withRoot)) return withRoot;

  let index = 2;
  while (usedPaths.has(`${withRoot} [${index}]`)) {
    index += 1;
  }
  return `${withRoot} [${index}]`;
}

function extractResponseText(data) {
  if (!data || typeof data !== 'object') return '';
  if (typeof data.output_text === 'string' && data.output_text.trim()) return data.output_text.trim();
  if (!Array.isArray(data.output)) return '';

  const textParts = [];
  for (const item of data.output) {
    if (!item || item.type !== 'message' || !Array.isArray(item.content)) continue;
    for (const part of item.content) {
      if (part && typeof part.text === 'string' && part.text.trim()) {
        textParts.push(part.text.trim());
      }
    }
  }
  return textParts.join('\n').trim();
}

function parseAgentStructuredReply(rawText, allowedPaths = []) {
  const text = String(rawText || '').trim();
  if (!text) return { answer: '', usedContextPaths: [] };

  const allowedSet = new Set((Array.isArray(allowedPaths) ? allowedPaths : []).map((p) => String(p)));
  const candidates = [text];

  const fencedJson = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fencedJson && fencedJson[1]) candidates.push(fencedJson[1].trim());

  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    candidates.push(text.slice(firstBrace, lastBrace + 1));
  }

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (!parsed || typeof parsed !== 'object') continue;

      const answer = typeof parsed.answer === 'string' ? parsed.answer.trim() : '';
      const usedContextPaths = Array.isArray(parsed.usedContextPaths)
        ? Array.from(
            new Set(
              parsed.usedContextPaths
                .map((p) => String(p || '').trim())
                .filter((p) => p && allowedSet.has(p))
            )
          )
        : [];

      if (answer) return { answer, usedContextPaths };
    } catch {
      // ignore parse failures and continue to next candidate
    }
  }

  return { answer: text, usedContextPaths: [] };
}

async function runAgent(vaultRoot, prompt, history = [], options = {}) {
  if (!OPENAI_API_KEY) {
    throw new Error('Missing OPENAI_API_KEY (or ACQUITTIFY_OPENAI_API_KEY) for Agent sidebar.');
  }

  const activeVaultRoot = path.resolve(String(vaultRoot || '').trim());
  const viewKind = normalizeAgentViewKind(options?.viewKind);
  const caselawRoots = normalizeCaselawVaultRoots(options?.caselawVaultRoots, activeVaultRoot);
  const retrievalRoots = viewKind === 'caselaw' && caselawRoots.length ? caselawRoots : [activeVaultRoot];
  const isMultiVault = retrievalRoots.length > 1;
  const search = searchVaultAcrossRoots(retrievalRoots, prompt, isMultiVault ? 18 : 12);
  const context = [];
  const usedContextPaths = new Set();
  for (const r of search.slice(0, 8)) {
    const sourceRoot = path.resolve(String(r.vaultRoot || activeVaultRoot));
    const abs = ensureInsideVault(sourceRoot, path.join(sourceRoot, r.path));
    let content = '';
    try {
      content = fs.readFileSync(abs, 'utf-8').slice(0, 3500);
    } catch {
      continue;
    }
    const contextPath = buildAgentContextPath(sourceRoot, r.path, isMultiVault, usedContextPaths);
    usedContextPaths.add(contextPath);
    context.push({
      path: contextPath,
      snippet: r.snippet,
      content,
      vaultRoot: sourceRoot,
      vaultLabel: inferJurisdictionLabelFromVaultPath(sourceRoot)
    });
  }

  const contextPaths = context.map((c) => c.path);
  const system = [
    'You are an ontology and vault operations assistant inside an Obsidian-like case intelligence workspace.',
    'A vault (or selected set of caselaw vaults) is already mounted and searchable. Never ask the user to paste/upload vault context.',
    'Use only provided vault context for factual claims.',
    'Do not cite or reference a source path unless it directly supports your answer.',
    'If the retrieved context is insufficient, say exactly what is missing and suggest 1-2 concise follow-up search prompts.',
    'Be concise and specific.',
    'When proposing YAML/ontology edits, provide exact field-level recommendations.',
    'Return ONLY valid JSON with this exact shape:',
    '{"answer":"<response to user>","usedContextPaths":["<path1>","<path2>"]}',
    'Rules for usedContextPaths:',
    '- Include only paths from the provided context array.',
    '- Include only paths materially used in the answer.',
    '- Use an empty array when no context path supports the answer.'
  ].join('\n');

  const priorTurns = Array.isArray(history)
    ? history
        .filter((m) => m && (m.role === 'user' || m.role === 'assistant') && typeof m.text === 'string')
        .slice(-16)
        .map((m) => ({
          role: m.role,
          text: m.text.slice(0, 5000)
        }))
    : [];

  const user = JSON.stringify(
    {
      prompt,
      history: priorTurns,
      retrieval: {
        viewKind,
        scope: isMultiVault ? 'multi_vault' : 'single_vault',
        vaultRoots: retrievalRoots,
        retrievedCount: context.length,
        retrievedPaths: contextPaths
      },
      context
    },
    null,
    2
  );
  const resp = await fetch(`${OPENAI_BASE_URL}/responses`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${OPENAI_API_KEY}`
    },
    body: JSON.stringify({
      model: OPENAI_MODEL,
      input: [
        {
          role: 'system',
          content: [{ type: 'input_text', text: system }]
        },
        {
          role: 'user',
          content: [{ type: 'input_text', text: user }]
        }
      ]
    })
  });
  if (!resp.ok) {
    const detail = (await resp.text()).slice(0, 600);
    throw new Error(`Agent request failed: ${resp.status} ${detail}`);
  }
  const data = await resp.json();
  const rawText = extractResponseText(data) || 'No response.';
  const parsed = parseAgentStructuredReply(rawText, contextPaths);

  return {
    answer: parsed.answer || rawText,
    contextPaths: parsed.usedContextPaths,
    model: OPENAI_MODEL,
    responseId: data?.id || null
  };
}

function getWhatsAppSessionsPath() {
  return path.join(app.getPath('userData'), WHATSAPP_SESSIONS_FILE);
}

function loadWhatsAppSessions() {
  let parsed = {};
  try {
    const raw = fs.readFileSync(getWhatsAppSessionsPath(), 'utf-8');
    const data = JSON.parse(raw);
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      parsed = data;
    }
  } catch {
    parsed = {};
  }
  whatsappSessions = parsed;
}

function persistWhatsAppSessions() {
  try {
    const target = getWhatsAppSessionsPath();
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, JSON.stringify(whatsappSessions, null, 2), 'utf-8');
  } catch (err) {
    console.error('[whatsapp] Failed to persist sessions:', err?.message || err);
  }
}

function getWhatsAppSessionKey(from, to) {
  const fromSafe = String(from || '').trim().toLowerCase();
  const toSafe = String(to || '').trim().toLowerCase();
  return `${fromSafe}::${toSafe}`;
}

function getWhatsAppSession(from, to) {
  const key = getWhatsAppSessionKey(from, to);
  if (!whatsappSessions[key] || typeof whatsappSessions[key] !== 'object') {
    whatsappSessions[key] = {
      mode: WHATSAPP_DEFAULT_MODE,
      history: [],
      updatedAt: new Date().toISOString(),
      lastInboundSid: '',
      lastResponseText: ''
    };
  }
  if (!Array.isArray(whatsappSessions[key].history)) {
    whatsappSessions[key].history = [];
  }
  if (whatsappSessions[key].mode !== 'caselaw') {
    whatsappSessions[key].mode = 'casefile';
  }
  return { key, session: whatsappSessions[key] };
}

function trimWhatsappResponse(text) {
  const value = String(text || '').trim() || 'No response.';
  if (value.length <= WHATSAPP_MAX_MESSAGE_CHARS) return value;
  const suffix = '\n\n[truncated]';
  const keep = Math.max(0, WHATSAPP_MAX_MESSAGE_CHARS - suffix.length);
  return `${value.slice(0, keep).trimEnd()}${suffix}`;
}

function appendWhatsAppHistory(session, role, text) {
  if (!session || !Array.isArray(session.history)) return;
  if (role !== 'user' && role !== 'assistant') return;
  const compact = String(text || '').trim();
  if (!compact) return;
  session.history.push({
    role,
    text: compact.slice(0, 5000)
  });
  const maxTurns = WHATSAPP_HISTORY_LIMIT * 2;
  if (session.history.length > maxTurns) {
    session.history = session.history.slice(-maxTurns);
  }
}

function buildIdentityKeys(value) {
  const raw = String(value || '').trim().toLowerCase();
  const keys = new Set();
  if (!raw) return keys;

  keys.add(raw);
  const withoutPrefix = raw.startsWith('whatsapp:') ? raw.slice('whatsapp:'.length) : raw;
  if (withoutPrefix) {
    keys.add(withoutPrefix);
    keys.add(`whatsapp:${withoutPrefix}`);
    const digits = withoutPrefix.replace(/[^\d]/g, '');
    if (digits) {
      keys.add(digits);
      keys.add(`+${digits}`);
      keys.add(`whatsapp:+${digits}`);
    }
  }
  return keys;
}

function isWhatsAppSenderAuthorized(sender) {
  if (!WHATSAPP_ENFORCE_ALLOWLIST) return true;
  if (!WHATSAPP_ALLOWED_NUMBERS.size) return false;

  const senderKeys = buildIdentityKeys(sender);
  if (!senderKeys.size) return false;

  for (const allowed of WHATSAPP_ALLOWED_NUMBERS) {
    const allowedKeys = buildIdentityKeys(allowed);
    for (const key of allowedKeys) {
      if (senderKeys.has(key)) {
        return true;
      }
    }
  }
  return false;
}

function formatCitationBlock(citations = []) {
  const normalized = Array.from(
    new Set(
      (Array.isArray(citations) ? citations : [])
        .map((entry) => String(entry || '').trim())
        .filter(Boolean)
    )
  );
  if (!normalized.length) return '';
  return `Citations:\n${normalized.map((entry, idx) => `[${idx + 1}] ${entry}`).join('\n')}`;
}

function composeWhatsAppMessage(body, citations = []) {
  const base = String(body || '').trim() || 'No response.';
  const citationBlock = formatCitationBlock(citations);
  if (!citationBlock) return trimWhatsappResponse(base);
  return trimWhatsappResponse(`${base}\n\n${citationBlock}`);
}

function compactInline(value, maxChars = 120) {
  const compact = String(value || '').replace(/\s+/g, ' ').trim();
  if (!compact) return '';
  if (compact.length <= maxChars) return compact;
  return `${compact.slice(0, Math.max(1, maxChars - 3)).trimEnd()}...`;
}

function splitCommandArgs(text) {
  const raw = String(text || '').trim();
  if (!raw) return [];
  return raw.split(/\s+/).filter(Boolean);
}

function parseWhatsAppCommand(text) {
  const trimmed = String(text || '').trim();
  if (!trimmed.startsWith('/')) return null;
  const match = trimmed.match(/^\/([a-z0-9_-]+)\b\s*([\s\S]*)$/i);
  if (!match) return null;

  const cmd = String(match[1] || '').toLowerCase();
  const rest = String(match[2] || '').trim();
  const args = splitCommandArgs(rest);

  if (cmd === 'matters') {
    return { kind: 'matters', query: rest };
  }
  if (cmd === 'matter') {
    return { kind: 'matter', matterId: args[0] || '' };
  }
  if (cmd === 'status') {
    return { kind: 'status', matterId: args[0] || '' };
  }
  if (cmd === 'docs') {
    return {
      kind: 'docs',
      matterId: args[0] || '',
      query: args.length > 1 ? rest.slice(rest.indexOf(args[1])) : ''
    };
  }
  if (cmd === 'doc') {
    const documentId = args[0] || '';
    let maxChars = WHATSAPP_MAX_DOC_EXCERPT_CHARS;
    if (args.length > 1 && /^\d+$/.test(args[1])) {
      maxChars = Math.max(120, Number(args[1]) || WHATSAPP_MAX_DOC_EXCERPT_CHARS);
    }
    return {
      kind: 'doc',
      documentId,
      maxChars
    };
  }
  return null;
}

async function requestPeregrine(method, routePath, params = null, payload = null) {
  const url = new URL(routePath, `${PEREGRINE_API_URL}/`);
  if (params && typeof params === 'object') {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue;
      url.searchParams.set(key, String(value));
    }
  }

  const headers = {
    Accept: 'application/json'
  };
  if (payload !== null) {
    headers['Content-Type'] = 'application/json';
  }
  if (PEREGRINE_API_TOKEN) {
    headers.Authorization = `Bearer ${PEREGRINE_API_TOKEN}`;
  }

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), PEREGRINE_API_TIMEOUT_MS);
  let resp;
  try {
    resp = await fetch(url.toString(), {
      method,
      headers,
      body: payload !== null ? JSON.stringify(payload) : undefined,
      signal: controller.signal
    });
  } finally {
    clearTimeout(timeoutHandle);
  }

  const contentType = String(resp.headers.get('content-type') || '').toLowerCase();
  const raw = await resp.text();
  if (!resp.ok) {
    const detail = compactInline(raw || `${resp.status}`, 300);
    throw new Error(`Peregrine API ${resp.status} (${routePath}): ${detail}`);
  }

  if (!raw) return {};
  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }

  try {
    return JSON.parse(raw);
  } catch {
    return { raw };
  }
}

function renderMatterLine(matter) {
  const id = String(
    matter?.external_id ||
      matter?.id ||
      matter?.matter_id ||
      matter?.uuid ||
      ''
  ).trim();
  const name = compactInline(
    matter?.title ||
      matter?.name ||
      matter?.caption ||
      matter?.case_name ||
      matter?.display_name ||
      'Untitled matter',
    72
  );
  const status = compactInline(matter?.status || matter?.state || matter?.stage || '', 24);
  return [id || '(no-id)', name, status].filter(Boolean).join(' | ');
}

function normalizeStatusCounts(payload) {
  if (!payload || typeof payload !== 'object') return {};
  if (payload.counts && typeof payload.counts === 'object') return payload.counts;
  if (payload.status_counts && typeof payload.status_counts === 'object') return payload.status_counts;
  const directEntries = Object.entries(payload).filter(([, value]) => typeof value === 'number');
  if (!directEntries.length) return {};
  return Object.fromEntries(directEntries);
}

async function executeWhatsAppCommand(command) {
  if (!command || typeof command !== 'object') {
    return composeWhatsAppMessage('Unsupported command.');
  }

  if (command.kind === 'matters') {
    const payload = await requestPeregrine('GET', '/matters');
    const matters = Array.isArray(payload?.matters) ? payload.matters : [];
    const query = String(command.query || '').trim().toLowerCase();
    const filtered = query
      ? matters.filter((matter) =>
          compactInline(
            [
              matter?.id,
              matter?.external_id,
              matter?.title,
              matter?.name,
              matter?.caption,
              matter?.case_name
            ]
              .filter(Boolean)
              .join(' '),
            400
          )
            .toLowerCase()
            .includes(query)
        )
      : matters;

    if (!filtered.length) {
      return composeWhatsAppMessage('No matters found.', ['Peregrine GET /matters']);
    }

    const lines = filtered.slice(0, WHATSAPP_MAX_LIST_ITEMS).map((matter, idx) => `${idx + 1}) ${renderMatterLine(matter)}`);
    const remaining = Math.max(0, filtered.length - lines.length);
    const footer = remaining ? `\n...and ${remaining} more.` : '';
    return composeWhatsAppMessage(`Matters (${filtered.length}):\n${lines.join('\n')}${footer}`, [
      'Peregrine GET /matters'
    ]);
  }

  if (command.kind === 'matter') {
    const matterId = String(command.matterId || '').trim();
    if (!matterId) {
      return composeWhatsAppMessage('Usage: /matter <matter_id>');
    }
    const encodedId = encodeURIComponent(matterId);
    const matter = await requestPeregrine('GET', `/matters/${encodedId}`);
    let statusPayload = {};
    try {
      statusPayload = await requestPeregrine('GET', `/matters/${encodedId}/documents/status`);
    } catch {
      statusPayload = {};
    }
    const counts = normalizeStatusCounts(statusPayload);
    const countsLine = Object.entries(counts)
      .slice(0, 8)
      .map(([k, v]) => `${k}:${v}`)
      .join(', ');
    const body = [
      `Matter: ${compactInline(matter?.title || matter?.name || matter?.caption || matter?.case_name || 'Untitled', 120)}`,
      `ID: ${compactInline(matter?.id || '', 80) || '(missing)'}`,
      `External: ${compactInline(matter?.external_id || '', 80) || 'n/a'}`,
      `Status: ${compactInline(matter?.status || matter?.state || matter?.stage || '', 40) || 'n/a'}`,
      `Document Status: ${countsLine || 'n/a'}`
    ].join('\n');

    return composeWhatsAppMessage(body, [
      `Peregrine GET /matters/${matterId}`,
      `Peregrine GET /matters/${matterId}/documents/status`
    ]);
  }

  if (command.kind === 'status') {
    const matterId = String(command.matterId || '').trim();
    if (!matterId) {
      return composeWhatsAppMessage('Usage: /status <matter_id>');
    }
    const encodedId = encodeURIComponent(matterId);
    const statusPayload = await requestPeregrine('GET', `/matters/${encodedId}/documents/status`);
    const counts = normalizeStatusCounts(statusPayload);
    const entries = Object.entries(counts);
    if (!entries.length) {
      return composeWhatsAppMessage(`No document status counts found for matter ${matterId}.`, [
        `Peregrine GET /matters/${matterId}/documents/status`
      ]);
    }
    const lines = entries.map(([k, v]) => `- ${k}: ${v}`);
    return composeWhatsAppMessage(`Document status for ${matterId}:\n${lines.join('\n')}`, [
      `Peregrine GET /matters/${matterId}/documents/status`
    ]);
  }

  if (command.kind === 'docs') {
    const matterId = String(command.matterId || '').trim();
    if (!matterId) {
      return composeWhatsAppMessage('Usage: /docs <matter_id> [query]');
    }
    const query = String(command.query || '').trim();
    const encodedId = encodeURIComponent(matterId);
    const payload = await requestPeregrine('GET', `/matters/${encodedId}/documents`, {
      limit: WHATSAPP_MAX_LIST_ITEMS,
      q: query || undefined
    });
    const docs = Array.isArray(payload?.documents) ? payload.documents : [];
    if (!docs.length) {
      return composeWhatsAppMessage(
        `No documents found for ${matterId}${query ? ` (query: ${query})` : ''}.`,
        [`Peregrine GET /matters/${matterId}/documents`]
      );
    }
    const lines = docs.map((doc, idx) => {
      const docId = compactInline(doc?.id || doc?.document_id || '', 40) || '(no-doc-id)';
      const name = compactInline(doc?.filename || doc?.title || doc?.name || 'Untitled', 48);
      const status = compactInline(doc?.status || '', 20);
      const docType = compactInline(doc?.doc_type || doc?.type || '', 20);
      return `${idx + 1}) ${docId} | ${name}${status ? ` | ${status}` : ''}${docType ? ` | ${docType}` : ''}`;
    });
    return composeWhatsAppMessage(
      `Documents for ${matterId}${query ? ` (query: ${query})` : ''}:\n${lines.join('\n')}`,
      [`Peregrine GET /matters/${matterId}/documents`]
    );
  }

  if (command.kind === 'doc') {
    const documentId = String(command.documentId || '').trim();
    if (!documentId) {
      return composeWhatsAppMessage('Usage: /doc <document_id> [max_chars]');
    }
    const encodedId = encodeURIComponent(documentId);
    const meta = await requestPeregrine('GET', `/documents/${encodedId}`);
    const textPayload = await requestPeregrine('GET', `/documents/${encodedId}/text`);
    const text = String(textPayload?.text || '').replace(/\r\n/g, '\n').trim();
    const maxChars = Math.max(120, Number(command.maxChars) || WHATSAPP_MAX_DOC_EXCERPT_CHARS);
    const excerpt = text ? text.slice(0, maxChars) : '';
    const excerptSuffix = text.length > excerpt.length ? '\n\n[excerpt truncated]' : '';
    const body = [
      `Document: ${documentId}`,
      `Filename: ${compactInline(meta?.filename || meta?.title || meta?.name || 'n/a', 80)}`,
      `Type: ${compactInline(meta?.doc_type || meta?.type || 'n/a', 40)}`,
      `Status: ${compactInline(meta?.status || 'n/a', 32)}`,
      `Text Length: ${Number(text.length || 0)}`,
      '',
      `Excerpt:\n${excerpt || '[No extracted text available]'}${excerptSuffix}`
    ].join('\n');

    return composeWhatsAppMessage(body, [
      `Peregrine GET /documents/${documentId}`,
      `Peregrine GET /documents/${documentId}/text`
    ]);
  }

  return composeWhatsAppMessage('Unsupported command.');
}

function xmlEscape(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function sendTwiml(res, message, statusCode = 200) {
  const safeMessage = trimWhatsappResponse(message);
  const payload = `<?xml version="1.0" encoding="UTF-8"?><Response><Message>${xmlEscape(safeMessage)}</Message></Response>`;
  res.statusCode = statusCode;
  res.setHeader('Content-Type', 'text/xml; charset=utf-8');
  res.end(payload);
}

function sendJson(res, payload, statusCode = 200) {
  res.statusCode = statusCode;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(payload));
}

function readRequestBody(req, maxBytes = WHATSAPP_REQUEST_BODY_LIMIT) {
  return new Promise((resolve, reject) => {
    let total = 0;
    const chunks = [];

    req.on('data', (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        const err = new Error('Request body too large');
        err.statusCode = 413;
        reject(err);
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });

    req.on('end', () => {
      resolve(Buffer.concat(chunks));
    });

    req.on('error', (err) => {
      reject(err);
    });
  });
}

function inferRequestPublicUrl(req) {
  const reqUrl = String(req.url || '/');
  if (WHATSAPP_PUBLIC_URL) {
    try {
      return new URL(reqUrl, WHATSAPP_PUBLIC_URL).toString();
    } catch {
      return `${WHATSAPP_PUBLIC_URL.replace(/\/+$/, '')}${reqUrl.startsWith('/') ? '' : '/'}${reqUrl}`;
    }
  }

  const forwardedProto = String(req.headers['x-forwarded-proto'] || '')
    .split(',')[0]
    .trim();
  const proto = forwardedProto || (req.socket?.encrypted ? 'https' : 'http');
  const host = String(req.headers['x-forwarded-host'] || req.headers.host || `${WHATSAPP_BIND_HOST}:${WHATSAPP_PORT}`)
    .split(',')[0]
    .trim();
  return `${proto}://${host}${reqUrl}`;
}

function secureCompare(a, b) {
  const left = Buffer.from(String(a || ''), 'utf-8');
  const right = Buffer.from(String(b || ''), 'utf-8');
  if (left.length !== right.length) return false;
  try {
    return crypto.timingSafeEqual(left, right);
  } catch {
    return false;
  }
}

function isTwilioSignatureValid(req, params) {
  if (!WHATSAPP_VALIDATE_SIGNATURE) return true;
  if (!WHATSAPP_AUTH_TOKEN) return false;

  const provided = String(req.headers['x-twilio-signature'] || '').trim();
  if (!provided) return false;

  const url = inferRequestPublicUrl(req);
  const keys = Object.keys(params || {}).sort();
  let data = url;
  for (const key of keys) {
    const raw = params[key];
    if (Array.isArray(raw)) {
      for (const value of raw) {
        data += key + String(value ?? '');
      }
      continue;
    }
    data += key + String(raw ?? '');
  }

  const computed = crypto.createHmac('sha1', WHATSAPP_AUTH_TOKEN).update(data, 'utf8').digest('base64');
  return secureCompare(provided, computed);
}

function parseWhatsappInput(rawText, currentMode) {
  let mode = currentMode === 'caselaw' ? 'caselaw' : 'casefile';
  let text = String(rawText || '').trim();

  if (!text) {
    return { mode, prompt: '', empty: true };
  }
  if (/^\/help\b/i.test(text)) {
    return { mode, prompt: '', showHelp: true };
  }
  if (/^\/reset\b/i.test(text)) {
    return { mode, prompt: '', reset: true };
  }

  const modeMatch = text.match(/^\/mode\s+(casefile|caselaw)\b\s*(.*)$/i);
  if (modeMatch) {
    mode = modeMatch[1].toLowerCase() === 'caselaw' ? 'caselaw' : 'casefile';
    text = String(modeMatch[2] || '').trim();
    const nextCommand = parseWhatsAppCommand(text);
    return {
      mode,
      prompt: nextCommand ? '' : text,
      modeChanged: true,
      command: nextCommand || undefined
    };
  }

  const command = parseWhatsAppCommand(text);
  if (command) {
    return { mode, prompt: '', command };
  }

  if (/^\/caselaw\b/i.test(text)) {
    mode = 'caselaw';
    text = text.replace(/^\/caselaw\b/i, '').trim();
  } else if (/^\/casefile\b/i.test(text) || /^\/vault\b/i.test(text)) {
    mode = 'casefile';
    text = text.replace(/^\/(?:casefile|vault)\b/i, '').trim();
  }

  return { mode, prompt: text, empty: !text };
}

function whatsappHelpText() {
  return [
    'Acquittify WhatsApp agent commands:',
    '/casefile <question> - Search the active casefile vault',
    '/caselaw <question> - Search caselaw vaults',
    '/matters [query] - List matters from Peregrine',
    '/matter <matter_id> - Get one matter',
    '/status <matter_id> - Document status counts for a matter',
    '/docs <matter_id> [query] - List matter documents',
    '/doc <document_id> [max_chars] - Document excerpt',
    '/mode casefile|caselaw - Set default mode',
    '/reset - Clear session history',
    '/help - Show commands'
  ].join('\n');
}

function getCaselawVaultRootsForWhatsApp() {
  const jurisdictions = discoverCaselawVaultJurisdictions(VAULT_ROOT);
  return jurisdictions
    .map((item) => String(item?.vaultRoot || '').trim())
    .filter(Boolean);
}

function renderWhatsAppAnswer(result) {
  const answer = String(result?.answer || '').trim() || 'No response.';
  const sources = Array.isArray(result?.contextPaths)
    ? result.contextPaths.map((p) => String(p || '').trim()).filter(Boolean)
    : [];
  return composeWhatsAppMessage(answer, sources.slice(0, 4));
}

async function handleWhatsAppWebhook(req, res) {
  const raw = await readRequestBody(req);
  const payload = querystring.parse(raw.toString('utf-8'));

  if (!isTwilioSignatureValid(req, payload)) {
    sendTwiml(res, 'Webhook signature verification failed.', 403);
    return;
  }

  const from = String(payload.From || '').trim();
  const to = String(payload.To || '').trim();
  const incomingBody = String(payload.Body || '').trim();
  const messageSid = String(payload.MessageSid || '').trim();

  if (!from) {
    sendTwiml(res, 'Missing sender identity.');
    return;
  }

  const { session } = getWhatsAppSession(from, to);
  session.updatedAt = new Date().toISOString();

  if (messageSid && session.lastInboundSid === messageSid && session.lastResponseText) {
    sendTwiml(res, session.lastResponseText);
    return;
  }

  const parsedInput = parseWhatsappInput(incomingBody, session.mode);
  session.mode = parsedInput.mode;

  if (parsedInput.showHelp) {
    const msg = whatsappHelpText();
    session.lastInboundSid = messageSid;
    session.lastResponseText = msg;
    persistWhatsAppSessions();
    sendTwiml(res, msg);
    return;
  }

  const authorized = isWhatsAppSenderAuthorized(from);
  if (!authorized) {
    const msg = WHATSAPP_ENFORCE_ALLOWLIST
      ? 'Access denied for this WhatsApp number. Ask the administrator to allowlist your number.'
      : 'Access denied.';
    session.lastInboundSid = messageSid;
    session.lastResponseText = msg;
    session.updatedAt = new Date().toISOString();
    persistWhatsAppSessions();
    sendTwiml(res, msg, 403);
    return;
  }

  if (parsedInput.reset) {
    session.history = [];
    const msg = 'Session history cleared.';
    session.lastInboundSid = messageSid;
    session.lastResponseText = msg;
    persistWhatsAppSessions();
    sendTwiml(res, msg);
    return;
  }

  if (parsedInput.modeChanged && !parsedInput.prompt && !parsedInput.command) {
    const msg = `Default mode set to ${parsedInput.mode}.`;
    session.lastInboundSid = messageSid;
    session.lastResponseText = msg;
    persistWhatsAppSessions();
    sendTwiml(res, msg);
    return;
  }

  if (parsedInput.command) {
    try {
      const responseText = await executeWhatsAppCommand(parsedInput.command);
      appendWhatsAppHistory(session, 'user', incomingBody);
      appendWhatsAppHistory(session, 'assistant', responseText);
      session.lastInboundSid = messageSid;
      session.lastResponseText = responseText;
      session.updatedAt = new Date().toISOString();
      persistWhatsAppSessions();
      sendTwiml(res, responseText);
    } catch (err) {
      const responseText = trimWhatsappResponse(`Acquittify command error: ${String(err?.message || err)}`);
      session.lastInboundSid = messageSid;
      session.lastResponseText = responseText;
      session.updatedAt = new Date().toISOString();
      persistWhatsAppSessions();
      sendTwiml(res, responseText);
    }
    return;
  }

  if (parsedInput.empty) {
    const msg = `Send a question or /help for commands. Current mode: ${parsedInput.mode}.`;
    session.lastInboundSid = messageSid;
    session.lastResponseText = msg;
    persistWhatsAppSessions();
    sendTwiml(res, msg);
    return;
  }

  const mode = parsedInput.mode === 'caselaw' ? 'caselaw' : 'casefile';
  const caselawVaultRoots = mode === 'caselaw' ? getCaselawVaultRootsForWhatsApp() : [];
  const history = Array.isArray(session.history)
    ? session.history
        .filter((item) => item && (item.role === 'user' || item.role === 'assistant') && typeof item.text === 'string')
        .slice(-(WHATSAPP_HISTORY_LIMIT * 2))
    : [];

  try {
    const result = await runAgent(VAULT_ROOT, parsedInput.prompt, history, {
      viewKind: mode,
      caselawVaultRoots
    });
    const responseText = renderWhatsAppAnswer(result);
    appendWhatsAppHistory(session, 'user', parsedInput.prompt);
    appendWhatsAppHistory(session, 'assistant', responseText);
    session.lastInboundSid = messageSid;
    session.lastResponseText = responseText;
    session.updatedAt = new Date().toISOString();
    persistWhatsAppSessions();
    sendTwiml(res, responseText);
  } catch (err) {
    const responseText = trimWhatsappResponse(`Acquittify error: ${String(err?.message || err)}`);
    session.lastInboundSid = messageSid;
    session.lastResponseText = responseText;
    session.updatedAt = new Date().toISOString();
    persistWhatsAppSessions();
    sendTwiml(res, responseText);
  }
}

async function handleWhatsAppHttpRequest(req, res) {
  const method = String(req.method || 'GET').toUpperCase();
  const host = String(req.headers.host || `${WHATSAPP_BIND_HOST}:${WHATSAPP_PORT}`);
  const parsedUrl = new URL(String(req.url || '/'), `http://${host}`);
  const pathname = parsedUrl.pathname;

  if (method === 'GET' && pathname === '/healthz') {
    sendJson(res, {
      status: 'ok',
      whatsapp: 'enabled',
      timestamp: new Date().toISOString()
    });
    return;
  }

  if (
    method === 'POST' &&
    (pathname === '/whatsapp/webhook' || pathname === '/channels/whatsapp/webhook')
  ) {
    await handleWhatsAppWebhook(req, res);
    return;
  }

  sendJson(
    res,
    {
      error: 'Not found'
    },
    404
  );
}

function startWhatsAppGatewayServer() {
  if (!WHATSAPP_ENABLED) return;
  if (whatsappServer) return;
  if (WHATSAPP_VALIDATE_SIGNATURE && !WHATSAPP_AUTH_TOKEN) {
    console.warn('[whatsapp] Signature validation is enabled but no auth token is configured.');
  }

  loadWhatsAppSessions();
  whatsappServer = http.createServer((req, res) => {
    handleWhatsAppHttpRequest(req, res).catch((err) => {
      console.error('[whatsapp] request failed:', err?.message || err);
      sendTwiml(res, `Acquittify webhook error: ${String(err?.message || err)}`, 500);
    });
  });
  whatsappServer.on('error', (err) => {
    console.error('[whatsapp] server error:', err?.message || err);
  });
  whatsappServer.listen(WHATSAPP_PORT, WHATSAPP_BIND_HOST, () => {
    console.log(
      `[whatsapp] listening on http://${WHATSAPP_BIND_HOST}:${WHATSAPP_PORT} (POST /whatsapp/webhook)`
    );
  });
}

function stopWhatsAppGatewayServer() {
  if (!whatsappServer) return;
  try {
    whatsappServer.close();
  } catch {
    // ignore
  }
  whatsappServer = null;
}

let mainWindow;
let VAULT_ROOT = '';
let whatsappServer = null;
let whatsappSessions = {};
const ALLOW_MULTI_INSTANCE =
  process.env.ACQUITTIFY_ALLOW_MULTI_INSTANCE === '1' || process.argv.includes('--allow-multi-instance');
const gotSingleInstanceLock = ALLOW_MULTI_INSTANCE ? true : app.requestSingleInstanceLock();

function sendAgentStreamEvent(runId, payload = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send('agent:stream', {
    runId,
    ...payload
  });
}

if (!gotSingleInstanceLock) {
  logStartup('single-instance lock failed; quitting');
  app.quit();
}

app.on('second-instance', () => {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) {
    try {
      mainWindow.restore();
    } catch {
      // ignore
    }
  }
  mainWindow.show();
  mainWindow.focus();
});

function emitWindowGeometryChanged(reason = 'unknown') {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const bounds = mainWindow.getContentBounds();
  mainWindow.webContents.send('window:geometry-changed', {
    reason,
    width: bounds.width,
    height: bounds.height,
    isFullScreen: mainWindow.isFullScreen(),
    isMaximized: mainWindow.isMaximized()
  });
}

function wireWindowGeometryEvents() {
  if (!mainWindow) return;

  const pulse = (reason) => {
    emitWindowGeometryChanged(reason);
    setTimeout(() => emitWindowGeometryChanged(`${reason}:late`), 120);
    setTimeout(() => emitWindowGeometryChanged(`${reason}:settled`), 350);
  };

  mainWindow.on('resize', () => pulse('resize'));
  mainWindow.on('maximize', () => pulse('maximize'));
  mainWindow.on('unmaximize', () => pulse('unmaximize'));
  mainWindow.on('enter-full-screen', () => pulse('enter-full-screen'));
  mainWindow.on('leave-full-screen', () => pulse('leave-full-screen'));
  mainWindow.on('restore', () => pulse('restore'));
  mainWindow.on('show', () => pulse('show'));
}

async function createWindow() {
  logStartup('createWindow: start');
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 920,
    backgroundColor: '#0a0a0a',
    show: false,
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: {
      contextIsolation: false,
      nodeIntegration: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  let readyShown = false;
  const ensureVisible = (reason = 'unknown') => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    if (mainWindow.isVisible()) return;
    try {
      mainWindow.center();
    } catch {
      // ignore centering errors
    }
    mainWindow.show();
    mainWindow.focus();
    emitWindowGeometryChanged(reason);
    logStartup(`createWindow: ensureVisible (${reason})`);
  };

  mainWindow.once('ready-to-show', () => {
    readyShown = true;
    logStartup('createWindow: ready-to-show');
    ensureVisible('ready-to-show');
  });

  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    logStartup(
      `createWindow: did-fail-load code=${errorCode} desc=${errorDescription} url=${validatedURL}`
    );
    ensureVisible('did-fail-load');
    try {
      mainWindow.webContents.openDevTools({ mode: 'detach' });
    } catch {
      // ignore devtools errors
    }
  });

  mainWindow.webContents.on('did-finish-load', () => {
    logStartup('createWindow: did-finish-load');
  });

  mainWindow.webContents.on('dom-ready', () => {
    logStartup('createWindow: dom-ready');
  });

  mainWindow.webContents.on('render-process-gone', (event, details) => {
    logStartup(`createWindow: render-process-gone reason=${details?.reason || 'unknown'}`);
  });

  mainWindow.on('unresponsive', () => {
    logStartup('createWindow: unresponsive');
  });

  mainWindow.on('closed', () => {
    logStartup('createWindow: closed');
    mainWindow = null;
  });

  setTimeout(() => {
    if (!readyShown) {
      logStartup('createWindow: startup-timeout');
      ensureVisible('startup-timeout');
    }
  }, 4000);

  try {
    await mainWindow.loadFile(path.join(__dirname, 'ui', 'index.html'));
    logStartup('createWindow: loadFile completed');
  } catch {
    logStartup('createWindow: loadFile failed');
    ensureVisible('load-error');
  }
  wireWindowGeometryEvents();
  emitWindowGeometryChanged('post-load');
}

if (gotSingleInstanceLock) {
app.whenReady().then(async () => {
  logStartup('app.whenReady: start');
  logStartup('app.whenReady: read settings');
  const settings = readAppSettings();
  logStartup('app.whenReady: settings loaded');
  VAULT_ROOT = resolveVaultPath(settings);
  logStartup(`app.whenReady: vaultRoot=${VAULT_ROOT || 'none'}`);
  ensurePeregrineBootstrapPromptNotes(VAULT_ROOT);
  startWhatsAppGatewayServer();
  logStartup('app.whenReady: whatsapp server started');

  ipcMain.handle('vault:get-root', async () => ({
    root: VAULT_ROOT,
    access: getVaultAccess(VAULT_ROOT)
  }));
  ipcMain.handle('app:get-build-info', async () => {
    const appPathResolved = path.resolve(app.getAppPath());
    const source = app.isPackaged || /app\.asar$/i.test(appPathResolved) ? 'packaged' : 'workspace';
    let buildMtime = '';
    try {
      buildMtime = fs.statSync(appPathResolved).mtime.toISOString();
    } catch {
      buildMtime = '';
    }
    return {
      source,
      isPackaged: Boolean(app.isPackaged),
      appPath: appPathResolved,
      execPath: String(process.execPath || ''),
      version: String(app.getVersion() || ''),
      buildMtime
    };
  });
  ipcMain.handle('vault:pick-root', async () => {
    const selection = await dialog.showOpenDialog(mainWindow, {
      title: 'Select Acquittify Vault Folder',
      defaultPath: VAULT_ROOT,
      properties: ['openDirectory']
    });
    if (selection.canceled || !selection.filePaths.length) {
      return {
        canceled: true,
        root: VAULT_ROOT,
        access: getVaultAccess(VAULT_ROOT)
      };
    }

    const pickedRoot = path.resolve(selection.filePaths[0]);
    VAULT_ROOT = pickedRoot;
    ensurePeregrineBootstrapPromptNotes(VAULT_ROOT);
    const nextSettings = readAppSettings();
    nextSettings.vaultRoot = pickedRoot;
    writeAppSettings(nextSettings);
    return {
      canceled: false,
      root: VAULT_ROOT,
      access: getVaultAccess(VAULT_ROOT)
    };
  });
  ipcMain.handle('vault:list', async (_event, relPath = '') => listDirSafe(VAULT_ROOT, relPath));
  ipcMain.handle('vault:read', async (_event, relPath) => {
    const abs = ensureInsideVault(VAULT_ROOT, path.join(VAULT_ROOT, relPath));
    return fs.readFileSync(abs, 'utf-8');
  });
  ipcMain.handle('vault:file-url', async (_event, relPath) => {
    const abs = ensureInsideVault(VAULT_ROOT, path.join(VAULT_ROOT, relPath));
    return { url: pathToFileURL(abs).toString() };
  });
  ipcMain.handle('vault:write', async (_event, payload) => {
    const relPath = payload?.path;
    const content = payload?.content ?? '';
    const abs = ensureInsideVault(VAULT_ROOT, path.join(VAULT_ROOT, relPath));
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, content, 'utf-8');
    return { ok: true };
  });
  ipcMain.handle('vault:create-note', async (_event, payload = {}) => {
    const parent = resolveVaultParentDirectory(VAULT_ROOT, payload?.parentPath || '');
    let noteName = normalizeVaultLeafName(payload?.name, 'Note name');
    if (!/\.(md|markdown)$/i.test(noteName)) {
      noteName = `${noteName}.md`;
    }
    const targetAbs = ensureInsideVault(VAULT_ROOT, path.join(parent.abs, noteName));
    if (fs.existsSync(targetAbs)) {
      throw new Error('A note with that name already exists.');
    }
    fs.mkdirSync(path.dirname(targetAbs), { recursive: true });
    const stem = noteName.replace(/\.(md|markdown)$/i, '');
    fs.writeFileSync(targetAbs, `# ${stem}\n\n`, 'utf-8');
    return {
      ok: true,
      type: 'file',
      path: toRel(VAULT_ROOT, targetAbs)
    };
  });
  ipcMain.handle('vault:create-folder', async (_event, payload = {}) => {
    const parent = resolveVaultParentDirectory(VAULT_ROOT, payload?.parentPath || '');
    const folderName = normalizeVaultLeafName(payload?.name, 'Folder name');
    const targetAbs = ensureInsideVault(VAULT_ROOT, path.join(parent.abs, folderName));
    if (fs.existsSync(targetAbs)) {
      throw new Error('A folder with that name already exists.');
    }
    fs.mkdirSync(targetAbs, { recursive: false });
    return {
      ok: true,
      type: 'directory',
      path: toRel(VAULT_ROOT, targetAbs)
    };
  });
  ipcMain.handle('vault:rename-path', async (_event, payload = {}) => {
    const entity = resolveVaultEntity(VAULT_ROOT, payload?.path, 'Path');
    const nextName = normalizeVaultLeafName(payload?.newName, 'New name');
    const targetAbs = ensureInsideVault(VAULT_ROOT, path.join(path.dirname(entity.abs), nextName));
    if (targetAbs === entity.abs) {
      return {
        ok: true,
        type: entity.stat.isDirectory() ? 'directory' : 'file',
        oldPath: entity.rel,
        path: entity.rel
      };
    }
    if (fs.existsSync(targetAbs)) {
      throw new Error('A file or folder with that name already exists.');
    }
    fs.renameSync(entity.abs, targetAbs);
    return {
      ok: true,
      type: entity.stat.isDirectory() ? 'directory' : 'file',
      oldPath: entity.rel,
      path: toRel(VAULT_ROOT, targetAbs)
    };
  });
  ipcMain.handle('vault:delete-path', async (_event, payload = {}) => {
    const entity = resolveVaultEntity(VAULT_ROOT, payload?.path, 'Path');
    if (entity.stat.isDirectory()) {
      fs.rmSync(entity.abs, { recursive: true, force: false });
      return { ok: true, type: 'directory', path: entity.rel };
    }
    fs.unlinkSync(entity.abs);
    return { ok: true, type: 'file', path: entity.rel };
  });
  ipcMain.handle('vault:ensure-extracted-note', async (_event, payload) => {
    const relPath = typeof payload === 'string' ? payload : payload?.path;
    if (!relPath || !String(relPath).trim()) {
      throw new Error('A vault-relative file path is required.');
    }
    const force = typeof payload === 'object' && payload ? Boolean(payload.force) : false;
    return ensureExtractedNoteForVaultFile(VAULT_ROOT, String(relPath), { force });
  });
  ipcMain.handle('vault:import-files', async (_event, payload = {}) => {
    const givenPaths = Array.isArray(payload.filePaths)
      ? payload.filePaths.map((p) => String(p || '')).filter(Boolean)
      : [];
    const targetDir = payload?.targetDir ? String(payload.targetDir) : VAULT_IMPORT_RELATIVE_DIR;

    let sourcePaths = givenPaths;
    if (!sourcePaths.length) {
      const selection = await dialog.showOpenDialog(mainWindow, {
        title: 'Import Files Into Acquittify Vault',
        defaultPath: VAULT_ROOT,
        properties: ['openFile', 'multiSelections'],
        filters: [
          { name: 'Common Case Files', extensions: IMPORT_DIALOG_EXTENSIONS },
          { name: 'All Files', extensions: ['*'] }
        ]
      });
      if (selection.canceled || !selection.filePaths.length) {
        return { canceled: true, results: [] };
      }
      sourcePaths = selection.filePaths;
    }

    return importFilesIntoVault(VAULT_ROOT, sourcePaths, { targetDir });
  });
  ipcMain.handle('casefile:bootstrap', async (_event, payload = {}) => {
    return bootstrapCasefileWorkspace(VAULT_ROOT, payload || {});
  });
  ipcMain.handle('vault:search', async (_event, query) => searchVault(VAULT_ROOT, query, 30));
  ipcMain.handle('citation:check', async (_event, payload) => {
    const rawInput = typeof payload === 'string' ? payload : payload?.text;
    if (!rawInput || !String(rawInput).trim()) {
      throw new Error('Citation input is required.');
    }
    return runFederalCitationCheck(String(rawInput));
  });
  ipcMain.handle('vault:graph', async () => buildGraph(VAULT_ROOT, GRAPH_FILE_LIMIT));
  ipcMain.handle('vault:ontology-graph', async () => buildOntologyGraph(VAULT_ROOT, ONTOLOGY_GRAPH_FILE_LIMIT));
  ipcMain.handle('vault:caselaw-jurisdictions', async () => discoverCaselawVaultJurisdictions(VAULT_ROOT));
  ipcMain.handle('vault:ontology-graph-multi', async (_event, payload = {}) => {
    const rawRoots = Array.isArray(payload?.vaultRoots)
      ? payload.vaultRoots
      : Array.isArray(payload)
        ? payload
        : [];
    const selectedRoots = normalizeCaselawVaultRoots(rawRoots, VAULT_ROOT);
    const roots = selectedRoots.length ? selectedRoots : [VAULT_ROOT];
    const limit = Math.max(500, Number(payload?.limit || ONTOLOGY_GRAPH_FILE_LIMIT) || ONTOLOGY_GRAPH_FILE_LIMIT);
    return buildOntologyGraphMulti(roots, limit);
  });
  ipcMain.handle('app:reload-with-code', async () => {
    const devDir = path.resolve(LOCAL_DEV_APP_DIR);
    const currentAppPath = path.resolve(app.getAppPath());
    const runningFromDevDir =
      currentAppPath === devDir || currentAppPath.startsWith(`${devDir}${path.sep}`);

    if (ENABLE_DEV_RELOAD_SWITCH && !runningFromDevDir && hasLocalDevAppDir(devDir)) {
      launchLocalDevApp(devDir);
      setTimeout(() => {
        try {
          app.quit();
        } catch {
          // ignore
        }
      }, 160);
      return {
        ok: true,
        mode: 'switched_to_local_dev',
        devDir
      };
    }

    setTimeout(() => {
      try {
        app.relaunch();
        app.exit(0);
      } catch {
        // ignore
      }
    }, 120);
    return {
      ok: true,
      mode: 'relaunched_current'
    };
  });
  ipcMain.handle('agent:run', async (_event, payload) => {
    const prompt = typeof payload === 'string' ? payload : payload?.prompt;
    const conversationId = typeof payload === 'string' ? '' : payload?.conversationId;
    if (!prompt || !String(prompt).trim()) {
      throw new Error('Agent prompt is required.');
    }
    return runOpenclawResponse(String(prompt), conversationId);
  });

  ipcMain.handle('agent:run-stream', async (_event, payload) => {
    const prompt = typeof payload === 'string' ? payload : payload?.prompt;
    const conversationId = typeof payload === 'string' ? '' : payload?.conversationId;
    if (!prompt || !String(prompt).trim()) {
      throw new Error('Agent prompt is required.');
    }
    const runId = crypto.randomUUID();
    void streamOpenclawResponse({
      prompt: String(prompt),
      conversationId,
      runId
    }).catch((err) => {
      sendAgentStreamEvent(runId, { type: 'error', error: String(err?.message || err) });
    });
    return { runId };
  });

  await createWindow();
  logStartup('app.whenReady: createWindow complete');

  app.on('activate', () => {
    if (mainWindow === null) {
      createWindow();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}).catch((err) => {
  logStartup(`app.whenReady: failed ${err?.stack || err}`);
});
}

app.on('before-quit', () => {
  stopWhatsAppGatewayServer();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
