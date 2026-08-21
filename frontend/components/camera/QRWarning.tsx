import Link from "next/link";
export function QRWarning() {
  return <section className="luxury-card mx-auto max-w-lg text-center" role="alert">
    <div className="mx-auto mb-5 grid size-16 place-items-center rounded-full border border-[#c9a84c] text-3xl">!</div>
    <h1 className="font-display text-3xl text-[#c9a84c]">Official verification required</h1>
    <p className="my-5 text-zinc-300">This QR code can only be verified through our official app</p>
    <p className="mb-6 text-sm text-zinc-500">Open JewelPass, allow camera access, and scan the code again.</p>
    <Link className="gold-button" href="/scan">Open official scanner</Link>
  </section>;
}
