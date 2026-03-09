import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, apiFetch } from "../lib/api";
import styles from "../styles/dashboardShell.module.css";

type MatterRow = { id: string; name: string; external_id?: string | null };

type AuthState = {
  user: {
    id: string;
    email: string;
    full_name?: string | null;
    mfa_enabled?: boolean;
  };
  organization: { id: string; name: string };
  role: string;
};

type MatterDocumentRow = {
  id: string;
  document_id: string;
  original_filename?: string | null;
  status?: string | null;
  mime_type?: string | null;
  ingested_at?: string | null;
  virtual_url?: string | null;
  is_virtual?: boolean;
};

type AgentCitation = {
  document_id: string;
  original_filename?: string | null;
  page_num?: number | null;
  text?: string;
  text_snippet?: string;
  score?: number;
};

type AgentChatResponse = {
  answer?: string;
  model?: string | null;
  citations?: AgentCitation[];
  used_search_fallback?: boolean;
  llm_error?: string;
};

type BootstrapReviewResponse = {
  enqueued?: number;
  enqueued_tasks?: number;
  skipped?: number;
};

type AgentMessage = {
  id: string;
  role: "system" | "user" | "assistant";
  text: string;
  timestamp: string;
};

type RawMatterDocumentRow = Partial<MatterDocumentRow> & {
  document_id?: string | null;
  id?: string | null;
};
type DashboardViewMode = "casefile" | "caselaw";
type CenterTabMode = "ontology_graph" | "ontology_admin";

type CaselawAdminSummary = {
  exists: boolean;
  reason?: string;
  cases?: {
    total?: number;
    touched_last_hour?: number;
    touched_last_24h?: number;
    new_last_hour?: number;
    new_last_24h?: number;
    with_frontmatter?: number;
    latest_ingest?: string | null;
  };
  graph?: {
    nodes?: number;
    edges?: number;
    node_breakdown?: Record<string, number>;
    edge_breakdown?: Record<string, number>;
  };
};

type CaselawAdminCaseRow = {
  case_id: string;
  case_name: string;
  court_id?: string | null;
  court_name?: string | null;
  date_filed?: string | null;
  case_type?: string | null;
  primary_citation?: string | null;
  first_ingested_at?: string | null;
  last_ingested_at?: string | null;
};

type CaselawAdminCaseDetail = CaselawAdminCaseRow & {
  frontmatter: Record<string, unknown>;
};

const CASELAW_CIRCUIT_OPTIONS = [
  "",
  "Supreme Court",
  "First Circuit",
  "Second Circuit",
  "Third Circuit",
  "Fourth Circuit",
  "Fifth Circuit",
  "Sixth Circuit",
  "Seventh Circuit",
  "Eighth Circuit",
  "Ninth Circuit",
  "Tenth Circuit",
  "Eleventh Circuit",
  "D.C. Circuit",
];

const BOOTSTRAP_SCHEMA_VAULT_ENTRY: MatterDocumentRow = {
  id: "bootstrap-schema-readme",
  document_id: "bootstrap-schema-readme",
  original_filename: "BOOTSTRAP_SCHEMA_README.md",
  status: "schema",
  mime_type: "text/markdown",
  ingested_at: null,
  virtual_url: "/BOOTSTRAP_SCHEMA_README.md",
  is_virtual: true,
};

const SHOW_SIDEBAR_2FA = false;

function normalizeMatterDocuments(rows: unknown): MatterDocumentRow[] {
  if (!Array.isArray(rows)) return [];
  const normalized: MatterDocumentRow[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const raw = row as RawMatterDocumentRow;
    const id = String(raw.id || raw.document_id || "").trim();
    if (!id) continue;
    normalized.push({
      id,
      document_id: id,
      original_filename: raw.original_filename ?? null,
      status: raw.status ?? null,
      mime_type: raw.mime_type ?? null,
      ingested_at: raw.ingested_at ?? null,
    });
  }
  return normalized;
}

function truncateSnippet(value: string | null | undefined, max = 120): string {
  const compact = String(value || "").replace(/\s+/g, " ").trim();
  if (!compact) return "";
  if (compact.length <= max) return compact;
  return `${compact.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

function formatMessageTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function Home() {
  const [matterName, setMatterName] = useState("");
  const [createdMatterId, setCreatedMatterId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [matters, setMatters] = useState<MatterRow[]>([]);
  const [mattersStatus, setMattersStatus] = useState<string | null>(null);
  const [selectedMatterId, setSelectedMatterId] = useState<string>("");
  const [activeView, setActiveView] = useState<DashboardViewMode>("casefile");
  const [centerTab, setCenterTab] = useState<CenterTabMode>("ontology_graph");
  const [autoStatus, setAutoStatus] = useState<string | null>(null);
  const [autoCreateStatus, setAutoCreateStatus] = useState<string | null>(null);
  const [caseParams, setCaseParams] = useState({
    caseId: "",
    caseName: "",
  });
  const [authState, setAuthState] = useState<AuthState | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authFullName, setAuthFullName] = useState("");
  const [authOrgName, setAuthOrgName] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authRetryAfterSec, setAuthRetryAfterSec] = useState<number | null>(null);
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaTicket, setMfaTicket] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaStatus, setMfaStatus] = useState<string | null>(null);
  const [mfaSubmitting, setMfaSubmitting] = useState(false);
  const [showPasswordHelp, setShowPasswordHelp] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotStatus, setForgotStatus] = useState<string | null>(null);
  const [resetToken, setResetToken] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [resetStatus, setResetStatus] = useState<string | null>(null);
  const [devResetToken, setDevResetToken] = useState<string | null>(null);
  const [securityStatus, setSecurityStatus] = useState<string | null>(null);
  const [mfaSetupSecret, setMfaSetupSecret] = useState<string | null>(null);
  const [mfaSetupUri, setMfaSetupUri] = useState<string | null>(null);
  const [mfaSetupCode, setMfaSetupCode] = useState("");
  const [mfaBackupCodes, setMfaBackupCodes] = useState<string[]>([]);
  const [vaultQuery, setVaultQuery] = useState("");
  const [matterDocuments, setMatterDocuments] = useState<MatterDocumentRow[]>([]);
  const [documentsStatus, setDocumentsStatus] = useState<string | null>(null);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [caselawKeywordsInput, setCaselawKeywordsInput] = useState("");
  const [caselawCircuitInput, setCaselawCircuitInput] = useState("");
  const [caselawCasesInput, setCaselawCasesInput] = useState("");
  const [caselawFilters, setCaselawFilters] = useState({
    keywords: "",
    circuit: "",
    cases: "",
  });
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [bootstrapRunning, setBootstrapRunning] = useState(false);
  const [bootstrapStatus, setBootstrapStatus] = useState<string | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [agentInput, setAgentInput] = useState("");
  const [agentSubmitting, setAgentSubmitting] = useState(false);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([
    {
      id: "agent-ready",
      role: "system",
      text: "Ask a question to search this matter and surface matching evidence.",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [adminSummary, setAdminSummary] = useState<CaselawAdminSummary | null>(null);
  const [adminSummaryStatus, setAdminSummaryStatus] = useState<string | null>(null);
  const [adminCases, setAdminCases] = useState<CaselawAdminCaseRow[]>([]);
  const [adminCasesStatus, setAdminCasesStatus] = useState<string | null>(null);
  const [adminQueryInput, setAdminQueryInput] = useState("");
  const [adminQueryApplied, setAdminQueryApplied] = useState("");
  const [adminTotalCases, setAdminTotalCases] = useState(0);
  const [adminOffset, setAdminOffset] = useState(0);
  const [adminSelectedCaseId, setAdminSelectedCaseId] = useState<string | null>(null);
  const [adminCaseDetail, setAdminCaseDetail] = useState<CaselawAdminCaseDetail | null>(null);
  const [adminCaseDetailStatus, setAdminCaseDetailStatus] = useState<string | null>(null);

  const { caseId, caseName } = caseParams;
  const ADMIN_CASE_PAGE_SIZE = 40;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setCaseParams({
      caseId: params.get("case_id") || "",
      caseName: params.get("case_name") || "",
    });
  }, []);

  useEffect(() => {
    if (!authRetryAfterSec || authRetryAfterSec <= 0) {
      return;
    }
    const interval = setInterval(() => {
      setAuthRetryAfterSec((value) => {
        if (!value || value <= 1) {
          return null;
        }
        return value - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [authRetryAfterSec]);

  const loadSession = async () => {
    try {
      const response = await apiFetch("/auth/me");
      if (!response.ok) {
        setAuthState(null);
        return;
      }
      const data = await response.json();
      setAuthState(data);
    } catch {
      setAuthState(null);
    }
  };

  useEffect(() => {
    const run = async () => {
      setAuthLoading(true);
      await loadSession();
      setAuthLoading(false);
    };
    run();
  }, []);

  useEffect(() => {
    const loadMatters = async () => {
      if (!authState) {
        return;
      }

      setMattersStatus("Loading matters...");
      try {
        const response = await apiFetch("/matters");
        if (response.status === 401) {
          setAuthState(null);
          setMattersStatus("Session expired. Please sign in again.");
          return;
        }
        if (!response.ok) {
          setMattersStatus(`Failed to load (${response.status}).`);
          return;
        }

        const data = await response.json();
        const loadedMatters = data.matters || [];
        setMatters(loadedMatters);

        if (!selectedMatterId && loadedMatters.length) {
          setSelectedMatterId(loadedMatters[0].id);
        }

        if (caseId || caseName) {
          const match = loadedMatters.find((matter: MatterRow) => {
            if (caseId && (matter.id === caseId || matter.external_id === caseId)) {
              return true;
            }
            if (caseName && matter.name?.toLowerCase() === caseName.toLowerCase()) {
              return true;
            }
            return false;
          });

          if (match) {
            setSelectedMatterId(match.id);
            setAutoStatus(`Loaded matter: ${match.name}`);
            return;
          }

          setAutoStatus(
            "No matching matter found. Create one linked to your Acquittify matter."
          );
        }

        setMattersStatus(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Network error";
        setMatters([]);
        setMattersStatus(`Failed to load (${message}).`);
      }
    };

    loadMatters();
  }, [authState, createdMatterId, caseId, caseName, selectedMatterId]);

  const loadDocumentsForMatter = async (matterId: string) => {
    if (!authState) {
      setMatterDocuments([]);
      setDocumentsStatus(null);
      return;
    }
    if (!matterId) {
      setMatterDocuments([]);
      setDocumentsStatus("Select a matter to view vault documents.");
      return;
    }

    setDocumentsLoading(true);
    setDocumentsStatus("Loading vault documents...");
    try {
      const response = await apiFetch(`/matters/${matterId}/documents?limit=500`);
      if (response.status === 401) {
        setAuthState(null);
        setDocumentsStatus("Session expired. Please sign in again.");
        setMatterDocuments([]);
        return;
      }
      if (!response.ok) {
        setDocumentsStatus(`Vault failed to load (${response.status}).`);
        setMatterDocuments([]);
        return;
      }
      const data = await response.json();
      const documents = normalizeMatterDocuments(data.documents);
      setMatterDocuments(documents);
      setDocumentsStatus(
        documents.length
          ? `${documents.length} document${documents.length === 1 ? "" : "s"} in vault.`
          : "No documents in this matter yet."
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setDocumentsStatus(`Vault failed to load (${message}).`);
      setMatterDocuments([]);
    } finally {
      setDocumentsLoading(false);
    }
  };

  useEffect(() => {
    void loadDocumentsForMatter(selectedMatterId);
  }, [authState, selectedMatterId, createdMatterId]);

  useEffect(() => {
    setUploadFiles([]);
    setUploadStatus(null);
    setBootstrapStatus(null);
    if (uploadInputRef.current) {
      uploadInputRef.current.value = "";
    }
  }, [selectedMatterId]);

  const applyCaselawFilters = () => {
    setCaselawFilters({
      keywords: caselawKeywordsInput.trim(),
      circuit: caselawCircuitInput.trim(),
      cases: caselawCasesInput.trim(),
    });
  };

  const clearCaselawFilters = () => {
    setCaselawKeywordsInput("");
    setCaselawCircuitInput("");
    setCaselawCasesInput("");
    setCaselawFilters({ keywords: "", circuit: "", cases: "" });
  };

  const caselawFiltersDirty =
    caselawKeywordsInput.trim() !== caselawFilters.keywords ||
    caselawCircuitInput.trim() !== caselawFilters.circuit ||
    caselawCasesInput.trim() !== caselawFilters.cases;

  const handleAuthSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthError(null);
    if (authSubmitting) {
      return;
    }
    if (authRetryAfterSec && authRetryAfterSec > 0) {
      setAuthError(`Too many attempts. Try again in ${authRetryAfterSec}s.`);
      return;
    }

    if (!authEmail.trim() || !authPassword.trim()) {
      setAuthError("Username/email and password are required.");
      return;
    }

    const endpoint = authMode === "login" ? "/auth/login" : "/auth/register";
    const body: Record<string, string> = {
      email: authEmail.trim(),
      password: authPassword,
    };

    if (authMode === "register") {
      if (authFullName.trim()) {
        body.full_name = authFullName.trim();
      }
      if (authOrgName.trim()) {
        body.organization_name = authOrgName.trim();
      }
    }

    setAuthSubmitting(true);
    try {
      const response = await apiFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const retryAfterHeader = response.headers.get("Retry-After");
        if (response.status === 429) {
          const retryAfter = Number.parseInt(retryAfterHeader || "", 10);
          if (Number.isFinite(retryAfter) && retryAfter > 0) {
            setAuthRetryAfterSec(retryAfter);
            setAuthError(`Too many attempts. Try again in ${retryAfter}s.`);
            return;
          }
          setAuthError("Too many attempts. Please try again shortly.");
          return;
        }
        const errorBody = await response.json().catch(() => ({}));
        setAuthError(errorBody.detail || `Authentication failed (${response.status}).`);
        return;
      }

      const data = await response.json();
      if (data?.mfa_required && typeof data?.mfa_ticket === "string") {
        setMfaRequired(true);
        setMfaTicket(data.mfa_ticket);
        setMfaCode("");
        setMfaStatus("Two-factor code required. Enter your authenticator code.");
        setAuthPassword("");
        setAuthError(null);
        setAuthRetryAfterSec(null);
        return;
      }
      setMfaRequired(false);
      setMfaTicket("");
      setMfaCode("");
      setMfaStatus(null);
      setAuthState(data);
      setAuthPassword("");
      setAuthError(null);
      setAuthRetryAfterSec(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setAuthError(
        `Sign-in failed before the API responded (${message}). Check connectivity/CORS to ${API_BASE}.`
      );
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleForgotPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setForgotStatus(null);
    setDevResetToken(null);
    const email = forgotEmail.trim();
    if (!email) {
      setForgotStatus("Enter your email address first.");
      return;
    }
    try {
      const response = await apiFetch("/auth/password/forgot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!response.ok) {
        const retryAfterHeader = response.headers.get("Retry-After");
        if (response.status === 429) {
          const retryAfter = Number.parseInt(retryAfterHeader || "", 10);
          setForgotStatus(
            Number.isFinite(retryAfter)
              ? `Too many reset requests. Try again in ${retryAfter}s.`
              : "Too many reset requests. Try again shortly."
          );
          return;
        }
        const errorBody = await response.json().catch(() => ({}));
        setForgotStatus(errorBody.detail || `Request failed (${response.status}).`);
        return;
      }
      const data = await response.json();
      if (typeof data.reset_code === "string" && data.reset_code) {
        setDevResetToken(data.reset_code);
        setResetToken(data.reset_code);
      } else if (typeof data.reset_token === "string" && data.reset_token) {
        setDevResetToken(data.reset_token);
        setResetToken(data.reset_token);
      }
      setForgotStatus(
        data.message ||
          "If your account exists, a reset code was sent. Enter your code below."
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setForgotStatus(`Reset request failed (${message}).`);
    }
  };

  const handleResetPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setResetStatus(null);
    if (!resetToken.trim()) {
      setResetStatus("Reset code is required.");
      return;
    }
    if (resetPassword.trim().length < 8) {
      setResetStatus("New password must be at least 8 characters.");
      return;
    }
    try {
      const response = await apiFetch("/auth/password/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: resetToken.trim(),
          new_password: resetPassword,
        }),
      });
      if (!response.ok) {
        const retryAfterHeader = response.headers.get("Retry-After");
        if (response.status === 429) {
          const retryAfter = Number.parseInt(retryAfterHeader || "", 10);
          setResetStatus(
            Number.isFinite(retryAfter)
              ? `Too many reset attempts. Try again in ${retryAfter}s.`
              : "Too many reset attempts. Try again shortly."
          );
          return;
        }
        const errorBody = await response.json().catch(() => ({}));
        setResetStatus(errorBody.detail || `Password reset failed (${response.status}).`);
        return;
      }
      setResetStatus("Password reset successful. Sign in with your new password.");
      setAuthMode("login");
      if (forgotEmail.trim()) {
        setAuthEmail(forgotEmail.trim());
      }
      setAuthPassword("");
      setResetPassword("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setResetStatus(`Password reset failed (${message}).`);
    }
  };

  const handleMfaLoginVerify = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!mfaRequired || !mfaTicket.trim()) {
      setMfaStatus("No active MFA challenge.");
      return;
    }
    if (!mfaCode.trim()) {
      setMfaStatus("Enter your 2FA code.");
      return;
    }
    if (mfaSubmitting) {
      return;
    }
    setMfaSubmitting(true);
    setMfaStatus(null);
    try {
      const response = await apiFetch("/auth/mfa/login/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket: mfaTicket.trim(), code: mfaCode.trim() }),
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        setMfaStatus(errorBody.detail || `MFA verification failed (${response.status}).`);
        return;
      }
      const data = await response.json();
      setAuthState(data);
      setMfaRequired(false);
      setMfaTicket("");
      setMfaCode("");
      setMfaStatus(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setMfaStatus(`MFA verification failed (${message}).`);
    } finally {
      setMfaSubmitting(false);
    }
  };

  const handleStartMfaSetup = async () => {
    setSecurityStatus("Starting 2FA setup...");
    setMfaBackupCodes([]);
    try {
      const response = await apiFetch("/auth/mfa/setup", { method: "POST" });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        setSecurityStatus(errorBody.detail || `2FA setup failed (${response.status}).`);
        return;
      }
      const data = await response.json();
      setMfaSetupSecret(typeof data.secret === "string" ? data.secret : null);
      setMfaSetupUri(typeof data.otpauth_uri === "string" ? data.otpauth_uri : null);
      setSecurityStatus("2FA secret created. Add it in your authenticator app, then verify.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setSecurityStatus(`2FA setup failed (${message}).`);
    }
  };

  const handleVerifyMfaSetup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!mfaSetupCode.trim()) {
      setSecurityStatus("Enter the 2FA code from your authenticator app.");
      return;
    }
    setSecurityStatus("Verifying 2FA setup...");
    try {
      const response = await apiFetch("/auth/mfa/setup/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: mfaSetupCode.trim() }),
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        setSecurityStatus(errorBody.detail || `2FA verification failed (${response.status}).`);
        return;
      }
      const data = await response.json();
      const backup = Array.isArray(data.backup_codes)
        ? data.backup_codes.map((item: unknown) => String(item))
        : [];
      setMfaBackupCodes(backup);
      setMfaSetupCode("");
      setMfaSetupSecret(null);
      setMfaSetupUri(null);
      await loadSession();
      setSecurityStatus("2FA enabled. Store your backup codes securely.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setSecurityStatus(`2FA verification failed (${message}).`);
    }
  };

  const handleLogout = async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    setAuthState(null);
    setMfaRequired(false);
    setMfaTicket("");
    setMfaCode("");
    setMfaStatus(null);
    setMatters([]);
    setSelectedMatterId("");
    setMattersStatus(null);
  };

  const handleCreateMatter = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!matterName.trim()) {
      setStatus("Enter a matter name first.");
      return;
    }

    setStatus("Creating matter...");
    try {
      const response = await apiFetch("/matters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: matterName.trim() }),
      });

      if (response.status === 401) {
        setAuthState(null);
        setStatus("Session expired. Please sign in again.");
        return;
      }
      if (!response.ok) {
        setStatus(`Create failed (${response.status}).`);
        return;
      }

      const data = await response.json();
      setCreatedMatterId(data.id);
      setSelectedMatterId(data.id);
      setStatus("Matter created.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setStatus(`Create failed (${message}). Check API + CORS at ${API_BASE}.`);
    }
  };

  const handleUploadDocuments = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedMatterId) {
      setUploadStatus("Select a matter before uploading.");
      return;
    }
    if (!uploadFiles.length) {
      setUploadStatus("Choose one or more files first.");
      return;
    }
    if (uploading) {
      return;
    }

    setUploading(true);
    setUploadStatus(`Uploading ${uploadFiles.length} file${uploadFiles.length === 1 ? "" : "s"}...`);
    try {
      const formData = new FormData();
      for (const file of uploadFiles) {
        formData.append("files", file, file.name);
      }
      const response = await apiFetch(`/matters/${selectedMatterId}/ingest/upload`, {
        method: "POST",
        body: formData,
      });
      if (response.status === 401) {
        setAuthState(null);
        setUploadStatus("Session expired. Please sign in again.");
        return;
      }
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        const detail =
          typeof errorBody.detail === "string"
            ? errorBody.detail
            : `Upload failed (${response.status}).`;
        setUploadStatus(detail);
        return;
      }
      const data = await response.json().catch(() => ({}));
      const uploadedCount = Array.isArray(data.document_ids) ? data.document_ids.length : uploadFiles.length;
      setUploadStatus(
        `Uploaded ${uploadedCount} file${uploadedCount === 1 ? "" : "s"}. Processing has started.`
      );
      setUploadFiles([]);
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
      await loadDocumentsForMatter(selectedMatterId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setUploadStatus(`Upload failed (${message}).`);
    } finally {
      setUploading(false);
    }
  };

  const handleBootstrapMatter = async () => {
    if (!selectedMatterId) {
      setBootstrapStatus("Select a matter before running bootstrap.");
      return;
    }

    setBootstrapRunning(true);
    setBootstrapStatus("Queueing bootstrap processing...");
    try {
      const response = await apiFetch(`/matters/${selectedMatterId}/documents/review`, { method: "POST" });

      if (response.status === 401) {
        setAuthState(null);
        setBootstrapStatus("Session expired. Please sign in again.");
        return;
      }

      if (!response.ok) {
        const detail = await response.text();
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
        `Bootstrap queued: ${tasks} task${tasks === 1 ? "" : "s"} across ${enqueued} document${enqueued === 1 ? "" : "s"} (skipped ${skipped}). Graph preserved; use Refresh Vault/Force Refresh to load updates.`
      );

      await loadDocumentsForMatter(selectedMatterId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setBootstrapStatus(`Bootstrap request failed (${message}). Check API/CORS at ${API_BASE}.`);
    } finally {
      setBootstrapRunning(false);
    }
  };

  const handleAutoCreate = async () => {
    if (!caseName.trim()) {
      setAutoCreateStatus("No case name provided by Acquittify.");
      return;
    }

    setAutoCreateStatus("Creating matter...");
    try {
      const response = await apiFetch("/matters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: caseName.trim(),
          external_id: caseId || null,
        }),
      });

      if (response.status === 401) {
        setAuthState(null);
        setAutoCreateStatus("Session expired. Please sign in again.");
        return;
      }
      if (!response.ok) {
        setAutoCreateStatus(`Create failed (${response.status}).`);
        return;
      }

      const data = await response.json();
      setAutoCreateStatus("Matter created.");
      setSelectedMatterId(data.id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setAutoCreateStatus(`Create failed (${message}).`);
    }
  };

  const pushAgentMessage = (
    role: AgentMessage["role"],
    text: string
  ) => {
    setAgentMessages((previous) => [
      ...previous,
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        role,
        text,
        timestamp: new Date().toISOString(),
      },
    ]);
  };

  const handleOpenDocument = async (document: MatterDocumentRow) => {
    if (document.virtual_url) {
      window.open(document.virtual_url, "_blank", "noopener,noreferrer");
      return;
    }
    const documentId = document.id;
    try {
      const response = await apiFetch(`/documents/${documentId}/download-url`);
      if (response.status === 401) {
        setAuthState(null);
        return;
      }
      if (!response.ok) {
        setDocumentsStatus(`Unable to open document (${response.status}).`);
        return;
      }
      const data = await response.json();
      if (typeof data.download_url !== "string" || !data.download_url) {
        setDocumentsStatus("Unable to open document (missing URL).");
        return;
      }
      window.open(data.download_url, "_blank", "noopener,noreferrer");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setDocumentsStatus(`Unable to open document (${message}).`);
    }
  };

  const handleAgentSend = async () => {
    const query = agentInput.trim();
    if (!query || agentSubmitting) return;

    setAgentInput("");
    pushAgentMessage("user", query);

    if (!selectedMatterId) {
      pushAgentMessage("assistant", "Select a matter before running a case search.");
      return;
    }

    setAgentSubmitting(true);
    try {
      const response = await apiFetch(`/matters/${selectedMatterId}/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query, limit: 6 }),
      });
      if (response.status === 401) {
        setAuthState(null);
        return;
      }
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        const detail =
          typeof errorBody.detail === "string"
            ? errorBody.detail
            : `Agent request failed (${response.status}).`;
        pushAgentMessage("assistant", detail);
        return;
      }

      const data = (await response.json()) as AgentChatResponse;
      const answer = (data.answer || "").trim() || "No answer was generated.";
      const citations = Array.isArray(data.citations)
        ? (data.citations as AgentCitation[])
        : [];
      const citationLines = citations.slice(0, 4).map((hit, index) => {
        const name = hit.original_filename || `Document ${hit.document_id.slice(0, 8)}`;
        const page = typeof hit.page_num === "number" ? ` p.${hit.page_num}` : "";
        const snippet = truncateSnippet(hit.text_snippet || hit.text, 110);
        return `${index + 1}. ${name}${page}: ${snippet}`;
      });
      const modelLine = data.model ? `\n\nModel: ${data.model}` : "";
      if (citationLines.length) {
        pushAgentMessage(
          "assistant",
          `${answer}\n\nEvidence:\n${citationLines.join("\n")}${modelLine}`
        );
      } else {
        pushAgentMessage("assistant", `${answer}${modelLine}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      pushAgentMessage(
        "assistant",
        `Agent request failed before API response (${message}). Check API/CORS at ${API_BASE}.`
      );
    } finally {
      setAgentSubmitting(false);
    }
  };

  const isAdminUser = useMemo(() => {
    const role = String(authState?.role || "").toLowerCase();
    const email = String(authState?.user?.email || "").toLowerCase();
    return role === "admin" || role === "owner" || email === "ron@ronaldwchapman.com";
  }, [authState]);

  const loadAdminSummary = async () => {
    if (!isAdminUser) return;
    setAdminSummaryStatus("Loading ontology statistics...");
    try {
      const response = await apiFetch("/admin/caselaw/summary");
      if (response.status === 401) {
        setAuthState(null);
        setAdminSummaryStatus("Session expired. Please sign in again.");
        return;
      }
      if (response.status === 403) {
        setAdminSummaryStatus("Admin privileges required.");
        return;
      }
      if (!response.ok) {
        setAdminSummaryStatus(`Failed to load statistics (${response.status}).`);
        return;
      }
      const data = (await response.json()) as CaselawAdminSummary;
      setAdminSummary(data);
      setAdminSummaryStatus(data.exists ? null : data.reason || "Caselaw dataset not available.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setAdminSummaryStatus(`Failed to load statistics (${message}).`);
    }
  };

  const loadAdminCases = async (options?: { resetOffset?: boolean }) => {
    if (!isAdminUser) return;
    const resetOffset = Boolean(options?.resetOffset);
    const nextOffset = resetOffset ? 0 : adminOffset;
    if (resetOffset) {
      setAdminOffset(0);
    }
    setAdminCasesStatus("Loading cases...");
    try {
      const params = new URLSearchParams();
      params.set("limit", String(ADMIN_CASE_PAGE_SIZE));
      params.set("offset", String(nextOffset));
      if (adminQueryApplied.trim()) params.set("query", adminQueryApplied.trim());
      const response = await apiFetch(`/admin/caselaw/cases?${params.toString()}`);
      if (response.status === 401) {
        setAuthState(null);
        setAdminCasesStatus("Session expired. Please sign in again.");
        return;
      }
      if (response.status === 403) {
        setAdminCasesStatus("Admin privileges required.");
        return;
      }
      if (!response.ok) {
        setAdminCasesStatus(`Failed to load cases (${response.status}).`);
        return;
      }
      const data = await response.json();
      setAdminCases(Array.isArray(data.items) ? (data.items as CaselawAdminCaseRow[]) : []);
      setAdminTotalCases(Number(data.total || 0));
      setAdminCasesStatus(null);
      if (resetOffset) {
        setAdminSelectedCaseId(null);
        setAdminCaseDetail(null);
        setAdminCaseDetailStatus(null);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setAdminCasesStatus(`Failed to load cases (${message}).`);
    }
  };

  const loadAdminCaseDetail = async (caseIdToLoad: string) => {
    if (!isAdminUser || !caseIdToLoad) return;
    setAdminCaseDetailStatus("Loading frontmatter...");
    try {
      const encodedId = encodeURIComponent(caseIdToLoad);
      const response = await apiFetch(`/admin/caselaw/cases/${encodedId}`);
      if (response.status === 401) {
        setAuthState(null);
        setAdminCaseDetailStatus("Session expired. Please sign in again.");
        return;
      }
      if (response.status === 403) {
        setAdminCaseDetailStatus("Admin privileges required.");
        return;
      }
      if (!response.ok) {
        setAdminCaseDetailStatus(`Failed to load case detail (${response.status}).`);
        return;
      }
      const data = (await response.json()) as CaselawAdminCaseDetail;
      setAdminCaseDetail(data);
      setAdminCaseDetailStatus(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setAdminCaseDetailStatus(`Failed to load case detail (${message}).`);
    }
  };

  const applyAdminCaseSearch = () => {
    setAdminQueryApplied(adminQueryInput.trim());
    setAdminOffset(0);
  };

  const clearAdminCaseSearch = () => {
    setAdminQueryInput("");
    setAdminQueryApplied("");
    setAdminOffset(0);
  };

  useEffect(() => {
    if (!isAdminUser && centerTab === "ontology_admin") {
      setCenterTab("ontology_graph");
    }
  }, [centerTab, isAdminUser]);

  useEffect(() => {
    if (!isAdminUser || centerTab !== "ontology_admin") return;
    void loadAdminSummary();
  }, [centerTab, isAdminUser]);

  useEffect(() => {
    if (!isAdminUser || centerTab !== "ontology_admin") return;
    void loadAdminCases();
  }, [centerTab, isAdminUser, adminOffset, adminQueryApplied]);

  useEffect(() => {
    if (!isAdminUser || centerTab !== "ontology_admin" || !adminSelectedCaseId) return;
    void loadAdminCaseDetail(adminSelectedCaseId);
  }, [centerTab, isAdminUser, adminSelectedCaseId]);

  const selectedMatter = matters.find((matter) => matter.id === selectedMatterId) || null;
  const graphTitle = activeView === "caselaw" ? "Caselaw Ontology Graph" : "Casefile Ontology Graph";
  const centerTitle =
    centerTab === "ontology_admin" ? "Caselaw Ontology Admin" : graphTitle;
  const ontologySrc = useMemo(() => {
    if (!selectedMatterId) return "";
    const params = new URLSearchParams();
    params.set("embed", "1");
    params.set("view", activeView);
    if (activeView === "caselaw") {
      if (caselawFilters.keywords) params.set("keywords", caselawFilters.keywords);
      if (caselawFilters.circuit) params.set("circuit", caselawFilters.circuit);
      if (caselawFilters.cases) params.set("cases", caselawFilters.cases);
    }
    return `/matters/${selectedMatterId}/ontology?${params.toString()}`;
  }, [selectedMatterId, activeView, caselawFilters]);
  const vaultDocuments = useMemo(() => {
    if (!selectedMatterId) return [];
    return [BOOTSTRAP_SCHEMA_VAULT_ENTRY, ...matterDocuments];
  }, [selectedMatterId, matterDocuments]);
  const filteredDocuments = useMemo(() => {
    const query = vaultQuery.trim().toLowerCase();
    if (!query) return vaultDocuments;
    return vaultDocuments.filter((document) => {
      const name = String(document.original_filename || "").toLowerCase();
      const statusValue = String(document.status || "").toLowerCase();
      const mime = String(document.mime_type || "").toLowerCase();
      return (
        name.includes(query) ||
        statusValue.includes(query) ||
        mime.includes(query) ||
        document.id.toLowerCase().includes(query)
      );
    });
  }, [vaultDocuments, vaultQuery]);

  if (authLoading) {
    return (
      <main
        style={{
          minHeight: "100vh",
          width: "100%",
          boxSizing: "border-box",
          padding: "2.5rem",
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          background: "#0f0f0f",
          color: "#f3f3f3",
        }}
      >
        Loading session...
      </main>
    );
  }

  if (!authState) {
    return (
      <main
        style={{
          minHeight: "100vh",
          width: "100%",
          boxSizing: "border-box",
          padding: "2.5rem",
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          background: "#0f0f0f",
          color: "#f3f3f3",
        }}
      >
        <h1 style={{ marginBottom: "0.5rem" }}>Acquittify</h1>
        <p style={{ color: "#6b7280", marginTop: 0 }}>
          Sign in with your username and password.
        </p>

        <section
          className="auth-card"
          style={{
            border: "1px solid #3a3a3a",
            borderRadius: "0.75rem",
            padding: "1.25rem",
            marginTop: "1.5rem",
            maxWidth: "480px",
            background: "#080808",
          }}
        >
          <div style={{ display: "flex", gap: "0.75rem", marginBottom: "0.75rem" }}>
            <button type="button" onClick={() => setAuthMode("login")}>Login</button>
            <button type="button" onClick={() => setAuthMode("register")}>Register</button>
          </div>

          <form onSubmit={handleAuthSubmit}>
            <label style={{ display: "block", marginBottom: "0.5rem" }}>
              Username or email
              <input
                type="text"
                value={authEmail}
                onChange={(event) => setAuthEmail(event.target.value)}
                style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem" }}
              />
            </label>

            <label style={{ display: "block", marginBottom: "0.5rem" }}>
              Password
              <input
                type="password"
                value={authPassword}
                onChange={(event) => setAuthPassword(event.target.value)}
                style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem" }}
              />
            </label>

            {authMode === "register" && (
              <>
                <label style={{ display: "block", marginBottom: "0.5rem" }}>
                  Full name (optional)
                  <input
                    type="text"
                    value={authFullName}
                    onChange={(event) => setAuthFullName(event.target.value)}
                    style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem" }}
                  />
                </label>

                <label style={{ display: "block", marginBottom: "0.5rem" }}>
                  Organization name (optional)
                  <input
                    type="text"
                    value={authOrgName}
                    onChange={(event) => setAuthOrgName(event.target.value)}
                    style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem" }}
                  />
                </label>
              </>
            )}

            <button
              type="submit"
              disabled={authSubmitting || (authRetryAfterSec || 0) > 0 || mfaRequired}
            >
              {authSubmitting
                ? "Submitting..."
                : mfaRequired
                  ? "2FA pending"
                : authMode === "login"
                  ? "Sign in"
                  : "Create account"}
            </button>
          </form>

          {mfaRequired && (
            <section
              style={{
                marginTop: "1rem",
                borderTop: "1px solid #2f2f2f",
                paddingTop: "0.9rem",
              }}
            >
              <h3 style={{ marginTop: 0, marginBottom: "0.5rem" }}>Two-Factor Verification</h3>
              <form onSubmit={handleMfaLoginVerify}>
                <label style={{ display: "block", marginBottom: "0.5rem" }}>
                  Authenticator code
                  <input
                    type="text"
                    value={mfaCode}
                    onChange={(event) => setMfaCode(event.target.value)}
                    style={{
                      display: "block",
                      width: "100%",
                      marginTop: "0.25rem",
                      padding: "0.5rem",
                    }}
                  />
                </label>
                <button type="submit" disabled={mfaSubmitting}>
                  {mfaSubmitting ? "Verifying..." : "Verify 2FA"}
                </button>
                <button
                  type="button"
                  style={{ marginLeft: "0.5rem" }}
                  onClick={() => {
                    setMfaRequired(false);
                    setMfaTicket("");
                    setMfaCode("");
                    setMfaStatus(null);
                  }}
                >
                  Cancel
                </button>
              </form>
              {mfaStatus && (
                <div style={{ marginTop: "0.5rem", color: "#374151" }}>{mfaStatus}</div>
              )}
            </section>
          )}

          {authMode === "login" && (
            <div style={{ marginTop: "0.65rem" }}>
              <button
                type="button"
                onClick={() => {
                  setShowPasswordHelp((value) => !value);
                  setForgotEmail(authEmail.trim() || forgotEmail);
                }}
              >
                {showPasswordHelp ? "Hide password help" : "Forgot password?"}
              </button>
            </div>
          )}

          {authError && (
            <div style={{ marginTop: "0.75rem", color: "#b91c1c" }}>
              {authError}
            </div>
          )}
          {authRetryAfterSec && authRetryAfterSec > 0 && (
            <div style={{ marginTop: "0.5rem", color: "#92400e" }}>
              Sign-in temporarily paused due to repeated attempts. Retry in{" "}
              {authRetryAfterSec}s.
            </div>
          )}

          {showPasswordHelp && authMode === "login" && (
            <section
              style={{
                marginTop: "1rem",
                borderTop: "1px solid #2f2f2f",
                paddingTop: "0.9rem",
              }}
            >
              <h3 style={{ marginTop: 0, marginBottom: "0.5rem" }}>Password Recovery</h3>
              <form onSubmit={handleForgotPassword}>
                <label style={{ display: "block", marginBottom: "0.5rem" }}>
                  Account email
                  <input
                    type="email"
                    value={forgotEmail}
                    onChange={(event) => setForgotEmail(event.target.value)}
                    style={{
                      display: "block",
                      width: "100%",
                      marginTop: "0.25rem",
                      padding: "0.5rem",
                    }}
                  />
                </label>
                <button type="submit">Request reset code</button>
              </form>
              {forgotStatus && (
                <div style={{ marginTop: "0.5rem", color: "#374151" }}>{forgotStatus}</div>
              )}
              {devResetToken && (
                <div style={{ marginTop: "0.5rem", color: "#b45309" }}>
                  Reset code: <code>{devResetToken}</code>
                </div>
              )}

              <form onSubmit={handleResetPassword} style={{ marginTop: "0.9rem" }}>
                <label style={{ display: "block", marginBottom: "0.5rem" }}>
                  Reset code
                  <input
                    type="text"
                    value={resetToken}
                    onChange={(event) => setResetToken(event.target.value)}
                    style={{
                      display: "block",
                      width: "100%",
                      marginTop: "0.25rem",
                      padding: "0.5rem",
                    }}
                  />
                </label>
                <label style={{ display: "block", marginBottom: "0.5rem" }}>
                  New password
                  <input
                    type="password"
                    value={resetPassword}
                    onChange={(event) => setResetPassword(event.target.value)}
                    style={{
                      display: "block",
                      width: "100%",
                      marginTop: "0.25rem",
                      padding: "0.5rem",
                    }}
                  />
                </label>
                <button type="submit">Reset password</button>
              </form>
              {resetStatus && (
                <div style={{ marginTop: "0.5rem", color: "#374151" }}>{resetStatus}</div>
              )}
            </section>
          )}
        </section>
        <style jsx>{`
          .auth-card button,
          .auth-card input {
            background: #111;
            color: #f3f3f3;
            border: 1px solid #3d3d3d;
            border-radius: 8px;
          }
          .auth-card button {
            padding: 0.42rem 0.78rem;
          }
          .auth-card button:hover {
            background: #1a1a1a;
          }
          .auth-card button:disabled {
            opacity: 0.7;
            cursor: not-allowed;
          }
          .auth-card input::placeholder {
            color: #8b8b8b;
          }
          .auth-card input:focus {
            outline: none;
            border-color: #6b7280;
            box-shadow: 0 0 0 1px #6b7280;
          }
        `}</style>
      </main>
    );
  }

  return (
    <main className={styles.shell}>
      <aside className={styles.leftPane}>
        <div className={styles.leftHeader}>
          <div className={styles.matterTitle}>
            {selectedMatter?.name || centerTitle}
          </div>
          <div className={styles.userLine}>
            {authState.user.email} ({authState.organization.name})
          </div>
          <div className={styles.viewSwitch}>
            <button
              type="button"
              className={
                activeView === "casefile" ? styles.viewButtonActive : styles.viewButton
              }
              onClick={() => setActiveView("casefile")}
            >
              Casefile View
            </button>
            <button
              type="button"
              className={
                activeView === "caselaw" ? styles.viewButtonActive : styles.viewButton
              }
              onClick={() => setActiveView("caselaw")}
            >
              Caselaw View
            </button>
          </div>
          <div className={styles.leftActions}>
            <button type="button" onClick={loadSession}>
              Refresh Session
            </button>
            <button type="button" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>

        <section className={styles.leftCard}>
          <div className={styles.cardLabel}>Matter</div>
          <select
            className={styles.matterSelect}
            value={selectedMatterId}
            onChange={(event) => setSelectedMatterId(event.target.value)}
          >
            <option value="" disabled>
              Select matter
            </option>
            {matters.map((matter) => (
              <option key={matter.id} value={matter.id}>
                {matter.name}
              </option>
            ))}
          </select>
          {mattersStatus && <div className={`${styles.notice} ${styles.noticeWarn}`}>{mattersStatus}</div>}
          {autoStatus && <div className={styles.notice}>{autoStatus}</div>}
          {caseName && !selectedMatterId && (
            <button className={styles.createButton} type="button" onClick={handleAutoCreate}>
              Create matter for "{caseName}"
            </button>
          )}
          {autoCreateStatus && <div className={styles.notice}>{autoCreateStatus}</div>}
        </section>

        <section className={styles.leftCard}>
          <div className={styles.cardLabel}>View Mode</div>
          <div className={styles.viewSwitch}>
            <button
              type="button"
              className={
                activeView === "casefile" ? styles.viewButtonActive : styles.viewButton
              }
              onClick={() => setActiveView("casefile")}
            >
              Casefile View
            </button>
            <button
              type="button"
              className={
                activeView === "caselaw" ? styles.viewButtonActive : styles.viewButton
              }
              onClick={() => setActiveView("caselaw")}
            >
              Caselaw View
            </button>
          </div>
        </section>

        {SHOW_SIDEBAR_2FA && (
          <section className={styles.leftCard}>
            <div className={styles.cardLabel}>Security</div>
            <div className={styles.notice}>
              2FA: {authState.user.mfa_enabled ? "Enabled" : "Not enabled"}
            </div>
            {!authState.user.mfa_enabled && !mfaSetupSecret && (
              <button
                className={styles.createButton}
                type="button"
                onClick={handleStartMfaSetup}
              >
                Enable 2FA
              </button>
            )}
            {mfaSetupSecret && (
              <div style={{ marginTop: "0.5rem" }}>
                <div className={styles.notice}>
                  Add this key in your authenticator app:
                  <div style={{ marginTop: "0.35rem", fontFamily: "monospace" }}>
                    {mfaSetupSecret}
                  </div>
                </div>
                {mfaSetupUri && (
                  <div className={styles.notice} style={{ wordBreak: "break-all" }}>
                    URI: {mfaSetupUri}
                  </div>
                )}
                <form onSubmit={handleVerifyMfaSetup} className={styles.createRow}>
                  <input
                    className={styles.createInput}
                    type="text"
                    value={mfaSetupCode}
                    onChange={(event) => setMfaSetupCode(event.target.value)}
                    placeholder="Authenticator code"
                  />
                  <button className={styles.createButton} type="submit">
                    Verify
                  </button>
                </form>
              </div>
            )}
            {mfaBackupCodes.length > 0 && (
              <div className={styles.notice} style={{ whiteSpace: "pre-wrap" }}>
                Backup codes:
                {"\n"}
                {mfaBackupCodes.join("\n")}
              </div>
            )}
            {securityStatus && <div className={styles.notice}>{securityStatus}</div>}
          </section>
        )}

        {activeView === "casefile" ? (
          <>
            <div className={styles.leftSearchWrap}>
              <input
                className={styles.leftSearch}
                placeholder="Search vault..."
                value={vaultQuery}
                onChange={(event) => setVaultQuery(event.target.value)}
              />
            </div>

            <section className={styles.leftCard}>
              <div className={styles.cardLabel}>Create Matter</div>
              <form onSubmit={handleCreateMatter} className={styles.createRow}>
                <input
                  className={styles.createInput}
                  type="text"
                  value={matterName}
                  onChange={(event) => setMatterName(event.target.value)}
                  placeholder="Matter name"
                />
                <button className={styles.createButton} type="submit">
                  Create
                </button>
              </form>
              {status && <div className={styles.notice}>{status}</div>}
              {createdMatterId && (
                <div className={styles.notice}>Created and selected new matter.</div>
              )}
            </section>

            <section className={styles.leftCard}>
              <div className={styles.cardLabel}>Upload Documents</div>
              <form onSubmit={handleUploadDocuments} className={styles.uploadForm}>
                <input
                  ref={uploadInputRef}
                  className={styles.uploadInput}
                  type="file"
                  multiple
                  onChange={(event) => {
                    const files = event.target.files ? Array.from(event.target.files) : [];
                    setUploadFiles(files);
                    setUploadStatus(null);
                  }}
                  accept=".pdf,.txt,.csv,.json,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
                />
                <div className={styles.uploadMeta}>
                  {uploadFiles.length
                    ? `${uploadFiles.length} file${uploadFiles.length === 1 ? "" : "s"} selected`
                    : "No files selected"}
                </div>
                <button
                  className={styles.createButton}
                  type="submit"
                  disabled={!selectedMatterId || uploading || !uploadFiles.length}
                >
                  {uploading ? "Uploading..." : "Upload files"}
                </button>
              </form>
              {uploadStatus && <div className={styles.notice}>{uploadStatus}</div>}
            </section>

            <section className={styles.leftCard}>
              <div className={styles.cardLabel}>Bootstrap</div>
              <button
                className={styles.createButton}
                type="button"
                onClick={() => void handleBootstrapMatter()}
                disabled={!selectedMatterId || bootstrapRunning || uploading}
              >
                {bootstrapRunning ? "Bootstrapping..." : "Run Bootstrap"}
              </button>
              <div className={styles.notice}>
                Queues bootstrap processing for all eligible matter documents.
              </div>
              {bootstrapStatus && <div className={styles.notice}>{bootstrapStatus}</div>}
            </section>

            <div className={styles.leftTree}>
              <div className={styles.treeHeader}>Vault</div>
              {!selectedMatterId && (
                <div className={`${styles.treeItem} ${styles.treeItemMuted}`}>
                  Select a matter to load ontology graph.
                </div>
              )}
              {selectedMatterId && documentsLoading && (
                <div className={`${styles.treeItem} ${styles.treeItemMuted}`}>
                  Loading vault documents...
                </div>
              )}
              {selectedMatterId &&
                !documentsLoading &&
                filteredDocuments.map((document) => (
                  <button
                    key={document.id}
                    type="button"
                    className={styles.treeDocButton}
                    onClick={() => void handleOpenDocument(document)}
                    title={document.original_filename || document.id}
                  >
                    <span className={styles.treeDocName}>
                      {document.original_filename || `Document ${document.id.slice(0, 8)}`}
                    </span>
                    <span className={styles.treeDocMeta}>
                      {(document.status || "unknown").toUpperCase()}
                    </span>
                  </button>
                ))}
              {selectedMatterId && !documentsLoading && filteredDocuments.length < 1 && (
                <div className={`${styles.treeItem} ${styles.treeItemMuted}`}>
                  {matterDocuments.length
                    ? "No documents match your vault search."
                    : "No documents in this matter yet."}
                </div>
              )}
              {selectedMatterId && documentsStatus && (
                <div className={styles.leftTreeStatus}>{documentsStatus}</div>
              )}
            </div>
          </>
        ) : (
          <section className={styles.leftCard}>
            <div className={styles.cardLabel}>Caselaw Search & Filters</div>
            <input
              className={styles.filterInput}
              type="text"
              placeholder="Keywords (comma-separated)"
              value={caselawKeywordsInput}
              onChange={(event) => setCaselawKeywordsInput(event.target.value)}
            />
            <select
              className={styles.filterSelect}
              value={caselawCircuitInput}
              onChange={(event) => setCaselawCircuitInput(event.target.value)}
            >
              <option value="">All circuits</option>
              {CASELAW_CIRCUIT_OPTIONS.filter((value) => value).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <input
              className={styles.filterInput}
              type="text"
              placeholder="Case filters (e.g. Brady v. Maryland, Strickland)"
              value={caselawCasesInput}
              onChange={(event) => setCaselawCasesInput(event.target.value)}
            />
            <div className={styles.filterHelp}>
              Filters apply to the caselaw ontology graph. Add multiple terms with commas.
            </div>
            <div className={styles.filterActions}>
              <button
                className={styles.createButton}
                type="button"
                onClick={applyCaselawFilters}
                disabled={!selectedMatterId || !caselawFiltersDirty}
              >
                Apply Filters
              </button>
              <button
                className={styles.createButton}
                type="button"
                onClick={clearCaselawFilters}
                disabled={!selectedMatterId}
              >
                Clear
              </button>
            </div>
            {caselawFiltersDirty && (
              <div className={`${styles.notice} ${styles.noticeWarn}`}>
                You have unapplied caselaw filter changes.
              </div>
            )}
            {!caselawFiltersDirty && selectedMatterId && (
              <div className={styles.notice}>
                Showing {graphTitle.toLowerCase()} for {selectedMatter?.name || "selected matter"}.
              </div>
            )}
          </section>
        )}
      </aside>

      <section className={styles.centerPane}>
        <div className={styles.tabs}>
          <button
            type="button"
            className={centerTab === "ontology_graph" ? styles.tabActive : styles.tab}
            onClick={() => setCenterTab("ontology_graph")}
          >
            Ontology Graph
          </button>
          {isAdminUser && (
            <button
              type="button"
              className={centerTab === "ontology_admin" ? styles.tabActive : styles.tab}
              onClick={() => setCenterTab("ontology_admin")}
            >
              Ontology Admin
            </button>
          )}
        </div>
        <div className={styles.centerHost}>
          {centerTab === "ontology_graph" ? (
            ontologySrc ? (
              <iframe
                key={ontologySrc}
                src={ontologySrc}
                className={styles.ontologyFrame}
                title={centerTitle}
              />
            ) : (
              <div className={styles.emptyState}>Select or create a matter to load the ontology dashboard.</div>
            )
          ) : (
            <section className={styles.adminPanel}>
              <div className={styles.adminToolbar}>
                <div className={styles.cardLabel}>Caselaw Ontology Admin</div>
                <button
                  className={styles.createButton}
                  type="button"
                  onClick={() => {
                    void loadAdminSummary();
                    void loadAdminCases();
                  }}
                >
                  Refresh
                </button>
              </div>

              {adminSummaryStatus && <div className={styles.notice}>{adminSummaryStatus}</div>}
              <div className={styles.adminMetricsGrid}>
                <div className={styles.adminMetricCard}>
                  <div className={styles.cardLabel}>Cases</div>
                  <div>{Number(adminSummary?.cases?.total || 0).toLocaleString()}</div>
                </div>
                <div className={styles.adminMetricCard}>
                  <div className={styles.cardLabel}>Nodes</div>
                  <div>{Number(adminSummary?.graph?.nodes || 0).toLocaleString()}</div>
                </div>
                <div className={styles.adminMetricCard}>
                  <div className={styles.cardLabel}>Edges</div>
                  <div>{Number(adminSummary?.graph?.edges || 0).toLocaleString()}</div>
                </div>
                <div className={styles.adminMetricCard}>
                  <div className={styles.cardLabel}>Touched Last Hour</div>
                  <div>{Number(adminSummary?.cases?.touched_last_hour || 0).toLocaleString()}</div>
                </div>
                <div className={styles.adminMetricCard}>
                  <div className={styles.cardLabel}>Touched Last 24h</div>
                  <div>{Number(adminSummary?.cases?.touched_last_24h || 0).toLocaleString()}</div>
                </div>
              </div>

              <div className={styles.adminToolbar}>
                <input
                  className={styles.filterInput}
                  type="text"
                  placeholder="Search cases (name, case_id, citation, court)"
                  value={adminQueryInput}
                  onChange={(event) => setAdminQueryInput(event.target.value)}
                />
                <button
                  className={styles.createButton}
                  type="button"
                  onClick={applyAdminCaseSearch}
                >
                  Search
                </button>
                <button
                  className={styles.createButton}
                  type="button"
                  onClick={clearAdminCaseSearch}
                >
                  Clear
                </button>
              </div>

              <div className={styles.adminContentGrid}>
                <section className={styles.adminCasesPane}>
                  {adminCasesStatus && <div className={styles.notice}>{adminCasesStatus}</div>}
                  <div className={styles.adminCasesTableWrap}>
                    <table className={styles.adminTable}>
                      <thead>
                        <tr>
                          <th>Case</th>
                          <th>Citation</th>
                          <th>Court</th>
                          <th>Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adminCases.map((row) => (
                          <tr
                            key={row.case_id}
                            onClick={() => setAdminSelectedCaseId(row.case_id)}
                            className={adminSelectedCaseId === row.case_id ? styles.adminRowSelected : ""}
                          >
                            <td>{row.case_name || row.case_id}</td>
                            <td>{row.primary_citation || ""}</td>
                            <td>{row.court_name || row.court_id || ""}</td>
                            <td>{row.date_filed || ""}</td>
                          </tr>
                        ))}
                        {adminCases.length < 1 && (
                          <tr>
                            <td colSpan={4}>No cases match this search.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className={styles.adminToolbar}>
                    <div className={styles.notice}>
                      Showing {adminCases.length.toLocaleString()} of {adminTotalCases.toLocaleString()}
                    </div>
                    <button
                      className={styles.createButton}
                      type="button"
                      disabled={adminOffset <= 0}
                      onClick={() => setAdminOffset((value) => Math.max(0, value - ADMIN_CASE_PAGE_SIZE))}
                    >
                      Prev
                    </button>
                    <button
                      className={styles.createButton}
                      type="button"
                      disabled={adminOffset + adminCases.length >= adminTotalCases}
                      onClick={() => setAdminOffset((value) => value + ADMIN_CASE_PAGE_SIZE)}
                    >
                      Next
                    </button>
                  </div>
                </section>

                <section className={styles.adminDetailPane}>
                  {adminCaseDetailStatus && <div className={styles.notice}>{adminCaseDetailStatus}</div>}
                  {adminCaseDetail ? (
                    <div className={styles.adminFrontmatterPane}>
                      <div className={styles.cardLabel}>Frontmatter: {adminCaseDetail.case_name}</div>
                      <pre>
                        {JSON.stringify(adminCaseDetail.frontmatter || {}, null, 2)}
                      </pre>
                    </div>
                  ) : (
                    <div className={styles.adminFrontmatterEmpty}>
                      Select a case to inspect normalized frontmatter.
                    </div>
                  )}
                </section>
              </div>
            </section>
          )}
        </div>
      </section>

      <aside className={styles.rightPane}>
        <div className={styles.rightHeader}>
          <div className={styles.rightTitle}>Agent</div>
          <div className={styles.agentContext}>
            {selectedMatter?.name || "No matter selected"}
          </div>
        </div>
        <div className={styles.agentLog}>
          {agentMessages.map((message) => (
            <div
              key={message.id}
              className={`${styles.agentMessage} ${
                message.role === "user"
                  ? styles.agentMessageUser
                  : message.role === "assistant"
                    ? styles.agentMessageAssistant
                    : styles.agentMessageSystem
              }`}
            >
              <div className={styles.agentMessageMeta}>
                {message.role} · {formatMessageTime(message.timestamp)}
              </div>
              <div className={styles.agentMessageBody}>{message.text}</div>
            </div>
          ))}
        </div>
        <div className={styles.agentInputWrap}>
          <textarea
            className={styles.agentInput}
            placeholder="Ask the agent..."
            value={agentInput}
            onChange={(event) => setAgentInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleAgentSend();
              }
            }}
          />
          <button
            className={styles.agentSend}
            type="button"
            onClick={() => void handleAgentSend()}
            disabled={agentSubmitting || !agentInput.trim()}
          >
            {agentSubmitting ? "Searching..." : "Send"}
          </button>
        </div>
      </aside>
    </main>
  );
}
