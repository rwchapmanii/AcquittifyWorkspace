const { Network, DataSet } = require('../node_modules/vis-network/standalone/umd/vis-network.cjs');

const CONVERSATIONS_STORAGE_KEY = 'acquittify.agent.conversations.v2';
const MAX_SAVED_MESSAGES = 500;
const MAX_HISTORY_MESSAGES = 20;
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

const state = {
  vaultRoot: '',
  vaultAccess: null,
  nextTabId: 1,
  openTabs: [],
  activeTabId: null,
  graph: { nodes: [], edges: [], meta: {} },
  graphNetwork: null,
  graphData: null,
  graphRendered: false,
  agent: {
    conversations: [],
    activeConversationId: null,
    nextConversationId: 1,
    nextMessageId: 1
  }
};

let els = {};

function initShell() {
  const root = document.getElementById('goldenRoot');
  root.innerHTML = `
    <div class="app-shell">
      <section class="sidebar-layout">
        <aside class="activity-bar">
          <button class="activity-btn active" data-tab="files" title="Files">📁</button>
          <button class="activity-btn" data-tab="search" title="Search">🔎</button>
          <button class="activity-btn" data-tab="graph" title="Graph">🕸️</button>
        </aside>
        <aside class="left-pane">
          <div class="pane-header">
            <div class="pane-header-top">
              <div id="vaultPath" class="vault-path">Vault</div>
              <button id="vaultImportBtn" class="vault-btn" title="Import files into vault">Import</button>
              <button id="vaultChooseBtn" class="vault-btn" title="Select vault folder">Switch</button>
            </div>
            <div id="vaultStatus" class="vault-status">Checking vault access...</div>
            <input id="globalSearch" type="text" placeholder="Search vault…" />
          </div>
          <div id="filesTab" class="left-content"></div>
          <div id="searchTab" class="left-content hidden"><div id="searchResults"></div></div>
        </aside>
      </section>

      <main class="center-pane">
        <div id="tabs" class="tabs"></div>
        <div id="editorToolbar" class="editor-toolbar">
          <span id="currentFile">No file selected</span>
          <div class="toolbar-actions">
            <button id="refreshBtn">Refresh</button>
            <button id="saveBtn">Save</button>
          </div>
        </div>
        <textarea id="editor" spellcheck="false" placeholder="Open a file to edit..."></textarea>
        <div id="pdfWrap" class="pdf-wrap hidden">
          <iframe id="pdfFrame" class="pdf-frame" title="PDF Viewer"></iframe>
        </div>
        <div id="mediaWrap" class="media-wrap hidden">
          <img id="mediaImage" class="media-image hidden" alt="Image Preview" />
          <audio id="mediaAudio" class="media-audio hidden" controls preload="metadata"></audio>
          <video id="mediaVideo" class="media-video hidden" controls preload="metadata"></video>
          <div id="binaryInfo" class="binary-info hidden"></div>
        </div>
        <div id="graphWrap" class="graph-wrap hidden">
          <div id="graphContainer" class="graph-container"></div>
          <div class="graph-hint">Scroll to zoom • Drag to pan • Click node to open note • Double-click background to fit</div>
        </div>
      </main>

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
    vaultPath: document.getElementById('vaultPath'),
    vaultStatus: document.getElementById('vaultStatus'),
    vaultImportBtn: document.getElementById('vaultImportBtn'),
    vaultChooseBtn: document.getElementById('vaultChooseBtn'),
    filesTab: document.getElementById('filesTab'),
    searchTab: document.getElementById('searchTab'),
    graphContainer: document.getElementById('graphContainer'),
    tabs: document.getElementById('tabs'),
    editorToolbar: document.getElementById('editorToolbar'),
    editor: document.getElementById('editor'),
    pdfWrap: document.getElementById('pdfWrap'),
    pdfFrame: document.getElementById('pdfFrame'),
    mediaWrap: document.getElementById('mediaWrap'),
    mediaImage: document.getElementById('mediaImage'),
    mediaAudio: document.getElementById('mediaAudio'),
    mediaVideo: document.getElementById('mediaVideo'),
    binaryInfo: document.getElementById('binaryInfo'),
    graphWrap: document.getElementById('graphWrap'),
    currentFile: document.getElementById('currentFile'),
    saveBtn: document.getElementById('saveBtn'),
    refreshBtn: document.getElementById('refreshBtn'),
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
    els.vaultPath &&
      els.vaultStatus &&
      els.vaultImportBtn &&
      els.vaultChooseBtn &&
      els.filesTab &&
      els.searchTab &&
      els.graphContainer &&
      els.tabs &&
      els.editorToolbar &&
      els.editor &&
      els.pdfWrap &&
      els.mediaWrap &&
      els.mediaImage &&
      els.mediaAudio &&
      els.mediaVideo &&
      els.binaryInfo &&
      els.graphWrap &&
      els.currentFile &&
      els.saveBtn &&
      els.refreshBtn &&
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

function getLowerExt(filePath = '') {
  const idx = String(filePath || '').lastIndexOf('.');
  if (idx < 0) return '';
  return String(filePath).slice(idx).toLowerCase();
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
    const row = document.createElement('button');
    row.type = 'button';
    row.className = `agent-thread ${conversation.id === state.agent.activeConversationId ? 'active' : ''}`;
    row.onclick = () => setActiveConversation(conversation.id);

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

    row.appendChild(title);
    row.appendChild(preview);
    row.appendChild(meta);
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
      text: 'Agent ready. Ask to retrieve notes, summarize material, or propose taxonomy/ontology edits.',
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

function addAgentNotice(text, meta = '') {
  const active = getActiveConversation();
  if (!active) return;
  appendConversationMessage(active.id, { role: 'assistant', text, meta });
}

function setActiveLeftTab(tab) {
  document.querySelectorAll('.activity-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  els.filesTab.classList.toggle('hidden', tab !== 'files');
  els.searchTab.classList.toggle('hidden', tab !== 'search');
}

function setShellMode(mode = 'default') {
  const shell = document.querySelector('.app-shell');
  if (!shell) return;
  const sidebar = document.querySelector('.sidebar-layout');
  const rightPane = document.querySelector('.right-pane');
  const centerPane = document.querySelector('.center-pane');

  shell.classList.toggle('pdf-focus', mode === 'pdf');
  if (mode === 'pdf') {
    if (sidebar) sidebar.style.display = 'none';
    if (rightPane) rightPane.style.display = 'none';
    shell.style.gridTemplateColumns = 'minmax(0, 1fr)';
    if (centerPane) {
      centerPane.style.gridColumn = '1';
      centerPane.style.width = '100%';
      centerPane.style.maxWidth = '100%';
    }
    if (els.tabs) els.tabs.classList.add('hidden');
    if (els.editorToolbar) els.editorToolbar.classList.add('hidden');
  } else {
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

async function loadTree(relPath = '', container = els.filesTab, depth = 0) {
  const items = await window.acquittifyApi.listVault(relPath);
  if (depth === 0) container.innerHTML = '';

  for (const item of items) {
    const row = document.createElement('div');
    row.className = `tree-item ${item.type === 'directory' ? 'tree-dir' : 'tree-file'}`;
    row.style.paddingLeft = `${depth * 12 + 6}px`;
    row.textContent = item.type === 'directory' ? `▸ ${item.name}` : item.name;

    if (item.type === 'directory') {
      let expanded = false;
      let childWrap = null;
      row.onclick = async () => {
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
      row.onclick = () => openFile(item.path);
    }

    container.appendChild(row);
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
  state.activeTabId = tabId;
  setShellMode('default');

  els.editor.classList.add('hidden');
  els.editor.readOnly = false;
  els.graphWrap.classList.add('hidden');
  els.pdfWrap.classList.add('hidden');
  els.pdfFrame.src = '';
  clearMediaPreview();

  if (tab.kind === 'pdf') {
    setShellMode('pdf');
    els.pdfWrap.classList.remove('hidden');
    els.pdfFrame.src = `${tab.url}#toolbar=0&navpanes=0&view=FitH&zoom=page-width`;
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
    els.saveBtn.disabled = true;
    els.saveBtn.title = 'Graph view is read-only';
    renderGraph();
  } else {
    els.editor.classList.remove('hidden');
    els.editor.value = tab.content;
    els.editor.readOnly = Boolean(tab.readOnly);
    els.saveBtn.disabled = !tab.path || Boolean(tab.readOnly);
    els.saveBtn.title = tab.readOnly ? 'This tab is read-only' : tab.path ? '' : 'Open a file to save changes';
  }
  els.currentFile.textContent = tab.title || tab.path || 'No file selected';
  renderTabs();
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
    title: 'Ontology Graph',
    path: '__graph__'
  };
  state.openTabs.push(tab);
  activateTab(tab.id);
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

  const replacement = await buildTabForPath(path);
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
  } catch (err) {
    state.graph = { nodes: [], edges: [], meta: {} };
    addAgentNotice(`Graph load error: ${err.message}`);
  }
}

function ensureGraphNetwork() {
  if (state.graphNetwork || !els.graphContainer) return;

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
  ensureGraphNetwork();
  if (!state.graphNetwork || !state.graphData) return;

  const knownIds = new Set((state.graph.nodes || []).map((n) => n.id));
  let edges = (state.graph.edges || [])
    .filter((e) => knownIds.has(e.source) && knownIds.has(e.target))
    .slice(0, 5000)
    .map((e, i) => ({ id: `${e.source}->${e.target}-${i}`, from: e.source, to: e.target }));

  const degree = new Map();
  for (const e of edges) {
    degree.set(e.from, (degree.get(e.from) || 0) + 1);
    degree.set(e.to, (degree.get(e.to) || 0) + 1);
  }

  const MIN_BUBBLE = 7;
  const MAX_BUBBLE = 26;
  let nodes = (state.graph.nodes || []).slice(0, 2500).map((n) => {
    const d = degree.get(n.id) || 0;
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

  state.graphData.nodes.clear();
  state.graphData.edges.clear();
  state.graphData.nodes.add(nodes);
  state.graphData.edges.add(edges);

  state.graphNetwork.redraw();
  if (!state.graphRendered || forceFit) {
    state.graphNetwork.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
  }
  state.graphRendered = true;
}

function updateVaultStatus(rootInfo) {
  state.vaultRoot = rootInfo?.root || '';
  state.vaultAccess = rootInfo?.access || null;

  els.vaultPath.textContent = state.vaultRoot || 'Vault unavailable';
  if (!state.vaultAccess) {
    els.vaultStatus.textContent = 'Unable to determine vault access.';
    els.vaultStatus.className = 'vault-status error';
    return;
  }

  const flags = [];
  if (state.vaultAccess.readable) flags.push('read');
  if (state.vaultAccess.writable) flags.push('write');
  const marker = state.vaultAccess.markerPresent ? 'Acquittify marker found' : 'Acquittify marker missing';

  if (state.vaultAccess.readable && state.vaultAccess.writable) {
    els.vaultStatus.textContent = `Access: ${flags.join('/') || 'none'} • ${marker}`;
    els.vaultStatus.className = 'vault-status ok';
  } else {
    const err = state.vaultAccess.error ? ` • ${state.vaultAccess.error}` : '';
    els.vaultStatus.textContent = `Access: ${flags.join('/') || 'none'} • ${marker}${err}`;
    els.vaultStatus.className = 'vault-status error';
  }
}

async function refreshVaultData(forceGraphFit = false) {
  await loadTree();
  await loadGraph();
  const active = state.openTabs.find((t) => t.id === state.activeTabId);
  if (active?.kind === 'graph') renderGraph(forceGraphFit);
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

  const history = conversation.messages
    .filter((m) => m.id !== pendingMessageId && (m.role === 'user' || m.role === 'assistant') && m.status !== 'pending')
    .slice(-MAX_HISTORY_MESSAGES)
    .map((m) => ({ role: m.role, text: m.text }));

  try {
    const res = await window.acquittifyApi.runAgent({ prompt, history });
    const metaParts = [];
    if (res.model) metaParts.push(`Model: ${res.model}`);
    if (res.responseId) metaParts.push(`Response: ${res.responseId}`);
    if (Array.isArray(res.contextPaths) && res.contextPaths.length) {
      metaParts.push(`Sources: ${res.contextPaths.join(', ')}`);
    }
    updateConversationMessage(conversation.id, pendingMessageId, {
      text: res.answer || 'No response.',
      status: 'complete',
      meta: metaParts.join(' • ')
    });
  } catch (e) {
    updateConversationMessage(conversation.id, pendingMessageId, {
      text: `Agent error: ${e.message}`,
      status: 'error'
    });
  } finally {
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
    syncViewportSize();
    if (state.graphNetwork && !els.graphWrap.classList.contains('hidden')) {
      state.graphNetwork.redraw();
    }
  };

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

  document.querySelectorAll('.activity-btn').forEach((btn) => {
    btn.onclick = () => {
      if (btn.dataset.tab === 'graph') {
        openGraphTab();
      } else {
        setActiveLeftTab(btn.dataset.tab);
      }
    };
  });

  els.vaultImportBtn.onclick = importVaultFiles;
  els.vaultChooseBtn.onclick = chooseVaultRoot;
  els.saveBtn.onclick = saveActive;
  els.refreshBtn.onclick = async () => {
    await refreshVaultData(true);
    addAgentNotice('Vault and graph reloaded.', 'Workspace');
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

  hydrateConversations();
  ensureAgentConversations();

  const rootInfo = await window.acquittifyApi.getVaultRoot();
  updateVaultStatus(rootInfo);
  wireEvents();
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
