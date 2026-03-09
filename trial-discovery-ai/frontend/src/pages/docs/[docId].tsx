import DocViewer from "../../components/DocViewer";

export default function DocumentView() {
  return (
    <main style={{ padding: "2rem", fontFamily: "system-ui" }}>
      <h1>Document Viewer</h1>
      <DocViewer
        title="Sample Document"
        body="Pass 1 facts, Pass 2 signals, Pass 4 priority will render here."
      />
      <div style={{ marginTop: "1rem" }}>
        <button style={{ marginRight: "0.5rem" }}>Mark Hot</button>
        <button>Mark Exhibit</button>
      </div>
    </main>
  );
}
