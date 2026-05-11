type Props = {
  title: string;
  detail?: string | null;
};

export function ErrorBanner({ title, detail }: Props) {
  return (
    <div
      role="alert"
      className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
    >
      <p className="font-medium">{title}</p>
      {detail ? <p className="mt-1 text-red-700">{detail}</p> : null}
    </div>
  );
}
