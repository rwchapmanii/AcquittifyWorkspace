import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "../../../styles/ontologyDesktop.module.css";
import { API_BASE, apiFetch } from "../../../lib/api";

type OntologyNode = {
  id: string;
  label?: string;
  type?: string;
  nodeType?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

type OntologyEdge = {
  id?: string;
  from?: string;
  to?: string;
  source?: string;
  target?: string;
  type?: string;
  edgeType?: string;
  relationType?: string;
  weight?: number;
  confidence?: number;
  [key: string]: unknown;
};

type OntologyMeta = {
  matter_id?: string;
  node_count?: number;
  edge_count?: number;
  documents_loaded?: number;
  truncated_documents?: boolean;
  source?: string;
  [key: string]: unknown;
};

type OntologyPayload = {
  nodes: OntologyNode[];
  edges: OntologyEdge[];
  meta: OntologyMeta;
};

type BootstrapReviewResponse = {
  enqueued?: number;
  enqueued_tasks?: number;
  skipped?: number;
};

type PreparedNode = {
  id: string;
  label: string;
  nodeType: string;
  metadata: Record<string, unknown>;
  raw: OntologyNode;
};

type EdgeRow = {
  source: string;
  target: string;
  edgeType: string;
  edge: OntologyEdge;
};

type RefreshTone = "neutral" | "working" | "ok" | "error";
type OntologyViewMode = "casefile" | "caselaw";

type HoverCardState = {
  nodeId: string;
  x: number;
  y: number;
} | null;

const DEFAULT_MAX_DOCUMENTS = 2500;
const CASELAW_NODE_TYPES = new Set([
  "case",
  "external_case",
  "holding",
  "issue",
  "constitution",
  "statute",
  "regulation",
  "taxonomy",
  "relation",
  "source",
  "secondary",
  "knowledge",
  "topic",
  "document_type",
]);
const CASELAW_HINT_PATTERN =
  /\b(v\.|vs\.|f\.\s?3d|f\.\s?2d|f\.\s?supp|u\.s\.|s\.?\s?ct\.|cir\.|circuit|precedent|certiorari)\b/i;
const CIRCUIT_MATCHERS: Record<string, RegExp[]> = {
  "Supreme Court": [/\bsupreme court\b/i, /\bscotus\b/i, /\bu\.s\.\b/i, /\bs\.?\s?ct\.\b/i],
  "First Circuit": [/\b1st\s+cir(cuit)?\b/i, /\bfirst\s+cir(cuit)?\b/i],
  "Second Circuit": [/\b2d\s+cir(cuit)?\b/i, /\b2nd\s+cir(cuit)?\b/i, /\bsecond\s+cir(cuit)?\b/i],
  "Third Circuit": [/\b3d\s+cir(cuit)?\b/i, /\b3rd\s+cir(cuit)?\b/i, /\bthird\s+cir(cuit)?\b/i],
  "Fourth Circuit": [/\b4th\s+cir(cuit)?\b/i, /\bfourth\s+cir(cuit)?\b/i],
  "Fifth Circuit": [/\b5th\s+cir(cuit)?\b/i, /\bfifth\s+cir(cuit)?\b/i],
  "Sixth Circuit": [/\b6th\s+cir(cuit)?\b/i, /\bsixth\s+cir(cuit)?\b/i],
  "Seventh Circuit": [/\b7th\s+cir(cuit)?\b/i, /\bseventh\s+cir(cuit)?\b/i],
  "Eighth Circuit": [/\b8th\s+cir(cuit)?\b/i, /\beighth\s+cir(cuit)?\b/i],
  "Ninth Circuit": [/\b9th\s+cir(cuit)?\b/i, /\bninth\s+cir(cuit)?\b/i],
  "Tenth Circuit": [/\b10th\s+cir(cuit)?\b/i, /\btenth\s+cir(cuit)?\b/i],
  "Eleventh Circuit": [/\b11th\s+cir(cuit)?\b/i, /\beleventh\s+cir(cuit)?\b/i],
  "D.C. Circuit": [/\bd\.?\s?c\.?\s+cir(cuit)?\b/i, /\bdistrict of columbia circuit\b/i],
};

const ONTOLOGY_NODE_COLORS: Record<string, string> = {
  case: "#60a5fa",
  constitution: "#ef4444",
  statute: "#f97316",
  indictment: "#f97316",
  count: "#38bdf8",
  witness: "#34d399",
  transcript: "#60a5fa",
  exhibit: "#f59e0b",
  regulation: "#06b6d4",
  taxonomy: "#facc15",
  external_case: "#64748b",
  holding: "#34d399",
  issue: "#f59e0b",
  relation: "#f472b6",
  source: "#c084fc",
  secondary: "#fb7185",
  event: "#a3e635",
  unknown: "#a3a3a3",
};

function normalizeNodeType(node: OntologyNode): string {
  const raw = String(node.type || node.nodeType || "unknown").trim().toLowerCase();
  return raw || "unknown";
}

function normalizeEdgeType(edge: OntologyEdge): string {
  const raw = String(edge.edgeType || edge.type || edge.relationType || "").trim().toLowerCase();
  return raw || "related";
}

function normalizeNodeLabel(node: OntologyNode): string {
  const raw = String(node.label || node.id || "").trim();
  return raw || String(node.id || "node");
}

function toMetadata(node: OntologyNode): Record<string, unknown> {
  if (node.metadata && typeof node.metadata === "object" && !Array.isArray(node.metadata)) {
    return node.metadata;
  }
  return {};
}

function ontologyEdgeColor(edgeType: string): string {
  if (edgeType === "constitution_citation") return "#ef4444";
  if (edgeType === "taxonomy_edge") return "#facc15";
  if (edgeType === "usc_title_citation") return "#f97316";
  if (edgeType === "cfr_title_citation") return "#06b6d4";
  if (edgeType === "case_citation") return "#60a5fa";
  return "#4a4a4a";
}

function ontologyEdgeWidth(edgeType: string): number {
  if (edgeType === "constitution_citation") return 2.35;
  if (edgeType === "taxonomy_edge") return 1.6;
  if (edgeType === "usc_title_citation") return 1.9;
  if (edgeType === "cfr_title_citation") return 1.75;
  if (edgeType === "case_citation") return 1.4;
  return 1.0;
}

function truncateText(value: unknown, max = 180): string {
  const compact = String(value || "").replace(/\s+/g, " ").trim();
  if (!compact) return "";
  if (compact.length <= max) return compact;
  return `${compact.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatMetadataValue(item)).join(", ");
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function toStringList(value: unknown, limit = 8): string[] {
  if (!Array.isArray(value)) return [];
  const output: string[] = [];
  const seen = new Set<string>();
  for (const raw of value) {
    const text = String(raw || "").replace(/\s+/g, " ").trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(text);
    if (output.length >= limit) break;
  }
  return output;
}

function nodeMatchesQuery(node: PreparedNode, query: string): boolean {
  if (!query) return true;
  const target = query.toLowerCase();
  if (node.label.toLowerCase().includes(target)) return true;
  if (node.nodeType.toLowerCase().includes(target)) return true;
  return Object.values(node.metadata).some((value) => {
    if (value === null || value === undefined) return false;
    if (typeof value === "string") return value.toLowerCase().includes(target);
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value).toLowerCase().includes(target);
    }
    return false;
  });
}

function parseFilterTerms(value: string): string[] {
  return value
    .split(/[\n,]+/g)
    .map((term) => term.trim().toLowerCase())
    .filter((term) => term.length > 0);
}

function appendMetadataText(value: unknown, fragments: string[]): void {
  if (value === null || value === undefined) return;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    fragments.push(String(value));
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => appendMetadataText(item, fragments));
    return;
  }
  if (typeof value === "object") {
    Object.values(value as Record<string, unknown>).forEach((child) =>
      appendMetadataText(child, fragments)
    );
  }
}

function buildNodeCorpus(node: PreparedNode): string {
  const fragments = [node.label, node.nodeType];
  appendMetadataText(node.metadata, fragments);
  return fragments.join(" ").toLowerCase();
}

function looksLikeCaselawNode(node: PreparedNode, corpus: string): boolean {
  if (CASELAW_NODE_TYPES.has(node.nodeType)) return true;
  if (node.id.toLowerCase().includes("case")) return true;
  return CASELAW_HINT_PATTERN.test(corpus);
}

function matchesCircuitFilter(corpus: string, circuit: string): boolean {
  if (!circuit) return true;
  const rules = CIRCUIT_MATCHERS[circuit];
  if (!rules || rules.length < 1) return corpus.includes(circuit.toLowerCase());
  return rules.some((rule) => rule.test(corpus));
}

function buildProjectionFromSeeds(
  nodes: PreparedNode[],
  edges: EdgeRow[],
  seedIds: Set<string>,
  hopLimit = 2
): { nodes: PreparedNode[]; edges: EdgeRow[]; seedIds: Set<string> } {
  if (!seedIds.size) {
    return { nodes: [], edges: [], seedIds: new Set<string>() };
  }

  const adjacency = new Map<string, Set<string>>();
  for (const edge of edges) {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set());
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set());
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }

  const visited = new Set<string>(seedIds);
  const queue: Array<{ id: string; depth: number }> = Array.from(seedIds).map((id) => ({
    id,
    depth: 0,
  }));

  while (queue.length) {
    const current = queue.shift();
    if (!current) break;
    if (current.depth >= hopLimit) continue;
    const neighbors = adjacency.get(current.id);
    if (!neighbors) continue;
    neighbors.forEach((neighbor) => {
      if (visited.has(neighbor)) return;
      visited.add(neighbor);
      queue.push({ id: neighbor, depth: current.depth + 1 });
    });
  }

  return {
    nodes: nodes.filter((node) => visited.has(node.id)),
    edges: edges.filter((edge) => visited.has(edge.source) && visited.has(edge.target)),
    seedIds: new Set(seedIds),
  };
}

function buildProjection(
  nodes: PreparedNode[],
  edges: EdgeRow[],
  query: string,
  hopLimit = 2
): { nodes: PreparedNode[]; edges: EdgeRow[]; seedIds: Set<string> } {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return { nodes, edges, seedIds: new Set<string>() };
  }
  const seedIds = new Set(
    nodes.filter((node) => nodeMatchesQuery(node, trimmed)).map((node) => node.id)
  );
  return buildProjectionFromSeeds(nodes, edges, seedIds, hopLimit);
}

function buildOntologyElasticTuning(nodeCount = 0, edgeCount = 0) {
  const nodes = Math.max(1, Number(nodeCount) || 1);
  const edges = Math.max(0, Number(edgeCount) || 0);
  const density = edges / nodes;
  const nodeScale = Math.max(0.8, Math.log2(nodes + 1));
  const crowdFactor = Math.max(0.92, Math.min(2.1, 0.86 + nodeScale / 8 + density / 18));

  return {
    springLength: Math.round(Math.max(132, Math.min(320, 128 * crowdFactor + density * 2.4))),
    springConstant: Math.max(0.016, Math.min(0.034, 0.032 - (crowdFactor - 1) * 0.007)),
    gravitationalConstant: -Math.round(Math.max(2400, Math.min(9000, 2400 * crowdFactor))),
    centralGravity: Math.max(0.01, Math.min(0.06, 0.055 / crowdFactor)),
    avoidOverlap: Math.max(0.36, Math.min(0.92, 0.36 + (crowdFactor - 0.9) * 0.33)),
    damping: Math.max(0.3, Math.min(0.42, 0.3 + (crowdFactor - 1) * 0.07)),
    minVelocity: Math.max(0.2, Math.min(0.45, 0.4 - (crowdFactor - 1) * 0.13)),
    stabilizationIterations: Math.round(Math.max(220, Math.min(520, 250 + nodes / 5))),
    fillRatio: Math.max(0.84, Math.min(0.93, 0.91 - (crowdFactor - 1) * 0.04)),
  };
}

export default function MatterOntologyPage() {
  const router = useRouter();
  const matterId = useMemo(() => {
    const value = router.query.id;
    return Array.isArray(value) ? value[0] : value || "";
  }, [router.query.id]);
  const ontologyView = useMemo<OntologyViewMode>(() => {
    const value = router.query.view;
    const raw = (Array.isArray(value) ? value[0] : value || "").toLowerCase();
    return raw === "caselaw" ? "caselaw" : "casefile";
  }, [router.query.view]);
  const isCaselawView = ontologyView === "caselaw";
  const isEmbedded = useMemo(() => {
    const value = router.query.embed;
    const raw = Array.isArray(value) ? value[0] : value || "";
    return raw === "1" || raw === "true";
  }, [router.query.embed]);
  const caselawKeywordsRaw = useMemo(() => {
    const value = router.query.keywords;
    return Array.isArray(value) ? value[0] || "" : value || "";
  }, [router.query.keywords]);
  const caselawCircuit = useMemo(() => {
    const value = router.query.circuit;
    return Array.isArray(value) ? value[0] || "" : value || "";
  }, [router.query.circuit]);
  const caselawCasesRaw = useMemo(() => {
    const value = router.query.cases;
    return Array.isArray(value) ? value[0] || "" : value || "";
  }, [router.query.cases]);
  const caselawKeywordTerms = useMemo(
    () => parseFilterTerms(caselawKeywordsRaw),
    [caselawKeywordsRaw]
  );
  const caselawCaseTerms = useMemo(
    () => parseFilterTerms(caselawCasesRaw),
    [caselawCasesRaw]
  );

  useEffect(() => {
    if (!router.isReady || !matterId || isEmbedded) {
      return;
    }
    router.replace(`/?case_id=${encodeURIComponent(matterId)}`);
  }, [isEmbedded, matterId, router]);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const visRef = useRef<any>(null);
  const networkRef = useRef<any>(null);
  const graphDataRef = useRef<{ nodes: any; edges: any } | null>(null);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideHoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resizeRafRef = useRef<number | null>(null);
  const suppressClickUntilRef = useRef(0);
  const draggingNodeRef = useRef(false);
  const renderSequenceRef = useRef(0);
  const hasRenderedRef = useRef(false);
  const lastProjectionSignatureRef = useRef("");

  const [ontology, setOntology] = useState<OntologyPayload | null>(null);
  const [status, setStatus] = useState("Loading ontology graph...");
  const [error, setError] = useState<string | null>(null);
  const [refreshTone, setRefreshTone] = useState<RefreshTone>("neutral");
  const [refreshText, setRefreshText] = useState("Ready.");
  const [searchStatus, setSearchStatus] = useState("Showing full ontology graph.");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [hoverCard, setHoverCard] = useState<HoverCardState>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [bootstrapRunning, setBootstrapRunning] = useState(false);
  const [bootstrapStatus, setBootstrapStatus] = useState<string | null>(null);
  const [maxDocuments] = useState(DEFAULT_MAX_DOCUMENTS);
  const [includeStatementNodes] = useState(true);
  const [includeEvidenceNodes] = useState(true);

  if (!isEmbedded && router.isReady) {
    return (
      <main className={styles.wrap}>
        <div className={styles.statusBar}>Redirecting to Acquittify dashboard...</div>
      </main>
    );
  }

  const preparedNodes = useMemo<PreparedNode[]>(() => {
    if (!ontology) return [];
    return ontology.nodes
      .map((node) => {
        const id = String(node.id || "").trim();
        if (!id) return null;
        return {
          id,
          label: normalizeNodeLabel(node),
          nodeType: normalizeNodeType(node),
          metadata: toMetadata(node),
          raw: node,
        };
      })
      .filter((node): node is PreparedNode => node !== null);
  }, [ontology]);

  const nodeById = useMemo(() => {
    const map = new Map<string, PreparedNode>();
    for (const node of preparedNodes) map.set(node.id, node);
    return map;
  }, [preparedNodes]);

  const preparedEdges = useMemo<EdgeRow[]>(() => {
    if (!ontology) return [];
    const knownIds = new Set(preparedNodes.map((node) => node.id));
    const rows: EdgeRow[] = [];
    ontology.edges.forEach((edge) => {
      const source = String(edge.from || edge.source || "").trim();
      const target = String(edge.to || edge.target || "").trim();
      if (!source || !target) return;
      if (!knownIds.has(source) || !knownIds.has(target)) return;
      rows.push({
        source,
        target,
        edgeType: normalizeEdgeType(edge),
        edge,
      });
    });
    return rows;
  }, [ontology, preparedNodes]);

  const nodeCorpusById = useMemo(() => {
    const map = new Map<string, string>();
    preparedNodes.forEach((node) => {
      map.set(node.id, buildNodeCorpus(node));
    });
    return map;
  }, [preparedNodes]);

  const projection = useMemo(() => {
    if (!isCaselawView) {
      return buildProjection(preparedNodes, preparedEdges, searchQuery, 2);
    }

    const domainNodes = preparedNodes.filter((node) =>
      looksLikeCaselawNode(node, nodeCorpusById.get(node.id) || "")
    );
    const workingNodes = domainNodes.length ? domainNodes : preparedNodes;
    const workingNodeIds = new Set(workingNodes.map((node) => node.id));
    const workingEdges = preparedEdges.filter(
      (edge) => workingNodeIds.has(edge.source) && workingNodeIds.has(edge.target)
    );

    const query = searchQuery.trim().toLowerCase();
    const hasExternalFilters =
      caselawKeywordTerms.length > 0 || caselawCaseTerms.length > 0 || !!caselawCircuit;

    const seeds = new Set(
      workingNodes
        .filter((node) => {
          const corpus = nodeCorpusById.get(node.id) || "";
          if (query && !nodeMatchesQuery(node, query)) return false;
          if (caselawKeywordTerms.some((term) => !corpus.includes(term))) return false;
          if (caselawCaseTerms.length > 0 && !caselawCaseTerms.some((term) => corpus.includes(term))) {
            return false;
          }
          if (!matchesCircuitFilter(corpus, caselawCircuit)) return false;
          return true;
        })
        .map((node) => node.id)
    );

    if (!seeds.size) {
      if (!query && !hasExternalFilters) {
        return {
          nodes: workingNodes,
          edges: workingEdges,
          seedIds: new Set<string>(),
        };
      }
      return { nodes: [], edges: [], seedIds: new Set<string>() };
    }
    return buildProjectionFromSeeds(workingNodes, workingEdges, seeds, 2);
  }, [
    isCaselawView,
    preparedNodes,
    preparedEdges,
    searchQuery,
    nodeCorpusById,
    caselawKeywordTerms,
    caselawCaseTerms,
    caselawCircuit,
  ]);

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return nodeById.get(selectedNodeId) || null;
  }, [selectedNodeId, nodeById]);

  const selectedNeighbors = useMemo(() => {
    if (!selectedNodeId) return [] as PreparedNode[];
    const ids = new Set<string>();
    projection.edges.forEach((row) => {
      if (row.source === selectedNodeId) ids.add(row.target);
      if (row.target === selectedNodeId) ids.add(row.source);
    });
    return Array.from(ids)
      .map((id) => nodeById.get(id))
      .filter((node): node is PreparedNode => !!node)
      .slice(0, 24);
  }, [selectedNodeId, projection.edges, nodeById]);

  const handleUnauthorized = useCallback(() => {
    router.replace("/");
  }, [router]);

  const closeHoverCard = useCallback(() => {
    if (hideHoverTimerRef.current) {
      clearTimeout(hideHoverTimerRef.current);
      hideHoverTimerRef.current = null;
    }
    setHoverCard(null);
  }, []);

  const resetNetwork = useCallback(() => {
    if (settleTimerRef.current) {
      clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
    if (hideHoverTimerRef.current) {
      clearTimeout(hideHoverTimerRef.current);
      hideHoverTimerRef.current = null;
    }
    if (resizeRafRef.current !== null) {
      cancelAnimationFrame(resizeRafRef.current);
      resizeRafRef.current = null;
    }
    if (networkRef.current) {
      try {
        networkRef.current.destroy();
      } catch {
        // ignore
      }
      networkRef.current = null;
    }
    graphDataRef.current = null;
    hasRenderedRef.current = false;
  }, []);

  useEffect(() => {
    return () => resetNetwork();
  }, [resetNetwork]);

  const fitGraphToViewport = useCallback((animate = true) => {
    const network = networkRef.current;
    if (!network) return;
    network.fit({
      animation: animate
        ? { duration: 320, easingFunction: "easeInOutQuad" }
        : false,
    });
  }, []);

  const ensureNetwork = useCallback(async () => {
    if (!containerRef.current) return null;
    if (!visRef.current) {
      visRef.current = await import("vis-network/standalone");
    }

    if (networkRef.current && graphDataRef.current) {
      return networkRef.current;
    }

    const vis = visRef.current;
    const nodes = new vis.DataSet([]);
    const edges = new vis.DataSet([]);
    graphDataRef.current = { nodes, edges };

    const network = new vis.Network(
      containerRef.current,
      { nodes, edges },
      {
        autoResize: true,
        layout: { improvedLayout: true },
        interaction: {
          hover: true,
          hoverConnectedEdges: true,
          tooltipDelay: 1000000000,
          keyboard: true,
          zoomSpeed: 0.65,
          zoomView: true,
          dragView: true,
          dragNodes: true,
          selectable: true,
        },
        physics: {
          enabled: true,
          solver: "barnesHut",
          stabilization: {
            enabled: true,
            iterations: 280,
            updateInterval: 20,
            fit: false,
          },
          barnesHut: {
            gravitationalConstant: -2600,
            centralGravity: 0.045,
            springLength: 150,
            springConstant: 0.028,
            damping: 0.32,
            avoidOverlap: 0.46,
          },
          minVelocity: 0.32,
          adaptiveTimestep: true,
        },
        edges: {
          color: {
            color: "#4a4a4a",
            highlight: "#fde047",
            hover: "#fde047",
            inherit: false,
          },
          width: 1,
          smooth: false,
        },
        nodes: {
          shape: "dot",
          scaling: {
            min: 7,
            max: 26,
            label: {
              enabled: true,
              min: 11,
              max: 18,
              drawThreshold: 6,
              maxVisible: 30,
            },
          },
          font: {
            color: "#f3f3f3",
            size: 12,
            face: "-apple-system, Segoe UI, sans-serif",
          },
        },
      }
    );

    network.on("doubleClick", (params: { nodes?: string[] }) => {
      if (!params.nodes?.length) {
        fitGraphToViewport(true);
      }
    });

    network.on("click", (params: { nodes?: string[] }) => {
      if (Date.now() < suppressClickUntilRef.current) return;
      closeHoverCard();
      const nodeId = params.nodes?.length ? params.nodes[0] : null;
      if (!nodeId) return;
      setSelectedNodeId(nodeId);
      setSidebarOpen(true);
    });

    network.on("hoverNode", (params: any) => {
      const nodeId = String(params?.node || "");
      if (!nodeById.has(nodeId)) {
        closeHoverCard();
        return;
      }
      if (hideHoverTimerRef.current) {
        clearTimeout(hideHoverTimerRef.current);
        hideHoverTimerRef.current = null;
      }
      const dom = params?.pointer?.DOM;
      const x = Number.isFinite(dom?.x) ? Number(dom.x) : 18;
      const y = Number.isFinite(dom?.y) ? Number(dom.y) : 18;
      setHoverCard({ nodeId, x, y });
    });

    network.on("blurNode", () => {
      if (hideHoverTimerRef.current) clearTimeout(hideHoverTimerRef.current);
      hideHoverTimerRef.current = setTimeout(() => setHoverCard(null), 420);
    });

    network.on("resize", () => {
      if (resizeRafRef.current !== null) {
        cancelAnimationFrame(resizeRafRef.current);
      }
      resizeRafRef.current = requestAnimationFrame(() => {
        resizeRafRef.current = null;
        try {
          network.setSize("100%", "100%");
          network.redraw();
          fitGraphToViewport(false);
        } catch {
          // ignore
        }
      });
    });

    network.on("dragStart", (params: { nodes?: string[] }) => {
      draggingNodeRef.current = Array.isArray(params.nodes) && params.nodes.length > 0;
      closeHoverCard();
      try {
        network.setOptions({ physics: { enabled: true, stabilization: false } });
      } catch {
        // ignore
      }
    });

    network.on("dragEnd", () => {
      if (draggingNodeRef.current) {
        suppressClickUntilRef.current = Date.now() + 260;
        setTimeout(() => {
          try {
            network.setOptions({ physics: { enabled: false } });
            network.stopSimulation?.();
          } catch {
            // ignore
          }
        }, 140);
      }
      draggingNodeRef.current = false;
    });

    networkRef.current = network;
    return network;
  }, [closeHoverCard, fitGraphToViewport, nodeById]);

  const fetchOntology = useCallback(async () => {
    if (!matterId) return;
    setError(null);
    setStatus(isCaselawView ? "Loading caselaw ontology graph..." : "Loading ontology graph...");
    setRefreshTone("working");
    setRefreshText(isCaselawView ? "Refreshing caselaw ontology…" : "Refreshing ontology graph…");

    try {
      const params = new URLSearchParams();
      params.set("view", ontologyView);
      params.set("max_documents", String(maxDocuments));
      params.set("include_statement_nodes", includeStatementNodes ? "true" : "false");
      params.set("include_evidence_nodes", includeEvidenceNodes ? "true" : "false");

      const response = await apiFetch(`/matters/${matterId}/ontology?${params.toString()}`);
      if (response.status === 401) {
        handleUnauthorized();
        return;
      }
      if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
      }

      const payload = (await response.json()) as OntologyPayload;
      setOntology(payload);
      const loadedNodes = Array.isArray(payload.nodes) ? payload.nodes.length : 0;
      const loadedEdges = Array.isArray(payload.edges) ? payload.edges.length : 0;
      const loadedDocs = Number(payload.meta?.documents_loaded || 0);
      setStatus(
        `${isCaselawView ? "Caselaw" : "Ontology"} graph loaded: ${loadedNodes} nodes, ${loadedEdges} edges from ${loadedDocs} documents.`
      );
      setRefreshTone("ok");
      setRefreshText(`${isCaselawView ? "Caselaw" : "Ontology"} graph loaded.`);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Network error";
      setError(`Unable to load ontology graph: ${message}. API: ${API_BASE}`);
      setStatus("Ontology graph load failed.");
      setRefreshTone("error");
      setRefreshText(`Load error: ${message}`);
      setOntology({ nodes: [], edges: [], meta: {} });
    }
  }, [
    handleUnauthorized,
    matterId,
    ontologyView,
    maxDocuments,
    includeStatementNodes,
    includeEvidenceNodes,
    isCaselawView,
  ]);

  useEffect(() => {
    const load = async () => {
      const sessionResponse = await apiFetch("/auth/me");
      if (sessionResponse.status === 401) {
        handleUnauthorized();
        return;
      }
      await fetchOntology();
    };

    load();
  }, [handleUnauthorized, fetchOntology, refreshTick]);

  useEffect(() => {
    const render = async () => {
      const network = await ensureNetwork();
      if (!network || !graphDataRef.current) return;

      const allNodes = projection.nodes;
      const allEdgeRows = projection.edges;
      const matchedNodeIds = projection.seedIds;

      const degree = new Map<string, number>();
      allEdgeRows.forEach((row) => {
        degree.set(row.source, (degree.get(row.source) || 0) + 1);
        degree.set(row.target, (degree.get(row.target) || 0) + 1);
      });

      const visualNodes = allNodes.map((node) => {
        const nodeDegree = Number(degree.get(node.id) || 0);
        const isMatch = matchedNodeIds.has(node.id);
        const baseSize = Math.max(7, Math.min(26, 7 + Math.log2(nodeDegree + 1) * 4));
        const value = isMatch ? Math.min(34, baseSize + 4) : baseSize;
        const nodeColor = ONTOLOGY_NODE_COLORS[node.nodeType] || ONTOLOGY_NODE_COLORS.unknown;
        return {
          id: node.id,
          label: node.label,
          value,
          mass: Math.max(1, nodeDegree / 4),
          physics: true,
          color: {
            background: nodeColor,
            border: isMatch ? "#fde047" : "#f5f5f5",
            highlight: { background: "#fde68a", border: "#fef3c7" },
            hover: { background: "#93c5fd", border: "#bfdbfe" },
          },
        };
      });

      const visualEdges = allEdgeRows.map((row, idx) => ({
        id: `${row.source}->${row.target}-${idx}`,
        from: row.source,
        to: row.target,
        color: {
          color: ontologyEdgeColor(row.edgeType),
          highlight: "#fde047",
          hover: "#facc15",
          inherit: false,
        },
        width: ontologyEdgeWidth(row.edgeType),
        selectionWidth: 1.9,
      }));

      const renderNodes =
        visualNodes.length > 0
          ? visualNodes
          : [
              {
                id: "__empty_ontology_graph__",
                label: searchQuery.trim()
                  ? `No nodes match \"${searchQuery.trim()}\"`
                  : "No ontology nodes to render",
                value: 18,
                mass: 1,
                color: {
                  background: "#60a5fa",
                  border: "#f5f5f5",
                  highlight: { background: "#93c5fd", border: "#fef3c7" },
                  hover: { background: "#93c5fd", border: "#bfdbfe" },
                },
              },
            ];

      const edgeCount = visualEdges.length;
      const nodeCount = renderNodes.length;
      const tuning = buildOntologyElasticTuning(nodeCount, edgeCount);
      const useCasefileTuning = String(ontology?.meta?.source || "").toLowerCase() === "casefile_schema";
      const solver = useCasefileTuning ? "forceAtlas2Based" : "barnesHut";
      const solverConfig = useCasefileTuning
        ? {
            gravitationalConstant: -72,
            centralGravity: 0.011,
            springLength: Math.round(Math.max(178, tuning.springLength * 1.12)),
            springConstant: 0.019,
            damping: 0.44,
            avoidOverlap: Math.max(0.62, tuning.avoidOverlap),
          }
        : {
            gravitationalConstant: tuning.gravitationalConstant,
            centralGravity: tuning.centralGravity,
            springLength: tuning.springLength,
            springConstant: tuning.springConstant,
            damping: tuning.damping,
            avoidOverlap: tuning.avoidOverlap,
          };

      renderSequenceRef.current += 1;
      const renderSequence = renderSequenceRef.current;

      graphDataRef.current.nodes.clear();
      graphDataRef.current.edges.clear();
      graphDataRef.current.nodes.add(renderNodes);
      graphDataRef.current.edges.add(visualEdges);

      network.setOptions({
        physics: {
          enabled: true,
          solver,
          stabilization: {
            enabled: true,
            iterations: useCasefileTuning ? Math.max(360, tuning.stabilizationIterations) : tuning.stabilizationIterations,
            updateInterval: 20,
            fit: false,
          },
          [solver]: solverConfig,
          minVelocity: useCasefileTuning ? 0.04 : tuning.minVelocity,
          maxVelocity: useCasefileTuning ? 38 : 42,
          timestep: useCasefileTuning ? 0.42 : 0.5,
          adaptiveTimestep: true,
        },
      });

      network.setSize("100%", "100%");
      network.redraw();

      const projectionSignature = [
        ontologyView,
        String(renderNodes.length),
        String(visualEdges.length),
        searchQuery.trim().toLowerCase(),
        caselawKeywordsRaw.trim().toLowerCase(),
        caselawCircuit.trim().toLowerCase(),
        caselawCasesRaw.trim().toLowerCase(),
      ].join("|");
      const shouldFit =
        isCaselawView ||
        !hasRenderedRef.current ||
        lastProjectionSignatureRef.current !== projectionSignature;
      hasRenderedRef.current = true;
      lastProjectionSignatureRef.current = projectionSignature;

      const settle = () => {
        if (renderSequence !== renderSequenceRef.current) return;
        if (shouldFit) {
          fitGraphToViewport(true);
        }
        try {
          network.setOptions({ physics: { enabled: false } });
          network.stopSimulation?.();
        } catch {
          // ignore
        }
      };

      if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
      try {
        network.once("stabilized", settle);
      } catch {
        // ignore
      }
      settleTimerRef.current = setTimeout(settle, 1200);
      try {
        network.startSimulation?.();
      } catch {
        // ignore
      }

      if (selectedNodeId && !renderNodes.some((node) => node.id === selectedNodeId)) {
        setSelectedNodeId(null);
        setSidebarOpen(false);
      }

      const query = searchQuery.trim();
      if (isCaselawView) {
        const activeFilterCount =
          (caselawKeywordTerms.length > 0 ? 1 : 0) +
          (caselawCaseTerms.length > 0 ? 1 : 0) +
          (caselawCircuit ? 1 : 0) +
          (query ? 1 : 0);
        if (!query && activeFilterCount < 1) {
          setSearchStatus(`Showing caselaw ontology: ${nodeCount} nodes, ${edgeCount} edges.`);
        } else if (matchedNodeIds.size < 1) {
          setSearchStatus("No caselaw nodes match the active filters.");
        } else {
          setSearchStatus(
            `Caselaw filters: ${matchedNodeIds.size} seed nodes • ${nodeCount} nodes within 2 hops • ${edgeCount} edges.`
          );
        }
      } else if (!query) {
        setSearchStatus(`Showing full ontology graph: ${nodeCount} nodes, ${edgeCount} edges.`);
      } else if (matchedNodeIds.size < 1) {
        setSearchStatus(`No matches for \"${query}\".`);
      } else {
        setSearchStatus(
          `\"${query}\": ${matchedNodeIds.size} matches • ${nodeCount} nodes within 2 hops • ${edgeCount} edges.`
        );
      }
    };

    render();
  }, [
    ensureNetwork,
    fitGraphToViewport,
    ontology,
    projection,
    searchQuery,
    selectedNodeId,
    ontologyView,
    isCaselawView,
    caselawKeywordsRaw,
    caselawCasesRaw,
    caselawKeywordTerms,
    caselawCaseTerms,
    caselawCircuit,
  ]);

  const hoverNode = hoverCard ? nodeById.get(hoverCard.nodeId) || null : null;
  const hoverFrontmatter = hoverNode ? toRecord(hoverNode.metadata.frontmatter_distilled) : null;
  const hoverDefenseSignals = hoverFrontmatter
    ? toRecord(hoverFrontmatter.defense_signals)
    : null;
  const hoverPrivilegeSignals = hoverFrontmatter
    ? toRecord(hoverFrontmatter.privilege_signals)
    : null;
  const hoverDocumentName =
    (hoverFrontmatter && typeof hoverFrontmatter.document_title === "string"
      ? hoverFrontmatter.document_title
      : hoverNode?.label) || "";
  const hoverNodeStandardName =
    (hoverFrontmatter && typeof hoverFrontmatter.node_name_standard === "string"
      ? hoverFrontmatter.node_name_standard
      : typeof hoverNode?.metadata.node_name_standard === "string"
        ? hoverNode.metadata.node_name_standard
        : null) || null;
  const hoverSummary =
    (hoverFrontmatter && typeof hoverFrontmatter.summary === "string"
      ? hoverFrontmatter.summary
      : typeof hoverNode?.metadata.summary === "string"
        ? hoverNode.metadata.summary
        : "") || "";
  const hoverWitnesses = toStringList(hoverFrontmatter?.witnesses, 8);
  const hoverRelatedDocs = toStringList(hoverFrontmatter?.related_documents, 6);
  const hoverPeople = toStringList(hoverFrontmatter?.key_people, 8);
  const hoverOrganizations = toStringList(hoverFrontmatter?.key_organizations, 8);
  const hoverEventSummaries = toStringList(hoverFrontmatter?.event_summaries, 4);
  const hoverPrivilegeFlags = toStringList(hoverPrivilegeSignals?.pii_flags, 6);
  const hoverExhibitPurposes = toStringList(hoverFrontmatter?.exhibit_purposes, 5);

  const saveGraphSnapshot = () => {
    const payload = {
      generated_at: new Date().toISOString(),
      matter_id: matterId,
      search_query: searchQuery,
      nodes: projection.nodes.map((node) => ({
        id: node.id,
        label: node.label,
        type: node.nodeType,
        metadata: node.metadata,
      })),
      edges: projection.edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        type: edge.edgeType,
      })),
      meta: ontology?.meta || {},
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${isCaselawView ? "caselaw" : "ontology"}-${matterId || "matter"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleBootstrapMatter = useCallback(async () => {
    if (!matterId || isCaselawView) {
      setBootstrapStatus("Bootstrap is only available in Casefile view.");
      return;
    }

    setBootstrapRunning(true);
    setBootstrapStatus("Queueing bootstrap processing...");
    try {
      const response = await apiFetch(`/matters/${matterId}/documents/review`, { method: "POST" });
      if (response.status === 401) {
        handleUnauthorized();
        setBootstrapStatus("Session expired. Please sign in again.");
        return;
      }
      if (!response.ok) {
        const detail = (await response.text()).trim();
        setBootstrapStatus(
          detail
            ? `Bootstrap failed (${response.status}): ${detail}`
            : `Bootstrap failed (${response.status}).`
        );
        return;
      }

      const data = (await response.json()) as BootstrapReviewResponse;
      const enqueued = Number(data.enqueued || 0);
      const tasks = Number(data.enqueued_tasks || 0);
      const skipped = Number(data.skipped || 0);
      setBootstrapStatus(
        `Bootstrap queued: ${tasks} task${tasks === 1 ? "" : "s"} across ${enqueued} document${enqueued === 1 ? "" : "s"} (skipped ${skipped}). Graph preserved; click Refresh Vault when processing progresses.`
      );
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Network error";
      setBootstrapStatus(`Bootstrap request failed (${message}). Check API/CORS at ${API_BASE}.`);
    } finally {
      setBootstrapRunning(false);
    }
  }, [handleUnauthorized, isCaselawView, matterId]);

  const refreshStatusClass = [
    styles.refreshStatus,
    refreshTone === "working" ? styles.refreshStatusWorking : "",
    refreshTone === "ok" ? styles.refreshStatusOk : "",
    refreshTone === "error" ? styles.refreshStatusError : "",
  ]
    .filter(Boolean)
    .join(" ");
  const graphTitle = isCaselawView ? "Caselaw Ontology Graph" : "Casefile Ontology Graph";
  const graphSearchPlaceholder = isCaselawView
    ? "Search caselaw ontology nodes…"
    : "Search ontology nodes…";
  const refreshButtonText = isCaselawView ? "Refresh Caselaw" : "Refresh Vault";
  const sidebarDefaultTitle = isCaselawView ? "Caselaw Reader" : "Case Reader";

  const graphShell = (
    <section className={`${styles.wrap} ${isEmbedded ? styles.wrapEmbedded : ""}`}>
      <div className={styles.toolbar}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{graphTitle}</h1>
          <span className={styles.badge}>{isCaselawView ? "CASELAW" : "WEB"}</span>
        </div>
        <div className={styles.toolbarActions}>
          <button type="button" onClick={() => setRefreshTick((value) => value + 1)}>
            {refreshButtonText}
          </button>
          {!isCaselawView && (
            <button
              type="button"
              onClick={() => void handleBootstrapMatter()}
              disabled={!matterId || bootstrapRunning}
            >
              {bootstrapRunning ? "Bootstrapping..." : "Run Bootstrap"}
            </button>
          )}
          <button type="button" onClick={() => window.location.reload()}>
            Reload App
          </button>
          <button type="button" onClick={saveGraphSnapshot}>
            Save
          </button>
        </div>
      </div>
      {!isCaselawView && bootstrapStatus && (
        <div className={styles.toolbarNotice}>{bootstrapStatus}</div>
      )}

      <div className={styles.controls}>
        <div className={styles.searchRow}>
          <input
            id="ontologyGraphSearch"
            className={styles.searchInput}
            type="text"
            value={searchQuery}
            placeholder={graphSearchPlaceholder}
            onChange={(event) => setSearchQuery(event.target.value)}
          />
          <button
            id="ontologyGraphSearchClear"
            type="button"
            className={styles.searchClear}
            onClick={() => setSearchQuery("")}
          >
            Clear
          </button>
        </div>
        <div className={styles.searchStatus}>{searchStatus}</div>
        <div className={styles.refreshRow}>
          <button
            id="ontologyForceRefreshBtn"
            type="button"
            className={styles.controlButton}
            onClick={() => {
              setRefreshTick((value) => value + 1);
              setSidebarOpen(false);
              setSelectedNodeId(null);
              closeHoverCard();
            }}
          >
            Force Refresh
          </button>
          <span id="ontologyRefreshStatus" className={refreshStatusClass}>
            {refreshText}
          </span>
        </div>
      </div>

      {error && <div className={styles.errorBox}>{error}</div>}

      <div
        className={`${styles.graphBody} ${sidebarOpen && selectedNode ? styles.graphBodyWithSidebar : ""}`}
      >
        <div ref={containerRef} className={styles.graphContainer} />

        <aside
          className={`${styles.caseSidebar} ${sidebarOpen && selectedNode ? styles.caseSidebarOpen : ""}`}
        >
          <div className={styles.sidebarHeader}>
            <div className={styles.sidebarTitle}>
              {selectedNode ? truncateText(selectedNode.label, 140) : sidebarDefaultTitle}
            </div>
            <button
              type="button"
              className={styles.sidebarClose}
              onClick={() => setSidebarOpen(false)}
            >
              Close
            </button>
          </div>
          <div className={styles.sidebarMeta}>
            {!selectedNode && <p>Select a node to view details.</p>}
            {selectedNode && (
              <>
                <h3>{selectedNode.label}</h3>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Node ID</span>
                  <span className={styles.metaValue}>{selectedNode.id}</span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Node Type</span>
                  <span className={styles.metaValue}>{selectedNode.nodeType}</span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Connected Nodes</span>
                  <span className={styles.metaValue}>{selectedNeighbors.length}</span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Neighbors</span>
                  <span className={styles.metaValue}>
                    {selectedNeighbors.length
                      ? selectedNeighbors.map((node) => node.label).join(", ")
                      : "None"}
                  </span>
                </div>
                {Object.entries(selectedNode.metadata).map(([key, value]) => (
                  <div className={styles.metaRow} key={key}>
                    <span className={styles.metaLabel}>{key}</span>
                    <span className={styles.metaValue}>{formatMetadataValue(value)}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </aside>

        {hoverNode && hoverCard && (
          <div
            className={styles.hoverCard}
            style={{ left: `${hoverCard.x + 14}px`, top: `${hoverCard.y + 14}px` }}
          >
            <div className={styles.hoverTitle}>{truncateText(hoverDocumentName || hoverNode.label, 170)}</div>
            <div className={styles.hoverRow}>Type: {hoverNode.nodeType}</div>
            <div className={styles.hoverRow}>ID: {truncateText(hoverNode.id, 200)}</div>
            {hoverNodeStandardName && (
              <div className={styles.hoverRow}>Node Name: {truncateText(hoverNodeStandardName, 220)}</div>
            )}
            {hoverSummary && <div className={styles.hoverSummary}>{truncateText(hoverSummary, 380)}</div>}

            {hoverFrontmatter && (
              <div className={styles.hoverSection}>
                <div className={styles.hoverSectionTitle}>Frontmatter (Distilled)</div>
                {typeof hoverFrontmatter.document_type === "string" && (
                  <div className={styles.hoverRow}>
                    Document Type: {truncateText(hoverFrontmatter.document_type, 120)}
                  </div>
                )}
                {typeof hoverFrontmatter.document_date === "string" && (
                  <div className={styles.hoverRow}>Document Date: {hoverFrontmatter.document_date}</div>
                )}
                {typeof hoverFrontmatter.relevance === "string" && (
                  <div className={styles.hoverRow}>Relevance: {hoverFrontmatter.relevance}</div>
                )}
                {typeof hoverFrontmatter.proponent === "string" && (
                  <div className={styles.hoverRow}>Proponent: {hoverFrontmatter.proponent}</div>
                )}
                {typeof hoverFrontmatter.priority_code === "string" && (
                  <div className={styles.hoverRow}>Priority: {hoverFrontmatter.priority_code}</div>
                )}
                {typeof hoverFrontmatter.hot_doc_candidate === "boolean" && (
                  <div className={styles.hoverRow}>
                    Hot Doc: {hoverFrontmatter.hot_doc_candidate ? "Yes" : "No"}
                  </div>
                )}
                {hoverRelatedDocs.length > 0 && (
                  <div className={styles.hoverRow}>
                    Related Documents: {truncateText(hoverRelatedDocs.join(" | "), 320)}
                  </div>
                )}
                {hoverWitnesses.length > 0 && (
                  <div className={styles.hoverRow}>
                    Witnesses: {truncateText(hoverWitnesses.join(" | "), 280)}
                  </div>
                )}
                {hoverPeople.length > 0 && (
                  <div className={styles.hoverRow}>
                    Key People: {truncateText(hoverPeople.join(" | "), 280)}
                  </div>
                )}
                {hoverOrganizations.length > 0 && (
                  <div className={styles.hoverRow}>
                    Organizations: {truncateText(hoverOrganizations.join(" | "), 280)}
                  </div>
                )}
                {hoverEventSummaries.length > 0 && (
                  <div className={styles.hoverRow}>
                    Event Highlights: {truncateText(hoverEventSummaries.join(" | "), 320)}
                  </div>
                )}
                {hoverExhibitPurposes.length > 0 && (
                  <div className={styles.hoverRow}>
                    Exhibit Purposes: {truncateText(hoverExhibitPurposes.join(" | "), 280)}
                  </div>
                )}
                {hoverDefenseSignals && (
                  <div className={styles.hoverRow}>
                    Defense Signals:{" "}
                    {truncateText(
                      [
                        `defense=${formatMetadataValue(hoverDefenseSignals.defense_value_likelihood)}`,
                        `govt=${formatMetadataValue(hoverDefenseSignals.govt_reliance_likelihood)}`,
                        `trial=${formatMetadataValue(hoverDefenseSignals.trial_relevance_hint)}`,
                        `jury=${formatMetadataValue(hoverDefenseSignals.jury_readability_hint)}`,
                      ].join(" | "),
                      320
                    )}
                  </div>
                )}
                {hoverPrivilegeSignals && (
                  <div className={styles.hoverRow}>
                    Privilege:{" "}
                    {truncateText(
                      [
                        `attorney_involved=${formatMetadataValue(
                          hoverPrivilegeSignals.attorney_involved
                        )}`,
                        `legal_advice=${formatMetadataValue(
                          hoverPrivilegeSignals.legal_advice_likelihood
                        )}`,
                        `work_product=${formatMetadataValue(
                          hoverPrivilegeSignals.work_product_likelihood
                        )}`,
                        hoverPrivilegeFlags.length
                          ? `flags=${hoverPrivilegeFlags.join("/")}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(" | "),
                      320
                    )}
                  </div>
                )}
              </div>
            )}
            <div className={styles.hoverActions}>
              <button
                type="button"
                className={styles.hoverButton}
                onClick={() => {
                  setSelectedNodeId(hoverNode.id);
                  setSidebarOpen(true);
                  closeHoverCard();
                }}
              >
                Open Node
              </button>
            </div>
          </div>
        )}
      </div>

      <div className={styles.graphHint}>{status}</div>
    </section>
  );

  if (isEmbedded) {
    return <div className={styles.embedRoot}>{graphShell}</div>;
  }

  return (
    <main className={styles.page}>
      <div className={styles.tabBar}>
        <button type="button" className={styles.tabBtnMuted}>
          New Tab
        </button>
        <div className={styles.tabBtnActive}>{graphTitle}</div>
        <button type="button" className={styles.tabPlus}>
          +
        </button>
      </div>
      {graphShell}
    </main>
  );
}
