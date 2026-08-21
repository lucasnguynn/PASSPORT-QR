"use client";
import Link from "next/link";
import { useState } from "react";
import { reactToStory, type ReactionType, type Story } from "@/lib/api";
export function StoryCard({ story }: { story: Story }) {
 const [expanded, setExpanded] = useState(false); const [count, setCount] = useState(story.reaction_count);
 async function react(type: ReactionType) { await reactToStory(story.id, type); setCount(value => value + 1); }
 return <article className="luxury-card" style={{borderLeftWidth: 4, borderLeftColor: story.color_hex || "#c9a84c"}}>
  <header className="mb-4 flex items-center gap-3"><div className="grid size-10 place-items-center rounded-full bg-zinc-800">{(story.display_name || "J")[0]}</div><div><b>{story.display_name || "Jewelry collector"}</b><div className="flex items-center gap-2 text-xs text-zinc-400"><span className="size-2 rounded-full" style={{background:story.color_hex || "#c9a84c"}} />{story.color_tag || "Gem"}</div></div></header>
  <h2 className="font-display text-2xl">{story.title || "A jewelry story"}</h2><p className={`mt-3 whitespace-pre-wrap text-zinc-300 ${expanded ? "" : "line-clamp-3"}`}>{story.content}</p><button onClick={() => setExpanded(v => !v)} className="mt-2 text-sm text-[#c9a84c]">{expanded ? "Show less" : "Read more"}</button>
  {story.product_name && <Link className="mt-4 block text-sm text-zinc-500" href={`/passport/${story.product_id}`}>◇ on: {story.product_name}</Link>}
  <footer className="mt-5 flex flex-wrap gap-2 border-t border-zinc-800 pt-4"><button onClick={() => react("love")} className="rounded-full bg-zinc-800 px-3 py-2">💎 Love</button><button onClick={() => react("sparkle")} className="rounded-full bg-zinc-800 px-3 py-2">✨ Sparkle</button><button onClick={() => react("inspired")} className="rounded-full bg-zinc-800 px-3 py-2">💡 Inspired</button><span className="self-center text-xs text-zinc-500">{count}</span></footer>
 </article>;
}
