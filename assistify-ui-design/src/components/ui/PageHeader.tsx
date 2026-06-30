export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6 sm:mb-8">
      <h1 className="mb-1 text-2xl font-bold text-[#fafaff] sm:mb-2 sm:text-3xl">{title}</h1>
      {subtitle && <p className="text-sm text-[#9ca3af] sm:text-base">{subtitle}</p>}
    </div>
  );
}
