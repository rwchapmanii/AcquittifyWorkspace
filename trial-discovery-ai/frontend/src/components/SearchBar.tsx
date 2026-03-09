type SearchBarProps = {
  placeholder?: string;
  onChange?: (value: string) => void;
};

export default function SearchBar({ placeholder = "Search", onChange }: SearchBarProps) {
  return (
    <input
      type="search"
      placeholder={placeholder}
      onChange={(event) => onChange?.(event.target.value)}
      style={{
        width: "100%",
        padding: "0.6rem 0.8rem",
        borderRadius: "0.5rem",
        border: "1px solid #e5e7eb",
      }}
    />
  );
}
