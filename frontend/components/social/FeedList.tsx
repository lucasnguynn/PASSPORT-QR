"use client";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { getFeed } from "@/lib/api";
import { StoryCard } from "./StoryCard";
export function FeedList({ color }: { color?: string }) {
 const sentinel = useRef<HTMLDivElement>(null); const query = useInfiniteQuery({ queryKey:["feed",color], queryFn:({pageParam}) => getFeed(pageParam), initialPageParam:1, getNextPageParam:(last) => last.items.length < last.limit ? undefined : last.page + 1 });
 useEffect(() => { const node=sentinel.current; if(!node)return; const observer=new IntersectionObserver(([entry]) => { if(entry.isIntersecting && query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage(); }); observer.observe(node); return()=>observer.disconnect(); },[query]);
 const stories=query.data?.pages.flatMap(page=>page.items).filter(story=>!color || story.color_tag===color) || [];
 return <div className="space-y-5">{stories.map(story=><StoryCard key={story.id} story={story}/>) }{query.isLoading&&<p className="text-center text-zinc-500">Curating stories…</p>}{query.isError&&<p className="text-center text-red-300">The feed could not be loaded.</p>}<div ref={sentinel} className="h-10" aria-hidden /></div>;
}
