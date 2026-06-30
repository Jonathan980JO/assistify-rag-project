import { Search } from "lucide-react";

export function SearchInput({
  value,
  onChange,
  placeholder = "Search...",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative flex-1">
      <Search className="absolute top-1/2 left-3 h-5 w-5 -translate-y-1/2 text-[#9ca3af]" />
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-[#333333] bg-[#2b2b2b] py-3 pr-4 pl-10 text-[#fafaff] placeholder-[#9ca3af] focus:border-[#10a37f] focus:outline-none"
      />
    </div>
  );
}
