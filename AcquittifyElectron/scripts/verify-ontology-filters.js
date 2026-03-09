#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..');
const MAIN_PATH = path.join(REPO_ROOT, 'main.js');
const REPORT_ROOT = path.resolve(REPO_ROOT, '..', 'reports');
const DEFAULT_VAULT_ROOT = process.env.ACQUITTIFY_PRECEDENT_VAULT_ROOT || process.env.ACQUITTIFY_VAULT_ROOT ||
  path.resolve(REPO_ROOT, '..', 'Obsidian', 'Ontology', 'precedent_vault');

const ONTOLOGY_RELATION_TYPES = [
  'applies',
  'clarifies',
  'extends',
  'distinguishes',
  'limits',
  'overrules',
  'questions'
];

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
  nodeTypes: ['case', 'constitution'],
  relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
  citationType: 'all',
  courtLevel: 'all',
  originatingCircuit: 'all',
  normativeStrength: 'all',
  factDimension: '',
  minEdgeStrength: null,
  minCaseImportance: null,
  maxEdgesPerNode: null,
  pfMin: null,
  consensusMin: null,
  driftMax: null,
  relationConfidenceMin: null,
  maxNodes: 20000
};

const ONTOLOGY_REPRESENTATIVE_CASE_LIMIT = 2500;
const ONTOLOGY_CIRCUIT_LABELS = {
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

function courtLevelBucket(value) {
  const raw = String(value || '').toLowerCase();
  if (!raw) return '';
  if (raw.includes('supreme') || raw === 'scotus') return 'supreme';
  if (raw.includes('district')) return 'district';
  if (raw.includes('circuit') || /^ca\d{1,2}$/.test(raw)) return 'circuit';
  return raw;
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
  return '';
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

function edgePassesOntologyFilters(edge, filters, nodeLookup) {
  if (!edge) return false;
  if (!nodeLookup.has(edge.source) || !nodeLookup.has(edge.target)) return false;

  const selectedRelationTypes = Array.isArray(filters?.relationTypes)
    ? filters.relationTypes.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : [];
  const relationFilterActive = selectedRelationTypes.length !== ONTOLOGY_RELATION_TYPES.length;
  const canonicalRelationType = canonicalOntologyRelationTypeFromEdge(edge);
  if (relationFilterActive) {
    if (!canonicalRelationType) return false;
    if (!selectedRelationTypes.includes(canonicalRelationType)) return false;
  } else if (canonicalRelationType && selectedRelationTypes.length && !selectedRelationTypes.includes(canonicalRelationType)) {
    return false;
  }

  if (filters.citationType !== 'all') {
    const citationType = String(edge.citationType || '').toLowerCase();
    if (!citationType) return false;
    if (citationType !== filters.citationType) return false;
  }

  if (filters.relationConfidenceMin !== null) {
    const confidence = Number(edge.confidence);
    if (!Number.isFinite(confidence)) return false;
    if (confidence < filters.relationConfidenceMin) return false;
  }

  return true;
}

function normalizeFilterInput(patch = {}, allNodeTypes = []) {
  const normalizedNodeTypes = Array.isArray(patch.nodeTypes)
    ? patch.nodeTypes.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : ONTOLOGY_FILTER_DEFAULTS.nodeTypes.slice();
  const normalizedRelationTypes = Array.isArray(patch.relationTypes)
    ? patch.relationTypes.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : ONTOLOGY_FILTER_DEFAULTS.relationTypes.slice();
  const preset = normalizeOntologyPreset(patch.viewPreset || ONTOLOGY_FILTER_DEFAULTS.viewPreset);
  const profile = getOntologyPresetProfile(preset);

  const minEdgeStrengthInput = patch.minEdgeStrength === undefined ? ONTOLOGY_FILTER_DEFAULTS.minEdgeStrength : patch.minEdgeStrength;
  const minCaseImportanceInput = patch.minCaseImportance === undefined ? ONTOLOGY_FILTER_DEFAULTS.minCaseImportance : patch.minCaseImportance;
  const maxEdgesPerNodeInput = patch.maxEdgesPerNode === undefined ? ONTOLOGY_FILTER_DEFAULTS.maxEdgesPerNode : patch.maxEdgesPerNode;
  const unconstrainedPreset = preset === 'full_ontology';

  const minEdgeStrength =
    minEdgeStrengthInput === null || minEdgeStrengthInput === ''
      ? (unconstrainedPreset ? null : clamp01(profile.minEdgeStrength))
      : clamp01(minEdgeStrengthInput);
  const minCaseImportance =
    minCaseImportanceInput === null || minCaseImportanceInput === ''
      ? (unconstrainedPreset ? null : clamp01(profile.minCaseImportance))
      : clamp01(minCaseImportanceInput);
  const maxEdgesPerNode =
    maxEdgesPerNodeInput === null || maxEdgesPerNodeInput === ''
      ? (unconstrainedPreset ? null : Math.max(1, Math.min(250, Number(profile.maxEdgesPerNode) || 1)))
      : Math.max(1, Math.min(250, Math.round(Number(maxEdgesPerNodeInput) || 1)));

  return {
    ...ONTOLOGY_FILTER_DEFAULTS,
    viewPreset: preset,
    query: String(patch.query ?? ONTOLOGY_FILTER_DEFAULTS.query).trim(),
    nodeTypes: normalizedNodeTypes.length ? normalizedNodeTypes : (allNodeTypes.length ? allNodeTypes.slice() : []),
    relationTypes: normalizedRelationTypes,
    citationType: String(patch.citationType ?? ONTOLOGY_FILTER_DEFAULTS.citationType).toLowerCase(),
    courtLevel: String(patch.courtLevel ?? ONTOLOGY_FILTER_DEFAULTS.courtLevel).toLowerCase(),
    originatingCircuit: String(patch.originatingCircuit ?? ONTOLOGY_FILTER_DEFAULTS.originatingCircuit).toLowerCase(),
    normativeStrength: String(patch.normativeStrength ?? ONTOLOGY_FILTER_DEFAULTS.normativeStrength).toLowerCase(),
    factDimension: String(patch.factDimension ?? ONTOLOGY_FILTER_DEFAULTS.factDimension).trim().toLowerCase(),
    minEdgeStrength,
    minCaseImportance,
    maxEdgesPerNode,
    pfMin: patch.pfMin === '' || patch.pfMin === undefined ? ONTOLOGY_FILTER_DEFAULTS.pfMin : Number(patch.pfMin),
    consensusMin:
      patch.consensusMin === '' || patch.consensusMin === undefined
        ? ONTOLOGY_FILTER_DEFAULTS.consensusMin
        : Number(patch.consensusMin),
    driftMax: patch.driftMax === '' || patch.driftMax === undefined ? ONTOLOGY_FILTER_DEFAULTS.driftMax : Number(patch.driftMax),
    relationConfidenceMin:
      patch.relationConfidenceMin === '' || patch.relationConfidenceMin === undefined
        ? ONTOLOGY_FILTER_DEFAULTS.relationConfidenceMin
        : Number(patch.relationConfidenceMin),
    maxNodes: Math.max(100, Math.min(20000, Number(patch.maxNodes ?? ONTOLOGY_FILTER_DEFAULTS.maxNodes) || ONTOLOGY_FILTER_DEFAULTS.maxNodes))
  };
}

function applyFilterPipeline(graph, patch = {}, allNodeTypes = []) {
  const filters = normalizeFilterInput(patch, allNodeTypes);
  const allNodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const allEdges = Array.isArray(graph?.edges) ? graph.edges : [];

  const filteredNodes = allNodes.filter((node) => nodePassesOntologyFilters(node, filters));
  const filteredNodeMap = new Map(filteredNodes.map((node) => [node.id, node]));
  const filteredEdges = allEdges.filter((edge) => edgePassesOntologyFilters(edge, filters, filteredNodeMap));

  const preset = normalizeOntologyPreset(filters.viewPreset);
  const minEdgeStrength = filters.minEdgeStrength === null || filters.minEdgeStrength === '' ? null : clamp01(filters.minEdgeStrength);
  const minCaseImportance =
    filters.minCaseImportance === null || filters.minCaseImportance === '' ? null : clamp01(filters.minCaseImportance);
  const maxEdgesPerNodeValue = Number(filters.maxEdgesPerNode);
  const maxEdgesPerNode =
    Number.isFinite(maxEdgesPerNodeValue) && maxEdgesPerNodeValue > 0
      ? Math.max(1, Math.min(250, Math.round(maxEdgesPerNodeValue)))
      : null;

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
  if (caseNodesAfterImportance.length > ONTOLOGY_REPRESENTATIVE_CASE_LIMIT) {
    sampledCaseNodes = buildRepresentativeCaseSample(caseNodesAfterImportance, ONTOLOGY_REPRESENTATIVE_CASE_LIMIT, caseImportanceById);
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
    if (nodeType === 'source') return 0;
    if (nodeType === 'issue') return 1;
    if (nodeType === 'holding') return 2;
    if (nodeType === 'relation') return 3;
    if (nodeType === 'secondary') return 4;
    if (nodeType === 'event') return 5;
    if (nodeType === 'external_case') return 6;
    return 7;
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
    ? Math.min(rankedNonCaseNodes.length, Math.max(40, Math.floor(maxNodes * 0.2)), Math.max(0, maxNodes - 25))
    : 0;
  const caseBudget = Math.max(1, maxNodes - nonCaseReserve);
  const selectedCaseNodes = rankedCaseNodes.slice(0, caseBudget);
  const selectedNonCaseNodes = rankedNonCaseNodes.slice(0, Math.max(0, maxNodes - selectedCaseNodes.length));
  const chosenNodes = selectedCaseNodes.concat(selectedNonCaseNodes);
  const chosenNodeIds = new Set(chosenNodes.map((node) => node.id));
  const visibleEdgeRows = edgeRows.filter((row) => chosenNodeIds.has(row.source) && chosenNodeIds.has(row.target));

  const canonicalRelationCounts = {};
  for (const row of visibleEdgeRows) {
    const key = canonicalOntologyRelationTypeFromEdge(row.edge) || 'none';
    canonicalRelationCounts[key] = (canonicalRelationCounts[key] || 0) + 1;
  }

  return {
    filters,
    nodes: chosenNodes,
    edgeRows: visibleEdgeRows,
    nodeCount: chosenNodes.length,
    edgeCount: visibleEdgeRows.length,
    canonicalRelationCounts,
    caseImportanceById
  };
}

function countBy(items = [], keyFn = () => '') {
  const out = {};
  for (const item of items) {
    const key = String(keyFn(item) || '').trim() || 'unknown';
    out[key] = (out[key] || 0) + 1;
  }
  return out;
}

function pickTopKey(counts = {}, predicate = () => true) {
  return Object.entries(counts)
    .filter(([key, value]) => predicate(key, value))
    .sort((a, b) => {
      const delta = Number(b[1] || 0) - Number(a[1] || 0);
      if (delta) return delta;
      return String(a[0]).localeCompare(String(b[0]));
    })[0]?.[0] || '';
}

function makeElectronStub(mainPath) {
  return {
    app: {
      whenReady: () => new Promise(() => {}),
      on: () => {},
      quit: () => {},
      getPath: () => '/tmp',
      getAppPath: () => path.dirname(mainPath),
      isPackaged: false,
      relaunch: () => {},
      exit: () => {},
      requestSingleInstanceLock: () => true
    },
    BrowserWindow: function BrowserWindowStub() {},
    ipcMain: { handle: () => {} },
    dialog: { showOpenDialog: async () => ({ canceled: true, filePaths: [] }) }
  };
}

function loadBuildOntologyGraph() {
  const code = fs.readFileSync(MAIN_PATH, 'utf8');
  const electronStub = makeElectronStub(MAIN_PATH);
  const sandboxRequire = (id) => {
    if (id === 'electron') return electronStub;
    return require(require.resolve(id, { paths: [path.dirname(MAIN_PATH)] }));
  };
  const sandbox = {
    require: sandboxRequire,
    module: { exports: {} },
    exports: {},
    __dirname: path.dirname(MAIN_PATH),
    __filename: MAIN_PATH,
    process,
    console,
    Buffer,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval
  };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: MAIN_PATH });
  if (typeof sandbox.buildOntologyGraph !== 'function') {
    throw new Error('Unable to load buildOntologyGraph from main.js');
  }
  return sandbox.buildOntologyGraph;
}

function ensureSearchToken(nodes = []) {
  for (const node of nodes) {
    if (String(node?.nodeType || '').toLowerCase() !== 'case') continue;
    const title = String(node.caseTitle || node.label || '').toLowerCase();
    if (!title.includes(' v. ')) continue;
    const tokens = title
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .map((item) => item.trim())
      .filter((item) => item.length >= 4 && item !== 'case' && item !== 'unknown');
    if (tokens.length) return tokens[0];
  }
  return '';
}

function allNodesMatch(nodes = [], predicate = () => true) {
  for (const node of nodes) {
    if (!predicate(node)) return false;
  }
  return true;
}

function allEdgesMatch(rows = [], predicate = () => true) {
  for (const row of rows) {
    if (!predicate(row.edge, row)) return false;
  }
  return true;
}

function run() {
  const vaultRoot = path.resolve(process.argv[2] || DEFAULT_VAULT_ROOT);
  const limit = Math.max(500, Number(process.argv[3] || 20000) || 20000);
  const buildOntologyGraph = loadBuildOntologyGraph();
  const graph = buildOntologyGraph(vaultRoot, limit);

  const graphNodeTypes = Array.from(new Set((graph.nodes || []).map((node) => String(node?.nodeType || '').toLowerCase()).filter(Boolean))).sort();
  const allNodeTypes = graphNodeTypes.length ? graphNodeTypes : ONTOLOGY_FILTER_DEFAULTS.nodeTypes.slice();
  const baseline = applyFilterPipeline(
    graph,
    {
      viewPreset: 'full_ontology',
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      maxNodes: 20000,
      minEdgeStrength: null,
      minCaseImportance: null,
      maxEdgesPerNode: null
    },
    allNodeTypes
  );

  const canonicalRelationCountsAll = countBy(graph.edges || [], (edge) => canonicalOntologyRelationTypeFromEdge(edge) || 'none');
  const citationTypeCountsAll = countBy(graph.edges || [], (edge) => String(edge?.citationType || '').toLowerCase() || 'none');
  const courtBucketCountsAll = countBy(graph.nodes || [], (node) => courtLevelBucket(node?.courtLevel || node?.court || '') || 'none');
  const circuitCountsAll = countBy(
    (graph.nodes || []).filter((node) => String(node?.nodeType || '').toLowerCase() === 'case'),
    (node) => normalizeOriginatingCircuit(node?.originatingCircuit || node?.originatingCircuitLabel || '') || 'none'
  );
  const normativeStrengthCounts = countBy(
    (graph.nodes || []).filter((node) => String(node?.nodeType || '').toLowerCase() === 'holding'),
    (node) => String(node?.normativeStrength || '').toLowerCase() || 'none'
  );
  const factDimensionCounts = {};
  for (const node of graph.nodes || []) {
    const dims = Array.isArray(node?.factDimensions) ? node.factDimensions : [];
    for (const dim of dims) {
      const key = String(dim || '').trim().toLowerCase();
      if (!key) continue;
      factDimensionCounts[key] = (factDimensionCounts[key] || 0) + 1;
    }
  }
  const pfValues = (graph.nodes || [])
    .map((node) => Number(node?.pfHolding ?? node?.pfIssue))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  const issueConsensusValues = (graph.nodes || [])
    .filter((node) => String(node?.nodeType || '').toLowerCase() === 'issue')
    .map((node) => Number(node?.consensus))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  const issueDriftValues = (graph.nodes || [])
    .filter((node) => String(node?.nodeType || '').toLowerCase() === 'issue')
    .map((node) => Number(node?.drift))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  const queryToken = ensureSearchToken(graph.nodes || []);

  const tests = [];
  const addResult = (id, description, status, details = {}) => {
    tests.push({ id, description, status, ...details });
  };

  const runTest = (id, description, filters, evaluator, enabled = true, skipReason = '') => {
    if (!enabled) {
      addResult(id, description, 'skipped', { reason: skipReason || 'not_applicable' });
      return;
    }
    const result = applyFilterPipeline(graph, filters, allNodeTypes);
    let pass = false;
    let info = {};
    try {
      const evaluation = evaluator(result);
      pass = Boolean(evaluation?.pass);
      info = evaluation?.details || {};
    } catch (err) {
      pass = false;
      info = { error: err?.message || String(err) };
    }
    addResult(id, description, pass ? 'pass' : 'fail', {
      rendered: { nodes: result.nodeCount, edges: result.edgeCount },
      filters: result.filters,
      ...info
    });
  };

  runTest(
    'baseline_full',
    'Full ontology baseline returns non-empty graph',
    {
      viewPreset: 'full_ontology',
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      maxNodes: 20000
    },
    (result) => ({
      pass: result.nodeCount > 0 && result.edgeCount > 0,
      details: {}
    })
  );

  runTest(
    'node_types_source',
    'Node type filter isolates source nodes',
    {
      nodeTypes: ['source'],
      viewPreset: 'full_ontology',
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      maxNodes: 20000
    },
    (result) => ({
      pass: result.nodeCount > 0 && allNodesMatch(result.nodes, (node) => String(node?.nodeType || '').toLowerCase() === 'source'),
      details: {}
    }),
    graphNodeTypes.includes('source'),
    'no_source_nodes'
  );

  runTest(
    'node_types_case_external',
    'Node type filter isolates case/external_case nodes',
    {
      nodeTypes: ['case', 'external_case'],
      viewPreset: 'full_ontology',
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.nodeCount > 0 &&
        allNodesMatch(result.nodes, (node) => {
          const nodeType = String(node?.nodeType || '').toLowerCase();
          return nodeType === 'case' || nodeType === 'external_case';
        }),
      details: {}
    })
  );

  runTest(
    'relation_only_applies',
    'Relation filter keeps only applies canonical edges',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ['applies'],
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.edgeCount > 0 &&
        allEdgesMatch(result.edgeRows, (edge) => canonicalOntologyRelationTypeFromEdge(edge) === 'applies'),
      details: {}
    }),
    Number(canonicalRelationCountsAll.applies || 0) > 0,
    'no_applies_edges'
  );

  runTest(
    'relation_exclude_ace',
    'Relation filter excluding applies/clarifies/extends removes those canonical types',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ['distinguishes', 'limits', 'overrules', 'questions'],
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass: allEdgesMatch(result.edgeRows, (edge) => {
        const c = canonicalOntologyRelationTypeFromEdge(edge);
        return !['applies', 'clarifies', 'extends'].includes(c);
      }),
      details: {}
    })
  );

  runTest(
    'citation_type_controlling',
    'Citation type filter keeps only controlling edges',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      citationType: 'controlling',
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.edgeCount > 0 &&
        allEdgesMatch(result.edgeRows, (edge) => String(edge?.citationType || '').toLowerCase() === 'controlling'),
      details: {}
    }),
    Number(citationTypeCountsAll.controlling || 0) > 0,
    'no_controlling_citation_edges'
  );

  runTest(
    'court_level_supreme',
    'Court level filter keeps supreme-level nodes',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      courtLevel: 'supreme',
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.nodeCount > 0 &&
        allNodesMatch(result.nodes, (node) => courtLevelBucket(node?.courtLevel || node?.court || '') === 'supreme'),
      details: {}
    }),
    Number(courtBucketCountsAll.supreme || 0) > 0,
    'no_supreme_nodes'
  );

  const topCircuit = pickTopKey(circuitCountsAll, (key) => key && key !== 'none');
  runTest(
    'originating_circuit',
    `Originating circuit filter keeps case nodes in ${topCircuit || 'selected circuit'}`,
    {
      nodeTypes: ['case'],
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      originatingCircuit: topCircuit,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.nodeCount > 0 &&
        allNodesMatch(
          result.nodes,
          (node) => normalizeOriginatingCircuit(node?.originatingCircuit || node?.originatingCircuitLabel || '') === topCircuit
        ),
      details: {}
    }),
    Boolean(topCircuit),
    'no_circuit_metadata'
  );

  const topNormativeStrength = pickTopKey(normativeStrengthCounts, (key) => key && key !== 'none');
  runTest(
    'normative_strength',
    `Normative strength filter isolates holding.${topNormativeStrength || 'unknown'}`,
    {
      nodeTypes: ['holding'],
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      normativeStrength: topNormativeStrength,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.nodeCount > 0 &&
        allNodesMatch(
          result.nodes,
          (node) =>
            String(node?.nodeType || '').toLowerCase() === 'holding' &&
            String(node?.normativeStrength || '').toLowerCase() === topNormativeStrength
        ),
      details: {}
    }),
    Boolean(topNormativeStrength),
    'no_holding_normative_strength'
  );

  const topFactDimension = pickTopKey(factDimensionCounts, (key) => key);
  runTest(
    'fact_dimension',
    `Fact dimension filter matches '${topFactDimension || ''}'`,
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      factDimension: topFactDimension,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.nodeCount > 0 &&
        allNodesMatch(result.nodes, (node) => {
          const dims = Array.isArray(node?.factDimensions) ? node.factDimensions.map((item) => String(item || '').toLowerCase()) : [];
          return dims.some((dim) => dim.includes(topFactDimension));
        }),
      details: {}
    }),
    Boolean(topFactDimension),
    'no_fact_dimensions'
  );

  runTest(
    'min_edge_strength',
    'Minimum edge strength threshold enforces edge strength floor',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      minEdgeStrength: 0.9,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass: allEdgesMatch(result.edgeRows, (edge) => ontologyEdgeStrength(edge) >= 0.9),
      details: {}
    })
  );

  runTest(
    'min_case_importance',
    'Minimum case importance threshold enforces case-importance floor',
    {
      nodeTypes: ['case'],
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      minCaseImportance: 0.6,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass: allNodesMatch(result.nodes, (node) => Number(result.caseImportanceById.get(node.id) || 0) >= 0.6),
      details: {}
    })
  );

  runTest(
    'max_edges_per_node',
    'Max edges per node reduces or maintains edge count',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      maxEdgesPerNode: 5,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass: result.edgeCount <= baseline.edgeCount,
      details: { baselineEdges: baseline.edgeCount }
    })
  );

  runTest(
    'relation_confidence_min',
    'Relation confidence threshold keeps only high-confidence edges',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      relationConfidenceMin: 0.9,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.edgeCount > 0 &&
        allEdgesMatch(result.edgeRows, (edge) => Number.isFinite(Number(edge?.confidence)) && Number(edge?.confidence) >= 0.9),
      details: {}
    }),
    (graph.edges || []).some((edge) => Number.isFinite(Number(edge?.confidence)) && Number(edge.confidence) >= 0.9),
    'no_high_confidence_edges'
  );

  runTest(
    'max_nodes',
    'Max node cap is honored',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      maxNodes: 500,
      viewPreset: 'full_ontology'
    },
    (result) => ({
      pass: result.nodeCount <= 500,
      details: {}
    })
  );

  runTest(
    'search_query',
    `Search filter token '${queryToken || ''}' restricts node search text`,
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      query: queryToken,
      viewPreset: 'full_ontology',
      maxNodes: 20000
    },
    (result) => ({
      pass:
        result.nodeCount > 0 &&
        allNodesMatch(result.nodes, (node) => String(node?.searchText || '').toLowerCase().includes(queryToken)),
      details: {}
    }),
    Boolean(queryToken),
    'no_query_token'
  );

  if (pfValues.length) {
    const medianPf = pfValues[Math.floor(pfValues.length / 2)];
    runTest(
      'pf_min',
      'PF minimum filter enforces PF threshold on PF-bearing nodes',
      {
        nodeTypes: allNodeTypes,
        relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
        pfMin: medianPf,
        viewPreset: 'full_ontology',
        maxNodes: 20000
      },
      (result) => ({
        pass: allNodesMatch(result.nodes, (node) => {
          const pf = node?.pfHolding ?? node?.pfIssue;
          if (pf === null || pf === undefined) return true;
          return Number(pf) >= medianPf;
        }),
        details: { threshold: medianPf }
      })
    );
  } else {
    addResult('pf_min', 'PF minimum filter enforces PF threshold on PF-bearing nodes', 'skipped', {
      reason: 'no_pf_values'
    });
  }

  if (issueConsensusValues.length) {
    const threshold = issueConsensusValues[Math.floor(issueConsensusValues.length / 2)];
    runTest(
      'consensus_min',
      'Consensus minimum filter enforces issue consensus threshold',
      {
        nodeTypes: ['issue'],
        relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
        consensusMin: threshold,
        viewPreset: 'full_ontology',
        maxNodes: 20000
      },
      (result) => ({
        pass: allNodesMatch(result.nodes, (node) => Number(node?.consensus) >= threshold),
        details: { threshold }
      })
    );
  } else {
    addResult('consensus_min', 'Consensus minimum filter enforces issue consensus threshold', 'skipped', {
      reason: 'no_issue_consensus_values'
    });
  }

  if (issueDriftValues.length) {
    const threshold = issueDriftValues[Math.floor(issueDriftValues.length / 2)];
    runTest(
      'drift_max',
      'Drift maximum filter enforces issue drift threshold',
      {
        nodeTypes: ['issue'],
        relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
        driftMax: threshold,
        viewPreset: 'full_ontology',
        maxNodes: 20000
      },
      (result) => ({
        pass: allNodesMatch(result.nodes, (node) => Number(node?.drift) <= threshold),
        details: { threshold }
      })
    );
  } else {
    addResult('drift_max', 'Drift maximum filter enforces issue drift threshold', 'skipped', {
      reason: 'no_issue_drift_values'
    });
  }

  runTest(
    'preset_constitutional',
    'Constitutional preset only allows constitutional/core edge families',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      viewPreset: 'constitutional',
      maxNodes: 20000
    },
    (result) => ({
      pass: allEdgesMatch(result.edgeRows, (edge) => ontologyEdgeAllowedByPreset(edge, 'constitutional')),
      details: {}
    })
  );

  runTest(
    'preset_statutory_regulatory',
    'Statutory/regulatory preset only allows statutory/regulatory/core edge families',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      viewPreset: 'statutory_regulatory',
      maxNodes: 20000
    },
    (result) => ({
      pass: allEdgesMatch(result.edgeRows, (edge) => ontologyEdgeAllowedByPreset(edge, 'statutory_regulatory')),
      details: {}
    })
  );

  runTest(
    'preset_core_precedent',
    'Core precedent preset only allows core precedent edge families',
    {
      nodeTypes: allNodeTypes,
      relationTypes: ONTOLOGY_RELATION_TYPES.slice(),
      viewPreset: 'core_precedent',
      maxNodes: 20000
    },
    (result) => ({
      pass: allEdgesMatch(result.edgeRows, (edge) => ontologyEdgeAllowedByPreset(edge, 'core_precedent')),
      details: {}
    })
  );

  const summary = {
    total: tests.length,
    pass: tests.filter((item) => item.status === 'pass').length,
    fail: tests.filter((item) => item.status === 'fail').length,
    skipped: tests.filter((item) => item.status === 'skipped').length
  };

  const report = {
    generated_at: new Date().toISOString(),
    vault_root: vaultRoot,
    limit,
    graph: {
      nodes: Array.isArray(graph?.nodes) ? graph.nodes.length : 0,
      edges: Array.isArray(graph?.edges) ? graph.edges.length : 0,
      node_type_counts: graph?.meta?.nodeTypeCounts || {},
      edge_type_counts: graph?.meta?.edgeTypeCounts || {},
      canonical_relation_counts: canonicalRelationCountsAll,
      citation_type_counts: citationTypeCountsAll,
      court_bucket_counts: courtBucketCountsAll,
      circuit_counts: circuitCountsAll
    },
    baseline_rendered: {
      nodes: baseline.nodeCount,
      edges: baseline.edgeCount
    },
    summary,
    tests
  };

  fs.mkdirSync(REPORT_ROOT, { recursive: true });
  const reportPath = path.join(
    REPORT_ROOT,
    `ontology_filter_audit_${new Date().toISOString().replace(/[:.]/g, '-')}.json`
  );
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), 'utf8');

  const prefix = '[ontology-filter-audit]';
  console.log(`${prefix} vault: ${vaultRoot}`);
  console.log(`${prefix} graph: nodes ${report.graph.nodes}, edges ${report.graph.edges}`);
  console.log(`${prefix} baseline: nodes ${baseline.nodeCount}, edges ${baseline.edgeCount}`);
  console.log(
    `${prefix} tests: pass ${summary.pass}, fail ${summary.fail}, skipped ${summary.skipped}, total ${summary.total}`
  );
  console.log(`${prefix} report: ${reportPath}`);

  if (summary.fail > 0) {
    process.exit(1);
  }
}

run();
