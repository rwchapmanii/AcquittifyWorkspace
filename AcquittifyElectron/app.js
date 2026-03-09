const { Network, DataSet } = require('../node_modules/vis-network/standalone/umd/vis-network.cjs');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { pathToFileURL, fileURLToPath } = require('url');

const CONVERSATIONS_STORAGE_KEY = 'acquittify.agent.conversations.v2';
const SIDEBAR_LAYOUT_STORAGE_KEY = 'acquittify.shell.sidebar-layout.v1';
const MAX_SAVED_MESSAGES = 500;
const MAX_HISTORY_MESSAGES = 20;
const MAX_RENDERED_PDF_PAGES = 300;
const SHELL_MIN_LEFT_WIDTH = 220;
const SHELL_MAX_LEFT_WIDTH = 720;
const SHELL_MIN_RIGHT_WIDTH = 240;
const SHELL_MAX_RIGHT_WIDTH = 760;
const SHELL_MIN_CENTER_WIDTH = 420;
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
const PDF_EXTENSIONS = new Set(['.pdf']);
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.heic', '.heif']);
const AUDIO_EXTENSIONS = new Set(['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma', '.aiff', '.m4b']);
const VIDEO_EXTENSIONS = new Set(['.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm']);
const PROCESSABLE_DOCUMENT_EXTENSIONS = new Set([
  '.doc',
  '.docx',
  '.odt',
  '.rtf',
  '.xls',
  '.xlsx',
  '.xlsm',
  '.ods',
  '.csv',
  '.tsv',
  '.eml',
  '.msg',
  '.ppt',
  '.pptx',
  '.odp'
]);
const CASE_CANVASES = [
  {
    id: 'savani',
    label: 'United States v. Savani',
    shortLabel: 'Savani Canvas',
    vaultRoot: path.join(os.homedir(), 'United States v. Savani'),
    entryCandidates: ['README.md', 'Ontology.md']
  }
];
const TRIAL_CANVAS_VIEW_TITLE = 'Trial Canvas';
const TRIAL_CANVAS_MENTION_REGEX = /mentions|referenced|references|refers to|cites/i;
const TRIAL_WIKILINK_REGEX = /\[\[([^\[\]]+)\]\]/g;
const ONTOLOGY_RELATION_TYPES = [
  'applies',
  'clarifies',
  'extends',
  'distinguishes',
  'limits',
  'overrules',
  'questions'
];
const ONTOLOGY_NODE_COLORS = {
  case: '#60a5fa',
  constitution: '#ef4444',
  statute: '#f97316',
  regulation: '#06b6d4',
  taxonomy: '#facc15',
  external_case: '#64748b',
  holding: '#34d399',
  issue: '#f59e0b',
  relation: '#f472b6',
  source: '#c084fc',
  secondary: '#fb7185',
  event: '#a3e635',
  unknown: '#a3a3a3'
};

const ONTOLOGY_ORIGINATING_CIRCUITS = [
  { code: 'ca1', label: 'First Circuit' },
  { code: 'ca2', label: 'Second Circuit' },
  { code: 'ca3', label: 'Third Circuit' },
  { code: 'ca4', label: 'Fourth Circuit' },
  { code: 'ca5', label: 'Fifth Circuit' },
  { code: 'ca6', label: 'Sixth Circuit' },
  { code: 'ca7', label: 'Seventh Circuit' },
  { code: 'ca8', label: 'Eighth Circuit' },
  { code: 'ca9', label: 'Ninth Circuit' },
  { code: 'ca10', label: 'Tenth Circuit' },
  { code: 'ca11', label: 'Eleventh Circuit' },
  { code: 'cadc', label: 'D.C. Circuit' }
];

function hslToHex(h, s, l) {
  const hue = Number(h) % 360;
  const sat = Math.max(0, Math.min(100, Number(s))) / 100;
  const light = Math.max(0, Math.min(100, Number(l))) / 100;
  const c = (1 - Math.abs(2 * light - 1)) * sat;
  const hp = hue / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;
  if (hp >= 0 && hp < 1) {
    r = c;
    g = x;
  } else if (hp >= 1 && hp < 2) {
    r = x;
    g = c;
  } else if (hp >= 2 && hp < 3) {
    g = c;
    b = x;
  } else if (hp >= 3 && hp < 4) {
    g = x;
    b = c;
  } else if (hp >= 4 && hp < 5) {
    r = x;
    b = c;
  } else if (hp >= 5 && hp < 6) {
    r = c;
    b = x;
  }
  const m = light - c / 2;
  const toHex = (value) => Math.round((value + m) * 255).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function buildCircuitColorMap() {
  const map = {};
  const total = Math.max(1, ONTOLOGY_ORIGINATING_CIRCUITS.length);
  ONTOLOGY_ORIGINATING_CIRCUITS.forEach((item, idx) => {
    // Evenly-spaced hues maximize categorical contrast across the 12 circuits.
    map[item.code] = hslToHex(Math.round((360 / total) * idx), 92, 55);
  });
  return map;
}

const ONTOLOGY_CIRCUIT_COLORS = buildCircuitColorMap();
const ONTOLOGY_CIRCUIT_LABELS = Object.fromEntries(
  ONTOLOGY_ORIGINATING_CIRCUITS.map((item) => [item.code, item.label])
);
const ONTOLOGY_REPRESENTATIVE_CASE_LIMIT = 2500;
const ONTOLOGY_VIEW_PRESET_PROFILES = {
  core_precedent: {
    label: 'Core Precedent',
    minEdgeStrength: 0.62,
    minCaseImportance: 0.18,
    maxEdgesPerNode: 28
  },
  constitutional: {
    label: 'Constitutional',
    minEdgeStrength: 0.66,
    minCaseImportance: 0.2,
    maxEdgesPerNode: 20
  },
  statutory_regulatory: {
    label: 'Statutory/Regulatory',
    minEdgeStrength: 0.58,
    minCaseImportance: 0.14,
    maxEdgesPerNode: 24
  },
  full_ontology: {
    label: 'Full Ontology',
    minEdgeStrength: 0.0,
    minCaseImportance: 0.0,
    maxEdgesPerNode: 250
  }
};

const ONTOLOGY_FILTER_DEFAULTS = {
  viewPreset: 'full_ontology',
  query: '',
  nodeTypes: ['case', 'constitution', 'statute', 'regulation', 'taxonomy'],
  relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
  citationType: 'all',
  caseDomain: 'all',
  courtLevel: 'all',
  originatingCircuit: 'all',
  normativeStrength: 'all',
  factDimension: '',
  minEdgeStrength: null,
  minCaseImportance: null,
  maxEdgesPerNode: null,
  pfMin: '',
  consensusMin: '',
  driftMax: '',
  relationConfidenceMin: '',
  maxNodes: 20000
};

const state = {
  vaultRoot: '',
  vaultAccess: null,
  vaultViewKind: 'casefile',
  caselawJurisdictions: [],
  caselawSelectedVaultRoots: [],
  caselawJurisdictionError: '',
  vaultSelection: null,
  nextTabId: 1,
  openTabs: [],
  activeTabId: null,
  graph: { nodes: [], edges: [], meta: {} },
  graphNetwork: null,
  graphData: null,
  graphRendered: false,
  graphRenderMode: 'unknown',
  graphVisDisabled: false,
  ontologyGraph: { nodes: [], edges: [], meta: {} },
  ontologyGraphNetwork: null,
  ontologyGraphData: null,
  ontologyGraphRendered: false,
  ontologyGraphRenderMode: 'unknown',
  ontologyGraphVisDisabled: false,
  ontologyGraphAutoRelaxAttempted: false,
  ontologyNodeLookup: new Map(),
  casePdfIndexByVaultRoot: new Map(),
  ontologyCaseHoverHideTimer: null,
  ontologyHoverRafPending: false,
  ontologyHoverLastPointer: null,
  ontologyCaseSidebarNodeId: '',
  ontologyCaseSidebarTabs: [],
  ontologyCaseSidebarActiveTabId: '',
  ontologyFilter: { ...ONTOLOGY_FILTER_DEFAULTS },
  trialCanvas: {
    activeCanvasId: CASE_CANVASES[0]?.id || '',
    root: '',
    treeExpanded: new Set(['']),
    selectedPath: '',
    selectedType: '',
    selectedContent: '',
    graphNodes: [],
    graphEdges: [],
    graphNetwork: null,
    graphData: null,
    graphRenderMode: 'unknown'
  },
  pdf: {
    renderRunId: 0,
    rerenderTimer: null
  },
  shellLayout: {
    leftWidth: 0,
    rightWidth: 0
  },
  agent: {
    conversations: [],
    activeConversationId: null,
    nextConversationId: 1,
    nextMessageId: 1
  }
};

let els = {};
const agentStreamRuns = new Map();
let agentStreamUnsubscribe = null;
let cachedPdfJsModulePromise = null;

function configurePdfWorker(pdfjs) {
  if (!pdfjs || !pdfjs.GlobalWorkerOptions) {
    throw new Error('pdfjs GlobalWorkerOptions is unavailable.');
  }

  if (pdfjs.GlobalWorkerOptions.workerSrc) {
    return pdfjs.GlobalWorkerOptions.workerSrc;
  }

  const candidates = [
    'pdfjs-dist/legacy/build/pdf.worker.min.js',
    '../node_modules/pdfjs-dist/legacy/build/pdf.worker.min.js',
    'pdfjs-dist/legacy/build/pdf.worker.js',
    '../node_modules/pdfjs-dist/legacy/build/pdf.worker.js'
  ];

  let lastError = null;
  for (const candidate of candidates) {
    try {
      const resolved = require.resolve(candidate);
      const workerSrc = pathToFileURL(resolved).toString();
      pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
      return workerSrc;
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error('Unable to resolve pdf.js worker script.');
}

function ensurePdfRuntimeGlobals() {
  if (typeof window === 'undefined') return;
  if (typeof globalThis.DOMMatrix === 'undefined' && typeof window.DOMMatrix !== 'undefined') {
    globalThis.DOMMatrix = window.DOMMatrix;
  }
  if (typeof globalThis.ImageData === 'undefined' && typeof window.ImageData !== 'undefined') {
    globalThis.ImageData = window.ImageData;
  }
  if (typeof globalThis.Path2D === 'undefined' && typeof window.Path2D !== 'undefined') {
    globalThis.Path2D = window.Path2D;
  }
}

async function withPdfBrowserRuntime(loadFn) {
  const hadOwnProcess = Object.prototype.hasOwnProperty.call(globalThis, 'process');
  const savedProcess = globalThis.process;
  try {
    // Force pdf.js environment detection to browser mode in Electron renderer.
    globalThis.process = undefined;
    return await loadFn();
  } finally {
    if (hadOwnProcess) {
      globalThis.process = savedProcess;
    } else {
      try {
        delete globalThis.process;
      } catch {
        // no-op
      }
    }
  }
}

function initShell() {
  const root = document.getElementById('goldenRoot');
  const caseCanvasButtons = CASE_CANVASES.map((canvas) => {
    const label = String(canvas.shortLabel || canvas.label || 'Case Canvas');
    const title = String(canvas.label || label);
    return `<button class="vault-btn vault-btn-canvas case-canvas-btn" data-canvas-id="${canvas.id}" title="Open ${title} (read-only)">${label}</button>`;
  }).join('');
  root.innerHTML = `
    <div class="app-shell">
      <section class="sidebar-layout">
        <aside class="activity-bar">
          <button class="activity-btn active" data-tab="files" title="Files">📁</button>
          <button class="activity-btn" data-tab="search" title="Search">🔎</button>
          <button class="activity-btn activity-btn-trial" data-action="trial-canvas" title="Trial Canvas" aria-label="Trial Canvas">⚖️</button>
          <button class="activity-btn" data-tab="graph" title="Casefile View" aria-label="Casefile View">🕸️</button>
          <button class="activity-btn activity-btn-caselaw" data-tab="ontology-graph" title="Caselaw View" aria-label="Caselaw View">
            <svg class="activity-icon-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <circle cx="6" cy="6" r="2.2" />
              <circle cx="18" cy="6" r="2.2" />
              <circle cx="12" cy="12" r="2.2" />
              <circle cx="6" cy="18" r="2.2" />
              <circle cx="18" cy="18" r="2.2" />
              <line x1="7.8" y1="7.4" x2="10.2" y2="10.4" />
              <line x1="16.2" y1="7.4" x2="13.8" y2="10.4" />
              <line x1="7.8" y1="16.6" x2="10.2" y2="13.6" />
              <line x1="16.2" y1="16.6" x2="13.8" y2="13.6" />
              <line x1="8.2" y1="6" x2="15.8" y2="6" />
              <line x1="8.2" y1="18" x2="15.8" y2="18" />
            </svg>
          </button>
        </aside>
        <aside class="left-pane">
          <div class="pane-header">
            <div class="pane-header-top">
              <div id="vaultPath" class="vault-path">Vault</div>
              <button id="vaultImportBtn" class="vault-btn" title="Import files into vault">Import</button>
              <button id="vaultChooseBtn" class="vault-btn" title="Select vault folder">Switch</button>
              <button id="openVaultGraphBtn" class="vault-btn vault-btn-graph" title="Open Casefile View">Casefile View</button>
              <button id="openOntologyGraphBtn" class="vault-btn vault-btn-caselaw" title="Open Caselaw View">Caselaw View</button>
              ${caseCanvasButtons}
            </div>
            <div id="vaultStatus" class="vault-status">Checking vault access...</div>
            <input id="globalSearch" type="text" placeholder="Search vault…" />
            <div class="icon-toolbar">
              <button id="vaultNewNoteBtn" class="icon-btn" title="Create note">📝</button>
              <button id="vaultNewFolderBtn" class="icon-btn" title="Create folder">📁</button>
              <button id="vaultRenameBtn" class="icon-btn" title="Rename selected">✏</button>
              <button id="vaultDeleteBtn" class="icon-btn" title="Delete selected">🗑</button>
            </div>
          </div>
          <div id="filesTab" class="left-content"></div>
          <div id="searchTab" class="left-content hidden"><div id="searchResults"></div></div>
        </aside>
      </section>
      <div
        id="leftSidebarResizer"
        class="pane-resizer pane-resizer-left"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize left sidebar"
        title="Drag to resize left sidebar"
      ></div>

      <main class="center-pane">
        <div id="tabs" class="tabs"></div>
        <div id="editorToolbar" class="editor-toolbar">
          <div class="editor-toolbar-left">
            <span id="currentFile">No file selected</span>
            <span id="buildSourceBadge" class="build-source-badge" data-source="unknown" title="Build source unavailable">Build: unknown</span>
          </div>
          <div class="toolbar-actions">
            <button id="refreshBtn">Refresh Vault</button>
            <button id="appReloadBtn" title="Reload app and pick up latest code changes">Reload App</button>
            <button id="saveBtn">Save</button>
          </div>
        </div>
        <div id="mainViewHost" class="main-view-host">
          <textarea id="editor" spellcheck="false" placeholder="Open a file to edit..."></textarea>
          <div id="pdfWrap" class="pdf-wrap hidden">
            <div id="pdfStatus" class="pdf-status hidden"></div>
            <div id="pdfCanvasWrap" class="pdf-canvas-wrap"></div>
            <iframe id="pdfFrame" class="pdf-frame hidden" title="PDF Viewer"></iframe>
          </div>
          <div id="mediaWrap" class="media-wrap hidden">
            <img id="mediaImage" class="media-image hidden" alt="Image Preview" />
            <audio id="mediaAudio" class="media-audio hidden" controls preload="metadata"></audio>
            <video id="mediaVideo" class="media-video hidden" controls preload="metadata"></video>
            <div id="binaryInfo" class="binary-info hidden"></div>
          </div>
          <div id="graphWrap" class="graph-wrap hidden">
            <div id="graphContainer" class="graph-container"></div>
            <div id="graphMeta" class="graph-hint">Scroll to zoom • Drag to pan • Click node to open note • Double-click background to fit</div>
          </div>
          <div id="ontologyGraphWrap" class="ontology-graph-wrap hidden">
            <div id="ontologyControlsHost" class="ontology-controls-host">
              <div id="ontologyControls" class="ontology-controls">
              <input id="ontologyGraphSearch" type="text" placeholder="Search case nodes (caption, citation, doctrine)…" />
              <div class="ontology-control-row">
                <label class="ontology-control-label">Node Types</label>
                <div id="ontologyNodeTypes" class="ontology-checklist">
                  <label><input type="checkbox" value="case" checked />Case</label>
                  <label><input type="checkbox" value="constitution" checked />Constitution</label>
                  <label><input type="checkbox" value="statute" checked />USC Title</label>
                  <label><input type="checkbox" value="regulation" checked />CFR Title</label>
                  <label><input type="checkbox" value="taxonomy" checked />Taxonomy</label>
                </div>
              </div>
              <div class="ontology-control-row">
                <label class="ontology-control-label">Relation Types</label>
                <div id="ontologyRelationTypes" class="ontology-checklist">
                  <label><input type="checkbox" value="applies" checked />applies</label>
                  <label><input type="checkbox" value="clarifies" checked />clarifies</label>
                  <label><input type="checkbox" value="extends" checked />extends</label>
                  <label><input type="checkbox" value="distinguishes" checked />distinguishes</label>
                  <label><input type="checkbox" value="limits" checked />limits</label>
                  <label><input type="checkbox" value="overrules" checked />overrules</label>
                  <label><input type="checkbox" value="questions" checked />questions</label>
                </div>
              </div>
              <div class="ontology-control-grid">
                <label>view_preset
                  <select id="ontologyViewPreset">
                    <option value="full_ontology" selected>full_ontology</option>
                    <option value="core_precedent">core_precedent</option>
                    <option value="constitutional">constitutional</option>
                    <option value="statutory_regulatory">statutory_regulatory</option>
                  </select>
                </label>
                <label>citation_type
                  <select id="ontologyCitationType">
                    <option value="all">all</option>
                    <option value="controlling">controlling</option>
                    <option value="persuasive">persuasive</option>
                    <option value="background">background</option>
                  </select>
                </label>
                <label>case_domain
                  <select id="ontologyCaseDomain">
                    <option value="all">all</option>
                    <option value="criminal">criminal</option>
                    <option value="civil">civil</option>
                  </select>
                </label>
                <label>court_level
                  <select id="ontologyCourtLevel">
                    <option value="all">all</option>
                    <option value="supreme">supreme</option>
                    <option value="circuit">circuit</option>
                    <option value="district">district</option>
                  </select>
                </label>
                <label>originating_circuit
                  <select id="ontologyOriginatingCircuit">
                    <option value="all">all</option>
                    <option value="ca1">First Circuit</option>
                    <option value="ca2">Second Circuit</option>
                    <option value="ca3">Third Circuit</option>
                    <option value="ca4">Fourth Circuit</option>
                    <option value="ca5">Fifth Circuit</option>
                    <option value="ca6">Sixth Circuit</option>
                    <option value="ca7">Seventh Circuit</option>
                    <option value="ca8">Eighth Circuit</option>
                    <option value="ca9">Ninth Circuit</option>
                    <option value="ca10">Tenth Circuit</option>
                    <option value="ca11">Eleventh Circuit</option>
                    <option value="cadc">D.C. Circuit</option>
                  </select>
                </label>
                <label>normative_strength
                  <select id="ontologyNormativeStrength">
                    <option value="all">all</option>
                    <option value="binding_core">binding_core</option>
                    <option value="binding_narrow">binding_narrow</option>
                    <option value="persuasive">persuasive</option>
                    <option value="dicta">dicta</option>
                  </select>
                </label>
                <label>fact_dimension
                  <input id="ontologyFactDimension" type="text" placeholder="vehicle_status" />
                </label>
                <label>min_edge_strength
                  <input id="ontologyMinEdgeStrength" type="number" step="0.01" min="0" max="1" placeholder="none" />
                </label>
                <label>min_case_importance
                  <input id="ontologyMinCaseImportance" type="number" step="0.01" min="0" max="1" placeholder="none" />
                </label>
                <label>max_edges_per_node
                  <input id="ontologyMaxEdgesPerNode" type="number" step="1" min="1" max="250" placeholder="none" />
                </label>
                <label>PF_min
                  <input id="ontologyPfMin" type="number" step="0.01" min="0" placeholder="none" />
                </label>
                <label>consensus_min
                  <input id="ontologyConsensusMin" type="number" step="0.01" min="0" max="1" placeholder="none" />
                </label>
                <label>drift_max
                  <input id="ontologyDriftMax" type="number" step="0.01" min="0" max="1" placeholder="none" />
                </label>
                <label>relation_confidence_min
                  <input id="ontologyRelationConfidenceMin" type="number" step="0.01" min="0" max="1" placeholder="none" />
                </label>
                <label>max_nodes
                  <input id="ontologyMaxNodes" type="number" step="1" min="100" max="20000" value="20000" />
                </label>
              </div>
              <div class="ontology-actions">
                <button id="ontologyApplyBtn" type="button">Apply</button>
                <button id="ontologyResetBtn" type="button">Reset</button>
                <button id="ontologyForceRefreshBtn" type="button" title="Reload ontology graph data from the vault">Force Refresh</button>
                <span id="ontologyRefreshStatus" class="ontology-refresh-status" data-state="neutral">Ready.</span>
              </div>
            </div>
            </div>
            <div id="ontologyGraphDiagnostics" class="ontology-diagnostics hidden" data-state="neutral" aria-live="polite"></div>
            <div id="ontologySampleNotice" class="ontology-sample-notice hidden" aria-live="polite"></div>
            <div id="ontologyGraphBody" class="ontology-graph-body">
              <div id="ontologyGraphContainer" class="graph-container ontology-graph-container"></div>
              <aside id="ontologyCaseSidebar" class="ontology-case-sidebar">
                <div class="ontology-case-sidebar-header">
                  <div id="ontologyCaseSidebarTitle" class="ontology-case-sidebar-title">Case Reader</div>
                  <button id="ontologyCaseSidebarClose" class="ontology-case-sidebar-close" type="button">Close</button>
                </div>
                <div id="ontologyCaseSidebarTabs" class="ontology-case-tabs hidden"></div>
                <div id="ontologyCaseSidebarMeta" class="ontology-case-sidebar-meta">Select a case to view details.</div>
                <iframe id="ontologyCasePdfFrame" class="ontology-case-pdf-frame hidden" title="Case PDF Reader"></iframe>
                <div id="ontologyCaseSidebarEmpty" class="ontology-case-sidebar-empty">No PDF available for this case.</div>
              </aside>
              <div id="ontologyCaseHoverCard" class="ontology-case-hover hidden"></div>
            </div>
            <div id="ontologyGraphMeta" class="graph-hint">Ontology graph ready.</div>
          </div>
        </div>
        <div id="trialCanvasView" class="trial-canvas-view hidden" aria-label="Trial Canvas View">
          <aside class="trial-canvas-sidebar">
            <div class="trial-canvas-sidebar-header">
              <div>
                <div id="trialCanvasLabel" class="trial-canvas-label">Trial Canvas</div>
                <div id="trialCanvasPath" class="trial-canvas-path"></div>
              </div>
              <button id="trialCanvasRefreshBtn" class="trial-canvas-btn" title="Reload Savani vault">Refresh</button>
            </div>
            <div id="trialCanvasSidebarStatus" class="trial-canvas-status"></div>
            <div id="trialCanvasTree" class="trial-canvas-tree"></div>
          </aside>
          <section class="trial-canvas-center">
            <div class="trial-canvas-center-header">
              <div>
                <div id="trialCanvasCurrentTitle" class="trial-canvas-current-title">Savani Canvas</div>
                <div id="trialCanvasCurrentRelPath" class="trial-canvas-current-path"></div>
              </div>
            </div>
            <div id="trialCanvasContent" class="trial-canvas-content">
              <div class="trial-canvas-empty">Select a note from the Savani vault.</div>
            </div>
          </section>
          <aside class="trial-canvas-graph-pane">
            <div class="trial-canvas-graph-header">
              <span>Canvas Relationships</span>
              <button id="trialCanvasGraphRefreshBtn" class="trial-canvas-btn" title="Rebuild relationships from current note">Reload</button>
            </div>
            <div id="trialCanvasGraphContainer" class="trial-canvas-graph-container"></div>
            <div id="trialCanvasGraphMeta" class="graph-hint">Relationships detected from mentions inside the active note.</div>
          </aside>
        </div>
      </main>
      <div
        id="rightSidebarResizer"
        class="pane-resizer pane-resizer-right"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize right sidebar"
        title="Drag to resize right sidebar"
      ></div>

      <aside class="right-pane">
        <div class="agent-header">
          <span>Agent</span>
          <button id="agentNewConversation" class="agent-new-btn" title="Start a new conversation">New</button>
        </div>
        <div class="agent-layout">
          <div id="agentThreads" class="agent-threads"></div>
          <div class="agent-chat">
            <div id="agentMessages" class="agent-messages"></div>
            <div class="agent-input-wrap">
              <textarea id="agentInput" rows="4" placeholder="Ask the agent..."></textarea>
              <button id="agentSend">Send</button>
            </div>
          </div>
        </div>
      </aside>
    </div>
  `;
}

function cacheElements() {
  els = {
    appShell: document.querySelector('.app-shell'),
    leftSidebarResizer: document.getElementById('leftSidebarResizer'),
    rightSidebarResizer: document.getElementById('rightSidebarResizer'),
    vaultPath: document.getElementById('vaultPath'),
    vaultStatus: document.getElementById('vaultStatus'),
    vaultImportBtn: document.getElementById('vaultImportBtn'),
    vaultChooseBtn: document.getElementById('vaultChooseBtn'),
    openVaultGraphBtn: document.getElementById('openVaultGraphBtn'),
    openOntologyGraphBtn: document.getElementById('openOntologyGraphBtn'),
    caseCanvasButtons: Array.from(document.querySelectorAll('.case-canvas-btn')),
    vaultNewNoteBtn: document.getElementById('vaultNewNoteBtn'),
    vaultNewFolderBtn: document.getElementById('vaultNewFolderBtn'),
    vaultRenameBtn: document.getElementById('vaultRenameBtn'),
    vaultDeleteBtn: document.getElementById('vaultDeleteBtn'),
    filesTab: document.getElementById('filesTab'),
    searchTab: document.getElementById('searchTab'),
    graphContainer: document.getElementById('graphContainer'),
    graphMeta: document.getElementById('graphMeta'),
    trialCanvasView: document.getElementById('trialCanvasView'),
    trialCanvasLabel: document.getElementById('trialCanvasLabel'),
    trialCanvasPath: document.getElementById('trialCanvasPath'),
    trialCanvasSidebarStatus: document.getElementById('trialCanvasSidebarStatus'),
    trialCanvasTree: document.getElementById('trialCanvasTree'),
    trialCanvasContent: document.getElementById('trialCanvasContent'),
    trialCanvasCurrentTitle: document.getElementById('trialCanvasCurrentTitle'),
    trialCanvasCurrentRelPath: document.getElementById('trialCanvasCurrentRelPath'),
    trialCanvasRefreshBtn: document.getElementById('trialCanvasRefreshBtn'),
    trialCanvasGraphContainer: document.getElementById('trialCanvasGraphContainer'),
    trialCanvasGraphRefreshBtn: document.getElementById('trialCanvasGraphRefreshBtn'),
    trialCanvasGraphMeta: document.getElementById('trialCanvasGraphMeta'),
    ontologyGraphBody: document.getElementById('ontologyGraphBody'),
    ontologyGraphContainer: document.getElementById('ontologyGraphContainer'),
    ontologyCaseSidebar: document.getElementById('ontologyCaseSidebar'),
    ontologyCaseSidebarTitle: document.getElementById('ontologyCaseSidebarTitle'),
    ontologyCaseSidebarTabs: document.getElementById('ontologyCaseSidebarTabs'),
    ontologyCaseSidebarMeta: document.getElementById('ontologyCaseSidebarMeta'),
    ontologyCaseSidebarClose: document.getElementById('ontologyCaseSidebarClose'),
    ontologyCaseSidebarEmpty: document.getElementById('ontologyCaseSidebarEmpty'),
    ontologyCasePdfFrame: document.getElementById('ontologyCasePdfFrame'),
    ontologyCaseHoverCard: document.getElementById('ontologyCaseHoverCard'),
    tabs: document.getElementById('tabs'),
    editorToolbar: document.getElementById('editorToolbar'),
    editor: document.getElementById('editor'),
    pdfWrap: document.getElementById('pdfWrap'),
    pdfStatus: document.getElementById('pdfStatus'),
    pdfCanvasWrap: document.getElementById('pdfCanvasWrap'),
    pdfFrame: document.getElementById('pdfFrame'),
    mediaWrap: document.getElementById('mediaWrap'),
    mediaImage: document.getElementById('mediaImage'),
    mediaAudio: document.getElementById('mediaAudio'),
    mediaVideo: document.getElementById('mediaVideo'),
    binaryInfo: document.getElementById('binaryInfo'),
    graphWrap: document.getElementById('graphWrap'),
    ontologyGraphWrap: document.getElementById('ontologyGraphWrap'),
    ontologyControlsHost: document.getElementById('ontologyControlsHost'),
    ontologyControls: document.getElementById('ontologyControls'),
    ontologyGraphSearch: document.getElementById('ontologyGraphSearch'),
    ontologyNodeTypes: document.getElementById('ontologyNodeTypes'),
    ontologyRelationTypes: document.getElementById('ontologyRelationTypes'),
    ontologyViewPreset: document.getElementById('ontologyViewPreset'),
    ontologyCitationType: document.getElementById('ontologyCitationType'),
    ontologyCaseDomain: document.getElementById('ontologyCaseDomain'),
    ontologyCourtLevel: document.getElementById('ontologyCourtLevel'),
    ontologyOriginatingCircuit: document.getElementById('ontologyOriginatingCircuit'),
    ontologyNormativeStrength: document.getElementById('ontologyNormativeStrength'),
    ontologyFactDimension: document.getElementById('ontologyFactDimension'),
    ontologyMinEdgeStrength: document.getElementById('ontologyMinEdgeStrength'),
    ontologyMinCaseImportance: document.getElementById('ontologyMinCaseImportance'),
    ontologyMaxEdgesPerNode: document.getElementById('ontologyMaxEdgesPerNode'),
    ontologyPfMin: document.getElementById('ontologyPfMin'),
    ontologyConsensusMin: document.getElementById('ontologyConsensusMin'),
    ontologyDriftMax: document.getElementById('ontologyDriftMax'),
    ontologyRelationConfidenceMin: document.getElementById('ontologyRelationConfidenceMin'),
    ontologyMaxNodes: document.getElementById('ontologyMaxNodes'),
    ontologyApplyBtn: document.getElementById('ontologyApplyBtn'),
    ontologyResetBtn: document.getElementById('ontologyResetBtn'),
    ontologyForceRefreshBtn: document.getElementById('ontologyForceRefreshBtn'),
    ontologyRefreshStatus: document.getElementById('ontologyRefreshStatus'),
    ontologyGraphDiagnostics: document.getElementById('ontologyGraphDiagnostics'),
    ontologySampleNotice: document.getElementById('ontologySampleNotice'),
    ontologyGraphMeta: document.getElementById('ontologyGraphMeta'),
    currentFile: document.getElementById('currentFile'),
    buildSourceBadge: document.getElementById('buildSourceBadge'),
    saveBtn: document.getElementById('saveBtn'),
    refreshBtn: document.getElementById('refreshBtn'),
    appReloadBtn: document.getElementById('appReloadBtn'),
    globalSearch: document.getElementById('globalSearch'),
    searchResults: document.getElementById('searchResults'),
    agentThreads: document.getElementById('agentThreads'),
    agentMessages: document.getElementById('agentMessages'),
    agentInput: document.getElementById('agentInput'),
    agentSend: document.getElementById('agentSend'),
    agentNewConversation: document.getElementById('agentNewConversation')
  };
}

function hasRequiredElements() {
  return Boolean(
      els.appShell &&
      els.leftSidebarResizer &&
      els.rightSidebarResizer &&
      els.vaultPath &&
      els.vaultStatus &&
      els.vaultImportBtn &&
      els.vaultChooseBtn &&
      els.vaultNewNoteBtn &&
      els.vaultNewFolderBtn &&
      els.vaultRenameBtn &&
      els.vaultDeleteBtn &&
      els.filesTab &&
      els.searchTab &&
      els.graphContainer &&
      els.graphMeta &&
      els.ontologyGraphBody &&
      els.ontologyGraphContainer &&
      els.ontologyCaseSidebar &&
      els.ontologyCaseSidebarTitle &&
      els.ontologyCaseSidebarTabs &&
      els.ontologyCaseSidebarMeta &&
      els.ontologyCaseSidebarClose &&
      els.ontologyCaseSidebarEmpty &&
      els.ontologyCasePdfFrame &&
      els.ontologyCaseHoverCard &&
      els.tabs &&
      els.editorToolbar &&
      els.editor &&
      els.pdfWrap &&
      els.pdfStatus &&
      els.pdfCanvasWrap &&
      els.mediaWrap &&
      els.mediaImage &&
      els.mediaAudio &&
      els.mediaVideo &&
      els.binaryInfo &&
      els.graphWrap &&
      els.ontologyGraphWrap &&
      els.ontologyControlsHost &&
      els.ontologyControls &&
      els.ontologyGraphSearch &&
      els.ontologyNodeTypes &&
      els.ontologyRelationTypes &&
      els.ontologyViewPreset &&
      els.ontologyCitationType &&
      els.ontologyCaseDomain &&
      els.ontologyCourtLevel &&
      els.ontologyOriginatingCircuit &&
      els.ontologyNormativeStrength &&
      els.ontologyFactDimension &&
      els.ontologyMinEdgeStrength &&
      els.ontologyMinCaseImportance &&
      els.ontologyMaxEdgesPerNode &&
      els.ontologyPfMin &&
      els.ontologyConsensusMin &&
      els.ontologyDriftMax &&
      els.ontologyRelationConfidenceMin &&
      els.ontologyMaxNodes &&
      els.ontologyApplyBtn &&
      els.ontologyResetBtn &&
      els.ontologyForceRefreshBtn &&
      els.ontologyRefreshStatus &&
      els.ontologyGraphDiagnostics &&
      els.ontologySampleNotice &&
      els.ontologyGraphMeta &&
      els.currentFile &&
      els.buildSourceBadge &&
      els.saveBtn &&
      els.refreshBtn &&
      els.appReloadBtn &&
      els.globalSearch &&
      els.searchResults &&
      els.agentThreads &&
      els.agentMessages &&
      els.agentInput &&
      els.agentSend &&
      els.agentNewConversation
  );
}

async function waitForRenderedElements(maxAttempts = 120, delayMs = 25) {
  for (let i = 0; i < maxAttempts; i++) {
    cacheElements();
    if (hasRequiredElements()) return;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  throw new Error('UI mount failed: renderer components did not render required elements in time.');
}

function clampNumber(value, min, max) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return min;
  return Math.min(max, Math.max(min, numeric));
}

function getShellWidth() {
  const width = Number(els.appShell?.getBoundingClientRect?.()?.width || 0);
  if (Number.isFinite(width) && width > 1) return width;
  const viewportWidth = Number(window.innerWidth || document.documentElement.clientWidth || 0);
  if (Number.isFinite(viewportWidth) && viewportWidth > 1) return viewportWidth;
  return 1200;
}

function defaultSidebarWidths(shellWidth = 0) {
  const width = Math.max(800, Number(shellWidth) || getShellWidth());
  const left = clampNumber(Math.round(width * 0.22), SHELL_MIN_LEFT_WIDTH, 420);
  const right = clampNumber(Math.round(width * 0.24), SHELL_MIN_RIGHT_WIDTH, 460);
  return { leftWidth: left, rightWidth: right };
}

function readStoredSidebarWidths() {
  try {
    const parsed = JSON.parse(localStorage.getItem(SIDEBAR_LAYOUT_STORAGE_KEY) || 'null');
    if (!parsed || typeof parsed !== 'object') return {};
    return {
      leftWidth: Number(parsed.leftWidth),
      rightWidth: Number(parsed.rightWidth)
    };
  } catch {
    return {};
  }
}

function persistSidebarWidths(widths = {}) {
  try {
    localStorage.setItem(
      SIDEBAR_LAYOUT_STORAGE_KEY,
      JSON.stringify({
        leftWidth: Math.round(Number(widths.leftWidth) || 0),
        rightWidth: Math.round(Number(widths.rightWidth) || 0)
      })
    );
  } catch {
    // ignore persistence failures
  }
}

function normalizeSidebarWidths(layout = {}, options = {}) {
  const shellWidth = Math.max(800, Number(options.shellWidth) || getShellWidth());
  const defaults = defaultSidebarWidths(shellWidth);

  const maxLeftCap = Math.max(
    SHELL_MIN_LEFT_WIDTH,
    Math.min(SHELL_MAX_LEFT_WIDTH, shellWidth - SHELL_MIN_CENTER_WIDTH - SHELL_MIN_RIGHT_WIDTH)
  );
  const maxRightCap = Math.max(
    SHELL_MIN_RIGHT_WIDTH,
    Math.min(SHELL_MAX_RIGHT_WIDTH, shellWidth - SHELL_MIN_CENTER_WIDTH - SHELL_MIN_LEFT_WIDTH)
  );

  let leftWidth = Number(layout.leftWidth);
  let rightWidth = Number(layout.rightWidth);
  if (!Number.isFinite(leftWidth)) leftWidth = defaults.leftWidth;
  if (!Number.isFinite(rightWidth)) rightWidth = defaults.rightWidth;

  leftWidth = clampNumber(leftWidth, SHELL_MIN_LEFT_WIDTH, maxLeftCap);
  rightWidth = clampNumber(rightWidth, SHELL_MIN_RIGHT_WIDTH, maxRightCap);

  const maxCombined = Math.max(
    SHELL_MIN_LEFT_WIDTH + SHELL_MIN_RIGHT_WIDTH,
    shellWidth - SHELL_MIN_CENTER_WIDTH
  );
  if (leftWidth + rightWidth > maxCombined) {
    let overflow = leftWidth + rightWidth - maxCombined;
    const preserve = options.preserveSide === 'left' || options.preserveSide === 'right' ? options.preserveSide : '';

    const shrinkLeft = () => {
      if (overflow <= 0) return;
      const reducible = Math.max(0, leftWidth - SHELL_MIN_LEFT_WIDTH);
      const delta = Math.min(reducible, overflow);
      leftWidth -= delta;
      overflow -= delta;
    };
    const shrinkRight = () => {
      if (overflow <= 0) return;
      const reducible = Math.max(0, rightWidth - SHELL_MIN_RIGHT_WIDTH);
      const delta = Math.min(reducible, overflow);
      rightWidth -= delta;
      overflow -= delta;
    };

    if (preserve === 'left') {
      shrinkRight();
      shrinkLeft();
    } else if (preserve === 'right') {
      shrinkLeft();
      shrinkRight();
    } else if (leftWidth >= rightWidth) {
      shrinkLeft();
      shrinkRight();
    } else {
      shrinkRight();
      shrinkLeft();
    }
  }

  return {
    leftWidth: Math.round(leftWidth),
    rightWidth: Math.round(rightWidth)
  };
}

function applySidebarWidths(layout = {}, options = {}) {
  const shell = els.appShell || document.querySelector('.app-shell');
  if (!shell) return;

  const next = normalizeSidebarWidths(
    {
      leftWidth: layout.leftWidth ?? state.shellLayout.leftWidth,
      rightWidth: layout.rightWidth ?? state.shellLayout.rightWidth
    },
    {
      shellWidth: Number(shell.getBoundingClientRect().width) || getShellWidth(),
      preserveSide: options.preserveSide
    }
  );

  state.shellLayout.leftWidth = next.leftWidth;
  state.shellLayout.rightWidth = next.rightWidth;

  shell.style.setProperty('--left-sidebar-width', `${next.leftWidth}px`);
  shell.style.setProperty('--right-sidebar-width', `${next.rightWidth}px`);

  if (options.persist !== false) {
    persistSidebarWidths(next);
  }
}

function initializeSidebarWidths() {
  const stored = readStoredSidebarWidths();
  applySidebarWidths(stored, { persist: false });
}

function wireSidebarResizers(onResize) {
  const shell = els.appShell;
  if (!shell || !els.leftSidebarResizer || !els.rightSidebarResizer) return;

  const queueResize = (() => {
    let raf = 0;
    return () => {
      if (!onResize || raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        onResize();
      });
    };
  })();

  const beginDrag = (side, event) => {
    if (event.button !== 0) return;
    event.preventDefault();

    const startX = Number(event.clientX) || 0;
    const startLeft = Number(state.shellLayout.leftWidth) || defaultSidebarWidths().leftWidth;
    const startRight = Number(state.shellLayout.rightWidth) || defaultSidebarWidths().rightWidth;
    const pointerId = event.pointerId;
    const handle = side === 'left' ? els.leftSidebarResizer : els.rightSidebarResizer;

    shell.classList.add('resizing');
    handle?.classList.add('active');
    try {
      handle?.setPointerCapture?.(pointerId);
    } catch {
      // ignore pointer capture failures
    }

    const onMove = (moveEvent) => {
      const dx = Number(moveEvent.clientX) - startX;
      if (!Number.isFinite(dx)) return;

      if (side === 'left') {
        applySidebarWidths(
          { leftWidth: startLeft + dx, rightWidth: startRight },
          { persist: false, preserveSide: 'left' }
        );
      } else {
        applySidebarWidths(
          { leftWidth: startLeft, rightWidth: startRight - dx },
          { persist: false, preserveSide: 'right' }
        );
      }
      queueResize();
    };

    const onEnd = () => {
      shell.classList.remove('resizing');
      handle?.classList.remove('active');
      applySidebarWidths({}, { persist: true });
      if (onResize) onResize();
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      window.removeEventListener('pointercancel', onEnd);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd);
    window.addEventListener('pointercancel', onEnd);
  };

  els.leftSidebarResizer.addEventListener('pointerdown', (event) => beginDrag('left', event));
  els.rightSidebarResizer.addEventListener('pointerdown', (event) => beginDrag('right', event));
}

function getLowerExt(filePath = '') {
  const idx = String(filePath || '').lastIndexOf('.');
  if (idx < 0) return '';
  return String(filePath).slice(idx).toLowerCase();
}

function pathIsDirectory(absPath = '') {
  try {
    return fs.statSync(absPath).isDirectory();
  } catch {
    return false;
  }
}

function pathIsFile(absPath = '') {
  try {
    return fs.statSync(absPath).isFile();
  } catch {
    return false;
  }
}

function getCaseCanvasById(id) {
  const normalized = String(id || '').trim();
  if (!normalized) return null;
  return CASE_CANVASES.find((canvas) => canvas.id === normalized) || null;
}

function resolveCaseCanvasEntry(canvas) {
  if (!canvas || !canvas.vaultRoot) return null;
  const root = path.resolve(String(canvas.vaultRoot || '').trim());
  if (!pathIsDirectory(root)) return null;

  const candidates = Array.isArray(canvas.entryCandidates) ? canvas.entryCandidates : [];
  for (const rel of candidates) {
    const relPath = String(rel || '').trim();
    if (!relPath) continue;
    const abs = path.resolve(root, relPath);
    if (!abs.startsWith(root + path.sep) && abs !== root) continue;
    if (pathIsFile(abs)) return { relPath, absPath: abs };
  }

  try {
    const entries = fs.readdirSync(root, { withFileTypes: true });
    const firstMarkdown = entries.find((entry) => entry.isFile() && /\.md$/i.test(entry.name));
    if (firstMarkdown) {
      const abs = path.resolve(root, firstMarkdown.name);
      if (pathIsFile(abs)) return { relPath: firstMarkdown.name, absPath: abs };
    }
  } catch {
    // ignore
  }

  return null;
}

function isTextExtension(ext = '') {
  return TEXT_EXTENSIONS.has(ext);
}

function isPdfExtension(ext = '') {
  return PDF_EXTENSIONS.has(ext);
}

function isImageExtension(ext = '') {
  return IMAGE_EXTENSIONS.has(ext);
}

function isAudioExtension(ext = '') {
  return AUDIO_EXTENSIONS.has(ext);
}

function isVideoExtension(ext = '') {
  return VIDEO_EXTENSIONS.has(ext);
}

function isProcessableDocumentExtension(ext = '') {
  return PROCESSABLE_DOCUMENT_EXTENSIONS.has(ext);
}

function basenameOf(relPath = '') {
  const clean = String(relPath || '').replaceAll('\\', '/').replace(/\/+$/g, '');
  if (!clean) return '';
  const idx = clean.lastIndexOf('/');
  return idx >= 0 ? clean.slice(idx + 1) : clean;
}

function dirnameOf(relPath = '') {
  const clean = String(relPath || '').replaceAll('\\', '/').replace(/\/+$/g, '');
  if (!clean) return '';
  const idx = clean.lastIndexOf('/');
  return idx >= 0 ? clean.slice(0, idx) : '';
}

function hasNameExtension(name = '') {
  return /\.[^./\\]+$/.test(String(name || ''));
}

function matchesPathScope(candidatePath, targetPath, isDirectory = false) {
  const candidate = String(candidatePath || '').replaceAll('\\', '/');
  const target = String(targetPath || '').replaceAll('\\', '/');
  if (!candidate || !target) return false;
  if (candidate === target) return true;
  if (!isDirectory) return false;
  return candidate.startsWith(`${target}/`);
}

function applyTreeSelectionStyles() {
  const selection = state.vaultSelection;
  document.querySelectorAll('.tree-item').forEach((row) => {
    const matches =
      Boolean(selection) &&
      row.dataset.path === selection.path &&
      row.dataset.type === selection.type;
    row.classList.toggle('selected', matches);
  });
}

function updateVaultActionState() {
  const editableTree = state.vaultViewKind !== 'caselaw';
  const writable = Boolean(state.vaultAccess?.writable) && editableTree;
  const hasSelection = editableTree && Boolean(state.vaultSelection?.path);
  if (els.vaultNewNoteBtn) els.vaultNewNoteBtn.disabled = !writable;
  if (els.vaultNewFolderBtn) els.vaultNewFolderBtn.disabled = !writable;
  if (els.vaultRenameBtn) els.vaultRenameBtn.disabled = !writable || !hasSelection;
  if (els.vaultDeleteBtn) els.vaultDeleteBtn.disabled = !writable || !hasSelection;
}

function setVaultSelection(path = '', type = '') {
  if (!path || !type) {
    state.vaultSelection = null;
  } else {
    state.vaultSelection = {
      path: String(path).replaceAll('\\', '/'),
      type
    };
  }
  applyTreeSelectionStyles();
  updateVaultActionState();
}

function getSelectedParentPath() {
  const selection = state.vaultSelection;
  if (!selection || !selection.path) return '';
  if (selection.type === 'directory') return selection.path;
  return dirnameOf(selection.path);
}

function remapOpenTabsAfterRename(oldPath, nextPath, isDirectory = false) {
  const oldRel = String(oldPath || '').replaceAll('\\', '/');
  const nextRel = String(nextPath || '').replaceAll('\\', '/');
  if (!oldRel || !nextRel) return;

  const remap = (candidate) => {
    if (!candidate || !matchesPathScope(candidate, oldRel, isDirectory)) return candidate;
    if (candidate === oldRel) return nextRel;
    return `${nextRel}${candidate.slice(oldRel.length)}`;
  };

  for (const tab of state.openTabs) {
    if (tab.path) tab.path = remap(tab.path);
    if (tab.sourcePath) tab.sourcePath = remap(tab.sourcePath);
    if (tab.path && tab.kind !== 'graph') {
      tab.title = basenameOf(tab.path) || tab.title;
    }
  }
  const active = state.openTabs.find((t) => t.id === state.activeTabId);
  if (active) {
    els.currentFile.textContent = active.title || active.path || 'No file selected';
  }
  renderTabs();
}

function removeOpenTabsForDeletedPath(targetPath, isDirectory = false) {
  const targetRel = String(targetPath || '').replaceAll('\\', '/');
  if (!targetRel) return;

  const shouldRemove = (tab) =>
    matchesPathScope(tab?.path, targetRel, isDirectory) ||
    matchesPathScope(tab?.sourcePath, targetRel, isDirectory);

  const activeWasRemoved = state.openTabs.some((t) => t.id === state.activeTabId && shouldRemove(t));
  const keptTabs = [];
  for (const tab of state.openTabs) {
    if (shouldRemove(tab)) {
      revokePdfTabObjectUrl(tab);
      continue;
    }
    keptTabs.push(tab);
  }
  state.openTabs = keptTabs;

  if (!state.openTabs.length) {
    createBlankTabAndActivate();
    return;
  }

  if (activeWasRemoved || !state.openTabs.some((t) => t.id === state.activeTabId)) {
    activateTab(state.openTabs[0].id);
  } else {
    renderTabs();
  }
}

function nowMs() {
  return Date.now();
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.valueOf())) return '';
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function lastConversationMessage(conversation) {
  if (!conversation || !Array.isArray(conversation.messages) || !conversation.messages.length) return null;
  return conversation.messages[conversation.messages.length - 1];
}

function conversationPreview(conversation) {
  const msg = lastConversationMessage(conversation);
  if (!msg || !msg.text) return 'No messages yet';
  const compact = msg.text.replace(/\s+/g, ' ').trim();
  if (!compact) return 'No messages yet';
  return compact.length > 70 ? `${compact.slice(0, 67)}...` : compact;
}

function createConversation(title = '') {
  const resolvedTitle = title || `Conversation ${state.agent.nextConversationId}`;
  const conversation = {
    id: state.agent.nextConversationId++,
    title: resolvedTitle,
    createdAt: nowMs(),
    updatedAt: nowMs(),
    pendingCount: 0,
    messages: []
  };
  state.agent.conversations.push(conversation);
  state.agent.activeConversationId = conversation.id;
  persistConversations();
  renderConversationList();
  renderActiveConversationMessages();
  return conversation;
}

function getConversationById(conversationId) {
  return state.agent.conversations.find((c) => c.id === conversationId) || null;
}

function getActiveConversation() {
  return getConversationById(state.agent.activeConversationId);
}

function touchConversation(conversation) {
  if (!conversation) return;
  conversation.updatedAt = nowMs();
}

function setActiveConversation(conversationId) {
  if (!getConversationById(conversationId)) return;
  state.agent.activeConversationId = conversationId;
  persistConversations();
  renderConversationList();
  renderActiveConversationMessages();
}

function deleteConversation(conversationId) {
  const conversation = getConversationById(conversationId);
  if (!conversation) return;

  const ok = window.confirm(`Delete conversation "${conversation.title}"?`);
  if (!ok) return;

  const idx = state.agent.conversations.findIndex((c) => c.id === conversationId);
  if (idx === -1) return;
  state.agent.conversations.splice(idx, 1);

  if (state.agent.activeConversationId === conversationId) {
    const nextActive =
      state.agent.conversations[idx]?.id ||
      state.agent.conversations[idx - 1]?.id ||
      state.agent.conversations[0]?.id ||
      null;
    state.agent.activeConversationId = nextActive;
  }

  persistConversations();
  renderConversationList();
  renderActiveConversationMessages();
}

function buildConversationTitleFromPrompt(prompt) {
  const clean = String(prompt || '').replace(/\s+/g, ' ').trim();
  if (!clean) return '';
  return clean.length > 40 ? `${clean.slice(0, 37)}...` : clean;
}

function maybeRetitleConversation(conversation, prompt) {
  if (!conversation) return;
  const defaultTitle = `Conversation ${conversation.id}`;
  if (conversation.title !== defaultTitle) return;
  const candidate = buildConversationTitleFromPrompt(prompt);
  if (candidate) {
    conversation.title = candidate;
    touchConversation(conversation);
  }
}

function renderConversationList() {
  els.agentThreads.innerHTML = '';
  const ordered = [...state.agent.conversations].sort((a, b) => b.updatedAt - a.updatedAt);

  for (const conversation of ordered) {
    const row = document.createElement('div');
    row.className = `agent-thread ${conversation.id === state.agent.activeConversationId ? 'active' : ''}`;
    row.setAttribute('role', 'listitem');

    const main = document.createElement('button');
    main.type = 'button';
    main.className = 'agent-thread-main';
    main.onclick = () => setActiveConversation(conversation.id);

    const title = document.createElement('div');
    title.className = 'agent-thread-title';
    title.textContent = conversation.title;

    const preview = document.createElement('div');
    preview.className = 'agent-thread-preview';
    preview.textContent = conversationPreview(conversation);

    const meta = document.createElement('div');
    meta.className = 'agent-thread-meta';
    let metaText = formatTime(conversation.updatedAt);
    if (conversation.pendingCount > 0) {
      metaText = metaText ? `${metaText} • ${conversation.pendingCount} pending` : `${conversation.pendingCount} pending`;
    }
    meta.textContent = metaText || ' ';

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'agent-thread-delete icon-btn';
    deleteBtn.title = 'Delete conversation';
    deleteBtn.textContent = '🗑';
    deleteBtn.onclick = (event) => {
      event.stopPropagation();
      deleteConversation(conversation.id);
    };

    main.appendChild(title);
    main.appendChild(preview);
    main.appendChild(meta);
    row.appendChild(main);
    row.appendChild(deleteBtn);
    els.agentThreads.appendChild(row);
  }
}

function renderActiveConversationMessages() {
  els.agentMessages.innerHTML = '';
  const conversation = getActiveConversation();
  if (!conversation) return;

  for (const message of conversation.messages) {
    const div = document.createElement('div');
    div.className = `agent-msg ${message.role} ${message.status || 'complete'}`;
    div.textContent = message.text || '';

    const metaParts = [];
    if (message.meta) metaParts.push(message.meta);
    const ts = formatTime(message.createdAt);
    if (ts) metaParts.push(ts);
    if (metaParts.length) {
      const meta = document.createElement('div');
      meta.className = 'agent-meta';
      meta.textContent = metaParts.join(' • ');
      div.appendChild(meta);
    }

    els.agentMessages.appendChild(div);
  }
  els.agentMessages.scrollTop = els.agentMessages.scrollHeight;
}

function persistConversations() {
  const trimmed = state.agent.conversations.map((c) => ({
    id: c.id,
    title: c.title,
    createdAt: c.createdAt,
    updatedAt: c.updatedAt,
    pendingCount: 0,
    messages: (Array.isArray(c.messages) ? c.messages : [])
      .slice(-MAX_SAVED_MESSAGES)
      .map((m) => ({
        id: m.id,
        role: m.role === 'user' ? 'user' : 'assistant',
        text: typeof m.text === 'string' ? m.text : '',
        meta: typeof m.meta === 'string' ? m.meta : '',
        createdAt: m.createdAt || nowMs(),
        status: m.status === 'error' ? 'error' : 'complete'
      }))
  }));

  const payload = {
    nextConversationId: state.agent.nextConversationId,
    nextMessageId: state.agent.nextMessageId,
    activeConversationId: state.agent.activeConversationId,
    conversations: trimmed
  };
  localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(payload));
}

function isWorkspaceNoticeMessage(message = {}) {
  if (!message || message.role !== 'assistant') return false;
  const meta = String(message.meta || '').trim().toLowerCase();
  if (meta === 'workspace') return true;

  const text = String(message.text || '');
  return (
    text.startsWith('Saved ') ||
    text.startsWith('Vault switched to ') ||
    text.startsWith('Imported ') ||
    text.startsWith('Import failures') ||
    text.startsWith('Import error:') ||
    text.startsWith('Extraction failed for ') ||
    text.startsWith('Graph load error:') ||
    text.startsWith('Graph render error:') ||
    text.startsWith('Ontology graph load error:') ||
    text.startsWith('Ontology graph render error:')
  );
}

function hydrateConversations() {
  let parsed = null;
  try {
    parsed = JSON.parse(localStorage.getItem(CONVERSATIONS_STORAGE_KEY) || 'null');
  } catch {
    parsed = null;
  }

  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.conversations)) {
    return;
  }

  state.agent.conversations = parsed.conversations
    .map((c) => ({
      id: Number(c.id),
      title: typeof c.title === 'string' && c.title.trim() ? c.title.trim() : `Conversation ${c.id}`,
      createdAt: Number(c.createdAt) || nowMs(),
      updatedAt: Number(c.updatedAt) || nowMs(),
      pendingCount: 0,
      messages: Array.isArray(c.messages)
        ? c.messages
            .map((m, idx) => {
              const rawId = Number(m.id);
              return {
                id: Number.isFinite(rawId) ? rawId : nowMs() + idx,
                role: m.role === 'user' ? 'user' : 'assistant',
                text: typeof m.text === 'string' ? m.text : '',
                meta: typeof m.meta === 'string' ? m.meta : '',
                createdAt: Number(m.createdAt) || nowMs(),
                status: m.status === 'error' ? 'error' : 'complete'
              };
            })
            .filter((m) => !isWorkspaceNoticeMessage(m))
            .filter((m) => Number.isFinite(m.id))
        : []
    }))
    .filter((c) => Number.isFinite(c.id));

  state.agent.nextConversationId =
    Math.max(Number(parsed.nextConversationId) || 1, ...state.agent.conversations.map((c) => c.id + 1), 1);
  state.agent.nextMessageId = Math.max(
    Number(parsed.nextMessageId) || 1,
    ...state.agent.conversations.flatMap((c) =>
      c.messages.map((m) => (Number.isFinite(m.id) ? m.id + 1 : 1))
    ),
    1
  );

  const requestedActive = Number(parsed.activeConversationId);
  state.agent.activeConversationId = getConversationById(requestedActive)
    ? requestedActive
    : state.agent.conversations[0]?.id || null;
}

function ensureAgentConversations() {
  if (!state.agent.conversations.length) {
    const c = createConversation('General');
    appendConversationMessage(c.id, {
      role: 'assistant',
      text: 'OpenClaw ready. Ask to retrieve notes, summarize material, or propose taxonomy/ontology edits.',
      meta: 'System'
    });
  }
  if (!getActiveConversation()) {
    state.agent.activeConversationId = state.agent.conversations[0].id;
  }
  renderConversationList();
  renderActiveConversationMessages();
}

function appendConversationMessage(conversationId, message) {
  const conversation = getConversationById(conversationId);
  if (!conversation) return null;

  const entry = {
    id: state.agent.nextMessageId++,
    role: message.role === 'user' ? 'user' : 'assistant',
    text: typeof message.text === 'string' ? message.text : '',
    meta: typeof message.meta === 'string' ? message.meta : '',
    createdAt: nowMs(),
    status: message.status || 'complete'
  };
  conversation.messages.push(entry);
  touchConversation(conversation);
  persistConversations();
  renderConversationList();
  if (state.agent.activeConversationId === conversationId) {
    renderActiveConversationMessages();
  }
  return entry.id;
}

function updateConversationMessage(conversationId, messageId, patch) {
  const conversation = getConversationById(conversationId);
  if (!conversation) return;
  const message = conversation.messages.find((m) => m.id === messageId);
  if (!message) return;

  if (typeof patch.text === 'string') message.text = patch.text;
  if (typeof patch.meta === 'string') message.meta = patch.meta;
  if (typeof patch.status === 'string') message.status = patch.status;
  touchConversation(conversation);
  persistConversations();
  renderConversationList();
  if (state.agent.activeConversationId === conversationId) {
    renderActiveConversationMessages();
  }
}

function setConversationPendingCount(conversationId, nextCount) {
  const conversation = getConversationById(conversationId);
  if (!conversation) return;
  conversation.pendingCount = Math.max(0, Number(nextCount) || 0);
  touchConversation(conversation);
  persistConversations();
  renderConversationList();
}

function handleAgentStreamEvent(payload = {}) {
  const runId = payload?.runId;
  if (!runId) return;
  const entry = agentStreamRuns.get(runId);
  if (!entry) return;

  if (payload.type === 'delta') {
    const delta = String(payload.delta || '');
    if (!delta) return;
    entry.text += delta;
    entry.sawDelta = true;
    updateConversationMessage(entry.conversationId, entry.messageId, {
      text: entry.text,
      status: 'pending'
    });
    return;
  }

  if (payload.type === 'error') {
    const errMsg = String(payload.error || 'OpenClaw error');
    updateConversationMessage(entry.conversationId, entry.messageId, {
      text: `Agent error: ${errMsg}`,
      status: 'error',
      meta: 'OpenClaw'
    });
    const latest = getConversationById(entry.conversationId);
    setConversationPendingCount(entry.conversationId, Math.max(0, (latest?.pendingCount || 0) - 1));
    agentStreamRuns.delete(runId);
    return;
  }

  if (payload.type === 'complete') {
    const finalText = entry.text || String(payload.text || '').trim() || 'No response.';
    updateConversationMessage(entry.conversationId, entry.messageId, {
      text: finalText,
      status: 'complete',
      meta: 'OpenClaw'
    });
    const latest = getConversationById(entry.conversationId);
    setConversationPendingCount(entry.conversationId, Math.max(0, (latest?.pendingCount || 0) - 1));
    agentStreamRuns.delete(runId);
  }
}

function attachAgentStreamHandlers() {
  if (agentStreamUnsubscribe || !window.acquittifyApi || typeof window.acquittifyApi.onAgentStream !== 'function') {
    return;
  }
  agentStreamUnsubscribe = window.acquittifyApi.onAgentStream(handleAgentStreamEvent);
}

function addAgentNotice(text, meta = 'Workspace') {
  const rawMeta = String(meta || 'Workspace').trim();
  const normalizedMeta = rawMeta.toLowerCase();
  if (normalizedMeta === 'workspace') {
    return;
  }
  const active = getActiveConversation();
  if (!active) return;
  appendConversationMessage(active.id, { role: 'assistant', text, meta: rawMeta });
}

function setActiveLeftTab(tab) {
  document.querySelectorAll('.activity-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  const showFilesTab = tab === 'files' || tab === 'graph' || tab === 'ontology-graph';
  els.filesTab.classList.toggle('hidden', !showFilesTab);
  els.searchTab.classList.toggle('hidden', tab !== 'search');
  if (showFilesTab && state.vaultViewKind === 'caselaw') {
    renderCaselawJurisdictionSidebar();
  }
}

function setShellMode(mode = 'default') {
  const shell = document.querySelector('.app-shell');
  if (!shell) return;
  const sidebar = document.querySelector('.sidebar-layout');
  const rightPane = document.querySelector('.right-pane');
  const centerPane = document.querySelector('.center-pane');
  void mode; // Shell focus modes are disabled; all content opens within the normal tabbed layout.
  shell.classList.remove('graph-focus');
  shell.classList.remove('pdf-focus');
  if (sidebar) sidebar.style.display = '';
  if (rightPane) rightPane.style.display = '';
  shell.style.gridTemplateColumns = '';
  if (centerPane) {
    centerPane.style.gridColumn = '';
    centerPane.style.width = '';
    centerPane.style.maxWidth = '';
  }
  if (els.tabs) els.tabs.classList.remove('hidden');
  if (els.editorToolbar) els.editorToolbar.classList.remove('hidden');
}

function enforcePdfLayoutContract() {
  if (els.pdfWrap) {
    // Keep PDF content bound to the center pane and stretched to full available space.
    els.pdfWrap.style.width = '100%';
    els.pdfWrap.style.height = '100%';
    els.pdfWrap.style.flex = '1 1 auto';
    els.pdfWrap.style.minWidth = '0';
    els.pdfWrap.style.minHeight = '0';
    els.pdfWrap.style.overflow = 'hidden';
  }
  if (els.pdfCanvasWrap) {
    els.pdfCanvasWrap.style.width = '100%';
    els.pdfCanvasWrap.style.flex = '1 1 auto';
    els.pdfCanvasWrap.style.minWidth = '0';
    els.pdfCanvasWrap.style.minHeight = '0';
  }
  if (els.pdfFrame) {
    els.pdfFrame.style.width = '100%';
    els.pdfFrame.style.height = '100%';
    els.pdfFrame.style.flex = '1 1 auto';
    els.pdfFrame.style.minWidth = '0';
    els.pdfFrame.style.minHeight = '0';
  }
}

async function loadPdfJsModule() {
  if (!cachedPdfJsModulePromise) {
    cachedPdfJsModulePromise = (async () => {
      ensurePdfRuntimeGlobals();

      const candidates = [
        'pdfjs-dist/legacy/build/pdf.js',
        '../node_modules/pdfjs-dist/legacy/build/pdf.js',
        'pdfjs-dist/legacy/build/pdf.min.js',
        '../node_modules/pdfjs-dist/legacy/build/pdf.min.js'
      ];

      let lastError = null;
      for (const candidate of candidates) {
        try {
          const mod = await withPdfBrowserRuntime(async () => require(candidate));
          if (mod?.getDocument) {
            configurePdfWorker(mod);
            return mod;
          }
          const normalized = mod?.default || mod;
          if (normalized?.getDocument) {
            configurePdfWorker(normalized);
            return normalized;
          }
        } catch (err) {
          lastError = err;
        }
      }

      throw lastError || new Error('Unable to load pdfjs-dist legacy build.');
    })();
  }
  return cachedPdfJsModulePromise;
}

function clearPdfCanvas() {
  if (els.pdfCanvasWrap) {
    els.pdfCanvasWrap.innerHTML = '';
  }
}

function setPdfStatus(message = '', isError = false) {
  if (!els.pdfStatus) return;
  const text = String(message || '').trim();
  if (!text) {
    els.pdfStatus.textContent = '';
    els.pdfStatus.classList.add('hidden');
    els.pdfStatus.classList.remove('error');
    return;
  }
  els.pdfStatus.textContent = text;
  els.pdfStatus.classList.remove('hidden');
  els.pdfStatus.classList.toggle('error', Boolean(isError));
}

function getPdfTargetWidth() {
  if (!els.pdfCanvasWrap) return 900;
  const width = Math.floor(els.pdfCanvasWrap.clientWidth || 0);
  return Math.max(420, width - 24);
}

function stopPdfRendering() {
  state.pdf.renderRunId += 1;
  if (state.pdf.rerenderTimer) {
    clearTimeout(state.pdf.rerenderTimer);
    state.pdf.rerenderTimer = null;
  }
}

function revokePdfTabObjectUrl(tab) {
  if (!tab || tab.kind !== 'pdf') return;
  if (!tab.pdfObjectUrl || typeof tab.url !== 'string' || !tab.url.startsWith('blob:')) return;
  try {
    URL.revokeObjectURL(tab.url);
  } catch {
    // ignore
  }
  tab.pdfObjectUrl = false;
}

async function ensurePdfTabDisplayUrl(tab) {
  if (!tab || tab.kind !== 'pdf') return String(tab?.url || '');
  if (tab.pdfObjectUrl && typeof tab.url === 'string' && tab.url.startsWith('blob:')) {
    return tab.url;
  }

  let absPath = '';
  if (tab.path && state.vaultRoot) {
    const candidate = path.resolve(path.resolve(String(state.vaultRoot || '')), String(tab.path).replaceAll('\\', '/'));
    if (fs.existsSync(candidate)) {
      absPath = candidate;
    }
  }

  if (!absPath && typeof tab.url === 'string' && tab.url.startsWith('file://')) {
    try {
      const candidate = fileURLToPath(tab.url);
      if (fs.existsSync(candidate)) {
        absPath = candidate;
      }
    } catch {
      // ignore
    }
  }

  if (!absPath) {
    tab.pdfObjectUrl = false;
    return String(tab.url || '');
  }

  try {
    const bytes = fs.readFileSync(absPath);
    const blob = new Blob([bytes], { type: 'application/pdf' });
    revokePdfTabObjectUrl(tab);
    tab.url = URL.createObjectURL(blob);
    tab.pdfObjectUrl = true;
    return tab.url;
  } catch {
    tab.pdfObjectUrl = false;
    return String(tab.url || '');
  }
}

function schedulePdfRerender() {
  const active = state.openTabs.find((t) => t.id === state.activeTabId);
  if (!active || active.kind !== 'pdf') return;
  if (state.pdf.rerenderTimer) {
    clearTimeout(state.pdf.rerenderTimer);
  }
  state.pdf.rerenderTimer = setTimeout(() => {
    void ensurePdfTabDisplayUrl(active).then((url) => renderPdfInCanvas(url));
  }, 180);
}

async function renderPdfInCanvas(url) {
  if (!els.pdfCanvasWrap) return;
  enforcePdfLayoutContract();
  ++state.pdf.renderRunId;
  clearPdfCanvas();
  setPdfStatus('');
  els.pdfCanvasWrap.classList.add('hidden');
  if (els.pdfFrame) {
    els.pdfFrame.classList.remove('hidden');
    const rawUrl = String(url || '').trim();
    if (!rawUrl) {
      els.pdfFrame.src = '';
      setPdfStatus('Unable to open PDF: missing URL.', true);
      return;
    }
    if (rawUrl.startsWith('blob:')) {
      els.pdfFrame.src = `${rawUrl}#view=Fit&zoom=page-fit&navpanes=0&pagemode=none`;
      return;
    }
    const sep = rawUrl.includes('?') ? '&' : '?';
    els.pdfFrame.src = `${rawUrl}${sep}_t=${Date.now()}#view=Fit&zoom=page-fit&navpanes=0&pagemode=none`;
  }
}

function isVerticallyScrollable(el) {
  if (!(el instanceof HTMLElement)) return false;
  const style = window.getComputedStyle(el);
  if (!/(auto|scroll)/.test(style.overflowY || '')) return false;
  return el.scrollHeight > el.clientHeight + 1;
}

function findScrollableAncestor(startNode) {
  let node = startNode;
  while (node && node !== document.body && node !== document.documentElement) {
    if (isVerticallyScrollable(node)) return node;
    node = node.parentElement;
  }
  return null;
}

function normalizeVaultRootForMatch(value = '') {
  return String(value || '')
    .trim()
    .replaceAll('\\', '/')
    .replace(/\/+$/g, '');
}

function selectedCaselawRootsSet() {
  return new Set((state.caselawSelectedVaultRoots || []).map((entry) => normalizeVaultRootForMatch(entry)));
}

function resolvedCaselawSelectedRoots() {
  const selected = selectedCaselawRootsSet();
  const byNormalized = new Map();
  for (const entry of state.caselawJurisdictions || []) {
    const rawRoot = String(entry?.vaultRoot || '').trim();
    const normalized = normalizeVaultRootForMatch(rawRoot);
    if (!normalized) continue;
    byNormalized.set(normalized, rawRoot || normalized);
  }
  return Array.from(selected)
    .map((normalized) => byNormalized.get(normalized) || normalized)
    .filter(Boolean);
}

function restoreOntologyControlsToMainHost() {
  if (!els.ontologyControls || !els.ontologyControlsHost) return;
  if (els.ontologyControls.parentElement !== els.ontologyControlsHost) {
    els.ontologyControlsHost.appendChild(els.ontologyControls);
  }
  els.ontologyControls.classList.remove('ontology-controls-sidebar');
}

function mountOntologyControlsInSidebar(container) {
  if (!els.ontologyControls || !container) return;
  if (els.ontologyControls.parentElement !== container) {
    container.appendChild(els.ontologyControls);
  }
  els.ontologyControls.classList.add('ontology-controls-sidebar');
}

function renderCaselawJurisdictionSidebar() {
  if (!els.filesTab) return;
  els.filesTab.innerHTML = '';
  const panel = document.createElement('div');
  panel.className = 'jurisdiction-panel';

  const title = document.createElement('div');
  title.className = 'jurisdiction-title';
  title.textContent = 'Jurisdictions';
  panel.appendChild(title);

  const hint = document.createElement('div');
  hint.className = 'jurisdiction-hint';
  hint.textContent = 'Select jurisdictions to include in Caselaw View.';
  panel.appendChild(hint);

  if (state.caselawJurisdictionError) {
    const error = document.createElement('div');
    error.className = 'jurisdiction-error';
    error.textContent = `Unable to load jurisdictions: ${state.caselawJurisdictionError}`;
    panel.appendChild(error);
  }

  const list = document.createElement('div');
  list.className = 'jurisdiction-list';
  const selectedRoots = selectedCaselawRootsSet();
  const jurisdictions = Array.isArray(state.caselawJurisdictions) ? state.caselawJurisdictions : [];

  if (!jurisdictions.length) {
    const empty = document.createElement('div');
    empty.className = 'jurisdiction-empty';
    empty.textContent = 'No caselaw vaults discovered.';
    list.appendChild(empty);
  } else {
    for (const item of jurisdictions) {
      const vaultRoot = String(item?.vaultRoot || '').trim();
      const normalizedRoot = normalizeVaultRootForMatch(vaultRoot);
      if (!normalizedRoot) continue;

      const row = document.createElement('label');
      row.className = 'jurisdiction-item';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = selectedRoots.has(normalizedRoot);
      checkbox.onchange = () => void toggleCaselawJurisdiction(vaultRoot, checkbox.checked);

      const textWrap = document.createElement('div');
      textWrap.className = 'jurisdiction-item-text';

      const name = document.createElement('div');
      name.className = 'jurisdiction-item-label';
      name.textContent = String(item?.label || basenameOf(vaultRoot) || vaultRoot);
      textWrap.appendChild(name);

      const sub = document.createElement('div');
      sub.className = 'jurisdiction-item-sub';
      sub.textContent = basenameOf(vaultRoot) || vaultRoot;
      sub.title = vaultRoot;
      textWrap.appendChild(sub);

      row.appendChild(checkbox);
      row.appendChild(textWrap);
      list.appendChild(row);
    }
  }

  panel.appendChild(list);

  const count = document.createElement('div');
  count.className = 'jurisdiction-count';
  count.textContent = `${selectedRoots.size} selected`;
  panel.appendChild(count);

  const ontologyPanel = document.createElement('div');
  ontologyPanel.className = 'jurisdiction-panel ontology-sidebar-panel';

  const ontologyTitle = document.createElement('div');
  ontologyTitle.className = 'ontology-sidebar-title';
  ontologyTitle.textContent = 'Ontology Filters';
  ontologyPanel.appendChild(ontologyTitle);

  const ontologyHint = document.createElement('div');
  ontologyHint.className = 'ontology-sidebar-hint';
  ontologyHint.textContent = 'Filter the ontology graph from the sidebar.';
  ontologyPanel.appendChild(ontologyHint);

  const controlsHost = document.createElement('div');
  controlsHost.className = 'ontology-sidebar-controls-host';
  ontologyPanel.appendChild(controlsHost);
  mountOntologyControlsInSidebar(controlsHost);

  els.filesTab.appendChild(panel);
  els.filesTab.appendChild(ontologyPanel);
  setVaultSelection('', '');
}

async function loadCaselawJurisdictions() {
  try {
    const items = await window.acquittifyApi.getCaselawJurisdictions();
    const normalizedItems = (Array.isArray(items) ? items : [])
      .map((item) => ({
        id: String(item?.id || item?.vaultRoot || '').trim(),
        label: String(item?.label || '').trim(),
        vaultRoot: String(item?.vaultRoot || '').trim()
      }))
      .filter((item) => item.vaultRoot);

    state.caselawJurisdictions = normalizedItems;
    state.caselawJurisdictionError = '';

    const available = new Set(normalizedItems.map((item) => normalizeVaultRootForMatch(item.vaultRoot)));
    let selected = Array.from(selectedCaselawRootsSet()).filter((root) => available.has(root));

    if (!selected.length) {
      const currentRoot = normalizeVaultRootForMatch(state.vaultRoot);
      if (currentRoot && available.has(currentRoot)) {
        selected = [currentRoot];
      } else {
        const first = normalizedItems[0]?.vaultRoot;
        if (first) selected = [normalizeVaultRootForMatch(first)];
      }
    }

    state.caselawSelectedVaultRoots = selected;
  } catch (err) {
    state.caselawJurisdictions = [];
    state.caselawJurisdictionError = err.message;
    if (!state.caselawSelectedVaultRoots.length && state.vaultRoot) {
      state.caselawSelectedVaultRoots = [normalizeVaultRootForMatch(state.vaultRoot)];
    }
  }

  if (state.vaultViewKind === 'caselaw' && !els.filesTab.classList.contains('hidden')) {
    renderCaselawJurisdictionSidebar();
  }
}

async function toggleCaselawJurisdiction(vaultRoot, checked) {
  const normalizedRoot = normalizeVaultRootForMatch(vaultRoot);
  if (!normalizedRoot) return;
  const next = selectedCaselawRootsSet();
  if (checked) next.add(normalizedRoot);
  else next.delete(normalizedRoot);

  if (!next.size) {
    window.alert('At least one jurisdiction must remain selected.');
    renderCaselawJurisdictionSidebar();
    return;
  }

  state.caselawSelectedVaultRoots = Array.from(next);
  renderCaselawJurisdictionSidebar();

  await loadOntologyGraph();
  const active = state.openTabs.find((t) => t.id === state.activeTabId);
  if (active?.kind === 'ontology-graph') {
    renderOntologyGraph(true);
  }
}

async function loadTree(relPath = '', container = els.filesTab, depth = 0) {
  if (state.vaultViewKind === 'caselaw') {
    renderCaselawJurisdictionSidebar();
    return;
  }
  restoreOntologyControlsToMainHost();
  const items = await window.acquittifyApi.listVault(relPath);
  if (depth === 0) container.innerHTML = '';

  for (const item of items) {
    const row = document.createElement('div');
    row.className = `tree-item ${item.type === 'directory' ? 'tree-dir' : 'tree-file'}`;
    row.style.paddingLeft = `${depth * 12 + 6}px`;
    row.dataset.path = item.path;
    row.dataset.type = item.type;
    row.textContent = item.type === 'directory' ? `▸ ${item.name}` : item.name;

    if (item.type === 'directory') {
      let expanded = false;
      let childWrap = null;
      row.onclick = async () => {
        setVaultSelection(item.path, item.type);
        expanded = !expanded;
        row.textContent = `${expanded ? '▾' : '▸'} ${item.name}`;
        if (!expanded && childWrap) {
          childWrap.remove();
          childWrap = null;
          return;
        }
        if (!childWrap) {
          childWrap = document.createElement('div');
          row.after(childWrap);
          await loadTree(item.path, childWrap, depth + 1);
        }
      };
    } else {
      row.onclick = async () => {
        setVaultSelection(item.path, item.type);
        await openFile(item.path);
      };
    }

    container.appendChild(row);
  }

  if (depth === 0) {
    applyTreeSelectionStyles();
    updateVaultActionState();
  }
}

async function createVaultNoteFromSelection() {
  if (!state.vaultAccess?.writable) return;
  const parentPath = getSelectedParentPath();
  const rawName = window.prompt('New note name', 'Untitled');
  if (rawName === null) return;
  const trimmed = String(rawName || '').trim();
  if (!trimmed) return;

  try {
    const created = await window.acquittifyApi.createVaultNote({
      parentPath,
      name: trimmed
    });
    await refreshVaultData(false);
    if (created?.path) {
      setVaultSelection(created.path, created.type || 'file');
      await openFile(created.path);
    }
  } catch (err) {
    window.alert(`Unable to create note: ${err.message}`);
  }
}

async function createVaultFolderFromSelection() {
  if (!state.vaultAccess?.writable) return;
  const parentPath = getSelectedParentPath();
  const rawName = window.prompt('New folder name', 'New Folder');
  if (rawName === null) return;
  const trimmed = String(rawName || '').trim();
  if (!trimmed) return;

  try {
    const created = await window.acquittifyApi.createVaultFolder({
      parentPath,
      name: trimmed
    });
    await refreshVaultData(false);
    if (created?.path) {
      setVaultSelection(created.path, created.type || 'directory');
    }
  } catch (err) {
    window.alert(`Unable to create folder: ${err.message}`);
  }
}

async function renameSelectedVaultEntry() {
  if (!state.vaultAccess?.writable || !state.vaultSelection?.path) return;
  const selection = state.vaultSelection;
  const currentName = basenameOf(selection.path);
  if (!currentName) return;

  const currentExt = selection.type === 'file' ? getLowerExt(currentName) : '';
  const suggested =
    selection.type === 'file' && currentExt
      ? currentName.slice(0, -currentExt.length)
      : currentName;

  const rawName = window.prompt(`Rename ${selection.type}`, suggested);
  if (rawName === null) return;

  let nextName = String(rawName || '').trim();
  if (!nextName) return;
  if (selection.type === 'file' && currentExt && !hasNameExtension(nextName)) {
    nextName += currentExt;
  }

  try {
    const renamed = await window.acquittifyApi.renameVaultPath({
      path: selection.path,
      newName: nextName
    });
    if (renamed?.path) {
      remapOpenTabsAfterRename(selection.path, renamed.path, selection.type === 'directory');
      await refreshVaultData(false);
      setVaultSelection(renamed.path, renamed.type || selection.type);
    }
  } catch (err) {
    window.alert(`Unable to rename ${selection.type}: ${err.message}`);
  }
}

async function deleteSelectedVaultEntry() {
  if (!state.vaultAccess?.writable || !state.vaultSelection?.path) return;
  const selection = state.vaultSelection;
  const label = basenameOf(selection.path) || selection.path;
  const noun = selection.type === 'directory' ? 'folder' : 'note';
  const ok = window.confirm(`Delete ${noun} "${label}"? This action cannot be undone.`);
  if (!ok) return;

  try {
    await window.acquittifyApi.deleteVaultPath({ path: selection.path });
    removeOpenTabsForDeletedPath(selection.path, selection.type === 'directory');
    setVaultSelection('', '');
    await refreshVaultData(false);
  } catch (err) {
    window.alert(`Unable to delete ${noun}: ${err.message}`);
  }
}

function renderTabs() {
  els.tabs.innerHTML = '';

  for (const tab of state.openTabs) {
    const el = document.createElement('div');
    el.className = `editor-tab ${state.activeTabId === tab.id ? 'active' : ''}`;
    const label = document.createElement('span');
    label.className = 'editor-tab-label';
    label.textContent = tab.title || (tab.path ? tab.path.split('/').pop() : 'New Tab');
    label.title = tab.title || tab.path || 'New Tab';
    label.onclick = () => activateTab(tab.id);

    const close = document.createElement('button');
    close.className = 'editor-tab-close';
    close.textContent = '×';
    close.title = 'Close tab';
    close.onclick = (e) => {
      e.stopPropagation();
      closeTab(tab.id);
    };

    el.appendChild(label);
    el.appendChild(close);
    el.onclick = () => activateTab(tab.id);
    els.tabs.appendChild(el);
  }

  const plus = document.createElement('button');
  plus.className = 'editor-tab-plus';
  plus.textContent = '+';
  plus.title = 'New tab';
  plus.onclick = () => createBlankTabAndActivate();
  els.tabs.appendChild(plus);
}

function closeTab(tabId) {
  const idx = state.openTabs.findIndex((t) => t.id === tabId);
  if (idx === -1) return;
  revokePdfTabObjectUrl(state.openTabs[idx]);
  const wasActive = state.activeTabId === tabId;
  state.openTabs.splice(idx, 1);

  if (!state.openTabs.length) {
    createBlankTabAndActivate();
    return;
  }

  if (wasActive) {
    const nextIdx = Math.max(0, idx - 1);
    activateTab(state.openTabs[nextIdx].id);
  } else {
    renderTabs();
  }
}

function createBlankTabAndActivate() {
  const tab = {
    id: state.nextTabId++,
    path: null,
    kind: 'text',
    content: '',
    sourcePath: null
  };
  state.openTabs.push(tab);
  activateTab(tab.id);
}

function clearMediaPreview() {
  els.mediaWrap.classList.add('hidden');
  els.mediaImage.classList.add('hidden');
  els.mediaAudio.classList.add('hidden');
  els.mediaVideo.classList.add('hidden');
  els.binaryInfo.classList.add('hidden');
  els.mediaImage.removeAttribute('src');
  els.mediaAudio.pause();
  els.mediaAudio.removeAttribute('src');
  els.mediaVideo.pause();
  els.mediaVideo.removeAttribute('src');
  els.binaryInfo.innerHTML = '';
}

function activateTab(tabId) {
  const tab = state.openTabs.find((t) => t.id === tabId);
  if (!tab) return;
  if (tab.kind === 'trial-canvas') {
    void openOntologyGraphTab();
    return;
  }
  state.activeTabId = tabId;
  if (tab.kind === 'graph') setActiveLeftTab('graph');
  else if (tab.kind === 'ontology-graph') setActiveLeftTab('ontology-graph');
  else setActiveLeftTab('files');
  setShellMode('default');
  enforcePdfLayoutContract();
  stopPdfRendering();

  els.editor.classList.add('hidden');
  els.editor.readOnly = false;
  els.graphWrap.classList.add('hidden');
  els.graphWrap.classList.remove('fullscreen');
  els.ontologyGraphWrap.classList.add('hidden');
  if (els.trialCanvasView) {
    els.trialCanvasView.classList.add('hidden');
  }
  hideOntologyCaseHoverCard(true);
  closeOntologyCaseSidebar(true);
  els.pdfWrap.classList.add('hidden');
  setPdfStatus('');
  clearPdfCanvas();
  els.pdfCanvasWrap.classList.remove('hidden');
  els.pdfFrame.classList.add('hidden');
  els.pdfFrame.src = '';
  clearMediaPreview();

  if (tab.kind === 'pdf') {
    els.pdfWrap.classList.remove('hidden');
    void ensurePdfTabDisplayUrl(tab).then((url) => renderPdfInCanvas(url));
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'PDF files are read-only in editor mode';
  } else if (tab.kind === 'image') {
    els.mediaWrap.classList.remove('hidden');
    els.mediaImage.classList.remove('hidden');
    els.mediaImage.src = tab.url;
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Images are read-only in preview mode';
  } else if (tab.kind === 'audio') {
    els.mediaWrap.classList.remove('hidden');
    els.mediaAudio.classList.remove('hidden');
    els.mediaAudio.src = tab.url;
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Audio files are read-only in preview mode';
  } else if (tab.kind === 'video') {
    els.mediaWrap.classList.remove('hidden');
    els.mediaVideo.classList.remove('hidden');
    els.mediaVideo.src = tab.url;
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Video files are read-only in preview mode';
  } else if (tab.kind === 'binary') {
    els.mediaWrap.classList.remove('hidden');
    els.binaryInfo.classList.remove('hidden');
    const fileLabel = tab.path || tab.title || 'Unknown file';
    const ext = getLowerExt(fileLabel);
    els.binaryInfo.innerHTML = '';
    const title = document.createElement('div');
    title.className = 'binary-title';
    title.textContent = `No inline viewer for ${ext || 'this file type'}.`;
    const subtitle = document.createElement('div');
    subtitle.className = 'binary-subtitle';
    subtitle.textContent = 'Import/processing still creates an extracted note for supported legal file formats.';
    const pathLine = document.createElement('div');
    pathLine.className = 'binary-path';
    pathLine.textContent = fileLabel;
    els.binaryInfo.appendChild(title);
    els.binaryInfo.appendChild(subtitle);
    els.binaryInfo.appendChild(pathLine);
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Binary files are read-only';
  } else if (tab.kind === 'graph') {
    els.graphWrap.classList.remove('hidden');
    els.graphWrap.classList.remove('fullscreen');
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Graph view is read-only';
    renderGraph(true);
    requestAnimationFrame(() => {
      if (!state.graphNetwork) return;
      state.graphNetwork.setSize('100%', '100%');
      state.graphNetwork.redraw();
      state.graphNetwork.fit({ animation: { duration: 250, easingFunction: 'easeInOutQuad' } });
    });
  } else if (tab.kind === 'ontology-graph') {
    els.ontologyGraphWrap.classList.remove('hidden');
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Ontology graph is read-only';
    renderOntologyGraph(true);
    requestAnimationFrame(() => {
      if (!state.ontologyGraphNetwork) return;
      state.ontologyGraphNetwork.setSize('100%', '100%');
      state.ontologyGraphNetwork.redraw();
      fitOntologyGraphToViewport({ animate: true, duration: 250 });
    });
  } else if (tab.kind === 'case-canvas') {
    els.editor.classList.remove('hidden');
    els.editor.value = tab.content;
    els.editor.readOnly = true;
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Case canvas notes are read-only';
  } else if (tab.kind === 'trial-canvas') {
    if (els.trialCanvasView) {
      els.trialCanvasView.classList.remove('hidden');
      refreshTrialCanvasView({ skipContent: !state.trialCanvas.selectedPath });
    }
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Trial canvas view is read-only';
  } else {
    els.editor.classList.remove('hidden');
    els.editor.value = tab.content;
    els.editor.readOnly = Boolean(tab.readOnly);
    els.saveBtn.disabled = !tab.path || Boolean(tab.readOnly);
    els.saveBtn.title = tab.readOnly ? 'This tab is read-only' : tab.path ? '' : 'Open a file to save changes';
  }
  els.currentFile.textContent = tab.title || tab.path || 'No file selected';
  renderTabs();
  syncTrialCanvasButtonState();
}

function openGraphTab() {
  const existing = state.openTabs.find((t) => t.kind === 'graph');
  if (existing) {
    activateTab(existing.id);
    return;
  }
  const tab = {
    id: state.nextTabId++,
    kind: 'graph',
    title: 'Casefile View',
    path: '__graph__'
  };
  state.openTabs.push(tab);
  activateTab(tab.id);
}

async function openOntologyGraphTab() {
  const tabTitle = state.vaultViewKind === 'caselaw' ? 'Caselaw Ontology Graph' : 'Casefile Ontology Graph';
  const existing = state.openTabs.find((t) => t.kind === 'ontology-graph');
  if (existing) {
    existing.title = tabTitle;
    activateTab(existing.id);
  } else {
    const tab = {
      id: state.nextTabId++,
      kind: 'ontology-graph',
      title: tabTitle,
      path: '__ontology_graph__'
    };
    state.openTabs.push(tab);
    activateTab(tab.id);
  }
  if (state.vaultViewKind === 'caselaw') {
    await loadCaselawJurisdictions();
  }
  await loadOntologyGraph();
  if (state.ontologyGraphVisDisabled && !state.ontologyGraphNetwork) {
    // Recover from transient startup failures and allow vis-network retry.
    state.ontologyGraphVisDisabled = false;
  }
  const active = state.openTabs.find((t) => t.id === state.activeTabId);
  if (active?.kind === 'ontology-graph') renderOntologyGraph(true);
}

function openCaseCanvas(canvasId) {
  const canvas = getCaseCanvasById(canvasId);
  if (!canvas) {
    addAgentNotice('Canvas not found for the requested case.', 'Workspace');
    return;
  }

  const entry = resolveCaseCanvasEntry(canvas);
  if (!entry) {
    addAgentNotice(`Canvas entry note not found for ${canvas.label}.`, 'Workspace');
    return;
  }

  let content = '';
  try {
    content = fs.readFileSync(entry.absPath, 'utf-8');
  } catch (err) {
    addAgentNotice(`Unable to load ${canvas.label}: ${err.message}`, 'Workspace');
    return;
  }

  const existing = state.openTabs.find((t) => t.kind === 'case-canvas' && t.canvasId === canvas.id);
  const tab = {
    id: existing ? existing.id : state.nextTabId++,
    title: `${canvas.label} (read-only)`,
    path: `case-canvas:${canvas.id}/${entry.relPath}`,
    kind: 'case-canvas',
    content,
    readOnly: true,
    canvasId: canvas.id,
    canvasRelPath: entry.relPath
  };

  if (existing) {
    const idx = state.openTabs.findIndex((t) => t.id === existing.id);
    if (idx !== -1) {
      state.openTabs[idx] = tab;
    } else {
      state.openTabs.push(tab);
    }
  } else {
    state.openTabs.push(tab);
  }

  activateTab(tab.id);
}

function normalizeTrialCanvasRelPath(relPath = '') {
  const clean = String(relPath || '').replaceAll('\\', '/').replace(/^\/+/, '').replace(/\/+$/g, '');
  return clean;
}

function ensureTrialCanvasTreeState() {
  if (!(state.trialCanvas.treeExpanded instanceof Set)) {
    state.trialCanvas.treeExpanded = new Set(['']);
  }
}

function getActiveTrialCanvasConfig() {
  const targetId = state.trialCanvas.activeCanvasId || CASE_CANVASES[0]?.id;
  if (!targetId) return null;
  return getCaseCanvasById(targetId) || CASE_CANVASES[0] || null;
}

function ensureTrialCanvasRoot() {
  const canvas = getActiveTrialCanvasConfig();
  if (!canvas) {
    state.trialCanvas.root = '';
    if (els.trialCanvasSidebarStatus) {
      els.trialCanvasSidebarStatus.textContent = 'No case canvas configured.';
    }
    return '';
  }
  const resolvedRoot = path.resolve(String(canvas.vaultRoot || '').trim());
  if (!pathIsDirectory(resolvedRoot)) {
    state.trialCanvas.root = '';
    if (els.trialCanvasSidebarStatus) {
      els.trialCanvasSidebarStatus.textContent = 'Savani vault not found on disk.';
    }
    if (els.trialCanvasLabel) els.trialCanvasLabel.textContent = canvas.label || TRIAL_CANVAS_VIEW_TITLE;
    if (els.trialCanvasPath) els.trialCanvasPath.textContent = String(canvas.vaultRoot || '');
    return '';
  }

  state.trialCanvas.root = resolvedRoot;
  state.trialCanvas.activeCanvasId = canvas.id;
  ensureTrialCanvasTreeState();

  if (els.trialCanvasLabel) els.trialCanvasLabel.textContent = canvas.label || TRIAL_CANVAS_VIEW_TITLE;
  if (els.trialCanvasPath) els.trialCanvasPath.textContent = resolvedRoot;
  if (els.trialCanvasSidebarStatus) els.trialCanvasSidebarStatus.textContent = '';

  if (!state.trialCanvas.selectedPath) {
    const entry = resolveCaseCanvasEntry(canvas);
    if (entry?.relPath) {
      const rel = normalizeTrialCanvasRelPath(entry.relPath);
      state.trialCanvas.selectedPath = rel;
      state.trialCanvas.selectedType = 'file';
      ensureTrialCanvasParentsExpanded(rel);
    }
  }

  return resolvedRoot;
}

function ensureTrialCanvasParentsExpanded(relPath = '') {
  ensureTrialCanvasTreeState();
  const normalized = normalizeTrialCanvasRelPath(relPath);
  if (!normalized) return;
  const parts = normalized.split('/');
  let current = '';
  for (let i = 0; i < parts.length - 1; i += 1) {
    const part = parts[i];
    if (!part) continue;
    current = current ? `${current}/${part}` : part;
    state.trialCanvas.treeExpanded.add(current);
  }
}

function listTrialCanvasEntries(relPath = '') {
  const root = state.trialCanvas.root || ensureTrialCanvasRoot();
  if (!root) return [];
  const normalized = normalizeTrialCanvasRelPath(relPath);
  const target = normalized ? path.resolve(root, normalized) : root;
  if (!target.startsWith(root)) return [];

  let entries;
  try {
    entries = fs.readdirSync(target, { withFileTypes: true });
  } catch (err) {
    if (els.trialCanvasSidebarStatus) {
      els.trialCanvasSidebarStatus.textContent = `Unable to read ${normalized || 'root'}: ${err.message}`;
    }
    return [];
  }

  return entries
    .filter((entry) => entry?.name && !entry.name.startsWith('.'))
    .map((entry) => ({
      name: entry.name,
      relPath: normalizeTrialCanvasRelPath(normalized ? `${normalized}/${entry.name}` : entry.name),
      type: entry.isDirectory() ? 'directory' : 'file'
    }))
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    });
}

function renderTrialCanvasTreeBranch(relPath = '', depth = 0, host) {
  const entries = listTrialCanvasEntries(relPath);
  for (const entry of entries) {
    const row = document.createElement('div');
    row.className = `trial-tree-item ${entry.type}`;
    row.dataset.relPath = entry.relPath;
    row.dataset.type = entry.type;
    row.style.paddingLeft = `${16 + depth * 4}px`;

    const caret = document.createElement('span');
    caret.className = 'trial-tree-caret';
    const label = document.createElement('span');
    label.className = 'trial-tree-label';
    label.textContent = entry.name;

    if (entry.type === 'directory') {
      const expanded = state.trialCanvas.treeExpanded.has(entry.relPath);
      caret.textContent = expanded ? '▾' : '▸';
      row.appendChild(caret);
      row.appendChild(label);
      host.appendChild(row);
      if (expanded) {
        const child = document.createElement('div');
        child.className = 'trial-tree-children';
        host.appendChild(child);
        renderTrialCanvasTreeBranch(entry.relPath, depth + 1, child);
      }
    } else {
      caret.textContent = '';
      row.appendChild(caret);
      row.appendChild(label);
      host.appendChild(row);
    }
  }
}

function renderTrialCanvasTree() {
  if (!els.trialCanvasTree) return;
  const root = ensureTrialCanvasRoot();
  if (!root) {
    els.trialCanvasTree.innerHTML = '<div class="trial-canvas-empty">Savani vault missing.</div>';
    return;
  }
  els.trialCanvasTree.innerHTML = '';
  const fragment = document.createDocumentFragment();
  renderTrialCanvasTreeBranch('', 0, fragment);
  els.trialCanvasTree.appendChild(fragment);
  updateTrialCanvasTreeSelectionStyles();
}

function updateTrialCanvasTreeSelectionStyles() {
  if (!els.trialCanvasTree) return;
  const selected = normalizeTrialCanvasRelPath(state.trialCanvas.selectedPath || '');
  const rows = els.trialCanvasTree.querySelectorAll('.trial-tree-item');
  rows.forEach((row) => {
    const rel = normalizeTrialCanvasRelPath(row.dataset.relPath || '');
    row.classList.toggle('selected', !!selected && rel === selected);
  });
}

function toggleTrialCanvasDirectory(relPath = '') {
  ensureTrialCanvasTreeState();
  const normalized = normalizeTrialCanvasRelPath(relPath);
  if (!normalized) return;
  if (state.trialCanvas.treeExpanded.has(normalized)) {
    state.trialCanvas.treeExpanded.delete(normalized);
  } else {
    state.trialCanvas.treeExpanded.add(normalized);
  }
  renderTrialCanvasTree();
}

function handleTrialCanvasTreeInteraction(relPath = '', type = '') {
  if (!relPath) return;
  if (type === 'directory') {
    toggleTrialCanvasDirectory(relPath);
    return;
  }
  if (type === 'file') {
    loadTrialCanvasEntry(relPath);
  }
}

function escapeTrialCanvasHtml(value = '') {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatTrialCanvasInline(text = '') {
  let html = escapeTrialCanvasHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(TRIAL_WIKILINK_REGEX, (_match, link) => `<span class="trial-wikilink">${escapeTrialCanvasHtml(link)}</span>`);
  return html;
}

function convertTrialCanvasMarkdownToHtml(markdown = '') {
  const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
  let html = '';
  let listOpen = false;
  let listType = 'ul';

  const closeList = () => {
    if (listOpen) {
      html += listType === 'ol' ? '</ol>' : '</ul>';
      listOpen = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      closeList();
      html += '<p></p>';
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(6, heading[1].length);
      html += `<h${level}>${formatTrialCanvasInline(heading[2])}</h${level}>`;
      continue;
    }

    const unordered = line.match(/^[-*+]\s+(.*)$/);
    if (unordered) {
      if (!listOpen || listType !== 'ul') {
        closeList();
        html += '<ul>';
        listOpen = true;
        listType = 'ul';
      }
      html += `<li>${formatTrialCanvasInline(unordered[1])}</li>`;
      continue;
    }

    const ordered = line.match(/^\d+\.\s+(.*)$/);
    if (ordered) {
      if (!listOpen || listType !== 'ol') {
        closeList();
        html += '<ol>';
        listOpen = true;
        listType = 'ol';
      }
      html += `<li>${formatTrialCanvasInline(ordered[1])}</li>`;
      continue;
    }

    closeList();
    html += `<p>${formatTrialCanvasInline(line)}</p>`;
  }

  closeList();
  return html || '<div class="trial-canvas-empty">No content available.</div>';
}

function buildTrialCanvasGraphFromContent(content = '') {
  const nodes = new Map();
  const edges = new Map();
  const lines = String(content || '').split(/\r?\n/);

  for (const line of lines) {
    const matches = Array.from(line.matchAll(TRIAL_WIKILINK_REGEX));
    if (!matches.length) continue;
    matches.forEach((match) => {
      const id = match[1];
      if (!nodes.has(id)) {
        nodes.set(id, {
          id,
          label: id.replace(/[_-]+/g, ' ')
        });
      }
    });

    if (matches.length >= 2 && TRIAL_CANVAS_MENTION_REGEX.test(line)) {
      const source = matches[0][1];
      for (let i = 1; i < matches.length; i += 1) {
        const target = matches[i][1];
        const key = `${source}->${target}`;
        if (!edges.has(key)) {
          edges.set(key, { id: key, from: source, to: target });
        }
      }
    }
  }

  return {
    nodes: Array.from(nodes.values()),
    edges: Array.from(edges.values())
  };
}

function ensureTrialCanvasGraphNetwork() {
  if (state.trialCanvas.graphNetwork && state.trialCanvas.graphData) return;
  if (!els.trialCanvasGraphContainer) return;
  const data = {
    nodes: new DataSet([]),
    edges: new DataSet([])
  };
  const options = {
    nodes: {
      shape: 'dot',
      color: '#60a5fa',
      font: { color: '#f5f5f5', size: 12 },
      borderWidth: 1,
      scaling: { min: 6, max: 26 }
    },
    edges: {
      color: '#475569',
      arrows: { to: { enabled: true, scaleFactor: 0.6 } },
      smooth: { type: 'dynamic' }
    },
    interaction: {
      hover: true,
      multiselect: false,
      keyboard: false
    },
    physics: {
      stabilization: { iterations: 200 },
      barnesHut: { gravitationalConstant: -8000, centralGravity: 0.2, springLength: 120 }
    }
  };
  state.trialCanvas.graphData = data;
  state.trialCanvas.graphNetwork = new Network(els.trialCanvasGraphContainer, data, options);
}

function updateTrialCanvasGraphMeta() {
  if (!els.trialCanvasGraphMeta) return;
  const nodes = Array.isArray(state.trialCanvas.graphNodes) ? state.trialCanvas.graphNodes.length : 0;
  const edges = Array.isArray(state.trialCanvas.graphEdges) ? state.trialCanvas.graphEdges.length : 0;
  if (!nodes) {
    els.trialCanvasGraphMeta.textContent = 'No ontology relationships detected in this note yet.';
  } else {
    els.trialCanvasGraphMeta.textContent = `${nodes} nodes · ${edges} relationships`;
  }
}

function renderTrialCanvasGraph(forceFit = false) {
  if (!els.trialCanvasGraphContainer) return;
  const nodes = Array.isArray(state.trialCanvas.graphNodes) ? state.trialCanvas.graphNodes : [];
  const edges = Array.isArray(state.trialCanvas.graphEdges) ? state.trialCanvas.graphEdges : [];

  if (!nodes.length) {
    els.trialCanvasGraphContainer.innerHTML = '<div class="trial-canvas-empty">No relationships to render. Add or select notes with wiki-links.</div>';
    state.trialCanvas.graphRenderMode = 'empty';
    updateTrialCanvasGraphMeta();
    return;
  }

  try {
    ensureTrialCanvasGraphNetwork();
  } catch (err) {
    state.trialCanvas.graphRenderMode = 'fallback';
    renderGraphFallback(els.trialCanvasGraphContainer, nodes, edges, {
      ariaLabel: 'Trial canvas ontology graph',
      emptyTitle: 'Graph unavailable',
      emptyBody: err.message || 'Unable to render graph.'
    });
    updateTrialCanvasGraphMeta();
    return;
  }

  if (!state.trialCanvas.graphNetwork || !state.trialCanvas.graphData) return;
  try {
    state.trialCanvas.graphData.nodes.clear();
    state.trialCanvas.graphData.edges.clear();
    state.trialCanvas.graphData.nodes.add(nodes);
    state.trialCanvas.graphData.edges.add(edges);
    state.trialCanvas.graphNetwork.setSize('100%', '100%');
    state.trialCanvas.graphNetwork.redraw();
    if (forceFit) {
      state.trialCanvas.graphNetwork.fit({ animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
    }
    state.trialCanvas.graphRenderMode = 'vis';
  } catch (err) {
    state.trialCanvas.graphRenderMode = 'fallback';
    renderGraphFallback(els.trialCanvasGraphContainer, nodes, edges, {
      ariaLabel: 'Trial canvas ontology graph',
      emptyTitle: 'Graph unavailable',
      emptyBody: err.message || 'Unable to render graph.'
    });
  }
  updateTrialCanvasGraphMeta();
}

function renderTrialCanvasContent(markdown = '') {
  if (!els.trialCanvasContent) return;
  els.trialCanvasContent.innerHTML = convertTrialCanvasMarkdownToHtml(markdown);
}

function loadTrialCanvasEntry(relPath = '') {
  const root = ensureTrialCanvasRoot();
  if (!root || !relPath) return;
  const normalized = normalizeTrialCanvasRelPath(relPath);
  const abs = path.resolve(root, normalized);
  if (!abs.startsWith(root)) return;

  let content = '';
  try {
    content = fs.readFileSync(abs, 'utf-8');
  } catch (err) {
    if (els.trialCanvasSidebarStatus) {
      els.trialCanvasSidebarStatus.textContent = `Unable to load ${normalized}: ${err.message}`;
    }
    return;
  }

  state.trialCanvas.selectedPath = normalized;
  state.trialCanvas.selectedType = 'file';
  state.trialCanvas.selectedContent = content;
  ensureTrialCanvasParentsExpanded(normalized);
  updateTrialCanvasTreeSelectionStyles();

  if (els.trialCanvasCurrentTitle) {
    els.trialCanvasCurrentTitle.textContent = basenameOf(normalized) || 'Savani Canvas';
  }
  if (els.trialCanvasCurrentRelPath) {
    els.trialCanvasCurrentRelPath.textContent = normalized;
  }

  renderTrialCanvasContent(content);
  const graphPayload = buildTrialCanvasGraphFromContent(content);
  state.trialCanvas.graphNodes = graphPayload.nodes;
  state.trialCanvas.graphEdges = graphPayload.edges;
  renderTrialCanvasGraph(true);
}

function refreshTrialCanvasView(options = {}) {
  const root = ensureTrialCanvasRoot();
  if (!root) return;
  renderTrialCanvasTree();
  if (!options.skipContent && state.trialCanvas.selectedPath) {
    loadTrialCanvasEntry(state.trialCanvas.selectedPath);
  }
}

function syncTrialCanvasButtonState() {
  const btn = document.querySelector('.activity-btn[data-action="trial-canvas"]');
  if (!btn) return;
  btn.classList.add('hidden');
  btn.classList.remove('active');
}

function openTrialCanvasTab() {
  void openOntologyGraphTab();
}

async function buildTabForPath(path) {
  const fileTitle = path.split('/').pop() || path;
  const ext = getLowerExt(path);

  if (isPdfExtension(ext)) {
    const { url } = await window.acquittifyApi.getVaultFileUrl(path);
    return {
      id: state.nextTabId++,
      title: fileTitle,
      path,
      kind: 'pdf',
      url,
      sourcePath: path
    };
  }

  if (isImageExtension(ext)) {
    const { url } = await window.acquittifyApi.getVaultFileUrl(path);
    return {
      id: state.nextTabId++,
      title: fileTitle,
      path,
      kind: 'image',
      url,
      sourcePath: path
    };
  }

  if (isAudioExtension(ext)) {
    const { url } = await window.acquittifyApi.getVaultFileUrl(path);
    return {
      id: state.nextTabId++,
      title: fileTitle,
      path,
      kind: 'audio',
      url,
      sourcePath: path
    };
  }

  if (isVideoExtension(ext)) {
    const { url } = await window.acquittifyApi.getVaultFileUrl(path);
    return {
      id: state.nextTabId++,
      title: fileTitle,
      path,
      kind: 'video',
      url,
      sourcePath: path
    };
  }

  if (isProcessableDocumentExtension(ext)) {
    try {
      const extracted = await window.acquittifyApi.ensureExtractedNote(path, false);
      if (extracted?.path && extracted.path !== path) {
        const extractedTab = await buildTabForPath(extracted.path);
        extractedTab.sourcePath = path;
        if (!extractedTab.title.includes('extracted')) {
          extractedTab.title = `${fileTitle} (extracted)`;
        }
        return extractedTab;
      }
    } catch (err) {
      addAgentNotice(`Extraction failed for ${fileTitle}: ${err.message}`, 'Workspace');
    }
  }

  if (!ext || isTextExtension(ext)) {
    const content = await window.acquittifyApi.readVaultFile(path);
    return {
      id: state.nextTabId++,
      title: fileTitle,
      path,
      kind: 'text',
      content,
      sourcePath: path
    };
  }

  const { url } = await window.acquittifyApi.getVaultFileUrl(path);
  return {
    id: state.nextTabId++,
    title: fileTitle,
    path,
    kind: 'binary',
    url,
    sourcePath: path
  };
}

async function openFile(path) {
  const existing = state.openTabs.find((t) => t.path === path || t.sourcePath === path);
  if (existing) {
    activateTab(existing.id);
    return;
  }

  if (!state.activeTabId) {
    const created = await buildTabForPath(path);
    state.openTabs.push(created);
    activateTab(created.id);
    return;
  }

  const activeIndex = state.openTabs.findIndex((t) => t.id === state.activeTabId);
  if (activeIndex === -1) {
    const created = await buildTabForPath(path);
    state.openTabs.push(created);
    activateTab(created.id);
    return;
  }

  const activeTab = state.openTabs[activeIndex];
  if (activeTab && activeTab.kind === 'case-canvas') {
    const created = await buildTabForPath(path);
    state.openTabs.push(created);
    activateTab(created.id);
    return;
  }

  const replacement = await buildTabForPath(path);
  revokePdfTabObjectUrl(state.openTabs[activeIndex]);
  replacement.id = state.openTabs[activeIndex].id;
  state.openTabs[activeIndex] = replacement;
  activateTab(replacement.id);
}

async function saveActive() {
  if (!state.activeTabId) return;
  const tab = state.openTabs.find((t) => t.id === state.activeTabId);
  if (!tab || tab.kind !== 'text' || !tab.path || tab.readOnly) return;
  tab.content = els.editor.value;
  await window.acquittifyApi.writeVaultFile(tab.path, tab.content);
  addAgentNotice(`Saved ${tab.path}`, 'Workspace');
}

function renderSearchResults(results) {
  els.searchResults.innerHTML = '';
  for (const r of results) {
    const hit = document.createElement('div');
    hit.className = 'search-hit';
    hit.innerHTML = `<div class="search-path">${r.path}</div><div class="search-snippet">${r.snippet}</div>`;
    hit.onclick = () => openFile(r.path);
    els.searchResults.appendChild(hit);
  }
}

async function performSearch(q) {
  const results = await window.acquittifyApi.searchVault(q);
  renderSearchResults(results);
  setActiveLeftTab('search');
}

async function loadGraph() {
  try {
    state.graph = await window.acquittifyApi.getGraph();
    state.graphRendered = false;
    if (!state.graphRenderMode || state.graphRenderMode === 'unknown') {
      state.graphRenderMode = 'vis';
    }
  } catch (err) {
    state.graph = { nodes: [], edges: [], meta: {} };
    state.graphRendered = false;
    state.graphRenderMode = 'fallback';
    addAgentNotice(`Graph load error: ${err.message}`);
  }
}

function ensureGraphContainerSize(container, minHeight = 340) {
  if (!container) return;
  if (!container.style.minHeight) container.style.minHeight = `${minHeight}px`;
}

function makeSvgEl(tag, attrs = {}) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null) continue;
    el.setAttribute(key, String(value));
  }
  return el;
}

function renderGraphFallback(container, rawNodes = [], rawEdges = [], options = {}) {
  if (!container) return;
  ensureGraphContainerSize(container);
  const suppressTooltips = options.suppressTooltips === true;

  const nodes = Array.isArray(rawNodes) ? rawNodes.slice(0, Number(options.maxNodes) || 180) : [];
  const nodeIds = new Set(nodes.map((n) => n.id));
  const edges = (Array.isArray(rawEdges) ? rawEdges : [])
    .filter((e) => nodeIds.has(e.from ?? e.source) && nodeIds.has(e.to ?? e.target))
    .slice(0, Number(options.maxEdges) || 1500);

  container.innerHTML = '';

  if (!nodes.length) {
    const empty = document.createElement('div');
    empty.className = 'graph-error';
    empty.innerHTML =
      `<div class="graph-error-title">${options.emptyTitle || 'Graph is empty'}</div>` +
      `<div class="graph-error-body">${options.emptyBody || 'No nodes available for this graph.'}</div>`;
    container.appendChild(empty);
    return;
  }

  const width = Math.max(680, container.clientWidth || 0);
  const height = Math.max(420, container.clientHeight || 0);
  const cx = width / 2;
  const cy = height / 2;
  const maxRadius = Math.max(120, Math.min(width, height) * 0.42);

  const degree = new Map();
  for (const e of edges) {
    const from = e.from ?? e.source;
    const to = e.to ?? e.target;
    degree.set(from, (degree.get(from) || 0) + 1);
    degree.set(to, (degree.get(to) || 0) + 1);
  }

  const coords = new Map();
  nodes.forEach((node, idx) => {
    const theta = idx * 2.399963229728653;
    const radius = Math.sqrt((idx + 1) / Math.max(1, nodes.length)) * maxRadius;
    coords.set(node.id, {
      x: cx + Math.cos(theta) * radius,
      y: cy + Math.sin(theta) * radius
    });
  });

  const svg = makeSvgEl('svg', {
    width: '100%',
    height: '100%',
    viewBox: `0 0 ${width} ${height}`,
    role: 'img',
    'aria-label': options.ariaLabel || 'Graph fallback view'
  });

  const edgeLayer = makeSvgEl('g', { opacity: '0.8' });
  for (const edge of edges) {
    const from = edge.from ?? edge.source;
    const to = edge.to ?? edge.target;
    const a = coords.get(from);
    const b = coords.get(to);
    if (!a || !b) continue;
    edgeLayer.appendChild(
      makeSvgEl('line', {
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
        stroke: edge.color || '#4a4a4a',
        'stroke-width': edge.width || 1.1
      })
    );
  }
  svg.appendChild(edgeLayer);

  const nodeLayer = makeSvgEl('g');
  for (const node of nodes) {
    const p = coords.get(node.id);
    if (!p) continue;
    const d = degree.get(node.id) || 0;
    const r = Math.max(4, Math.min(11, 4 + Math.log2(d + 1) * 2));
    const g = makeSvgEl('g');
    const circle = makeSvgEl('circle', {
      cx: p.x,
      cy: p.y,
      r,
      fill: node?.color?.background || '#8ab4f8',
      stroke: '#efefef',
      'stroke-width': 0.8
    });
    if (!suppressTooltips) {
      const title = makeSvgEl('title');
      title.textContent = String(node.title || node.label || node.id || '');
      circle.appendChild(title);
    }
    g.appendChild(circle);
    if (nodes.length <= 90) {
      const label = makeSvgEl('text', {
        x: p.x + r + 2,
        y: p.y + 3,
        fill: '#dddddd',
        'font-size': 10,
        'font-family': '-apple-system, Segoe UI, sans-serif'
      });
      const rawLabel = String(node.label || node.id || '');
      label.textContent = rawLabel.length > 22 ? `${rawLabel.slice(0, 21)}…` : rawLabel;
      g.appendChild(label);
    }
    nodeLayer.appendChild(g);
  }
  svg.appendChild(nodeLayer);
  container.appendChild(svg);
}

function updateGraphMeta(visibleNodes, visibleEdges) {
  if (!els.graphMeta) return;
  const meta = state.graph?.meta || {};
  const scannedFiles = Number(meta.scannedFiles || 0);
  const truncated = meta.truncated ? ' • truncated' : '';
  const mode = state.graphRenderMode ? ` • mode: ${state.graphRenderMode}` : '';
  els.graphMeta.textContent =
    `Vault graph • nodes: ${visibleNodes} • edges: ${visibleEdges}` +
    ` • scanned files: ${scannedFiles}${truncated}${mode}`;
}

function showGraphRenderError(err) {
  const message = err?.message ? String(err.message) : String(err || 'Unknown graph render error');
  if (els.graphContainer) {
    els.graphContainer.innerHTML =
      `<div class="graph-error">` +
      `<div class="graph-error-title">Vault Graph Render Error</div>` +
      `<div class="graph-error-body">${message}</div>` +
      `</div>`;
  }
  if (els.graphMeta) {
    els.graphMeta.textContent = `Vault graph error: ${message}`;
  }
  addAgentNotice(`Graph render error: ${message}`, 'Workspace');
}

function showOntologyGraphRenderError(err) {
  const message = err?.message ? String(err.message) : String(err || 'Unknown ontology graph render error');
  if (els.ontologyGraphContainer) {
    els.ontologyGraphContainer.innerHTML =
      `<div class="graph-error">` +
      `<div class="graph-error-title">Caselaw Ontology Graph Render Error</div>` +
      `<div class="graph-error-body">${message}</div>` +
      `</div>`;
  }
  if (els.ontologyGraphMeta) {
    els.ontologyGraphMeta.textContent = `Ontology graph error: ${message}`;
  }
  setOntologyRefreshStatus(`Render error: ${message}`, 'error');
  addAgentNotice(`Ontology graph render error: ${message}`, 'Workspace');
}

function hasUsableGraphCanvas(container) {
  if (!container) return false;
  const canvas = container.querySelector('canvas');
  if (!canvas) return false;
  const rect = canvas.getBoundingClientRect();
  return rect.width > 20 && rect.height > 20;
}

function buildOntologyElasticTuning(nodeCount = 0, edgeCount = 0) {
  const nodes = Math.max(1, Number(nodeCount) || 1);
  const edges = Math.max(0, Number(edgeCount) || 0);
  const density = edges / nodes;
  const nodeScale = Math.max(0.8, Math.log2(nodes + 1));
  const crowdFactor = Math.max(0.92, Math.min(2.1, 0.86 + nodeScale / 8 + density / 18));

  const springLength = Math.round(Math.max(132, Math.min(320, 128 * crowdFactor + density * 2.4)));
  const springConstant = Math.max(0.016, Math.min(0.034, 0.032 - (crowdFactor - 1) * 0.007));
  const gravitationalConstant = -Math.round(Math.max(2400, Math.min(9000, 2400 * crowdFactor)));
  const centralGravity = Math.max(0.01, Math.min(0.06, 0.055 / crowdFactor));
  const avoidOverlap = Math.max(0.36, Math.min(0.92, 0.36 + (crowdFactor - 0.9) * 0.33));
  const damping = Math.max(0.3, Math.min(0.42, 0.3 + (crowdFactor - 1) * 0.07));
  const minVelocity = Math.max(0.2, Math.min(0.45, 0.4 - (crowdFactor - 1) * 0.13));
  const stabilizationIterations = Math.round(Math.max(220, Math.min(520, 250 + nodes / 5)));
  const fillRatio = Math.max(0.84, Math.min(0.93, 0.91 - (crowdFactor - 1) * 0.04));

  return {
    springLength,
    springConstant,
    gravitationalConstant,
    centralGravity,
    avoidOverlap,
    damping,
    minVelocity,
    stabilizationIterations,
    fillRatio,
    minScale: 0.12,
    maxScale: 2.4
  };
}

function applyOntologyElasticTuning(tuning = {}) {
  if (!state.ontologyGraphNetwork) return;
  const resolved = {
    ...buildOntologyElasticTuning(0, 0),
    ...(tuning && typeof tuning === 'object' ? tuning : {})
  };
  try {
    state.ontologyGraphNetwork.setOptions({
      physics: {
        enabled: true,
        solver: 'barnesHut',
        stabilization: {
          enabled: true,
          iterations: Number(resolved.stabilizationIterations) || 280,
          updateInterval: 20,
          fit: false
        },
        barnesHut: {
          gravitationalConstant: Number(resolved.gravitationalConstant) || -2600,
          centralGravity: Number(resolved.centralGravity) || 0.045,
          springLength: Number(resolved.springLength) || 150,
          springConstant: Number(resolved.springConstant) || 0.028,
          damping: Number(resolved.damping) || 0.32,
          avoidOverlap: Number(resolved.avoidOverlap) || 0.46
        },
        minVelocity: Number(resolved.minVelocity) || 0.32,
        adaptiveTimestep: true
      }
    });
  } catch {
    // Keep defaults when runtime tuning is unavailable.
  }
}

function fitOntologyGraphToViewport(options = {}) {
  const network = state.ontologyGraphNetwork;
  const data = state.ontologyGraphData;
  const container = els.ontologyGraphContainer;
  if (!network || !data || !container) return;

  const nodeIds = data.nodes.getIds();
  if (!Array.isArray(nodeIds) || !nodeIds.length) return;

  const positions = network.getPositions(nodeIds);
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const nodeId of nodeIds) {
    const pos = positions?.[nodeId];
    if (!pos) continue;
    const x = Number(pos.x);
    const y = Number(pos.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }

  if (!Number.isFinite(minX) || !Number.isFinite(maxX) || !Number.isFinite(minY) || !Number.isFinite(maxY)) {
    return;
  }

  const graphWidth = Math.max(1, maxX - minX);
  const graphHeight = Math.max(1, maxY - minY);
  const viewportWidth = Math.max(1, Number(container.clientWidth) || 1);
  const viewportHeight = Math.max(1, Number(container.clientHeight) || 1);
  const fillRaw = Number(options.fillRatio);
  const fillRatio = Number.isFinite(fillRaw) ? Math.max(0.7, Math.min(0.97, fillRaw)) : 0.9;
  const minScaleRaw = Number(options.minScale);
  const maxScaleRaw = Number(options.maxScale);
  const minScale = Number.isFinite(minScaleRaw) ? Math.max(0.02, minScaleRaw) : 0.12;
  const maxScale = Number.isFinite(maxScaleRaw) ? Math.max(minScale, maxScaleRaw) : 2.4;

  let targetScale = Math.min(
    (viewportWidth * fillRatio) / graphWidth,
    (viewportHeight * fillRatio) / graphHeight
  );
  if (!Number.isFinite(targetScale) || targetScale <= 0) {
    targetScale = Math.min(maxScale, Math.max(minScale, network.getScale() || 1));
  } else {
    targetScale = Math.min(maxScale, Math.max(minScale, targetScale));
  }

  const targetPosition = {
    x: (minX + maxX) / 2,
    y: (minY + maxY) / 2
  };
  const animate = options.animate !== false;
  network.moveTo({
    position: targetPosition,
    scale: targetScale,
    animation: animate
      ? {
          duration: Math.max(120, Number(options.duration) || 320),
          easingFunction: 'easeInOutQuad'
        }
      : false
  });
}

function ensureGraphNetwork() {
  if (state.graphNetwork || !els.graphContainer) return;

  try {
    const nodes = new DataSet([]);
    const edges = new DataSet([]);
    state.graphData = { nodes, edges };

    state.graphNetwork = new Network(
      els.graphContainer,
      { nodes, edges },
      {
        autoResize: true,
        interaction: {
          hover: true,
          navigationButtons: false,
          keyboard: true,
          zoomView: true,
          dragView: true
        },
        physics: {
          enabled: true,
          stabilization: { iterations: 300 },
          barnesHut: {
            gravitationalConstant: -2500,
            springLength: 110,
            springConstant: 0.035,
            damping: 0.28
          }
        },
        edges: {
          color: {
            color: '#4a4a4a',
            highlight: '#8b5cf6',
            hover: '#3b82f6',
            inherit: false
          },
          width: 1,
          smooth: false
        },
        nodes: {
          shape: 'dot',
          size: 7,
          scaling: {
            min: 7,
            max: 26,
            label: {
              enabled: true,
              min: 11,
              max: 18,
              drawThreshold: 6,
              maxVisible: 28
            }
          },
          color: {
            background: '#c9c9c9',
            border: '#e5e5e5',
            highlight: { background: '#8b5cf6', border: '#a78bfa' },
            hover: { background: '#3b82f6', border: '#60a5fa' }
          },
          font: {
            color: '#f3f3f3',
            size: 12,
            face: '-apple-system, Segoe UI, sans-serif',
            strokeWidth: 0
          }
        }
      }
    );
  } catch (err) {
    state.graphNetwork = null;
    state.graphData = null;
    throw err;
  }

  state.graphNetwork.on('doubleClick', (params) => {
    if (!params.nodes.length) state.graphNetwork.fit({ animation: true });
  });

  state.graphNetwork.on('click', async (params) => {
    const nodeId = params.nodes[0];
    if (!nodeId) return;

    const knownNode = (state.graph.nodes || []).find((n) => n.id === nodeId);
    if (knownNode?.path) {
      try {
        await openFile(knownNode.path);
        return;
      } catch {
        // continue with fallback
      }
    }

    const directCandidates = [`${nodeId}.md`, `${nodeId}.markdown`, `${nodeId}.yaml`, `${nodeId}.yml`];
    for (const candidate of directCandidates) {
      try {
        await openFile(candidate);
        return;
      } catch {
        // continue fallback chain
      }
    }

    try {
      const results = await window.acquittifyApi.searchVault(String(nodeId));
      const exact = results.find((r) => directCandidates.some((c) => r.path === c || r.path.endsWith(`/${c}`)));
      if (exact) await openFile(exact.path);
    } catch {
      // ignore
    }
  });
}

function renderGraph(forceFit = false) {
  ensureGraphContainerSize(els.graphContainer);

  const MAX_RENDER_NODES = 2500;
  const MAX_RENDER_EDGES = 5000;
  const graphNodes = Array.isArray(state.graph.nodes) ? state.graph.nodes : [];
  const graphEdges = Array.isArray(state.graph.edges) ? state.graph.edges : [];

  const knownIds = new Set(graphNodes.map((n) => n.id));
  const validEdges = graphEdges.filter((e) => knownIds.has(e.source) && knownIds.has(e.target));

  const fullDegree = new Map();
  for (const e of validEdges) {
    fullDegree.set(e.source, (fullDegree.get(e.source) || 0) + 1);
    fullDegree.set(e.target, (fullDegree.get(e.target) || 0) + 1);
  }

  const selectedBaseNodes = graphNodes
    .slice()
    .sort((a, b) => {
      const degreeDelta = (fullDegree.get(b.id) || 0) - (fullDegree.get(a.id) || 0);
      if (degreeDelta) return degreeDelta;
      return String(a.id).localeCompare(String(b.id));
    })
    .slice(0, MAX_RENDER_NODES);

  const selectedNodeIds = new Set(selectedBaseNodes.map((n) => n.id));

  let edges = validEdges
    .filter((e) => selectedNodeIds.has(e.source) && selectedNodeIds.has(e.target))
    .slice(0, MAX_RENDER_EDGES)
    .map((e, i) => ({ id: `${e.source}->${e.target}-${i}`, from: e.source, to: e.target }));

  const visibleDegree = new Map();
  for (const e of edges) {
    visibleDegree.set(e.from, (visibleDegree.get(e.from) || 0) + 1);
    visibleDegree.set(e.to, (visibleDegree.get(e.to) || 0) + 1);
  }

  const MIN_BUBBLE = 7;
  const MAX_BUBBLE = 26;
  let nodes = selectedBaseNodes.map((n) => {
    const d = visibleDegree.get(n.id) || 0;
    const size = Math.max(MIN_BUBBLE, Math.min(MAX_BUBBLE, MIN_BUBBLE + Math.log2(d + 1) * 4));
    return {
      id: n.id,
      label: n.label || String(n.id).split('/').pop(),
      title: `${n.id}\nConnectors: ${d}`,
      value: size,
      mass: Math.max(1, d / 4)
    };
  });

  if (!nodes.length) {
    nodes = [
      {
        id: '__empty_graph__',
        label: 'No graphable notes',
        title: 'No markdown/yaml notes found in selected vault.',
        value: 18,
        mass: 1
      }
    ];
    edges = [];
  }

  if (!state.graphVisDisabled) {
    try {
      ensureGraphNetwork();
    } catch (err) {
      state.graphVisDisabled = true;
      state.graphRenderMode = 'fallback';
      showGraphRenderError(err);
    }
  }

  if (!state.graphNetwork || !state.graphData) {
    state.graphRenderMode = 'fallback';
    renderGraphFallback(els.graphContainer, nodes, edges, {
      ariaLabel: 'Vault graph fallback view',
      emptyTitle: 'No graphable notes',
      emptyBody: 'No markdown/yaml notes found in selected vault.'
    });
    updateGraphMeta(nodes.length, edges.length);
    return;
  }

  try {
    state.graphData.nodes.clear();
    state.graphData.edges.clear();
    state.graphData.nodes.add(nodes);
    state.graphData.edges.add(edges);

    state.graphNetwork.setSize('100%', '100%');
    state.graphNetwork.redraw();
    if (!state.graphRendered || forceFit) {
      state.graphNetwork.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
    }
    state.graphRendered = true;
    state.graphRenderMode = 'vis';
  } catch (err) {
    state.graphVisDisabled = true;
    state.graphRenderMode = 'fallback';
    showGraphRenderError(err);
    renderGraphFallback(els.graphContainer, nodes, edges, {
      ariaLabel: 'Vault graph fallback view',
      emptyTitle: 'No graphable notes',
      emptyBody: 'No markdown/yaml notes found in selected vault.'
    });
  }

  if (!hasUsableGraphCanvas(els.graphContainer)) {
    setTimeout(() => {
      if (hasUsableGraphCanvas(els.graphContainer)) return;
      state.graphVisDisabled = true;
      state.graphRenderMode = 'fallback';
      renderGraphFallback(els.graphContainer, nodes, edges, {
        ariaLabel: 'Vault graph fallback view',
        emptyTitle: 'No graphable notes',
        emptyBody: 'No markdown/yaml notes found in selected vault.'
      });
    }, 120);
  }

  updateGraphMeta(nodes.length, edges.length);
}

async function loadOntologyGraph() {
  try {
    if (state.vaultViewKind === 'caselaw') {
      const selectedRoots = resolvedCaselawSelectedRoots();
      if (selectedRoots.length) {
        state.ontologyGraph = await window.acquittifyApi.getOntologyGraphMulti({
          vaultRoots: selectedRoots
        });
      } else {
        state.ontologyGraph = {
          nodes: [],
          edges: [],
          meta: {
            source: 'multi_vault',
            selectedVaultRoots: [],
            exists: false,
            ontologyRoot: 'multiple vaults (0)',
            multiVault: true
          }
        };
      }
    } else {
      state.ontologyGraph = await window.acquittifyApi.getOntologyGraph();
    }
    const lookup = new Map();
    const ontologyNodes = Array.isArray(state.ontologyGraph?.nodes) ? state.ontologyGraph.nodes : [];
    for (const node of ontologyNodes) {
      if (!node || node.id === undefined || node.id === null) continue;
      lookup.set(String(node.id), node);
    }
    state.ontologyNodeLookup = lookup;
    state.ontologyGraphRendered = false;
    if (!state.ontologyGraphRenderMode || state.ontologyGraphRenderMode === 'unknown') {
      state.ontologyGraphRenderMode = 'vis';
    }
    setOntologyRefreshStatus('Ontology graph loaded.', 'neutral');
  } catch (err) {
    state.ontologyGraph = { nodes: [], edges: [], meta: {} };
    state.ontologyNodeLookup = new Map();
    state.ontologyGraphRendered = false;
    state.ontologyGraphRenderMode = 'fallback';
    setOntologyRefreshStatus(`Load error: ${err.message}`, 'error');
    addAgentNotice(`Ontology graph load error: ${err.message}`);
  }
}

function ensureOntologyGraphNetwork() {
  if (state.ontologyGraphNetwork || !els.ontologyGraphContainer) return;

  try {
    const nodes = new DataSet([]);
    const edges = new DataSet([]);
    state.ontologyGraphData = { nodes, edges };
    const baseTuning = buildOntologyElasticTuning(240, 520);

    state.ontologyGraphNetwork = new Network(
      els.ontologyGraphContainer,
      { nodes, edges },
      {
        autoResize: true,
        layout: {
          improvedLayout: true
        },
        interaction: {
          hover: true,
          hoverConnectedEdges: false,
          tooltipDelay: 1000000000,
          keyboard: true,
          zoomView: true,
          dragView: true
        },
        physics: {
          enabled: true,
          solver: 'barnesHut',
          stabilization: {
            enabled: true,
            iterations: baseTuning.stabilizationIterations,
            updateInterval: 20,
            fit: false
          },
          barnesHut: {
            gravitationalConstant: baseTuning.gravitationalConstant,
            centralGravity: baseTuning.centralGravity,
            springLength: baseTuning.springLength,
            springConstant: baseTuning.springConstant,
            damping: baseTuning.damping,
            avoidOverlap: baseTuning.avoidOverlap
          },
          minVelocity: baseTuning.minVelocity,
          adaptiveTimestep: true
        },
        edges: {
          color: { color: '#4a4a4a', highlight: '#f59e0b', hover: '#60a5fa', inherit: false },
          width: 1,
          smooth: false
        },
        nodes: {
          shape: 'dot',
          scaling: {
            min: 7,
            max: 26,
            label: {
              enabled: true,
              min: 11,
              max: 18,
              drawThreshold: 6,
              maxVisible: 30
            }
          },
          font: {
            color: '#f3f3f3',
            size: 12,
            face: '-apple-system, Segoe UI, sans-serif'
          }
        }
      }
    );
  } catch (err) {
    state.ontologyGraphNetwork = null;
    state.ontologyGraphData = null;
    throw err;
  }

  state.ontologyGraphNetwork.on('doubleClick', (params) => {
    if (!params.nodes.length) {
      fitOntologyGraphToViewport({ animate: true, duration: 280 });
    }
  });

  state.ontologyGraphNetwork.on('click', async (params) => {
    hideOntologyCaseHoverCard(true);
    const nodeId = params.nodes[0];
    if (!nodeId) return;
    const knownNode = findOntologyNodeById(nodeId);
    if (knownNode && isCaseOntologyNode(knownNode)) {
      await openOntologyCaseSidebar(knownNode);
      return;
    }
    if (knownNode?.path) {
      try {
        await openFile(knownNode.path);
      } catch {
        // no-op
      }
    }
  });

  state.ontologyGraphNetwork.on('hoverNode', (params) => {
    const nodeId = params?.node;
    const knownNode = findOntologyNodeById(nodeId);
    if (!knownNode || !isCaseOntologyNode(knownNode)) {
      hideOntologyCaseHoverCard(true);
      return;
    }
    const pointer = ontologyHoverPointerPosition(params) || { x: 12, y: 12 };
    showOntologyCaseHoverCard(knownNode, pointer);
  });

  state.ontologyGraphNetwork.on('blurNode', () => {
    scheduleHideOntologyCaseHoverCard(420);
  });

  state.ontologyGraphNetwork.on('dragStart', () => {
    hideOntologyCaseHoverCard(true);
  });
}

function checkedValuesFrom(container) {
  if (!container) return [];
  return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

function parseNumberInput(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : null;
}

function truncateText(value, max = 240) {
  const compact = String(value || '').replace(/\s+/g, ' ').trim();
  if (!compact) return '';
  if (compact.length <= max) return compact;
  return `${compact.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

function isCaseOntologyNode(node) {
  const nodeType = String(node?.nodeType || '').toLowerCase();
  if (nodeType) return nodeType === 'case';
  if (node?.caseId || node?.case_id || node?.caseTitle || node?.caseDisplayLabel || node?.caseCitation) {
    const pathText = String(node?.path || '').toLowerCase();
    if (pathText.includes('/events/')) return false;
    return true;
  }
  const idText = String(node?.id || '');
  if (/^event[._:-]/i.test(idText)) return false;
  return /^us\.scotus\./i.test(idText) || /^case[._:-]/i.test(idText);
}

function normalizeOntologyCaseCitation(value) {
  const raw = String(value || '').replace(/\s+/g, ' ').trim();
  if (!raw) return '';
  if (/citation unavailable|unknown citation|^unknown$/i.test(raw)) return '';
  if (/^\d{1,2}-\d{1,6}[a-z]*$/i.test(raw)) return '';
  const usMatch = raw.match(/\b(\d+)\s*U\.?\s*S\.?\s*([0-9_]+)\b/i);
  if (usMatch) return `${Number(usMatch[1])} U.S. ${usMatch[2]}`;
  const sctMatch = raw.match(/\b(\d+)\s*S\.?\s*Ct\.?\s*([0-9_]+)\b/i);
  if (sctMatch) return `${Number(sctMatch[1])} S. Ct. ${sctMatch[2]}`;
  const ledMatch = raw.match(/\b(\d+)\s*L\.?\s*Ed\.?\s*2d\s*([0-9_]+)\b/i);
  if (ledMatch) return `${Number(ledMatch[1])} L. Ed. 2d ${ledMatch[2]}`;
  return '';
}

function ontologyCaseLabel(node) {
  const candidates = [node?.caseDisplayLabel, node?.caseTitle, node?.label, node?.id];
  for (const candidate of candidates) {
    const text = truncateText(candidate, 160);
    if (!text) continue;
    if (/^us\.scotus\./i.test(text) || /^scotus-/i.test(text)) continue;
    return text;
  }
  return truncateText(node?.caseDisplayLabel || node?.caseTitle || node?.label || node?.id || 'Case', 160);
}

function ontologyCaseCitation(node) {
  const candidates = [
    node?.caseCitation,
    node?.citation,
    node?.caseDisplayLabel,
    node?.caseTitle,
    node?.label
  ];
  for (const candidate of candidates) {
    const normalized = normalizeOntologyCaseCitation(candidate);
    if (normalized) return truncateText(normalized, 160);
  }
  return '';
}

function ontologyCaseEssentialHolding(node) {
  return truncateText(node?.essentialHolding || '', 380);
}

function ontologyCaseSummary(node) {
  const summary = truncateText(node?.caseSummary || '', 620);
  if (summary) return summary;
  return 'Structured case summary is not available yet for this node.';
}

function ontologyCaseDomain(node) {
  const normalized = normalizeOntologyCaseDomain(node?.caseDomain || node?.caseType || node?.domain || '');
  if (normalized === 'criminal') return 'criminal';
  return 'civil';
}

function findOntologyNodeById(nodeId) {
  if (nodeId === undefined || nodeId === null || nodeId === '') return null;
  const key = String(nodeId);
  if (state.ontologyNodeLookup instanceof Map && state.ontologyNodeLookup.has(key)) {
    return state.ontologyNodeLookup.get(key) || null;
  }
  const nodes = Array.isArray(state.ontologyGraph?.nodes) ? state.ontologyGraph.nodes : [];
  return nodes.find((node) => node && String(node.id) === key) || null;
}

function clearOntologyHoverHideTimer() {
  if (state.ontologyCaseHoverHideTimer) {
    clearTimeout(state.ontologyCaseHoverHideTimer);
    state.ontologyCaseHoverHideTimer = null;
  }
}

function hideOntologyCaseHoverCard(clearNode = false) {
  clearOntologyHoverHideTimer();
  if (!els.ontologyCaseHoverCard) return;
  if (clearNode) {
    els.ontologyCaseHoverCard.dataset.nodeId = '';
    els.ontologyCaseHoverCard.innerHTML = '';
    state.ontologyHoverLastPointer = null;
  }
  els.ontologyCaseHoverCard.classList.add('hidden');
}

function scheduleHideOntologyCaseHoverCard(delayMs = 220) {
  clearOntologyHoverHideTimer();
  state.ontologyCaseHoverHideTimer = setTimeout(() => hideOntologyCaseHoverCard(true), Math.max(0, delayMs));
}

function ontologyHoverPointerPosition(params) {
  const dom = params?.pointer?.DOM;
  if (dom && Number.isFinite(dom.x) && Number.isFinite(dom.y)) {
    return { x: Number(dom.x), y: Number(dom.y) };
  }
  const eventLike = params?.event?.srcEvent || params?.event;
  if (!eventLike || !els.ontologyGraphContainer) return null;
  const rect = els.ontologyGraphContainer.getBoundingClientRect();
  if (!rect || !Number.isFinite(eventLike.clientX) || !Number.isFinite(eventLike.clientY)) return null;
  return { x: eventLike.clientX - rect.left, y: eventLike.clientY - rect.top };
}

function refreshOntologyHoverFromPointer(pointer) {
  if (!pointer || !state.ontologyGraphNetwork || !els.ontologyCaseHoverCard) return;
  if (state.ontologyGraphRenderMode !== 'vis') return;
  let nodeId = null;
  try {
    nodeId = state.ontologyGraphNetwork.getNodeAt(pointer);
  } catch {
    nodeId = null;
  }
  const knownNode = findOntologyNodeById(nodeId);
  if (!knownNode || !isCaseOntologyNode(knownNode)) {
    if (!els.ontologyCaseHoverCard.classList.contains('hidden') && !els.ontologyCaseHoverCard.matches(':hover')) {
      scheduleHideOntologyCaseHoverCard(320);
    }
    return;
  }
  showOntologyCaseHoverCard(knownNode, pointer);
}

function requestOntologyHoverRefresh(pointer) {
  if (!pointer) return;
  if (els.ontologyCaseHoverCard?.classList.contains('hidden')) {
    refreshOntologyHoverFromPointer(pointer);
    return;
  }
  state.ontologyHoverLastPointer = pointer;
  if (state.ontologyHoverRafPending) return;
  state.ontologyHoverRafPending = true;
  requestAnimationFrame(() => {
    state.ontologyHoverRafPending = false;
    const pendingPointer = state.ontologyHoverLastPointer;
    state.ontologyHoverLastPointer = null;
    refreshOntologyHoverFromPointer(pendingPointer);
  });
}

function positionOntologyCaseHoverCard(pointer = { x: 0, y: 0 }) {
  if (!els.ontologyCaseHoverCard || !els.ontologyGraphContainer) return;
  const containerRect = els.ontologyGraphContainer.getBoundingClientRect();
  const cardRect = els.ontologyCaseHoverCard.getBoundingClientRect();
  const gap = 14;
  const maxX = Math.max(gap, containerRect.width - cardRect.width - gap);
  const maxY = Math.max(gap, containerRect.height - cardRect.height - gap);
  const left = Math.max(gap, Math.min(maxX, Number(pointer.x || 0) + gap));
  const top = Math.max(gap, Math.min(maxY, Number(pointer.y || 0) + gap));
  els.ontologyCaseHoverCard.style.left = `${left}px`;
  els.ontologyCaseHoverCard.style.top = `${top}px`;
}

function parseYamlScalar(value = '') {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'"))) {
    return raw.slice(1, -1).trim();
  }
  return raw;
}

function normalizeCaseIdLookup(value = '') {
  return String(value || '').trim().toLowerCase();
}

function extractCasePdfMetadataFromNote(noteAbsPath) {
  let text = '';
  try {
    text = fs.readFileSync(noteAbsPath, 'utf8');
  } catch {
    return null;
  }
  const lines = String(text || '').split(/\r?\n/);
  if (lines[0] !== '---') return null;

  let caseId = '';
  let opinionPdfPath = '';
  for (let idx = 1; idx < lines.length; idx++) {
    const line = lines[idx];
    if (line.trim() === '---') break;
    const caseIdMatch = line.match(/^\s*case_id\s*:\s*(.+)\s*$/i);
    if (caseIdMatch) {
      caseId = parseYamlScalar(caseIdMatch[1]);
      continue;
    }
    const pdfMatch = line.match(/^\s*opinion_pdf_path\s*:\s*(.+)\s*$/i);
    if (pdfMatch) {
      opinionPdfPath = parseYamlScalar(pdfMatch[1]);
      continue;
    }
  }

  if (!caseId && !opinionPdfPath) return null;
  return { caseId, opinionPdfPath };
}

function resolvePotentialPdfPath(value = '', vaultRoot = '', noteDir = '') {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw) || raw.startsWith('file://')) return raw;
  if (path.isAbsolute(raw)) return raw;

  const roots = [];
  if (noteDir) roots.push(noteDir);
  if (vaultRoot) roots.push(vaultRoot);
  for (const root of roots) {
    const candidate = path.resolve(root, raw.replaceAll('\\', '/'));
    if (fs.existsSync(candidate)) return candidate;
  }
  return '';
}

function walkMarkdownFilesInCasesDir(rootDir, out = [], maxFiles = 25000) {
  if (!rootDir || out.length >= maxFiles) return out;
  let entries = [];
  try {
    entries = fs.readdirSync(rootDir, { withFileTypes: true });
  } catch {
    return out;
  }

  for (const entry of entries) {
    if (out.length >= maxFiles) break;
    const abs = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      walkMarkdownFilesInCasesDir(abs, out, maxFiles);
      continue;
    }
    if (entry.isFile() && /\.md$/i.test(entry.name)) {
      out.push(abs);
    }
  }
  return out;
}

function getCasePdfIndexForVault(vaultRoot = '') {
  const resolvedRoot = path.resolve(String(vaultRoot || '').trim());
  if (!resolvedRoot) return new Map();
  if (state.casePdfIndexByVaultRoot instanceof Map && state.casePdfIndexByVaultRoot.has(resolvedRoot)) {
    return state.casePdfIndexByVaultRoot.get(resolvedRoot) || new Map();
  }

  const index = new Map();
  const casesRoot = path.join(resolvedRoot, 'Ontology', 'precedent_vault', 'cases');
  if (!fs.existsSync(casesRoot)) {
    state.casePdfIndexByVaultRoot.set(resolvedRoot, index);
    return index;
  }

  const noteFiles = walkMarkdownFilesInCasesDir(casesRoot, []);
  for (const noteAbs of noteFiles) {
    const meta = extractCasePdfMetadataFromNote(noteAbs);
    if (!meta || !meta.caseId || !meta.opinionPdfPath) continue;
    const normalizedCaseId = normalizeCaseIdLookup(meta.caseId);
    if (!normalizedCaseId || index.has(normalizedCaseId)) continue;
    const resolvedPdfPath = resolvePotentialPdfPath(meta.opinionPdfPath, resolvedRoot, path.dirname(noteAbs));
    if (!resolvedPdfPath || /^https?:\/\//i.test(resolvedPdfPath) || resolvedPdfPath.startsWith('file://')) continue;
    if (!/\.pdf$/i.test(resolvedPdfPath) || !fs.existsSync(resolvedPdfPath)) continue;
    index.set(normalizedCaseId, resolvedPdfPath);
  }

  state.casePdfIndexByVaultRoot.set(resolvedRoot, index);
  return index;
}

async function resolveOntologyCasePdfUrl(node) {
  const raw = String(node?.pdfPath || node?.opinionUrl || '').trim();
  const looksLikePdfReference = (value = '') => /\.pdf(?:[#?]|$)/i.test(String(value || '').trim());
  const pdfTargetToUrl = (target = '') => {
    const normalized = String(target || '').trim();
    if (!normalized) return '';
    if (/^https?:\/\//i.test(normalized) || normalized.startsWith('file://')) {
      return looksLikePdfReference(normalized) ? normalized : '';
    }
    if (!looksLikePdfReference(normalized)) return '';
    if (!path.isAbsolute(normalized)) return '';
    if (!fs.existsSync(normalized)) return '';
    return pathToFileURL(normalized).toString();
  };
  if (raw && (/^https?:\/\//i.test(raw) || raw.startsWith('file://')) && looksLikePdfReference(raw)) return raw;
  if (raw && path.isAbsolute(raw) && looksLikePdfReference(raw) && fs.existsSync(raw)) {
    return pathToFileURL(raw).toString();
  }

  const sourceVaultRoots = [];
  const pushRoot = (value) => {
    const root = String(value || '').trim();
    if (!root) return;
    const resolved = path.resolve(root);
    if (!resolved || sourceVaultRoots.includes(resolved)) return;
    sourceVaultRoots.push(resolved);
  };

  pushRoot(node?.sourceVaultRoot);
  if (Array.isArray(node?.sourceVaultRoots)) {
    for (const root of node.sourceVaultRoots) pushRoot(root);
  }
  for (const root of resolvedCaselawSelectedRoots()) {
    pushRoot(root);
  }
  pushRoot(state.vaultRoot);

  const resolveFromVaultRoots = (relativePath = '') => {
    const normalized = String(relativePath || '').replaceAll('\\', '/').replace(/^\.?\//, '');
    if (!normalized) return '';
    for (const vaultRoot of sourceVaultRoots) {
      const candidate = path.resolve(vaultRoot, normalized);
      if (!fs.existsSync(candidate)) continue;
      return pathToFileURL(candidate).toString();
    }
    return '';
  };

  const resolveViaVaultApi = async (relativePath = '') => {
    const normalized = String(relativePath || '').replaceAll('\\', '/').replace(/^\.?\//, '');
    if (!normalized) return '';
    try {
      const response = await window.acquittifyApi.getVaultFileUrl(normalized);
      return String(response?.url || '');
    } catch {
      return '';
    }
  };

  if (raw) {
    if (looksLikePdfReference(raw)) {
      const fromRoot = resolveFromVaultRoots(raw);
      if (fromRoot) return fromRoot;
      const fromActive = await resolveViaVaultApi(raw);
      if (fromActive) return fromActive;
    }
  }

  const notePath = String(node?.path || '').trim().replaceAll('\\', '/');
  if (notePath) {
    const noteBase = notePath.replace(/\.[^./\\]+$/i, '');
    const fallbackCandidates = [`${noteBase}.pdf`];
    for (const candidate of fallbackCandidates) {
      const fromRoot = resolveFromVaultRoots(candidate);
      if (fromRoot) return fromRoot;
      const fromActive = await resolveViaVaultApi(candidate);
      if (fromActive) return fromActive;
    }

    const normalizedNotePath = notePath.replace(/^\.?\//, '');
    for (const vaultRoot of sourceVaultRoots) {
      const noteAbs = path.resolve(vaultRoot, normalizedNotePath);
      if (fs.existsSync(noteAbs)) {
        const noteMeta = extractCasePdfMetadataFromNote(noteAbs);
        const notePdfTarget = resolvePotentialPdfPath(
          noteMeta?.opinionPdfPath || '',
          vaultRoot,
          path.dirname(noteAbs)
        );
        const notePdfUrl = pdfTargetToUrl(notePdfTarget);
        if (notePdfUrl) return notePdfUrl;
      }
      const noteDir = path.dirname(noteAbs);
      if (!fs.existsSync(noteDir)) continue;
      let entries = [];
      try {
        entries = fs.readdirSync(noteDir, { withFileTypes: true });
      } catch {
        continue;
      }
      const siblingPdfs = entries
        .filter((entry) => entry?.isFile?.() && /\.pdf$/i.test(String(entry.name || '')))
        .map((entry) => String(entry.name || '').trim())
        .filter(Boolean)
        .sort((a, b) => a.localeCompare(b));
      if (!siblingPdfs.length) continue;

      const preferredStem = path.basename(noteBase).toLowerCase();
      const exact = siblingPdfs.find((name) => path.basename(name, path.extname(name)).toLowerCase() === preferredStem);
      const chosen = exact || siblingPdfs[0];
      if (!chosen) continue;
      const pdfAbs = path.resolve(noteDir, chosen);
      if (fs.existsSync(pdfAbs)) {
        return pathToFileURL(pdfAbs).toString();
      }
    }
  }

  const caseIdCandidates = Array.from(
    new Set(
      [String(node?.caseId || '').trim(), String(node?.id || '').trim()]
        .map((value) => normalizeCaseIdLookup(value))
        .filter(Boolean)
    )
  );
  if (caseIdCandidates.length) {
    for (const vaultRoot of sourceVaultRoots) {
      const index = getCasePdfIndexForVault(vaultRoot);
      for (const candidate of caseIdCandidates) {
        const indexedPath = index.get(candidate);
        const indexedUrl = pdfTargetToUrl(indexedPath);
        if (indexedUrl) return indexedUrl;
      }
    }
  }

  return '';
}

function setOntologyCaseSidebarOpen(open) {
  const isOpen = Boolean(open);
  if (els.ontologyCaseSidebar) {
    els.ontologyCaseSidebar.classList.toggle('open', isOpen);
  }
  if (els.ontologyGraphBody) {
    els.ontologyGraphBody.classList.toggle('case-sidebar-open', isOpen);
  }
}

async function openOntologyCaseSidebar(node) {
  if (!node || !isCaseOntologyNode(node)) return;
  closeOntologyCaseSidebar(true);
  const label = ontologyCaseLabel(node);
  const pdfUrl = await resolveOntologyCasePdfUrl(node);
  if (!pdfUrl) {
    window.alert('No linked PDF is available for this case node.');
    return;
  }

  let absolutePdfPath = '';
  if (/^file:\/\//i.test(pdfUrl)) {
    try {
      absolutePdfPath = fileURLToPath(pdfUrl);
    } catch {
      absolutePdfPath = '';
    }
  }

  const currentVaultRoot = path.resolve(String(state.vaultRoot || '').trim());
  if (absolutePdfPath && currentVaultRoot) {
    const resolvedPdfPath = path.resolve(absolutePdfPath);
    const insideCurrentVault =
      resolvedPdfPath === currentVaultRoot ||
      resolvedPdfPath.startsWith(`${currentVaultRoot}${path.sep}`);
    if (insideCurrentVault) {
      const relPath = path.relative(currentVaultRoot, resolvedPdfPath).replaceAll('\\', '/');
      if (relPath && !relPath.startsWith('..')) {
        const existingVaultPdfTab = state.openTabs.find(
          (tab) => tab.kind === 'pdf' && (tab.path === relPath || tab.sourcePath === relPath)
        );
        if (existingVaultPdfTab) {
          activateTab(existingVaultPdfTab.id);
          return;
        }
        const created = await buildTabForPath(relPath);
        state.openTabs.push(created);
        activateTab(created.id);
        return;
      }
    }
  }

  const caseKey = String(node.path || node.pdfPath || node.opinionUrl || node.id || label).trim();
  const existing = state.openTabs.find(
    (tab) => tab.kind === 'pdf' && String(tab.ontologyCaseKey || '') === caseKey
  );
  if (existing) {
    activateTab(existing.id);
    return;
  }

  const tabTitle = label.toLowerCase().endsWith('.pdf') ? label : `${label}.pdf`;
  state.openTabs.push({
    id: state.nextTabId++,
    kind: 'pdf',
    title: tabTitle,
    path: null,
    url: pdfUrl,
    sourcePath: node.path || null,
    ontologyCaseKey: caseKey
  });
  activateTab(state.openTabs[state.openTabs.length - 1].id);
}

function closeOntologyCaseSidebar(clearFrame = true) {
  if (!els.ontologyCaseSidebar) return;
  setOntologyCaseSidebarOpen(false);
  state.ontologyCaseSidebarNodeId = '';
  if (clearFrame && els.ontologyCasePdfFrame) {
    els.ontologyCasePdfFrame.src = '';
    els.ontologyCasePdfFrame.classList.add('hidden');
  }
}

function showOntologyCaseHoverCard(node, pointer = { x: 0, y: 0 }) {
  if (!els.ontologyCaseHoverCard || !node || !isCaseOntologyNode(node)) {
    hideOntologyCaseHoverCard(true);
    return;
  }
  clearOntologyHoverHideTimer();
  const nodeId = String(node.id || '');
  const shouldReuseContent = els.ontologyCaseHoverCard.dataset.nodeId === nodeId;
  if (shouldReuseContent) {
    els.ontologyCaseHoverCard.classList.remove('hidden');
    positionOntologyCaseHoverCard(pointer);
    return;
  }
  els.ontologyCaseHoverCard.innerHTML = '';
  els.ontologyCaseHoverCard.dataset.nodeId = nodeId;

  const title = document.createElement('div');
  title.className = 'ontology-case-hover-title';
  title.textContent = ontologyCaseLabel(node);

  const citation = ontologyCaseCitation(node);
  const citationRow = document.createElement('div');
  citationRow.className = 'ontology-case-hover-row';
  citationRow.textContent = citation ? `Citation: ${citation}` : 'Citation: unavailable';

  const holding = document.createElement('div');
  holding.className = 'ontology-case-hover-row';
  holding.textContent = `Essential holding: ${ontologyCaseEssentialHolding(node) || 'Not extracted yet.'}`;

  const summary = document.createElement('div');
  summary.className = 'ontology-case-hover-row';
  summary.textContent = `Summary: ${ontologyCaseSummary(node)}`;

  const domain = document.createElement('div');
  domain.className = 'ontology-case-hover-row';
  domain.textContent = `Case domain: ${ontologyCaseDomain(node)}`;

  const actions = document.createElement('div');
  actions.className = 'ontology-case-hover-actions';

  const openPdfBtn = document.createElement('button');
  openPdfBtn.type = 'button';
  openPdfBtn.textContent = 'Open PDF';
  openPdfBtn.onclick = async () => {
    await openOntologyCaseSidebar(node);
  };

  const openNoteBtn = document.createElement('button');
  openNoteBtn.type = 'button';
  openNoteBtn.textContent = 'Open Note';
  openNoteBtn.onclick = async () => {
    if (node.path) {
      await openFile(node.path);
    }
  };

  actions.appendChild(openPdfBtn);
  actions.appendChild(openNoteBtn);

  els.ontologyCaseHoverCard.appendChild(title);
  els.ontologyCaseHoverCard.appendChild(citationRow);
  els.ontologyCaseHoverCard.appendChild(holding);
  els.ontologyCaseHoverCard.appendChild(summary);
  els.ontologyCaseHoverCard.appendChild(domain);
  els.ontologyCaseHoverCard.appendChild(actions);
  els.ontologyCaseHoverCard.classList.remove('hidden');
  positionOntologyCaseHoverCard(pointer);
}

function courtLevelBucket(value) {
  const raw = String(value || '').toLowerCase();
  if (!raw) return '';
  if (raw.includes('supreme') || raw === 'scotus') return 'supreme';
  if (raw.includes('district')) return 'district';
  if (raw.includes('circuit') || /^ca\d{1,2}$/.test(raw)) return 'circuit';
  return raw;
}

function normalizeOntologyCaseDomain(value) {
  const raw = String(value || '')
    .trim()
    .toLowerCase();
  if (!raw) return 'civil';
  if (raw === 'criminal' || raw === 'crim' || raw.includes('criminal')) return 'criminal';
  if (raw === 'civil' || raw === 'civ' || raw.includes('civil')) return 'civil';
  return 'civil';
}

function normalizeOriginatingCircuit(value) {
  const raw = String(value || '')
    .trim()
    .toLowerCase();
  if (!raw) return '';
  if (ONTOLOGY_CIRCUIT_LABELS[raw]) return raw;

  const compact = raw.replace(/[^a-z0-9]+/g, '');
  if (ONTOLOGY_CIRCUIT_LABELS[compact]) return compact;
  if (compact === 'dc' || compact === 'dccircuit' || compact === 'districtofcolumbia') return 'cadc';
  if (/^ca(?:[1-9]|10|11)$/.test(compact)) return compact;
  if (/^(?:[1-9]|10|11)(?:st|nd|rd|th)?$/.test(compact)) {
    const n = compact.match(/^([1-9]|10|11)/);
    if (n && ONTOLOGY_CIRCUIT_LABELS[`ca${n[1]}`]) return `ca${n[1]}`;
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
  if (raw.includes('district of columbia')) return 'cadc';
  if (raw.includes('first')) return 'ca1';
  if (raw.includes('second')) return 'ca2';
  if (raw.includes('third')) return 'ca3';
  if (raw.includes('fourth')) return 'ca4';
  if (raw.includes('fifth')) return 'ca5';
  if (raw.includes('sixth')) return 'ca6';
  if (raw.includes('seventh')) return 'ca7';
  if (raw.includes('eighth')) return 'ca8';
  if (raw.includes('ninth')) return 'ca9';
  if (raw.includes('tenth')) return 'ca10';
  if (raw.includes('eleventh')) return 'ca11';
  return '';
}

function clamp01(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(1, numeric));
}

function normalizeOntologyPreset(value = '') {
  const preset = String(value || '').trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(ONTOLOGY_VIEW_PRESET_PROFILES, preset)) return preset;
  return ONTOLOGY_FILTER_DEFAULTS.viewPreset;
}

function getOntologyPresetProfile(value = '') {
  const preset = normalizeOntologyPreset(value);
  return ONTOLOGY_VIEW_PRESET_PROFILES[preset] || ONTOLOGY_VIEW_PRESET_PROFILES.core_precedent;
}

function applyOntologyPresetSelection(value = '', syncControls = true) {
  const preset = normalizeOntologyPreset(value);
  const profile = getOntologyPresetProfile(preset);
  state.ontologyFilter.viewPreset = preset;
  if (!syncControls) return preset;
  if (els.ontologyViewPreset) els.ontologyViewPreset.value = preset;
  if (preset === 'full_ontology') {
    if (els.ontologyMinEdgeStrength) els.ontologyMinEdgeStrength.value = '';
    if (els.ontologyMinCaseImportance) els.ontologyMinCaseImportance.value = '';
    if (els.ontologyMaxEdgesPerNode) els.ontologyMaxEdgesPerNode.value = '';
  } else {
    if (els.ontologyMinEdgeStrength) els.ontologyMinEdgeStrength.value = String(profile.minEdgeStrength);
    if (els.ontologyMinCaseImportance) els.ontologyMinCaseImportance.value = String(profile.minCaseImportance);
    if (els.ontologyMaxEdgesPerNode) els.ontologyMaxEdgesPerNode.value = String(profile.maxEdgesPerNode);
  }
  return preset;
}

function setOntologySampleNotice(details = {}) {
  if (!els.ontologySampleNotice) return;
  const active = Boolean(details.active);
  if (!active) {
    els.ontologySampleNotice.textContent = '';
    els.ontologySampleNotice.classList.add('hidden');
    return;
  }
  const shown = Math.max(0, Number(details.shown || 0));
  const total = Math.max(0, Number(details.total || 0));
  const limit = Math.max(1, Number(details.limit || ONTOLOGY_REPRESENTATIVE_CASE_LIMIT));
  els.ontologySampleNotice.textContent =
    `Showing representative sample of ${shown} of ${total} cases (cap ${limit}). ` +
    'Use filters/preset controls to narrow to 2,500 or fewer cases for complete rendering.';
  els.ontologySampleNotice.classList.remove('hidden');
}

function ontologyEdgeAllowedByPreset(edge, presetValue = '') {
  const preset = normalizeOntologyPreset(presetValue);
  const edgeType = String(edge?.edgeType || '').trim().toLowerCase();
  if (!edgeType) return false;
  const allowed = new Set([
    'case_citation',
    'constitution_citation',
    'taxonomy_edge',
    'usc_title_citation',
    'cfr_title_citation'
  ]);
  if (!allowed.has(edgeType)) return false;
  if (preset === 'constitutional') {
    return edgeType === 'case_citation' || edgeType === 'constitution_citation' || edgeType === 'taxonomy_edge';
  }
  if (preset === 'statutory_regulatory') {
    return (
      edgeType === 'case_citation' ||
      edgeType === 'usc_title_citation' ||
      edgeType === 'cfr_title_citation' ||
      edgeType === 'taxonomy_edge'
    );
  }
  return true;
}

function ontologyEdgeStrength(edge) {
  const edgeType = String(edge?.edgeType || '').trim().toLowerCase();
  const citationType = String(edge?.citationType || '').trim().toLowerCase();
  const baseByEdgeType = {
    constitution_citation: 1.0,
    case_citation: 0.88,
    taxonomy_edge: 0.76,
    usc_title_citation: 0.84,
    cfr_title_citation: 0.8
  };
  const base = baseByEdgeType[edgeType] ?? 0.58;
  const confidence = Number(edge?.confidence);
  let score = Number.isFinite(confidence) ? (base * 0.7 + clamp01(confidence) * 0.3) : base;
  if (citationType === 'controlling') score += 0.03;
  if (citationType === 'background') score -= 0.06;
  return clamp01(score);
}

function ontologyCaseImportance(node, degreeValue = 0) {
  if (String(node?.nodeType || '').toLowerCase() !== 'case') return 0;
  const degreeNorm = Math.max(0, Math.min(1, Math.log2(Math.max(0, Number(degreeValue)) + 1) / 6));
  const pfRaw = Number(node?.pfHolding ?? node?.pfIssue);
  const pfNorm = Number.isFinite(pfRaw) ? clamp01(pfRaw) : 0;
  const courtLevel = String(node?.courtLevel || '').toLowerCase();
  const courtNorm = courtLevel === 'supreme' ? 1 : courtLevel === 'circuit' ? 0.78 : courtLevel === 'district' ? 0.58 : 0.5;
  const contentNorm = String(node?.essentialHolding || node?.caseSummary || '').trim() ? 1 : 0;
  return clamp01(degreeNorm * 0.6 + pfNorm * 0.2 + courtNorm * 0.15 + contentNorm * 0.05);
}

function limitEdgesByNodeBudget(edgeRows = [], maxEdgesPerNode = 0, importanceById = new Map()) {
  const budget = Math.max(1, Number(maxEdgesPerNode) || 0);
  if (!edgeRows.length || !Number.isFinite(budget) || budget < 1) return edgeRows;
  const byNode = new Map();
  const ensureBucket = (nodeId) => {
    if (!byNode.has(nodeId)) byNode.set(nodeId, []);
    return byNode.get(nodeId);
  };

  for (const row of edgeRows) {
    ensureBucket(row.source).push(row);
    ensureBucket(row.target).push(row);
  }

  const keepKeys = new Set();
  for (const [nodeId, bucket] of byNode.entries()) {
    const importance = clamp01(importanceById instanceof Map ? importanceById.get(nodeId) : 0);
    let dynamicBudget = budget;
    if (importance >= 0.78) dynamicBudget = Math.max(budget, Math.round(budget * 4));
    else if (importance >= 0.58) dynamicBudget = Math.max(budget, Math.round(budget * 2.5));
    else if (importance >= 0.38) dynamicBudget = Math.max(budget, Math.round(budget * 1.5));

    bucket
      .slice()
      .sort((left, right) => {
        const strengthDelta = Number(right?.strength || 0) - Number(left?.strength || 0);
        if (strengthDelta) return strengthDelta;
        return String(left?.key || '').localeCompare(String(right?.key || ''));
      })
      .slice(0, dynamicBudget)
      .forEach((row) => keepKeys.add(row.key));
  }
  return edgeRows.filter((row) => keepKeys.has(row.key));
}

function buildRepresentativeCaseSample(caseNodes = [], limit = ONTOLOGY_REPRESENTATIVE_CASE_LIMIT, importanceById = new Map()) {
  const maxCount = Math.max(1, Number(limit) || ONTOLOGY_REPRESENTATIVE_CASE_LIMIT);
  if (caseNodes.length <= maxCount) return caseNodes.slice();
  return caseNodes
    .slice()
    .sort((left, right) => {
      const leftImportance = Number(importanceById.get(left?.id) || 0);
      const rightImportance = Number(importanceById.get(right?.id) || 0);
      const importanceDelta = rightImportance - leftImportance;
      if (importanceDelta) return importanceDelta;
      return String(left?.id || '').localeCompare(String(right?.id || ''));
    })
    .slice(0, maxCount);
}

function ontologyLayerForNode(node = {}) {
  const nodeType = String(node?.nodeType || '').toLowerCase();
  if (nodeType === 'constitution') return 0;
  if (nodeType === 'statute' || nodeType === 'regulation') return 0.2;
  if (nodeType === 'taxonomy') return 0.45;
  if (nodeType === 'source' || nodeType === 'secondary') return 0.6;
  if (nodeType === 'issue') return 1;
  if (nodeType === 'event') return 1.6;
  if (nodeType === 'holding') return 2;
  if (nodeType === 'relation') return 2.5;
  if (nodeType === 'case' || nodeType === 'external_case') return 3;
  return 2.4;
}

function ontologyCommunityFromNeighbor(node = {}, neighbor = {}) {
  const neighborType = String(neighbor?.nodeType || '').toLowerCase();
  if (neighborType === 'constitution') return `constitution:${neighbor.id}`;
  if (neighborType === 'statute') return `statute:${neighbor.id}`;
  if (neighborType === 'regulation') return `regulation:${neighbor.id}`;
  if (neighborType === 'taxonomy') return `taxonomy:${neighbor.id}`;
  if (neighborType === 'source' || neighborType === 'secondary') return `source:${neighbor.id}`;
  if (neighborType === 'issue') return `issue:${neighbor.id}`;
  if (neighborType === 'holding') return `holding:${neighbor.id}`;
  if (neighborType === 'case') return `case:${neighbor.id}`;
  return '';
}

function buildCaseUnionComponents(caseIds = [], edgeRows = [], threshold = 0.72) {
  const parent = new Map();
  const find = (id) => {
    const key = String(id || '').trim();
    if (!key) return '';
    if (!parent.has(key)) parent.set(key, key);
    let root = key;
    while (parent.get(root) !== root) root = parent.get(root);
    let node = key;
    while (parent.get(node) !== root) {
      const next = parent.get(node);
      parent.set(node, root);
      node = next;
    }
    return root;
  };
  const union = (left, right) => {
    const a = find(left);
    const b = find(right);
    if (!a || !b || a === b) return;
    if (a.localeCompare(b) <= 0) parent.set(b, a);
    else parent.set(a, b);
  };

  for (const caseId of caseIds) find(caseId);
  for (const row of edgeRows) {
    const source = String(row?.source || '').trim();
    const target = String(row?.target || '').trim();
    if (!source || !target || source === target) continue;
    if (!parent.has(source) || !parent.has(target)) continue;
    if (Number(row?.strength || 0) < threshold) continue;
    union(source, target);
  }

  const componentByCase = new Map();
  for (const caseId of caseIds) {
    const root = find(caseId);
    componentByCase.set(caseId, root ? `component:${root}` : `component:${caseId}`);
  }
  return componentByCase;
}

function buildOntologyNativeLayout(nodes = [], edgeRows = [], caseImportanceById = new Map(), degreeById = new Map()) {
  const nodeById = new Map();
  for (const node of nodes) {
    const nodeId = String(node?.id || '').trim();
    if (!nodeId) continue;
    nodeById.set(nodeId, node);
  }

  const adjacency = new Map();
  const addAdjacency = (left, right, row) => {
    if (!adjacency.has(left)) adjacency.set(left, []);
    adjacency.get(left).push({ neighborId: right, row });
  };
  for (const row of edgeRows) {
    const source = String(row?.source || '').trim();
    const target = String(row?.target || '').trim();
    if (!nodeById.has(source) || !nodeById.has(target) || source === target) continue;
    addAdjacency(source, target, row);
    addAdjacency(target, source, row);
  }

  const caseIds = Array.from(nodeById.values())
    .filter((node) => String(node?.nodeType || '').toLowerCase() === 'case')
    .map((node) => String(node.id || '').trim())
    .filter(Boolean);
  const caseComponents = buildCaseUnionComponents(caseIds, edgeRows, 0.72);

  const communityById = new Map();
  for (const node of nodeById.values()) {
    const nodeId = String(node.id || '').trim();
    const nodeType = String(node.nodeType || '').toLowerCase();
    if (!nodeId) continue;
    if (nodeType === 'constitution') {
      communityById.set(nodeId, `constitution:${nodeId}`);
      continue;
    }
    if (nodeType === 'source' || nodeType === 'secondary') {
      communityById.set(nodeId, `source:${nodeId}`);
      continue;
    }
    if (nodeType === 'issue') {
      communityById.set(nodeId, `issue:${nodeId}`);
      continue;
    }
    if (nodeType === 'holding') {
      communityById.set(nodeId, `holding:${nodeId}`);
      continue;
    }
    if (nodeType === 'case') {
      const neighborScores = new Map();
      for (const item of adjacency.get(nodeId) || []) {
        const neighbor = nodeById.get(item.neighborId);
        if (!neighbor) continue;
        const key = ontologyCommunityFromNeighbor(node, neighbor);
        if (!key) continue;
        const weight = Number(item?.row?.strength || 0);
        const neighborNodeType = String(neighbor.nodeType || '').toLowerCase();
        const nodeTypeBonus =
          neighborNodeType === 'constitution'
            ? 1.32
            : neighborNodeType === 'source'
              ? 1.25
              : neighborNodeType === 'issue'
                ? 1.08
                : neighborNodeType === 'holding'
                  ? 1.0
                  : 0.94;
        neighborScores.set(key, (neighborScores.get(key) || 0) + weight * nodeTypeBonus);
      }
      if (neighborScores.size) {
        const best = Array.from(neighborScores.entries()).sort((left, right) => {
          const scoreDelta = Number(right[1] || 0) - Number(left[1] || 0);
          if (scoreDelta) return scoreDelta;
          return String(left[0]).localeCompare(String(right[0]));
        })[0];
        communityById.set(nodeId, best?.[0] || `case:${nodeId}`);
      } else {
        communityById.set(nodeId, caseComponents.get(nodeId) || `case:${nodeId}`);
      }
      continue;
    }

    const linked = (adjacency.get(nodeId) || [])
      .map((item) => ({ key: communityById.get(item.neighborId) || '', score: Number(item?.row?.strength || 0) }))
      .filter((item) => item.key);
    if (linked.length) {
      linked.sort((left, right) => {
        const scoreDelta = right.score - left.score;
        if (scoreDelta) return scoreDelta;
        return String(left.key).localeCompare(String(right.key));
      });
      communityById.set(nodeId, linked[0].key);
    } else {
      communityById.set(nodeId, `misc:${nodeId}`);
    }
  }

  const clusters = new Map();
  for (const node of nodeById.values()) {
    const nodeId = String(node.id || '').trim();
    const key = communityById.get(nodeId) || `misc:${nodeId}`;
    if (!clusters.has(key)) clusters.set(key, []);
    clusters.get(key).push(node);
  }

  const clusterMetrics = Array.from(clusters.entries()).map(([key, members]) => {
    let score = 0;
    for (const node of members) {
      const nodeId = String(node?.id || '').trim();
      const nodeType = String(node?.nodeType || '').toLowerCase();
      const degree = Number(degreeById.get(nodeId) || 0);
      if (nodeType === 'case') score += Number(caseImportanceById.get(nodeId) || 0) * 8 + Math.log2(degree + 1);
      else if (nodeType === 'constitution' || nodeType === 'source' || nodeType === 'issue' || nodeType === 'holding') {
        score += 1.2 + Math.log2(degree + 1) * 0.5;
      }
      else score += 0.5;
    }
    return { key, members, score };
  });
  clusterMetrics.sort((left, right) => {
    const scoreDelta = right.score - left.score;
    if (scoreDelta) return scoreDelta;
    return String(left.key).localeCompare(String(right.key));
  });

  const clusterWidth = (members = []) => {
    const count = Math.max(1, Number(members.length || 0));
    return Math.max(320, Math.min(1300, Math.ceil(Math.sqrt(count)) * 180));
  };

  const hashString = (value = '') => {
    let hash = 2166136261;
    const text = String(value || '');
    for (let idx = 0; idx < text.length; idx += 1) {
      hash ^= text.charCodeAt(idx);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  };
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));

  // Deterministic organic packing: avoids rigid row/column appearance while staying reproducible.
  const widths = clusterMetrics.map((item) => clusterWidth(item.members));
  const avgWidth = widths.length
    ? widths.reduce((acc, value) => acc + Number(value || 0), 0) / widths.length
    : 520;
  const relaxedRadialStep = Math.max(560, Math.min(1460, Math.round(avgWidth * 0.96)));
  const aspectX = 1.24;
  const aspectY = 0.93;

  const clusterCenterByKey = new Map();
  for (let idx = 0; idx < clusterMetrics.length; idx += 1) {
    const cluster = clusterMetrics[idx];
    const hash = hashString(cluster.key);
    const jitter = (((hash % 360) * Math.PI) / 180) * 0.08;
    const angle = idx * goldenAngle + jitter;
    const radius = relaxedRadialStep * Math.sqrt(idx + 0.85);
    const centerX = Math.cos(angle) * radius * aspectX;
    const centerY = Math.sin(angle) * radius * aspectY;
    clusterCenterByKey.set(cluster.key, { x: centerX, y: centerY });
  }

  const layerBaseY = new Map([
    [0, -780],
    [1, -260],
    [1.6, 80],
    [2, 350],
    [2.5, 560],
    [3, 860]
  ]);

  const positionById = new Map();
  for (const cluster of clusterMetrics) {
    const center = clusterCenterByKey.get(cluster.key) || { x: 0, y: 0 };
    const centerX = Number(center.x || 0);
    const centerY = Number(center.y || 0);
    const byLayer = new Map();
    for (const node of cluster.members) {
      const layer = ontologyLayerForNode(node);
      if (!byLayer.has(layer)) byLayer.set(layer, []);
      byLayer.get(layer).push(node);
    }

    for (const [layer, layerNodes] of byLayer.entries()) {
      layerNodes.sort((left, right) => {
        const leftType = String(left?.nodeType || '').toLowerCase();
        const rightType = String(right?.nodeType || '').toLowerCase();
        if (leftType === 'case' && rightType === 'case') {
          const importanceDelta = Number(caseImportanceById.get(right.id) || 0) - Number(caseImportanceById.get(left.id) || 0);
          if (importanceDelta) return importanceDelta;
        }
        const yearLeft = parseInt(String(left?.decisionYear || ''), 10);
        const yearRight = parseInt(String(right?.decisionYear || ''), 10);
        if (Number.isFinite(yearLeft) && Number.isFinite(yearRight) && yearLeft !== yearRight) return yearLeft - yearRight;
        return String(left?.id || '').localeCompare(String(right?.id || ''));
      });

      const count = layerNodes.length;
      const spreadBase = layer >= 3 ? 62 : 78;
      const crowdingScale = Math.max(1, Math.min(2.15, Math.sqrt(Math.max(1, count)) / 2.35));
      const spread = spreadBase * crowdingScale;
      const baseY = Number(layerBaseY.get(layer) || 220) + centerY;
      for (let idx = 0; idx < layerNodes.length; idx += 1) {
        const node = layerNodes[idx];
        const nodeHash = hashString(`${cluster.key}|${String(layer)}|${String(node.id || '')}`);
        const jitter = ((nodeHash % 1000) / 1000) - 0.5;
        const angle = idx * goldenAngle + ((nodeHash % 628) / 100);
        const radius = spread * Math.sqrt(idx + 1.1) * (0.92 + ((nodeHash >>> 8) % 35) / 95);
        const x = centerX + Math.cos(angle) * radius * (1.04 + jitter * 0.2);
        const y = baseY + Math.sin(angle) * radius * (0.9 + jitter * 0.18);
        positionById.set(String(node.id || ''), { x, y });
      }
    }
  }

  return {
    positionById,
    communityById
  };
}

function captureOntologyFiltersFromUI() {
  const preset = normalizeOntologyPreset(String(els.ontologyViewPreset?.value || ONTOLOGY_FILTER_DEFAULTS.viewPreset));
  const profile = getOntologyPresetProfile(preset);
  const minEdgeStrengthRaw = parseNumberInput(els.ontologyMinEdgeStrength?.value);
  const minCaseImportanceRaw = parseNumberInput(els.ontologyMinCaseImportance?.value);
  const maxEdgesPerNodeRaw = parseNumberInput(els.ontologyMaxEdgesPerNode?.value);
  const unconstrainedPreset = preset === 'full_ontology';
  const resolvedMinEdgeStrength =
    minEdgeStrengthRaw === null ? (unconstrainedPreset ? null : clamp01(profile.minEdgeStrength)) : clamp01(minEdgeStrengthRaw);
  const resolvedMinCaseImportance =
    minCaseImportanceRaw === null ? (unconstrainedPreset ? null : clamp01(profile.minCaseImportance)) : clamp01(minCaseImportanceRaw);
  const resolvedMaxEdgesPerNode =
    maxEdgesPerNodeRaw === null
      ? (unconstrainedPreset ? null : Math.max(1, Math.min(250, Number(profile.maxEdgesPerNode) || 1)))
      : Math.max(1, Math.min(250, Math.round(maxEdgesPerNodeRaw)));
  state.ontologyFilter = {
    viewPreset: preset,
    query: String(els.ontologyGraphSearch?.value || '').trim(),
    nodeTypes: checkedValuesFrom(els.ontologyNodeTypes),
    relationTypes: checkedValuesFrom(els.ontologyRelationTypes),
    citationType: String(els.ontologyCitationType?.value || 'all'),
    caseDomain: String(els.ontologyCaseDomain?.value || 'all'),
    courtLevel: String(els.ontologyCourtLevel?.value || 'all'),
    originatingCircuit: String(els.ontologyOriginatingCircuit?.value || 'all'),
    normativeStrength: String(els.ontologyNormativeStrength?.value || 'all'),
    factDimension: String(els.ontologyFactDimension?.value || '').trim().toLowerCase(),
    minEdgeStrength: resolvedMinEdgeStrength,
    minCaseImportance: resolvedMinCaseImportance,
    maxEdgesPerNode: resolvedMaxEdgesPerNode,
    pfMin: parseNumberInput(els.ontologyPfMin?.value),
    consensusMin: parseNumberInput(els.ontologyConsensusMin?.value),
    driftMax: parseNumberInput(els.ontologyDriftMax?.value),
    relationConfidenceMin: parseNumberInput(els.ontologyRelationConfidenceMin?.value),
    maxNodes: Math.max(
      100,
      Math.min(
        20000,
        parseInt(String(els.ontologyMaxNodes?.value || String(ONTOLOGY_FILTER_DEFAULTS.maxNodes || 20000)), 10) ||
          Number(ONTOLOGY_FILTER_DEFAULTS.maxNodes || 20000)
      )
    )
  };
}

function applyOntologyFilterDefaults() {
  state.ontologyFilter = { ...ONTOLOGY_FILTER_DEFAULTS };
  if (els.ontologyViewPreset) els.ontologyViewPreset.value = ONTOLOGY_FILTER_DEFAULTS.viewPreset;
  if (els.ontologyGraphSearch) els.ontologyGraphSearch.value = ONTOLOGY_FILTER_DEFAULTS.query;
  if (els.ontologyNodeTypes) {
    Array.from(els.ontologyNodeTypes.querySelectorAll('input[type="checkbox"]')).forEach((input) => {
      input.checked = ONTOLOGY_FILTER_DEFAULTS.nodeTypes.includes(input.value);
    });
  }
  if (els.ontologyRelationTypes) {
    Array.from(els.ontologyRelationTypes.querySelectorAll('input[type="checkbox"]')).forEach((input) => {
      input.checked = ONTOLOGY_FILTER_DEFAULTS.relationTypes.includes(input.value);
    });
  }
  if (els.ontologyCitationType) els.ontologyCitationType.value = ONTOLOGY_FILTER_DEFAULTS.citationType;
  if (els.ontologyCaseDomain) els.ontologyCaseDomain.value = ONTOLOGY_FILTER_DEFAULTS.caseDomain;
  if (els.ontologyCourtLevel) els.ontologyCourtLevel.value = ONTOLOGY_FILTER_DEFAULTS.courtLevel;
  if (els.ontologyOriginatingCircuit) els.ontologyOriginatingCircuit.value = ONTOLOGY_FILTER_DEFAULTS.originatingCircuit;
  if (els.ontologyNormativeStrength) els.ontologyNormativeStrength.value = ONTOLOGY_FILTER_DEFAULTS.normativeStrength;
  if (els.ontologyFactDimension) els.ontologyFactDimension.value = '';
  if (els.ontologyMinEdgeStrength) els.ontologyMinEdgeStrength.value = ONTOLOGY_FILTER_DEFAULTS.minEdgeStrength === null ? '' : String(ONTOLOGY_FILTER_DEFAULTS.minEdgeStrength);
  if (els.ontologyMinCaseImportance) els.ontologyMinCaseImportance.value = ONTOLOGY_FILTER_DEFAULTS.minCaseImportance === null ? '' : String(ONTOLOGY_FILTER_DEFAULTS.minCaseImportance);
  if (els.ontologyMaxEdgesPerNode) els.ontologyMaxEdgesPerNode.value = ONTOLOGY_FILTER_DEFAULTS.maxEdgesPerNode === null ? '' : String(ONTOLOGY_FILTER_DEFAULTS.maxEdgesPerNode);
  if (els.ontologyPfMin) els.ontologyPfMin.value = '';
  if (els.ontologyConsensusMin) els.ontologyConsensusMin.value = '';
  if (els.ontologyDriftMax) els.ontologyDriftMax.value = '';
  if (els.ontologyRelationConfidenceMin) els.ontologyRelationConfidenceMin.value = '';
  if (els.ontologyMaxNodes) els.ontologyMaxNodes.value = String(ONTOLOGY_FILTER_DEFAULTS.maxNodes);
}

function nodePassesOntologyFilters(node, filters) {
  const nodeType = String(node.nodeType || 'unknown').toLowerCase();
  if (filters.nodeTypes.length && !filters.nodeTypes.includes(nodeType)) return false;

  if (filters.query) {
    const haystack = String(node.searchText || '').toLowerCase();
    const queryTokens = filters.query.toLowerCase().split(/\s+/).filter(Boolean);
    for (const token of queryTokens) {
      if (!haystack.includes(token)) return false;
    }
  }

  if (filters.courtLevel !== 'all') {
    const bucket = courtLevelBucket(node.courtLevel || node.court || '');
    if (bucket !== filters.courtLevel) return false;
  }

  if ((filters.caseDomain || 'all') !== 'all') {
    if (nodeType === 'case' || nodeType === 'external_case') {
      const nodeCaseDomain = normalizeOntologyCaseDomain(node.caseDomain || node.caseType || node.domain || '');
      if (nodeCaseDomain !== filters.caseDomain) return false;
    }
  }

  if ((filters.originatingCircuit || 'all') !== 'all') {
    const nodeCircuit = normalizeOriginatingCircuit(node.originatingCircuit || node.originatingCircuitLabel || '');
    if (nodeCircuit !== filters.originatingCircuit) return false;
  }

  if (filters.normativeStrength !== 'all') {
    const strength = String(node.normativeStrength || '').toLowerCase();
    if (nodeType === 'holding' && strength !== filters.normativeStrength) return false;
  }

  if (filters.factDimension) {
    const dimensions = Array.isArray(node.factDimensions) ? node.factDimensions : [];
    const normalized = dimensions.map((item) => String(item || '').toLowerCase());
    if (!normalized.some((item) => item.includes(filters.factDimension))) return false;
  }

  if (filters.pfMin !== null) {
    const pf = node.pfHolding ?? node.pfIssue;
    if (pf !== null && pf !== undefined) {
      if (Number(pf) < filters.pfMin) return false;
    }
  }

  if (filters.consensusMin !== null && nodeType === 'issue') {
    if (node.consensus === null || node.consensus === undefined || Number(node.consensus) < filters.consensusMin) {
      return false;
    }
  }

  if (filters.driftMax !== null && nodeType === 'issue') {
    if (node.drift === null || node.drift === undefined || Number(node.drift) > filters.driftMax) {
      return false;
    }
  }

  return true;
}

function canonicalOntologyRelationTypeFromEdge(edge) {
  const direct = String(edge?.relationType || '').trim().toLowerCase();
  if (ONTOLOGY_RELATION_TYPES.includes(direct)) return direct;

  const interpretive = String(edge?.interpretiveEdgeType || '').trim().toUpperCase();
  if (!interpretive) return '';
  if (
    interpretive.startsWith('APPLIES_') ||
    interpretive === 'APPLIES_PLAIN_MEANING' ||
    interpretive === 'APPLIES_LENITY' ||
    interpretive === 'APPLIES_CONSTITUTIONAL_AVOIDANCE'
  ) {
    return 'applies';
  }
  if (interpretive.startsWith('CLARIFIES_') || interpretive.startsWith('EXPLAINS_')) return 'clarifies';
  if (
    interpretive.startsWith('INTERPRETS_') ||
    interpretive.startsWith('RESOLVES_') ||
    interpretive.startsWith('USES_') ||
    interpretive.startsWith('FINDS_STATUTE_AMBIGUOUS')
  ) {
    return 'clarifies';
  }
  if (interpretive.startsWith('EXTENDS_') || interpretive.startsWith('BROADENS_') || interpretive.startsWith('RECOGNIZES_')) {
    return 'extends';
  }
  if (interpretive.startsWith('DISTINGUISHES_')) return 'distinguishes';
  if (
    interpretive.startsWith('NARROWS_') ||
    interpretive.startsWith('LIMITS_') ||
    interpretive.startsWith('REJECTS_') ||
    interpretive.startsWith('CONSTRUES_')
  ) {
    return 'limits';
  }
  if (interpretive.startsWith('OVERRULES_') || interpretive.startsWith('INVALIDATES_')) return 'overrules';
  if (interpretive.startsWith('QUESTIONS_') || interpretive.startsWith('FINDS_')) return 'questions';
  return '';
}

function edgePassesOntologyFilters(edge, filters, nodeLookup) {
  if (!edge) return false;
  if (!nodeLookup.has(edge.source) || !nodeLookup.has(edge.target)) return false;

  const selectedRelationTypes = Array.isArray(filters?.relationTypes)
    ? filters.relationTypes.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : [];
  const relationFilterActive =
    selectedRelationTypes.length !== ONTOLOGY_RELATION_TYPES.length;
  const edgeType = String(edge?.edgeType || '').trim().toLowerCase();
  const relationRelevant =
    edgeType.startsWith('relation_') ||
    edgeType === 'precedent_relation' ||
    edgeType === 'relation_effect' ||
    Boolean(edge?.relationType || edge?.interpretiveEdgeType);
  const canonicalRelationType = canonicalOntologyRelationTypeFromEdge(edge);
  if (relationFilterActive && relationRelevant) {
    if (!canonicalRelationType) return false;
    if (!selectedRelationTypes.includes(canonicalRelationType)) return false;
  } else if (relationRelevant && canonicalRelationType && selectedRelationTypes.length && !selectedRelationTypes.includes(canonicalRelationType)) {
    return false;
  }

  if (filters.citationType !== 'all') {
    const citationEdgeTypes = new Set([
      'case_citation',
      'constitution_citation',
      'usc_title_citation',
      'cfr_title_citation'
    ]);
    if (citationEdgeTypes.has(edgeType)) {
      const citationType = String(edge.citationType || '').toLowerCase();
      if (!citationType) return false;
      if (citationType !== filters.citationType) return false;
    }
  }

  if (filters.relationConfidenceMin !== null) {
    const confidence = Number(edge.confidence);
    if (!Number.isFinite(confidence)) return false;
    if (confidence < filters.relationConfidenceMin) return false;
  }

  return true;
}

function updateOntologyGraphMeta(visibleNodes, visibleEdges) {
  if (!els.ontologyGraphMeta) return;
  const meta = state.ontologyGraph.meta || {};
  const root = meta.ontologyRoot ? `root: ${meta.ontologyRoot}` : 'root: unavailable';
  const jurisdictions = Array.isArray(meta.selectedVaultRoots) ? meta.selectedVaultRoots.length : 0;
  const fallback =
    meta.fallbackFromVault === true
      ? meta.fallbackReason === 'ontology_dataset_empty'
        ? 'status: fallback from vault links (ontology dataset empty)'
        : 'status: fallback from vault links'
      : '';
  const status = fallback || (meta.exists === false ? 'status: ontology vault not found' : 'status: ready');
  const selected = jurisdictions ? ` • jurisdictions: ${jurisdictions}` : '';
  const source = meta.source ? ` • source: ${meta.source}` : '';
  const checked = meta.checkedCandidates ? ` • checked: ${meta.checkedCandidates}` : '';
  const mode = state.ontologyGraphRenderMode ? ` • mode: ${state.ontologyGraphRenderMode}` : '';
  els.ontologyGraphMeta.textContent = `${root} • ${status} • nodes: ${visibleNodes} • edges: ${visibleEdges}${selected}${source}${checked}${mode}`;
}

function toSortedCountEntries(counts = {}) {
  return Object.entries(counts || {})
    .map(([key, value]) => [String(key || 'unknown').trim() || 'unknown', Number(value)])
    .filter(([, value]) => Number.isFinite(value) && value > 0)
    .sort((left, right) => {
      const valueDelta = right[1] - left[1];
      if (valueDelta) return valueDelta;
      return left[0].localeCompare(right[0]);
    });
}

function summarizeCountMap(counts = {}, limit = 10) {
  const entries = toSortedCountEntries(counts);
  if (!entries.length) return 'none';
  const maxItems = Math.max(1, Number(limit) || 10);
  const shown = entries.slice(0, maxItems).map(([key, value]) => `${key}:${value}`);
  if (entries.length > maxItems) shown.push(`+${entries.length - maxItems} more`);
  return shown.join(', ');
}

function countEdgeFieldValues(edges = [], field = 'edgeType') {
  const counts = {};
  for (const edge of Array.isArray(edges) ? edges : []) {
    const raw = edge && typeof edge === 'object' && !Array.isArray(edge) ? edge[field] : '';
    const key = String(raw || '').trim().toLowerCase() || 'unknown';
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

function updateOntologyGraphDiagnostics(details = {}) {
  if (!els.ontologyGraphDiagnostics) return;
  if (!els.ontologyGraphDiagnostics.classList.contains('hidden')) {
    els.ontologyGraphDiagnostics.classList.add('hidden');
  }
  if (!details?.forceVisible) return;
  const totalNodes = Math.max(0, Number(details.totalNodesCount || 0));
  const totalEdges = Math.max(0, Number(details.totalEdgesCount || 0));
  const filteredNodes = Math.max(0, Number(details.filteredNodesCount || 0));
  const filteredEdges = Math.max(0, Number(details.filteredEdgesCount || 0));
  const renderedNodes = Math.max(0, Number(details.renderedNodesCount || 0));
  const renderedEdges = Math.max(0, Number(details.renderedEdgesCount || 0));
  const maxNodes = Math.max(0, Number(details.maxNodes || 0));
  const mode = String(details.mode || state.ontologyGraphRenderMode || 'unknown');
  const fallbackReason = String(details.fallbackReason || '');
  const connectivityRepairs = Math.max(0, Number(details.connectivityRepairs || 0));
  const viewPreset = normalizeOntologyPreset(details.viewPreset || state.ontologyFilter?.viewPreset || ONTOLOGY_FILTER_DEFAULTS.viewPreset);
  const minEdgeStrengthRaw = details.minEdgeStrength ?? state.ontologyFilter?.minEdgeStrength ?? ONTOLOGY_FILTER_DEFAULTS.minEdgeStrength;
  const minCaseImportanceRaw = details.minCaseImportance ?? state.ontologyFilter?.minCaseImportance ?? ONTOLOGY_FILTER_DEFAULTS.minCaseImportance;
  const maxEdgesPerNodeRaw = details.maxEdgesPerNode ?? state.ontologyFilter?.maxEdgesPerNode ?? ONTOLOGY_FILTER_DEFAULTS.maxEdgesPerNode;
  const minEdgeStrength = minEdgeStrengthRaw === null || minEdgeStrengthRaw === '' ? null : clamp01(minEdgeStrengthRaw);
  const minCaseImportance = minCaseImportanceRaw === null || minCaseImportanceRaw === '' ? null : clamp01(minCaseImportanceRaw);
  const maxEdgesPerNodeNumeric = Number(maxEdgesPerNodeRaw);
  const maxEdgesPerNode =
    maxEdgesPerNodeRaw === null || maxEdgesPerNodeRaw === '' || !Number.isFinite(maxEdgesPerNodeNumeric)
      ? null
      : Math.max(1, maxEdgesPerNodeNumeric);
  const sampleActive = Boolean(details.sampleActive);
  const totalCaseCandidates = Math.max(0, Number(details.totalCaseCandidates || 0));
  const sampledCaseCount = Math.max(0, Number(details.sampledCaseCount || 0));
  const sampleLimit = Math.max(1, Number(details.sampleLimit || ONTOLOGY_REPRESENTATIVE_CASE_LIMIT));

  const lines = [
    `Dataset: nodes ${totalNodes}, edges ${totalEdges}`,
    `Filtered: nodes ${filteredNodes}, edges ${filteredEdges}`,
    `Rendered: nodes ${renderedNodes}, edges ${renderedEdges}${maxNodes ? ` (max_nodes ${maxNodes})` : ''}`,
    'Layout: force_elastic (seeded clusters + force relaxation)',
    `Preset: ${viewPreset} • min_edge_strength ${minEdgeStrength === null ? 'none' : minEdgeStrength.toFixed(2)} • min_case_importance ${minCaseImportance === null ? 'none' : minCaseImportance.toFixed(2)} • max_edges_per_node ${maxEdgesPerNode === null ? 'none' : Math.round(maxEdgesPerNode)}`,
    sampleActive
      ? `Sampling: representative case sample ${sampledCaseCount}/${totalCaseCandidates} (cap ${sampleLimit})`
      : `Sampling: full case set (${totalCaseCandidates} cases)`,
    `Edge types (dataset): ${summarizeCountMap(details.datasetEdgeTypeCounts || {}, 9)}`,
    `Edge types (filtered): ${summarizeCountMap(details.filteredEdgeTypeCounts || {}, 9)}`,
    `Relation types (filtered): ${summarizeCountMap(details.filteredRelationTypeCounts || {}, 8)}`,
    `Mode: ${mode}${connectivityRepairs ? ` • connectivity_repairs ${connectivityRepairs}` : ''}${fallbackReason ? ` • fallback_reason ${fallbackReason}` : ''}`
  ];
  els.ontologyGraphDiagnostics.textContent = lines.join('\n');
  els.ontologyGraphDiagnostics.dataset.state = fallbackReason || mode === 'fallback' ? 'fallback' : 'ready';
}

function setOntologyRefreshStatus(message = 'Ready.', tone = 'neutral') {
  if (!els.ontologyRefreshStatus) return;
  const safeTone = ['neutral', 'working', 'ok', 'error'].includes(String(tone || '').toLowerCase())
    ? String(tone || '').toLowerCase()
    : 'neutral';
  els.ontologyRefreshStatus.textContent = String(message || 'Ready.');
  els.ontologyRefreshStatus.dataset.state = safeTone;
}

function ontologyEdgeColor(edge) {
  const edgeType = String(edge?.edgeType || '');
  if (edgeType === 'constitution_citation') return '#ef4444';
  if (edgeType === 'taxonomy_edge') return '#facc15';
  if (edgeType === 'usc_title_citation') return '#f97316';
  if (edgeType === 'cfr_title_citation') return '#06b6d4';
  if (edgeType === 'case_citation') return '#60a5fa';
  return '#4a4a4a';
}

function ontologyEdgeWidth(edge) {
  const edgeType = String(edge?.edgeType || '');
  if (edgeType === 'constitution_citation') return 2.35;
  if (edgeType === 'taxonomy_edge') return 1.6;
  if (edgeType === 'usc_title_citation') return 1.9;
  if (edgeType === 'cfr_title_citation') return 1.75;
  if (edgeType === 'case_citation') return 1.4;
  return 1.0;
}

function renderOntologyGraph(forceFit = false) {
  ensureGraphContainerSize(els.ontologyGraphContainer, 340);
  captureOntologyFiltersFromUI();
  const filters = state.ontologyFilter;

  const allNodes = Array.isArray(state.ontologyGraph.nodes) ? state.ontologyGraph.nodes : [];
  const allEdges = Array.isArray(state.ontologyGraph.edges) ? state.ontologyGraph.edges : [];
  const filteredNodes = allNodes.filter((node) => nodePassesOntologyFilters(node, filters));
  const filteredNodeMap = new Map(filteredNodes.map((node) => [node.id, node]));

  const filteredEdges = allEdges.filter((edge) => edgePassesOntologyFilters(edge, filters, filteredNodeMap));
  state.ontologyGraphAutoRelaxAttempted = false;
  const preset = normalizeOntologyPreset(filters.viewPreset);
  const minEdgeStrength = filters.minEdgeStrength === null || filters.minEdgeStrength === '' ? null : clamp01(filters.minEdgeStrength);
  const minCaseImportance = filters.minCaseImportance === null || filters.minCaseImportance === '' ? null : clamp01(filters.minCaseImportance);
  const maxEdgesPerNodeValue = Number(filters.maxEdgesPerNode);
  const maxEdgesPerNode = Number.isFinite(maxEdgesPerNodeValue) && maxEdgesPerNodeValue > 0
    ? Math.max(1, Math.min(250, Math.round(maxEdgesPerNodeValue)))
    : null;
  const sampleLimit = ONTOLOGY_REPRESENTATIVE_CASE_LIMIT;

  const edgeCandidates = [];
  for (let idx = 0; idx < filteredEdges.length; idx += 1) {
    const edge = filteredEdges[idx];
    if (!ontologyEdgeAllowedByPreset(edge, preset)) continue;
    const strength = ontologyEdgeStrength(edge);
    if (minEdgeStrength !== null && strength < minEdgeStrength) continue;
    edgeCandidates.push({
      key: `${String(edge?.source || '')}->${String(edge?.target || '')}:${idx}`,
      source: String(edge?.source || ''),
      target: String(edge?.target || ''),
      edge,
      strength
    });
  }

  const degreeBeforeImportance = new Map();
  for (const row of edgeCandidates) {
    degreeBeforeImportance.set(row.source, (degreeBeforeImportance.get(row.source) || 0) + 1);
    degreeBeforeImportance.set(row.target, (degreeBeforeImportance.get(row.target) || 0) + 1);
  }

  const caseImportanceById = new Map();
  for (const node of filteredNodes) {
    if (String(node?.nodeType || '').toLowerCase() !== 'case') continue;
    caseImportanceById.set(node.id, ontologyCaseImportance(node, degreeBeforeImportance.get(node.id) || 0));
  }

  const nodesAfterImportance = filteredNodes.filter((node) => {
    if (String(node?.nodeType || '').toLowerCase() !== 'case') return true;
    if (minCaseImportance === null) return true;
    return Number(caseImportanceById.get(node.id) || 0) >= minCaseImportance;
  });
  const nodeMapAfterImportance = new Map(nodesAfterImportance.map((node) => [node.id, node]));

  let edgeRows = edgeCandidates.filter((row) => nodeMapAfterImportance.has(row.source) && nodeMapAfterImportance.has(row.target));
  if (maxEdgesPerNode !== null) {
    edgeRows = limitEdgesByNodeBudget(edgeRows, maxEdgesPerNode, caseImportanceById);
  }

  const caseNodesAfterImportance = nodesAfterImportance.filter((node) => String(node.nodeType || '').toLowerCase() === 'case');
  let sampledCaseNodes = caseNodesAfterImportance;
  let sampleActive = false;
  if (caseNodesAfterImportance.length > sampleLimit) {
    sampledCaseNodes = buildRepresentativeCaseSample(caseNodesAfterImportance, sampleLimit, caseImportanceById);
    sampleActive = true;
  }
  const sampledCaseIds = new Set(sampledCaseNodes.map((node) => node.id));
  let workingNodes = nodesAfterImportance.filter((node) => {
    const nodeType = String(node.nodeType || '').toLowerCase();
    return nodeType !== 'case' || sampledCaseIds.has(node.id);
  });
  let workingNodeMap = new Map(workingNodes.map((node) => [node.id, node]));
  edgeRows = edgeRows.filter((row) => workingNodeMap.has(row.source) && workingNodeMap.has(row.target));

  const degree = new Map();
  for (const row of edgeRows) {
    degree.set(row.source, (degree.get(row.source) || 0) + 1);
    degree.set(row.target, (degree.get(row.target) || 0) + 1);
  }
  const layoutDegree = new Map(degreeBeforeImportance);
  for (const [nodeId, nodeDegree] of degree.entries()) {
    const current = Number(layoutDegree.get(nodeId) || 0);
    if (nodeDegree > current) layoutDegree.set(nodeId, nodeDegree);
  }
  for (const node of workingNodes) {
    if (String(node?.nodeType || '').toLowerCase() !== 'case') continue;
    caseImportanceById.set(node.id, ontologyCaseImportance(node, layoutDegree.get(node.id) || 0));
  }

  const datasetEdgeTypeCounts =
    state.ontologyGraph?.meta && typeof state.ontologyGraph.meta.edgeTypeCounts === 'object'
      ? state.ontologyGraph.meta.edgeTypeCounts
      : countEdgeFieldValues(allEdges, 'edgeType');
  const filteredEdgeTypeCounts = countEdgeFieldValues(edgeRows.map((row) => row.edge), 'edgeType');
  const filteredRelationTypeCounts = countEdgeFieldValues(edgeRows.map((row) => row.edge), 'relationType');

  const maxNodes = Math.max(100, Number(filters.maxNodes || 8000));
  const rankedNodes = workingNodes.slice().sort((a, b) => {
    const aType = String(a?.nodeType || '').toLowerCase();
    const bType = String(b?.nodeType || '').toLowerCase();
    if (aType === 'case' && bType === 'case') {
      const importanceDelta = Number(caseImportanceById.get(b.id) || 0) - Number(caseImportanceById.get(a.id) || 0);
      if (importanceDelta) return importanceDelta;
    }
    const degreeDelta = (layoutDegree.get(b.id) || 0) - (layoutDegree.get(a.id) || 0);
    if (degreeDelta) return degreeDelta;
    return String(a.id).localeCompare(String(b.id));
  });
  const rankedCaseNodes = rankedNodes.filter((node) => String(node.nodeType || '').toLowerCase() === 'case');
  const nonCaseTypePriority = (node) => {
    const nodeType = String(node?.nodeType || '').toLowerCase();
    if (nodeType === 'constitution') return 0;
    if (nodeType === 'source') return 1;
    if (nodeType === 'issue') return 2;
    if (nodeType === 'holding') return 3;
    if (nodeType === 'relation') return 4;
    if (nodeType === 'secondary') return 5;
    if (nodeType === 'event') return 6;
    if (nodeType === 'external_case') return 7;
    return 8;
  };
  const rankedNonCaseNodes = rankedNodes
    .filter((node) => String(node.nodeType || '').toLowerCase() !== 'case')
    .sort((a, b) => {
      const typeDelta = nonCaseTypePriority(a) - nonCaseTypePriority(b);
      if (typeDelta) return typeDelta;
      const degreeDelta = (layoutDegree.get(b.id) || 0) - (layoutDegree.get(a.id) || 0);
      if (degreeDelta) return degreeDelta;
      return String(a.id).localeCompare(String(b.id));
    });

  const nonCaseReserve = rankedNonCaseNodes.length
    ? Math.min(
        rankedNonCaseNodes.length,
        Math.max(40, Math.floor(maxNodes * 0.2)),
        Math.max(0, maxNodes - 25)
      )
    : 0;
  const caseBudget = Math.max(1, maxNodes - nonCaseReserve);
  const selectedCaseNodes = rankedCaseNodes.slice(0, caseBudget);
  const selectedNonCaseNodes = rankedNonCaseNodes.slice(0, Math.max(0, maxNodes - selectedCaseNodes.length));
  const chosenNodes = selectedCaseNodes.concat(selectedNonCaseNodes);
  const chosenNodeIds = new Set(chosenNodes.map((node) => node.id));
  setOntologySampleNotice({
    active: sampleActive,
    shown: sampledCaseNodes.length,
    total: caseNodesAfterImportance.length,
    limit: sampleLimit
  });
  if (els.ontologyCaseHoverCard?.dataset?.nodeId && !chosenNodeIds.has(els.ontologyCaseHoverCard.dataset.nodeId)) {
    hideOntologyCaseHoverCard(true);
  }

  const visibleEdgeRows = edgeRows.filter((row) => chosenNodeIds.has(row.source) && chosenNodeIds.has(row.target));
  const layoutResult = buildOntologyNativeLayout(chosenNodes, visibleEdgeRows, caseImportanceById, layoutDegree);
  const graphEdges = visibleEdgeRows
    .map((row, idx) => ({
      id: `${row.source}->${row.target}-${idx}`,
      from: row.source,
      to: row.target,
      color: ontologyEdgeColor(row.edge),
      width: ontologyEdgeWidth(row.edge)
    }));
  let graphNodes = chosenNodes.map((node) => {
    const nodeType = String(node.nodeType || 'unknown').toLowerCase();
    const originatingCircuit = normalizeOriginatingCircuit(node.originatingCircuit || node.originatingCircuitLabel || '');
    const circuitLabel = ONTOLOGY_CIRCUIT_LABELS[originatingCircuit] || '';
    const caseLabel = nodeType === 'case' ? ontologyCaseLabel(node) : '';
    const caseCitation = nodeType === 'case' ? ontologyCaseCitation(node) : '';
    const essentialHolding = nodeType === 'case' ? ontologyCaseEssentialHolding(node) : '';
    const caseSummary = nodeType === 'case' ? ontologyCaseSummary(node) : '';
    const color =
      nodeType === 'case' && originatingCircuit
        ? ONTOLOGY_CIRCUIT_COLORS[originatingCircuit] || (ONTOLOGY_NODE_COLORS[nodeType] || ONTOLOGY_NODE_COLORS.unknown)
        : ONTOLOGY_NODE_COLORS[nodeType] || ONTOLOGY_NODE_COLORS.unknown;
    const nodeDegree = layoutDegree.get(node.id) || degree.get(node.id) || 0;
    const size = Math.max(7, Math.min(26, 7 + Math.log2(nodeDegree + 1) * 4));
    const position = layoutResult.positionById.get(String(node.id || '')) || null;
    const seededPosition = position ? { x: Number(position.x), y: Number(position.y) } : {};
    return {
      id: node.id,
      label: nodeType === 'case' ? caseLabel || node.label || node.id : node.label || node.id,
      value: size,
      mass: Math.max(1, nodeDegree / 4),
      ...seededPosition,
      physics: true,
      color: {
        background: color,
        border: '#f5f5f5',
        highlight: { background: '#fde68a', border: '#fef3c7' },
        hover: { background: '#93c5fd', border: '#bfdbfe' }
      }
    };
  });

  const ontologyUnavailable =
    state.ontologyGraph?.meta?.exists === false && state.ontologyGraph?.meta?.fallbackFromVault !== true;
  if (!graphNodes.length) {
    if (ontologyUnavailable) {
      const missingRoot = String(state.ontologyGraph?.meta?.ontologyRoot || 'unknown path');
      graphNodes = [
        {
          id: '__missing_ontology_graph__',
          label: 'Ontology vault not found',
          value: 22,
          mass: 1
        }
      ];
    } else {
      graphNodes = [
        {
          id: '__empty_ontology_graph__',
          label: 'No matching ontology nodes',
          value: 18,
          mass: 1
        }
      ];
    }
  }
  const fallbackMaxNodes = Math.max(200, Math.min(maxNodes, Math.max(200, graphNodes.length || maxNodes)));
  const fallbackMaxEdges = Math.max(1500, Math.min(60000, Math.max(graphEdges.length, 1500)));
  const elasticTuning = buildOntologyElasticTuning(graphNodes.length, graphEdges.length);

  if (!state.ontologyGraphVisDisabled) {
    try {
      ensureOntologyGraphNetwork();
    } catch (err) {
      state.ontologyGraphVisDisabled = true;
      state.ontologyGraphRenderMode = 'fallback';
      showOntologyGraphRenderError(err);
    }
  }

  if (!state.ontologyGraphNetwork || !state.ontologyGraphData) {
    state.ontologyGraphRenderMode = 'fallback';
    renderGraphFallback(els.ontologyGraphContainer, graphNodes, graphEdges, {
      ariaLabel: 'Caselaw ontology graph fallback view',
      emptyTitle: 'Ontology graph is empty',
      emptyBody: 'No ontology nodes available for current filters.',
      suppressTooltips: true,
      maxNodes: fallbackMaxNodes,
      maxEdges: fallbackMaxEdges
    });
    updateOntologyGraphDiagnostics({
      totalNodesCount: allNodes.length,
      totalEdgesCount: allEdges.length,
      filteredNodesCount: workingNodes.length,
      filteredEdgesCount: edgeRows.length,
      renderedNodesCount: graphNodes.length,
      renderedEdgesCount: graphEdges.length,
      maxNodes,
      mode: state.ontologyGraphRenderMode,
      fallbackReason: String(state.ontologyGraph?.meta?.fallbackReason || 'graph_network_unavailable'),
      connectivityRepairs: Number(state.ontologyGraph?.meta?.connectivityRepairs || 0),
      viewPreset: preset,
      minEdgeStrength,
      minCaseImportance,
      maxEdgesPerNode,
      sampleActive,
      totalCaseCandidates: caseNodesAfterImportance.length,
      sampledCaseCount: sampledCaseNodes.length,
      sampleLimit,
      datasetEdgeTypeCounts,
      filteredEdgeTypeCounts,
      filteredRelationTypeCounts
    });
    updateOntologyGraphMeta(graphNodes.length, graphEdges.length);
    return;
  }

  try {
    applyOntologyElasticTuning(elasticTuning);
    state.ontologyGraphData.nodes.clear();
    state.ontologyGraphData.edges.clear();
    state.ontologyGraphData.nodes.add(graphNodes);
    state.ontologyGraphData.edges.add(graphEdges);

    state.ontologyGraphNetwork.setSize('100%', '100%');
    state.ontologyGraphNetwork.redraw();
    if (!state.ontologyGraphRendered || forceFit) {
      let fitted = false;
      const fitWhenReady = () => {
        if (fitted) return;
        fitted = true;
        fitOntologyGraphToViewport({
          fillRatio: elasticTuning.fillRatio,
          minScale: elasticTuning.minScale,
          maxScale: elasticTuning.maxScale,
          animate: true,
          duration: 340
        });
      };
      state.ontologyGraphNetwork.once('stabilized', fitWhenReady);
      setTimeout(fitWhenReady, 620);
      setTimeout(() => {
        fitOntologyGraphToViewport({
          fillRatio: elasticTuning.fillRatio,
          minScale: elasticTuning.minScale,
          maxScale: elasticTuning.maxScale,
          animate: true,
          duration: 260
        });
      }, 940);
    }
    state.ontologyGraphRendered = true;
    state.ontologyGraphRenderMode = 'vis';
  } catch (err) {
    state.ontologyGraphVisDisabled = true;
    state.ontologyGraphRenderMode = 'fallback';
    showOntologyGraphRenderError(err);
    renderGraphFallback(els.ontologyGraphContainer, graphNodes, graphEdges, {
      ariaLabel: 'Caselaw ontology graph fallback view',
      emptyTitle: 'Ontology graph is empty',
      emptyBody: 'No ontology nodes available for current filters.',
      suppressTooltips: true,
      maxNodes: fallbackMaxNodes,
      maxEdges: fallbackMaxEdges
    });
  }

  if (!hasUsableGraphCanvas(els.ontologyGraphContainer)) {
    setTimeout(() => {
      if (hasUsableGraphCanvas(els.ontologyGraphContainer)) return;
      try {
        state.ontologyGraphNetwork?.setSize('100%', '100%');
        state.ontologyGraphNetwork?.redraw();
      } catch {
        // continue to fallback below
      }
      setTimeout(() => {
        if (hasUsableGraphCanvas(els.ontologyGraphContainer)) return;
        state.ontologyGraphRenderMode = 'fallback';
        renderGraphFallback(els.ontologyGraphContainer, graphNodes, graphEdges, {
          ariaLabel: 'Caselaw ontology graph fallback view',
          emptyTitle: 'Ontology graph is empty',
          emptyBody: 'No ontology nodes available for current filters.',
          suppressTooltips: true,
          maxNodes: fallbackMaxNodes,
          maxEdges: fallbackMaxEdges
        });
      }, 260);
    }, 120);
  }

  updateOntologyGraphDiagnostics({
    totalNodesCount: allNodes.length,
    totalEdgesCount: allEdges.length,
    filteredNodesCount: workingNodes.length,
    filteredEdgesCount: edgeRows.length,
    renderedNodesCount: graphNodes.length,
    renderedEdgesCount: graphEdges.length,
    maxNodes,
    mode: state.ontologyGraphRenderMode,
    fallbackReason:
      state.ontologyGraphRenderMode === 'fallback'
        ? String(state.ontologyGraph?.meta?.fallbackReason || 'render_fallback')
        : '',
    connectivityRepairs: Number(state.ontologyGraph?.meta?.connectivityRepairs || 0),
    viewPreset: preset,
    minEdgeStrength,
    minCaseImportance,
    maxEdgesPerNode,
    sampleActive,
    totalCaseCandidates: caseNodesAfterImportance.length,
    sampledCaseCount: sampledCaseNodes.length,
    sampleLimit,
    datasetEdgeTypeCounts,
    filteredEdgeTypeCounts,
    filteredRelationTypeCounts
  });
  updateOntologyGraphMeta(graphNodes.length, graphEdges.length);
}

function determineVaultViewKind() {
  const kind = String(state.vaultAccess?.vaultKind || '').toLowerCase();
  if (kind === 'caselaw' || kind === 'casefile') return kind;
  if (state.vaultAccess?.caselawPresent) return 'caselaw';
  if (state.vaultAccess?.markerPresent) return 'casefile';
  return 'casefile';
}

function applyVaultViewMode() {
  state.vaultViewKind = determineVaultViewKind();
  const isCaselaw = state.vaultViewKind === 'caselaw';
  if (!isCaselaw) {
    restoreOntologyControlsToMainHost();
  }

  const graphActivityBtn = document.querySelector('.activity-btn[data-tab="graph"]');
  const ontologyActivityBtn = document.querySelector('.activity-btn[data-tab="ontology-graph"]');
  const trialCanvasActivityBtn = document.querySelector('.activity-btn[data-action="trial-canvas"]');

  if (graphActivityBtn) {
    graphActivityBtn.classList.toggle('hidden', isCaselaw);
    graphActivityBtn.title = 'Casefile View';
    graphActivityBtn.setAttribute('aria-label', 'Casefile View');
  }
  if (ontologyActivityBtn) {
    ontologyActivityBtn.classList.remove('hidden');
    ontologyActivityBtn.title = isCaselaw ? 'Caselaw View' : 'Ontology View';
    ontologyActivityBtn.setAttribute('aria-label', isCaselaw ? 'Caselaw View' : 'Ontology View');
  }
  if (trialCanvasActivityBtn) {
    trialCanvasActivityBtn.classList.add('hidden');
  }

  if (els.openVaultGraphBtn) {
    els.openVaultGraphBtn.textContent = 'Casefile View';
    els.openVaultGraphBtn.title = 'Open Casefile View';
    els.openVaultGraphBtn.classList.toggle('hidden', isCaselaw);
  }
  if (els.openOntologyGraphBtn) {
    els.openOntologyGraphBtn.textContent = isCaselaw ? 'Caselaw View' : 'Ontology View';
    els.openOntologyGraphBtn.title = isCaselaw ? 'Open Caselaw View' : 'Open Ontology View';
    els.openOntologyGraphBtn.classList.remove('hidden');
  }

  const active = state.openTabs.find((t) => t.id === state.activeTabId);
  if (isCaselaw && active?.kind === 'graph') {
    void openOntologyGraphTab();
  }

  if (els.filesTab && !els.filesTab.classList.contains('hidden')) {
    if (isCaselaw) {
      void loadCaselawJurisdictions();
    } else {
      void loadTree();
    }
  }
}

function updateVaultStatus(rootInfo) {
  state.vaultRoot = rootInfo?.root || '';
  state.vaultAccess = rootInfo?.access || null;

  const vaultName = state.vaultRoot ? basenameOf(state.vaultRoot) || state.vaultRoot : 'Vault unavailable';
  els.vaultPath.textContent = vaultName;
  els.vaultPath.title = state.vaultRoot || '';
  const viewKind = determineVaultViewKind();
  const viewLabel = viewKind === 'caselaw' ? 'Caselaw View' : 'Casefile View';
  if (!state.vaultAccess) {
    els.vaultStatus.textContent = viewLabel;
    els.vaultStatus.className = 'vault-status error';
    applyVaultViewMode();
    updateVaultActionState();
    return;
  }
  els.vaultStatus.textContent = viewLabel;
  els.vaultStatus.className = state.vaultAccess.readable && state.vaultAccess.writable ? 'vault-status ok' : 'vault-status error';
  applyVaultViewMode();
  updateVaultActionState();
}

function applyBuildInfo(info) {
  if (!els.buildSourceBadge) return;
  const sourceRaw = String(info?.source || '').toLowerCase();
  const source = sourceRaw || (info?.isPackaged ? 'packaged' : 'workspace');
  const sourceLabel = source === 'packaged' ? 'PACKAGED' : source === 'workspace' ? 'WORKSPACE' : source.toUpperCase();
  const version = String(info?.version || '').trim();
  const badgeText = `${sourceLabel}${version ? ` v${version}` : ''}`;
  els.buildSourceBadge.dataset.source = source;
  els.buildSourceBadge.textContent = badgeText;
  const appPath = String(info?.appPath || '');
  const execPath = String(info?.execPath || '');
  const buildMtime = String(info?.buildMtime || '');
  const tooltipParts = [`Source: ${source}`];
  if (version) tooltipParts.push(`Version: ${version}`);
  if (appPath) tooltipParts.push(`App path: ${appPath}`);
  if (execPath) tooltipParts.push(`Executable: ${execPath}`);
  if (buildMtime) tooltipParts.push(`Build mtime: ${buildMtime}`);
  els.buildSourceBadge.title = tooltipParts.join('\n');
}

async function loadBuildInfo() {
  try {
    const info = await window.acquittifyApi.getBuildInfo();
    applyBuildInfo(info);
  } catch (err) {
    if (!els.buildSourceBadge) return;
    els.buildSourceBadge.dataset.source = 'unknown';
    els.buildSourceBadge.textContent = 'BUILD UNKNOWN';
    els.buildSourceBadge.title = `Build source unavailable: ${err.message}`;
  }
}

async function refreshVaultData(forceGraphFit = false) {
  if (state.vaultViewKind === 'caselaw') {
    await loadCaselawJurisdictions();
  } else {
    await loadTree();
  }
  await loadGraph();
  await loadOntologyGraph();
  const active = state.openTabs.find((t) => t.id === state.activeTabId);
  if (active?.kind === 'graph') renderGraph(forceGraphFit);
  if (active?.kind === 'ontology-graph') renderOntologyGraph(forceGraphFit);
}

async function forceRefreshOntologyGraph(forceFit = true) {
  if (els.ontologyForceRefreshBtn) {
    els.ontologyForceRefreshBtn.disabled = true;
  }
  setOntologyRefreshStatus('Refreshing ontology graph…', 'working');
  hideOntologyCaseHoverCard(true);
  closeOntologyCaseSidebar(true);
  state.ontologyGraphRendered = false;

  try {
    await loadOntologyGraph();
    if (state.ontologyGraphVisDisabled && !state.ontologyGraphNetwork) {
      state.ontologyGraphVisDisabled = false;
    }
    renderOntologyGraph(Boolean(forceFit));
    const nodeCount = Array.isArray(state.ontologyGraph?.nodes) ? state.ontologyGraph.nodes.length : 0;
    const edgeCount = Array.isArray(state.ontologyGraph?.edges) ? state.ontologyGraph.edges.length : 0;
    setOntologyRefreshStatus(
      `Refreshed ${new Date().toLocaleTimeString()} • nodes ${nodeCount} • edges ${edgeCount}`,
      'ok'
    );
  } catch (err) {
    const message = err?.message ? String(err.message) : String(err || 'Unknown error');
    setOntologyRefreshStatus(`Refresh failed: ${message}`, 'error');
    addAgentNotice(`Ontology graph refresh failed: ${message}`, 'Workspace');
  } finally {
    if (els.ontologyForceRefreshBtn) {
      els.ontologyForceRefreshBtn.disabled = false;
    }
  }
}

async function chooseVaultRoot() {
  const rootInfo = await window.acquittifyApi.pickVaultRoot();
  updateVaultStatus(rootInfo);
  await refreshVaultData(true);
  addAgentNotice(`Vault switched to ${state.vaultRoot}`, 'Workspace');
}

async function importVaultFiles() {
  els.vaultImportBtn.disabled = true;
  const originalLabel = els.vaultImportBtn.textContent;
  els.vaultImportBtn.textContent = 'Importing...';
  try {
    const response = await window.acquittifyApi.importVaultFiles();
    if (!response || response.canceled) return;

    const results = Array.isArray(response.results) ? response.results : [];
    const successes = results.filter((r) => r.status === 'imported');
    const failures = results.filter((r) => r.status !== 'imported');

    await refreshVaultData(true);

    if (successes.length) {
      const firstExtracted = successes.find((r) => r.extractedPath)?.extractedPath;
      if (firstExtracted) {
        try {
          await openFile(firstExtracted);
        } catch {
          // continue
        }
      }
      addAgentNotice(
        `Imported ${successes.length} file(s). Native + extracted linked notes created in ${response.targetDir || 'vault import folder'}.`,
        'Workspace'
      );
    }

    if (failures.length) {
      const preview = failures
        .slice(0, 3)
        .map((f) => `${f.filename}: ${f.message || 'Unknown error'}`)
        .join(' | ');
      addAgentNotice(`Import failures (${failures.length}): ${preview}`, 'Workspace');
    }
  } catch (err) {
    addAgentNotice(`Import error: ${err.message}`, 'Workspace');
  } finally {
    els.vaultImportBtn.disabled = false;
    els.vaultImportBtn.textContent = originalLabel || 'Import';
  }
}

function tokenizeSlashCommand(input = '') {
  const tokens = [];
  const source = String(input || '');
  const regex = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let match = regex.exec(source);
  while (match) {
    tokens.push(String(match[1] ?? match[2] ?? match[3] ?? ''));
    match = regex.exec(source);
  }
  return tokens;
}

function normalizeBootstrapModeValue(value = '') {
  const _mode = String(value || '').trim().toLowerCase();
  return 'deep';
}

function parseBootstrapSlashCommand(prompt = '') {
  const trimmed = String(prompt || '').trim();
  if (!trimmed) return null;
  const lower = trimmed.toLowerCase();
  if (!lower.startsWith('/bootstrap') && !lower.startsWith('bootstrap')) return null;

  const tokens = tokenizeSlashCommand(trimmed);
  if (!tokens.length) return null;
  const commandToken = String(tokens[0] || '').toLowerCase();
  if (commandToken !== '/bootstrap' && commandToken !== 'bootstrap') return null;

  let mode = '';
  let casePath = '';
  let refresh = false;
  for (let i = 1; i < tokens.length; i += 1) {
    const token = String(tokens[i] || '');
    const lowerToken = token.toLowerCase();
    if (!token) continue;
    if (lowerToken === 'refresh' || lowerToken === '--refresh') {
      refresh = true;
      continue;
    }
    if (lowerToken.startsWith('--operation=') || lowerToken.startsWith('--action=')) {
      const action = lowerToken.includes('=') ? lowerToken.split('=')[1] : '';
      if (action === 'refresh') refresh = true;
      continue;
    }
    if (lowerToken === '--operation' || lowerToken === '--action') {
      const action = String(tokens[i + 1] || '').trim().toLowerCase();
      if (action === 'refresh') refresh = true;
      i += 1;
      continue;
    }
    if (lowerToken.startsWith('--mode=')) {
      mode = token.slice('--mode='.length);
      continue;
    }
    if (lowerToken === '--mode') {
      mode = String(tokens[i + 1] || '');
      i += 1;
      continue;
    }
    if (lowerToken.startsWith('--case=')) {
      casePath = token.slice('--case='.length);
      continue;
    }
    if (lowerToken.startsWith('--casepath=')) {
      casePath = token.slice('--casepath='.length);
      continue;
    }
    if (lowerToken === '--case' || lowerToken === '--casepath' || lowerToken === '--path') {
      casePath = String(tokens[i + 1] || '');
      i += 1;
      continue;
    }
    if (token.startsWith('-')) continue;
    if (/^[\\/.]/.test(token) || token.includes(':') || /[\\/]/.test(token)) {
      if (!casePath) casePath = token;
      continue;
    }
    if (!mode && lowerToken === 'deep') mode = 'deep';
  }

  return {
    mode: normalizeBootstrapModeValue(mode),
    refresh,
    casePath: String(casePath || '').trim()
  };
}

function formatBootstrapCompletionMessage(result, activeVaultRoot = '') {
  const operation = String(result?.operation || '').toLowerCase() === 'refresh' ? 'refresh' : 'bootstrap';
  const root = String(result?.caseRoot || '').trim();
  const normalizedRoot = normalizeVaultRootForMatch(root);
  const normalizedVault = normalizeVaultRootForMatch(activeVaultRoot);
  const displayRoot = normalizedRoot && normalizedRoot === normalizedVault ? '.' : (root || '.');
  const lines = [
    operation === 'refresh' ? 'Bootstrap refresh completed.' : 'Bootstrap completed.',
    `Case root: ${displayRoot}`,
    `Mode: ${result?.mode || 'deep'}`,
    `Counts: ${Number(result?.counts || 0)}`,
    `Witnesses: ${Number(result?.witnesses || 0)}`,
    `Attorneys: ${Number(result?.attorneys || 0)}`,
    `Documents: ${Number(result?.documents || 0)}`,
    `Discovery queue items: ${Number(result?.discoveryQueueItems || 0)}`,
    `Workspace note: ${result?.workspaceNote || 'Trial/Peregrine Startup Workspace.md'}`,
    `Bootstrap prompt (root): ${result?.bootstrapPromptRoot || 'BOOTSTRAP_PROMPT.md'}`,
    `Bootstrap prompt: ${result?.bootstrapPromptNote || 'Trial/Peregrine Bootstrap Prompt.md'}`,
    `Bootstrap refresh prompt (root): ${result?.bootstrapRefreshPromptRoot || 'BOOTSTRAP_REFRESH_PROMPT.md'}`,
    `Bootstrap refresh prompt: ${result?.bootstrapRefreshPromptNote || 'Trial/Peregrine Bootstrap Refresh Prompt.md'}`,
    `Schema root: ${result?.schemaRoot || 'Casefile'}`,
    `Ontology index: ${result?.ontologyIndexPath || 'Casefile/00_Metadata/ontology_index.json'}`,
    `Relationships: ${result?.relationshipsPath || 'Casefile/06_Link_Graph/relationships.json'}`,
    `Source index: ${result?.sourceIndexPath || 'Casefile/00_Metadata/bootstrap_source_index.json'}`,
    `Delta report: ${result?.refreshReportPath || 'Casefile/00_Metadata/bootstrap_refresh_report.json'}`
  ];
  if (operation === 'refresh') {
    lines.push(`New documents: ${Number(result?.newDocuments || 0)}`);
    lines.push(`Updated documents: ${Number(result?.updatedDocuments || 0)}`);
    lines.push(`Removed documents: ${Number(result?.removedDocuments || 0)}`);
  }

  const warnings = Array.isArray(result?.warnings)
    ? result.warnings.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  if (warnings.length) {
    lines.push('');
    lines.push(`Warnings: ${warnings.join(' | ')}`);
  }
  return lines.join('\n');
}

async function runAgent() {
  const prompt = els.agentInput.value.trim();
  if (!prompt) return;

  let conversation = getActiveConversation();
  if (!conversation) {
    conversation = createConversation();
  }

  maybeRetitleConversation(conversation, prompt);
  appendConversationMessage(conversation.id, { role: 'user', text: prompt });
  els.agentInput.value = '';

  const pendingMessageId = appendConversationMessage(conversation.id, {
    role: 'assistant',
    text: 'Thinking...',
    status: 'pending'
  });
  setConversationPendingCount(conversation.id, conversation.pendingCount + 1);

  try {
    const bootstrapCommand = parseBootstrapSlashCommand(prompt);
    if (bootstrapCommand) {
      if (!window.acquittifyApi || typeof window.acquittifyApi.bootstrapCasefile !== 'function') {
        throw new Error("No handler registered for 'casefile:bootstrap'");
      }
      const payload = { mode: bootstrapCommand.mode };
      if (bootstrapCommand.refresh) {
        payload.refresh = true;
        payload.operation = 'refresh';
      }
      if (bootstrapCommand.casePath) payload.casePath = bootstrapCommand.casePath;
      const result = await window.acquittifyApi.bootstrapCasefile(payload);
      updateConversationMessage(conversation.id, pendingMessageId, {
        text: formatBootstrapCompletionMessage(result, state.vaultRoot),
        status: 'complete',
        meta: 'Peregrine Bootstrap'
      });
      const latest = getConversationById(conversation.id);
      setConversationPendingCount(conversation.id, Math.max(0, (latest?.pendingCount || 0) - 1));

      await refreshVaultData(true);
      await openOntologyGraphTab();
      return;
    }

    const viewKind = state.vaultViewKind === 'caselaw' ? 'caselaw' : 'casefile';
    const caselawVaultRoots = viewKind === 'caselaw'
      ? Array.from(
          new Set(
            (state.caselawSelectedVaultRoots || [])
              .map((entry) => normalizeVaultRootForMatch(entry))
              .filter(Boolean)
          )
        )
      : [];
    if (viewKind === 'caselaw' && !caselawVaultRoots.length && state.vaultRoot) {
      caselawVaultRoots.push(normalizeVaultRootForMatch(state.vaultRoot));
    }

    if (window.acquittifyApi && typeof window.acquittifyApi.runAgentStream === 'function') {
      const res = await window.acquittifyApi.runAgentStream({
        prompt,
        conversationId: conversation.id,
        viewKind,
        caselawVaultRoots
      });
      const runId = res?.runId;
      if (!runId) {
        throw new Error('OpenClaw stream did not start.');
      }
      agentStreamRuns.set(runId, {
        conversationId: conversation.id,
        messageId: pendingMessageId,
        text: '',
        sawDelta: false
      });
      return;
    }

    if (!window.acquittifyApi || typeof window.acquittifyApi.runAgent !== 'function') {
      throw new Error('Agent API is unavailable in this build.');
    }
    const fallback = await window.acquittifyApi.runAgent({
      prompt,
      conversationId: conversation.id,
      viewKind,
      caselawVaultRoots
    });
    const answer = String(fallback?.answer || 'No response.');
    updateConversationMessage(conversation.id, pendingMessageId, {
      text: answer,
      status: 'complete',
      meta: 'OpenClaw'
    });
    const latest = getConversationById(conversation.id);
    setConversationPendingCount(conversation.id, Math.max(0, (latest?.pendingCount || 0) - 1));
  } catch (e) {
    updateConversationMessage(conversation.id, pendingMessageId, {
      text: `Agent error: ${e.message}`,
      status: 'error'
    });
    const latest = getConversationById(conversation.id);
    setConversationPendingCount(conversation.id, Math.max(0, (latest?.pendingCount || 0) - 1));
  }
}

function wireEvents() {
  const syncViewportSize = () => {
    const w = Math.max(1, Math.floor(window.innerWidth || document.documentElement.clientWidth || 1));
    const h = Math.max(1, Math.floor(window.innerHeight || document.documentElement.clientHeight || 1));
    document.documentElement.style.setProperty('--acquittify-vw', `${w}px`);
    document.documentElement.style.setProperty('--acquittify-vh', `${h}px`);
  };

  const resizeLayout = () => {
    applySidebarWidths({}, { persist: false });
    syncViewportSize();
    enforcePdfLayoutContract();
    if (state.graphNetwork && !els.graphWrap.classList.contains('hidden')) {
      state.graphNetwork.setSize('100%', '100%');
      state.graphNetwork.redraw();
    }
    if (state.ontologyGraphNetwork && !els.ontologyGraphWrap.classList.contains('hidden')) {
      state.ontologyGraphNetwork.setSize('100%', '100%');
      state.ontologyGraphNetwork.redraw();
    }
    schedulePdfRerender();
  };
  wireSidebarResizers(resizeLayout);

  window.addEventListener('resize', resizeLayout);
  window.addEventListener('orientationchange', resizeLayout);
  window.addEventListener('focus', resizeLayout);
  document.addEventListener('visibilitychange', resizeLayout);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', resizeLayout);
  }
  if (window.acquittifyApi && typeof window.acquittifyApi.onWindowGeometryChanged === 'function') {
    window.acquittifyApi.onWindowGeometryChanged(() => resizeLayout());
  }
  requestAnimationFrame(resizeLayout);
  setTimeout(resizeLayout, 50);
  setTimeout(resizeLayout, 200);
  setTimeout(resizeLayout, 500);

  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => resizeLayout());
    const root = document.getElementById('goldenRoot');
    if (root) ro.observe(root);
    else ro.observe(document.body);
  }

  document.addEventListener(
    'wheel',
    (event) => {
      if (!event || event.defaultPrevented) return;
      if (event.ctrlKey || event.metaKey) return;
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.closest('textarea,input,select')) return;
      if (target.closest('#graphContainer')) return;
      if (target.closest('#ontologyGraphContainer')) return;

      const scrollable = findScrollableAncestor(target);
      if (!scrollable) return;

      const before = scrollable.scrollTop;
      if (event.deltaY) {
        scrollable.scrollTop += event.deltaY;
      }
      if (event.deltaX) {
        scrollable.scrollLeft += event.deltaX;
      }

      if (scrollable.scrollTop !== before) {
        event.preventDefault();
      }
    },
    { passive: false, capture: true }
  );

  const activatePrimaryWorkspaceTab = () => {
    const active = state.openTabs.find((t) => t.id === state.activeTabId);
    if (active && active.kind !== 'graph' && active.kind !== 'ontology-graph') return;
    const fallback = state.openTabs.find((t) => t.kind !== 'graph' && t.kind !== 'ontology-graph');
    if (fallback) {
      activateTab(fallback.id);
      return;
    }
    createBlankTabAndActivate();
  };

  document.querySelectorAll('.activity-btn').forEach((btn) => {
    btn.onclick = () => {
      if (btn.dataset.action === 'trial-canvas') {
        void openOntologyGraphTab();
        return;
      }
      if (btn.dataset.tab === 'graph') {
        openGraphTab();
      } else if (btn.dataset.tab === 'ontology-graph') {
        void openOntologyGraphTab();
      } else if (btn.dataset.tab === 'files') {
        activatePrimaryWorkspaceTab();
        setActiveLeftTab('files');
        if (state.vaultViewKind === 'caselaw') {
          void loadCaselawJurisdictions();
        } else {
          void loadTree();
        }
      } else if (btn.dataset.tab === 'search') {
        activatePrimaryWorkspaceTab();
        setActiveLeftTab('search');
      } else if (btn.dataset.tab) {
        setActiveLeftTab(btn.dataset.tab);
      }
    };
  });

  const rerenderOntologyGraph = () => {
    const active = state.openTabs.find((t) => t.id === state.activeTabId);
    if (active?.kind === 'ontology-graph') {
      renderOntologyGraph(false);
    }
  };
  els.ontologyApplyBtn.onclick = () => renderOntologyGraph(true);
  els.ontologyResetBtn.onclick = () => {
    applyOntologyFilterDefaults();
    renderOntologyGraph(true);
  };
  els.ontologyForceRefreshBtn.onclick = () => {
    void forceRefreshOntologyGraph(true);
  };
  if (els.ontologyViewPreset) {
    els.ontologyViewPreset.addEventListener('change', () => {
      applyOntologyPresetSelection(els.ontologyViewPreset.value, true);
      rerenderOntologyGraph();
    });
  }
  els.ontologyGraphSearch.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') renderOntologyGraph(true);
  });
  [
    els.ontologyMinEdgeStrength,
    els.ontologyMinCaseImportance,
    els.ontologyMaxEdgesPerNode,
    els.ontologyCitationType,
    els.ontologyCaseDomain,
    els.ontologyCourtLevel,
    els.ontologyOriginatingCircuit,
    els.ontologyNormativeStrength,
    els.ontologyFactDimension,
    els.ontologyPfMin,
    els.ontologyConsensusMin,
    els.ontologyDriftMax,
    els.ontologyRelationConfidenceMin,
    els.ontologyMaxNodes
  ].forEach((input) => {
    input.addEventListener('change', rerenderOntologyGraph);
  });
  Array.from(els.ontologyNodeTypes.querySelectorAll('input[type="checkbox"]')).forEach((input) => {
    input.addEventListener('change', rerenderOntologyGraph);
  });
  Array.from(els.ontologyRelationTypes.querySelectorAll('input[type="checkbox"]')).forEach((input) => {
    input.addEventListener('change', rerenderOntologyGraph);
  });
  if (els.ontologyCaseSidebarClose) {
    els.ontologyCaseSidebarClose.onclick = () => closeOntologyCaseSidebar(true);
  }
  if (els.ontologyCaseHoverCard) {
    els.ontologyCaseHoverCard.addEventListener('mouseenter', () => clearOntologyHoverHideTimer());
    els.ontologyCaseHoverCard.addEventListener('mouseleave', () => scheduleHideOntologyCaseHoverCard(120));
  }
  if (els.ontologyGraphContainer) {
    els.ontologyGraphContainer.addEventListener('mousemove', (event) => {
      const pointer = ontologyHoverPointerPosition({ event });
      if (!pointer) return;
      requestOntologyHoverRefresh(pointer);
    });
    els.ontologyGraphContainer.addEventListener('mouseleave', (event) => {
      const next = event.relatedTarget;
      if (next instanceof Node && (next === els.ontologyCaseHoverCard || els.ontologyCaseHoverCard?.contains(next))) {
        return;
      }
      scheduleHideOntologyCaseHoverCard(240);
    });
  }

  els.vaultImportBtn.onclick = importVaultFiles;
  els.vaultChooseBtn.onclick = chooseVaultRoot;
  if (els.openVaultGraphBtn) {
    els.openVaultGraphBtn.onclick = () => {
      openGraphTab();
    };
  }
  if (els.openOntologyGraphBtn) {
    els.openOntologyGraphBtn.onclick = () => {
      void openOntologyGraphTab();
    };
  }
  if (Array.isArray(els.caseCanvasButtons)) {
    els.caseCanvasButtons.forEach((btn) => {
      const canvasId = btn.dataset.canvasId;
      const canvas = getCaseCanvasById(canvasId);
      if (!canvas || !pathIsDirectory(canvas.vaultRoot)) {
        btn.disabled = true;
        btn.title = 'Case canvas vault not found';
        return;
      }
      btn.onclick = () => openCaseCanvas(canvasId);
    });
  }
  els.vaultNewNoteBtn.onclick = createVaultNoteFromSelection;
  els.vaultNewFolderBtn.onclick = createVaultFolderFromSelection;
  els.vaultRenameBtn.onclick = renameSelectedVaultEntry;
  els.vaultDeleteBtn.onclick = deleteSelectedVaultEntry;
  els.saveBtn.onclick = saveActive;
  els.refreshBtn.onclick = async () => {
    await refreshVaultData(true);
  };
  els.appReloadBtn.onclick = async () => {
    const originalLabel = els.appReloadBtn.textContent;
    els.appReloadBtn.disabled = true;
    els.appReloadBtn.textContent = 'Reloading...';
    try {
      await window.acquittifyApi.reloadAppWithCode();
    } catch (err) {
      window.alert(`Unable to reload app: ${err.message}`);
      els.appReloadBtn.disabled = false;
      els.appReloadBtn.textContent = originalLabel || 'Reload App';
    }
  };
  els.globalSearch.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter') await performSearch(els.globalSearch.value);
  });

  els.agentNewConversation.onclick = () => {
    const created = createConversation();
    appendConversationMessage(created.id, {
      role: 'assistant',
      text: 'New conversation started.',
      meta: 'System'
    });
  };
  els.agentSend.onclick = runAgent;
  els.agentInput.addEventListener('keydown', async (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') await runAgent();
  });

  els.editor.addEventListener('input', () => {
    const tab = state.openTabs.find((t) => t.id === state.activeTabId);
    if (tab && tab.kind === 'text' && !tab.readOnly) tab.content = els.editor.value;
  });
}

async function init() {
  if (!window.acquittifyApi) {
    throw new Error('Renderer bridge unavailable: acquittifyApi is not defined.');
  }

  initShell();
  await waitForRenderedElements();
  initializeSidebarWidths();
  enforcePdfLayoutContract();
  applyOntologyFilterDefaults();
  setOntologyRefreshStatus('Ready.', 'neutral');

  hydrateConversations();
  ensureAgentConversations();
  attachAgentStreamHandlers();

  const rootInfo = await window.acquittifyApi.getVaultRoot();
  updateVaultStatus(rootInfo);
  wireEvents();
  await loadBuildInfo();
  setActiveLeftTab('files');
  await refreshVaultData(false);
  createBlankTabAndActivate();
}

init().catch((err) => {
  document.body.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.style.padding = '16px';
  wrap.style.fontFamily = '-apple-system,Segoe UI,sans-serif';
  wrap.style.background = '#111';
  wrap.style.color = '#f5f5f5';

  const title = document.createElement('h3');
  title.style.margin = '0 0 10px 0';
  title.textContent = 'Acquittify startup error';

  const details = document.createElement('div');
  details.style.whiteSpace = 'pre-wrap';
  details.style.lineHeight = '1.4';
  details.textContent = String(err && err.stack ? err.stack : err);

  wrap.appendChild(title);
  wrap.appendChild(details);
  document.body.appendChild(wrap);
});
