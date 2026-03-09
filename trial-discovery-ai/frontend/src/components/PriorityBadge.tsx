type PriorityBadgeProps = {
  code: "P1" | "P2" | "P3" | "P4";
};

const colors: Record<PriorityBadgeProps["code"], string> = {
  P1: "#b91c1c",
  P2: "#d97706",
  P3: "#0f766e",
  P4: "#4b5563",
};

export default function PriorityBadge({ code }: PriorityBadgeProps) {
  return (
    <span
      style={{
        backgroundColor: colors[code],
        color: "#fff",
        padding: "0.15rem 0.5rem",
        borderRadius: "0.4rem",
        fontSize: "0.75rem",
        fontWeight: 600,
      }}
    >
      {code}
    </span>
  );
}
