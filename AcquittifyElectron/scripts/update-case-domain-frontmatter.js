#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const yaml = require('js-yaml');

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

function normalizeCaseDomain(value) {
  const raw = String(value || '').trim().toLowerCase();
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
  const raw = String(value || '').trim().toLowerCase();
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

function firstMarkdownHeading(body) {
  const lines = String(body || '').split(/\r?\n/);
  for (const line of lines) {
    const m = line.match(/^#\s+(.+?)\s*$/);
    if (m && m[1]) return m[1].trim();
  }
  return '';
}

function inferCaseDomainFromInputs(input = {}) {
  const explicitCandidates = [
    input.caseDomain,
    input.caseType,
    input.domain,
    input.matterType,
    input.practiceArea
  ];
  const flattened = [];
  for (const candidate of explicitCandidates) {
    if (Array.isArray(candidate)) flattened.push(...candidate);
    else flattened.push(candidate);
  }
  if (Array.isArray(input.tags)) flattened.push(...input.tags);

  for (const candidate of flattened) {
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
  const bodyExcerpt = String(input.bodyExcerpt || '').slice(0, 20000);
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
  if (
    /\bv\.?\b/.test(caption) &&
    /\b(inc\.?|llc|corp\.?|company|insurance|bank|board|commission|city|county|school|university)\b/.test(caption)
  ) {
    civilScore += 2;
  }
  if (/^\s*in re\b/.test(caption)) {
    civilScore += 1;
  }
  if (pathLike.toLowerCase().includes('/criminal/')) criminalScore += 2;
  if (pathLike.toLowerCase().includes('/civil/')) civilScore += 2;

  if (criminalScore > civilScore) return 'criminal';
  return 'civil';
}

function splitFrontmatter(text) {
  const source = String(text || '');
  const newline = source.includes('\r\n') ? '\r\n' : '\n';
  if (!source.startsWith(`---${newline}`) && !source.startsWith('---\n') && !source.startsWith('---\r\n')) {
    return {
      hasFrontmatter: false,
      frontmatter: '',
      body: source,
      newline,
      frontmatterBlock: ''
    };
  }

  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!match) {
    return {
      hasFrontmatter: false,
      frontmatter: '',
      body: source,
      newline,
      frontmatterBlock: ''
    };
  }

  return {
    hasFrontmatter: true,
    frontmatter: match[1],
    body: source.slice(match[0].length),
    newline,
    frontmatterBlock: match[0]
  };
}

function parseFrontmatter(frontmatterText) {
  try {
    const parsed = yaml.load(frontmatterText);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
    return {};
  } catch {
    return {};
  }
}

function upsertCaseDomainInFrontmatter(frontmatterText, caseDomain, newline) {
  const lines = String(frontmatterText || '').split(/\r?\n/);
  const assignment = `case_domain: ${caseDomain}`;
  const existingIdx = lines.findIndex((line) => /^\s*case_domain\s*:/i.test(line));
  if (existingIdx >= 0) {
    lines[existingIdx] = assignment;
    return lines.join(newline);
  }

  const preferredAnchor = lines.findIndex((line) => /^\s*(case_id|title)\s*:/i.test(line));
  if (preferredAnchor >= 0) {
    lines.splice(preferredAnchor + 1, 0, assignment);
  } else {
    lines.push(assignment);
  }
  return lines.join(newline);
}

function walkCaseNotes(dir, out = []) {
  let entries = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }

  for (const entry of entries) {
    if (!entry) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkCaseNotes(full, out);
      continue;
    }
    if (entry.isFile() && /\.(md|markdown)$/i.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function discoverCaseRoots() {
  const docsRoot = path.join(
    os.homedir(),
    'Library',
    'Mobile Documents',
    'iCloud~md~obsidian',
    'Documents'
  );

  const roots = [];
  let entries = [];
  try {
    entries = fs.readdirSync(docsRoot, { withFileTypes: true });
  } catch {
    return roots;
  }

  for (const entry of entries) {
    if (!entry?.isDirectory?.()) continue;
    const caseRoot = path.join(docsRoot, entry.name, 'Ontology', 'precedent_vault', 'cases');
    try {
      if (fs.existsSync(caseRoot) && fs.statSync(caseRoot).isDirectory()) {
        roots.push(caseRoot);
      }
    } catch {
      // ignore unreadable entries
    }
  }
  return roots;
}

function parseArgs(argv) {
  const args = Array.isArray(argv) ? argv.slice(2) : [];
  const options = {
    dryRun: false,
    roots: []
  };

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--dry-run') {
      options.dryRun = true;
      continue;
    }
    if ((arg === '--root' || arg === '--vault-root') && args[i + 1]) {
      options.roots.push(path.resolve(args[i + 1]));
      i += 1;
    }
  }
  return options;
}

function main() {
  const options = parseArgs(process.argv);
  const roots = options.roots.length ? options.roots : discoverCaseRoots();

  if (!roots.length) {
    console.log('No ontology case roots found.');
    process.exit(0);
  }

  const files = [];
  for (const root of roots) {
    walkCaseNotes(root, files);
  }

  let changed = 0;
  let unchanged = 0;
  let failures = 0;
  const domainCounts = { criminal: 0, civil: 0 };

  for (const file of files) {
    let raw = '';
    try {
      raw = fs.readFileSync(file, 'utf-8');
    } catch (err) {
      failures += 1;
      console.error(`[read-failed] ${file}: ${err.message}`);
      continue;
    }

    const { hasFrontmatter, frontmatter, body, newline } = splitFrontmatter(raw);
    const data = parseFrontmatter(frontmatter);
    const heading = firstMarkdownHeading(body);
    const title = String(data.title || heading || '').trim();
    const summary = String(data.case_summary || '').trim();
    const holding = String(data.essential_holding || '').trim();
    const tags = Array.isArray(data.tags) ? data.tags : [];

    const domain = inferCaseDomainFromInputs({
      caseDomain: data.case_domain,
      caseType: data.case_type,
      domain: data.domain,
      matterType: data.matter_type,
      practiceArea: data.practice_area,
      ruleType: data.rule_type,
      tags,
      isCriminalCase: data.is_criminal_case,
      criminalCase: data.criminal_case,
      isCivilCase: data.is_civil_case,
      civilCase: data.civil_case,
      authorityAnchors: Array.isArray(data.authority_anchors) ? data.authority_anchors : [],
      pathLike: file,
      title,
      summary,
      holding,
      bodyExcerpt: body
    });

    const resolvedDomain = domain === 'criminal' ? 'criminal' : 'civil';
    domainCounts[resolvedDomain] = (domainCounts[resolvedDomain] || 0) + 1;

    const existingDomain = normalizeCaseDomain(data.case_domain || '') || 'civil';
    const nextFrontmatter = upsertCaseDomainInFrontmatter(frontmatter, resolvedDomain, newline);
    const nextText = hasFrontmatter
      ? `---${newline}${nextFrontmatter}${newline}---${newline}${body}`
      : `---${newline}case_domain: ${resolvedDomain}${newline}---${newline}${raw}`;

    if (nextText === raw && existingDomain === resolvedDomain) {
      unchanged += 1;
      continue;
    }

    if (!options.dryRun) {
      try {
        fs.writeFileSync(file, nextText, 'utf-8');
      } catch (err) {
        failures += 1;
        console.error(`[write-failed] ${file}: ${err.message}`);
        continue;
      }
    }

    changed += 1;
  }

  const mode = options.dryRun ? 'DRY RUN' : 'WRITE';
  console.log(`Mode: ${mode}`);
  console.log(`Roots: ${roots.length}`);
  console.log(`Files scanned: ${files.length}`);
  console.log(`Updated: ${changed}`);
  console.log(`Unchanged: ${unchanged}`);
  console.log(`Failures: ${failures}`);
  console.log(`Domain counts: criminal=${domainCounts.criminal || 0}, civil=${domainCounts.civil || 0}`);

  if (failures > 0) process.exitCode = 1;
}

main();
