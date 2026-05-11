type Props = {
  label?: string;
};

export function Loading({ label = "Loading…" }: Props) {
  return (
    <div className="flex items-center gap-3 text-sm text-neutral-500">
      <span
        aria-hidden
        className="inline-block h-3 w-3 animate-pulse rounded-full bg-neutral-400"
      />
      <span>{label}</span>
    </div>
  );
}
