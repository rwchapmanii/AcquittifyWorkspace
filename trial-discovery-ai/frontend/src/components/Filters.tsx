export default function Filters() {
  return (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
      <select style={{ padding: "0.4rem" }}>
        <option>Doc Type</option>
        <option>Email</option>
        <option>PDF</option>
      </select>
      <select style={{ padding: "0.4rem" }}>
        <option>Date Range</option>
        <option>Last 30 days</option>
        <option>Last 90 days</option>
      </select>
      <select style={{ padding: "0.4rem" }}>
        <option>Exhibit Only</option>
        <option>Yes</option>
        <option>No</option>
      </select>
    </div>
  );
}
