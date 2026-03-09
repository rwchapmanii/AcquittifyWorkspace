type WitnessListProps = {
  witnesses: { id: string; name: string; docs: number }[];
};

export default function WitnessList({ witnesses }: WitnessListProps) {
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {witnesses.map((witness) => (
        <li
          key={witness.id}
          style={{
            padding: "0.6rem 0.4rem",
            borderBottom: "1px solid #e5e7eb",
          }}
        >
          <strong>{witness.name}</strong>
          <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
            {witness.docs} docs
          </div>
        </li>
      ))}
    </ul>
  );
}
