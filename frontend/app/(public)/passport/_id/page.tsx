import Link from "next/link";
import { notFound } from "next/navigation";
import { PassportCard } from "@/components/passport/PassportCard";
import type { PassportData, Story } from "@/lib/api";

// Thêm hàm này để Next.js cho phép Export file tĩnh
export function generateStaticParams() {
  return [];
}

const serverApi = process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || "http://backend:8000/api";

async function load<T>(path: string): Promise<T | null> {
  // Đã gỡ bỏ { cache: "no-store" } gây lỗi
  const response = await fetch(`${serverApi}${path}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`DPP API returned ${response.status}`);
  return response.json() as Promise<T>;
}

export default async function PassportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const passport = await load<PassportData>(`/passport/${encodeURIComponent(id)}`);
  if (!passport) notFound();

  const stories = await load<{items?: Story[]} | Story[]>(`/social/stories/by-product/${encodeURIComponent(id)}`).catch(() => [] as Story[]);

  const storyItems = Array.isArray(stories) ? stories : stories?.items || [];
  const { product, design_story: design } = passport;

  const hero = design?.media_urls?.[0];

  return <main className="mx-auto min-h-screen max-w-6xl space-y-8 px-5 pb-20">
    <header className="relative -mx-5 flex min-h-[28rem] items-end overflow-hidden p-8 md:p-16" style={{background: `linear-gradient(145deg, ${product.gem_color_hex || "#3f3f46"}99, #0a0a0a 72%)`}}>
    {hero && <div className="absolute inset-0 bg-cover bg-center opacity-40" style={{backgroundImage:`url(${JSON.stringify(hero).slice(1,-1)})`}} />}
    <div className="relative"><p className="mb-3 uppercase tracking-[.35em] text-[#c9a84c]">Digital Product Passport</p><h1 className="font-display text-5xl md:text-7xl">{product.name}</h1><p className="mt-3 text-zinc-300">Verified piece   {product.sku}</p></div>
    </header>
    <PassportCard product={product} />
    <section className="luxury-card fade-section"><h2 className="font-display mb-5 text-2xl text-[#c9a84c]">Certificates</h2><div className="grid gap-3">{passport.certificates.length ? passport.certificates.map(cert => <div className="flex items-center justify-between rounded-xl bg-black/30 p-4" key={cert.id}><span>  <b>{cert.cert_type}</b>   {cert.issuer} {cert.cert_number && `#${cert.cert_number}`}</span>{cert.document_url && <a className="text-[#c9a84c] underline" href={cert.document_url} download>PDF</a>}</div>) : <p className="text-zinc-500">No certificates published.</p>}</div></section>
    {design && <section className="luxury-card fade-section"><h2 className="font-display text-2xl text-[#c9a84c]">Design story</h2><p className="mt-2 text-sm uppercase tracking-widest text-zinc-500">By {design.designer_name || "Our atelier"}</p><p className="mt-5 leading-7 text-zinc-300">{design.inspiration}</p><h3 className="mt-6 font-semibold">Craft process</h3><p className="mt-2 leading-7 text-zinc-400">{design.craft_process}</p></section>}
    <section className="luxury-card fade-section"><h2 className="font-display text-2xl text-[#c9a84c]">Maintenance</h2><p className="my-4 text-zinc-300">Next service: {passport.maintenance_schedules[0] ? new Date(passport.maintenance_schedules[0].scheduled_at).toLocaleDateString() : "Schedule at your convenience"}</p><button className="gold-button">Book service</button></section>
    <section className="luxury-card fade-section"><h2 className="font-display mb-5 text-2xl text-[#c9a84c]">Customer stories</h2>{storyItems.length ? storyItems.map(story => <article className="border-t border-zinc-800 py-4" key={story.id}><b>{story.title}</b><p className="line-clamp-2 text-zinc-400">{story.content}</p></article>) : <p className="text-zinc-500">Be the first to share this piece&apos;s story.</p>}</section>
    <div className="text-center"><Link href={`/scan?product_id=${id}`} className="gold-button">Verify Authenticity</Link></div>
  </main>;
}
