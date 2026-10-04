import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-20 text-center">
      <p className="text-xs font-medium uppercase tracking-[0.14em] text-sage">Not found</p>
      <h1 className="mt-2 font-serif text-3xl text-forest">This page isn&apos;t on the menu.</h1>
      <Link href="/" className="mt-6 inline-block text-sm font-medium text-forest underline">
        Back to the overview
      </Link>
    </div>
  );
}
