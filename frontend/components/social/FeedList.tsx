import { StoryCard } from "./StoryCard";
export function FeedList({ stories }: { stories: string[] }) { return <section>{stories.map((story) => <StoryCard key={story} title={story} />)}</section>; }
