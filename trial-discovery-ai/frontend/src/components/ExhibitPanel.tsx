type ExhibitPanelProps = {
  purposes: string[];
};

export default function ExhibitPanel({ purposes }: ExhibitPanelProps) {
  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "0.75rem",
        padding: "1rem",
      }}
    >
      <h3 style={{ marginTop: 0 }}>Exhibit Purposes</h3>
      <ul style={{ margin: 0, paddingLeft: "1rem" }}>
        {purposes.map((purpose) => (
          <li key={purpose}>{purpose}</li>
        ))}
      </ul>
    </section>
  );
}
