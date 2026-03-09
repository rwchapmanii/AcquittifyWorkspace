type DocViewerProps = {
  title: string;
  body: string;
};

export default function DocViewer({ title, body }: DocViewerProps) {
  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "0.75rem",
        padding: "1rem",
        minHeight: "300px",
      }}
    >
      <h2 style={{ marginTop: 0 }}>{title}</h2>
      <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>{body}</pre>
    </section>
  );
}
