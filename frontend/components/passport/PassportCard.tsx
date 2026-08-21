import type { Product } from "@/lib/api";
export function PassportCard({ product }: { product: Product }) {
 const details = [["Gem", product.gem_type], ["Carat", product.gem_carat], ["Color", product.gem_color], ["Origin", product.gem_origin], ["Clarity", product.gem_clarity], ["Silver grade", product.silver_grade]];
 return <section className="luxury-card fade-section"><h2 className="font-display mb-5 text-2xl text-[#c9a84c]">Gem details</h2><dl className="grid gap-5 sm:grid-cols-2 md:grid-cols-3">{details.map(([label,value]) => <div key={String(label)}><dt className="text-xs uppercase tracking-widest text-zinc-500">{label}</dt><dd className="mt-1 text-lg">{value || "—"}</dd></div>)}</dl></section>;
}
