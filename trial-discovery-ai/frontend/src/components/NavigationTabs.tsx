type NavigationTabsProps = {
  basePath?: string;
};

export default function NavigationTabs({ basePath = "/matters/1" }: NavigationTabsProps) {
  const tabs = [
    { label: "Matter", href: `${basePath}` },
    { label: "Hot Docs", href: `${basePath}/hotdocs` },
    { label: "Exhibits", href: `${basePath}/exhibits` },
    { label: "Witnesses", href: `${basePath}/witnesses` },
    { label: "Ontology", href: `${basePath}/ontology` },
  ];

  return (
    <nav style={{ marginTop: "0.5rem", marginBottom: "1rem" }}>
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
        {tabs.map((tab) => (
          <a
            key={tab.label}
            href={tab.href}
            style={{
              padding: "0.45rem 0.9rem",
              borderRadius: "999px",
              border: "1px solid #e5e7eb",
              background: "#f9fafb",
              color: "#111827",
              textDecoration: "none",
              fontSize: "0.9rem",
              fontWeight: 600,
            }}
          >
            {tab.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
