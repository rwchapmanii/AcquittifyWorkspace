const state = {
  vaultRoot: '',
  openTabs: [],
  activeTab: null,
  graph: { nodes: [], edges: [] }
};

const els = {
  vaultPath: document.getElementById('vaultPath'),
  filesTab: document.getElementById('filesTab'),
  graphTab: document.getElementById('graphTab'),
  searchTab: document.getElementById('searchTab'),
  graphCanvas: document.getElementById('graphCanvas'),
  tabs: document.getElementById('tabs'),
  editor: document.getElementById('editor'),
  currentFile: document.getElementById('currentFile'),
  saveBtn: document.getElementById('saveBtn'),
  refreshBtn: document.getElementById('refreshBtn'),
  globalSearch: document.getElementById('globalSearch'),
  searchResults: document.getElementById('searchResults'),
  agentMessages: document.getElementById('agentMessages'),
  agentInput: document.getElementById('agentInput'),
  agentSend: document.getElementById('agentSend')
};

function addMessage(role, text, meta = '') {
  const div = document.createElement('div');
  div.className = `agent-msg ${role}`;
  div.textContent = text;
  if (meta) {
    const m = document.createElement('div');
    m.className = 'agent-meta';
    m.textContent = meta;
    div.appendChild(m);
  }
  els.agentMessages.appendChild(div);
  els.agentMessages.scrollTop = els.agentMessages.scrollHeight;
}

function setActiveLeftTab(tab) {
  document.querySelectorAll('.left-tab').forEach((b) => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  els.filesTab.classList.toggle('hidden', tab !== 'files');
  els.graphTab.classList.toggle('hidden', tab !== 'graph');
  els.searchTab.classList.toggle('hidden', tab !== 'search');
  if (tab === 'graph') renderGraph();
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
    el.className = `editor-tab ${state.activeTab === tab.path ? 'active' : ''}`;
    el.textContent = tab.path.split('/').pop();
    el.title = tab.path;
    el.onclick = () => activateTab(tab.path);
    els.tabs.appendChild(el);
  }
}

function activateTab(path) {
  const tab = state.openTabs.find((t) => t.path === path);
  if (!tab) return;
  state.activeTab = path;
  els.editor.value = tab.content;
  els.currentFile.textContent = path;
  renderTabs();
}

async function openFile(path) {
  let tab = state.openTabs.find((t) => t.path === path);
  if (!tab) {
    const content = await window.acquittifyApi.readVaultFile(path);
    tab = { path, content };
    state.openTabs.push(tab);
  }
  activateTab(path);
}

async function saveActive() {
  if (!state.activeTab) return;
  const tab = state.openTabs.find((t) => t.path === state.activeTab);
  if (!tab) return;
  tab.content = els.editor.value;
  await window.acquittifyApi.writeVaultFile(tab.path, tab.content);
  addMessage('assistant', `Saved ${tab.path}`);
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
  state.graph = await window.acquittifyApi.getGraph();
}

function renderGraph() {
  const canvas = els.graphCanvas;
  const ctx = canvas.getContext('2d');
  const { nodes, edges } = state.graph;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!nodes.length) return;

  const n = Math.min(nodes.length, 120);
  const radius = Math.min(canvas.width, canvas.height) * 0.38;
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const positions = new Map();

  for (let i = 0; i < n; i++) {
    const a = (2 * Math.PI * i) / n;
    positions.set(nodes[i].id, {
      x: cx + Math.cos(a) * radius,
      y: cy + Math.sin(a) * radius
    });
  }

  ctx.strokeStyle = '#2b3b55';
  ctx.lineWidth = 1;
  edges.slice(0, 220).forEach((e) => {
    const s = positions.get(e.source);
    const t = positions.get(e.target);
    if (!s || !t) return;
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);
    ctx.stroke();
  });

  for (let i = 0; i < n; i++) {
    const node = nodes[i];
    const p = positions.get(node.id);
    ctx.fillStyle = '#60a5fa';
    ctx.beginPath();
    ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.fillStyle = '#94a3b8';
  ctx.font = '12px sans-serif';
  ctx.fillText(`Nodes: ${nodes.length}  Edges: ${edges.length}`, 10, 18);
}

async function runAgent() {
  const prompt = els.agentInput.value.trim();
  if (!prompt) return;
  addMessage('user', prompt);
  els.agentInput.value = '';
  try {
    const res = await window.acquittifyApi.runAgent(prompt);
    addMessage('assistant', res.answer, `Sources: ${res.contextPaths.join(', ')}`);
  } catch (e) {
    addMessage('assistant', `Agent error: ${e.message}`);
  }
}

function wireEvents() {
  document.querySelectorAll('.left-tab').forEach((btn) => {
    btn.onclick = () => setActiveLeftTab(btn.dataset.tab);
  });
  els.saveBtn.onclick = saveActive;
  els.refreshBtn.onclick = async () => {
    await loadTree();
    await loadGraph();
    renderGraph();
  };
  els.globalSearch.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter') await performSearch(els.globalSearch.value);
  });
  els.agentSend.onclick = runAgent;
  els.agentInput.addEventListener('keydown', async (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') await runAgent();
  });
  els.editor.addEventListener('input', () => {
    const tab = state.openTabs.find((t) => t.path === state.activeTab);
    if (tab) tab.content = els.editor.value;
  });
}

async function init() {
  const { root } = await window.acquittifyApi.getVaultRoot();
  state.vaultRoot = root;
  els.vaultPath.textContent = root;
  wireEvents();
  await loadTree();
  await loadGraph();
  addMessage('assistant', 'Agent ready. Ask to retrieve notes, summarize material, or propose taxonomy/ontology edits.');
}

init();
