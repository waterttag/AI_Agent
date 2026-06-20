import { Link, useNavigate } from "react-router-dom";
import { useGames } from "@/hooks/useGames";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/utils";
import { Gamepad2, Sparkles, ArrowRight, Play, User, Clock, Loader2, ChevronLeft, ChevronRight, Eye, Heart } from "lucide-react";
import { useState, useMemo } from "react";
import { useFavoriteGameIds, useToggleFavorite } from "@/hooks/useFavorites";
import { useAuthStore } from "@/lib/auth-store";

// Tag → gradient map for cover images
const COVER_GRADIENTS: Record<string, string> = {
  arcade: "from-pink-500/30 via-orange-500/20 to-yellow-500/30",
  puzzle: "from-blue-500/30 via-purple-500/20 to-indigo-500/30",
  classic: "from-emerald-500/30 via-teal-500/20 to-green-500/30",
  action: "from-red-500/30 via-rose-500/20 to-orange-500/30",
  shooter: "from-red-500/40 via-yellow-500/20 to-gray-500/30",
  memory: "from-violet-500/30 via-fuchsia-500/20 to-pink-500/30",
  casual: "from-cyan-500/30 via-sky-500/20 to-blue-500/30",
  snake: "from-lime-500/30 via-green-500/20 to-emerald-500/30",
  breakout: "from-orange-500/30 via-red-500/20 to-rose-500/30",
  default: "from-primary/20 via-secondary/20 to-accent/20",
};

function gameCoverGradient(tags: string[]): string {
  for (const t of tags) {
    if (COVER_GRADIENTS[t]) return COVER_GRADIENTS[t];
  }
  return COVER_GRADIENTS.default;
}

function GameCard({ game, onTagClick, isFav, onToggleFav }: { game: any; onTagClick?: (tag: string) => void; isFav?: boolean; onToggleFav?: () => void }) {
  const navigate = useNavigate();
  const grad = gameCoverGradient(game.tags || []);

  return (
    <Card
      className="group cursor-pointer overflow-hidden border-border hover:border-primary/50 transition-all duration-300 hover:shadow-lg hover:shadow-primary/10 relative"
      onClick={() => navigate(`/play/${game.id}`)}
    >
      <div className={`aspect-video bg-gradient-to-br ${grad} flex items-center justify-center relative overflow-hidden`}>
        <Gamepad2 className="h-16 w-16 text-white/30 group-hover:scale-110 transition-transform duration-300" />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
          <Play className="h-12 w-12 text-white opacity-0 group-hover:opacity-100 transition-opacity duration-300 drop-shadow-lg" />
        </div>
        {/* Heart button */}
        {onToggleFav && (
          <button
            className="absolute top-2 right-2 p-1.5 rounded-full bg-black/40 hover:bg-black/60 transition-colors z-10"
            onClick={(e) => { e.stopPropagation(); onToggleFav(); }}
          >
            <Heart className={`h-4 w-4 ${isFav ? "fill-red-500 text-red-500" : "text-white"}`} />
          </button>
        )}
      </div>
      <CardContent className="p-4 space-y-3">
        <h3 className="font-semibold text-lg truncate">{game.title}</h3>
        <p className="text-sm text-muted-foreground line-clamp-2">{game.description}</p>
        <div className="flex flex-wrap gap-1.5">
          {(game.tags || []).slice(0, 4).map((t: string) => (
            <Badge
              key={t}
              variant="secondary"
              className="text-xs cursor-pointer hover:bg-primary/20 transition-colors"
              onClick={(e) => { e.stopPropagation(); onTagClick?.(t); }}
            >
              {t}
            </Badge>
          ))}
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
          <span className="flex items-center gap-1"><User className="h-3 w-3" /> {game.author_name || "Author"}</span>
          <span className="flex items-center gap-2">
            <span className="flex items-center gap-1"><Eye className="h-3 w-3" /> {game.play_count || 0}</span>
            <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {formatDate(game.created_at)}</span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

export function HomePage() {
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [showFavorites, setShowFavorites] = useState(false);
  const pageSize = 12;
  const { data, isLoading, error } = useGames(page, activeTag || undefined);
  const { data: favIds } = useFavoriteGameIds();
  const toggleFav = useToggleFavorite();
  const isLoggedIn = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();

  const favSet = useMemo(() => new Set(favIds || []), [favIds]);

  // Collect all tags from games
  const allTags = useMemo(() => {
    if (!data?.items) return [];
    const set = new Set<string>();
    data.items.forEach((g: any) => (g.tags || []).forEach((t: string) => set.add(t)));
    return Array.from(set).sort();
  }, [data?.items]);

  return (
    <div className="space-y-12">
      {/* Hero */}
      <section className="text-center py-12 space-y-6">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 text-primary text-sm">
          <Sparkles className="h-4 w-4" />
          Powered by AI Agents
        </div>
        <h1 className="text-5xl font-extrabold tracking-tight">
          Discover & Create{" "}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-purple-400">
            AI-Powered
          </span>{" "}
          Games
        </h1>
        <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
          Browse community-generated games, or describe your idea and let AI build it for you.
        </p>
        <div className="flex gap-4 justify-center">
          <Button size="lg" onClick={() => navigate("/create")}>
            <Sparkles className="mr-2 h-4 w-4" />
            Create a Game
          </Button>
          <Button size="lg" variant="outline" onClick={() => document.getElementById("games-grid")?.scrollIntoView({ behavior: "smooth" })}>
            Browse Games
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </section>

      {/* Tag Filter Bar */}
      {allTags.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-muted-foreground mr-2">Filter:</span>
          <Badge
            variant={!showFavorites && activeTag === null ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => { setActiveTag(null); setShowFavorites(false); }}
          >
            All
          </Badge>
          {isLoggedIn && (
            <Badge
              variant={showFavorites ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => { setActiveTag(null); setShowFavorites(!showFavorites); }}
            >
              <Heart className="mr-1 h-3 w-3" />
              Favorites
            </Badge>
          )}
          {allTags.map((t) => (
            <Badge
              key={t}
              variant={!showFavorites && activeTag === t ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => { setShowFavorites(false); setActiveTag(activeTag === t ? null : t); }}
            >
              {t}
            </Badge>
          ))}
        </div>
      )}

      {/* Game Grid */}
      <section id="games-grid" className="space-y-6">
        <h2 className="text-2xl font-bold">
          {activeTag ? `${activeTag} Games` : "Featured Games"}
        </h2>
        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : error ? (
          <div className="text-center py-20 text-muted-foreground">
            <p>Failed to load games. Make sure the backend is running.</p>
          </div>
        ) : !data?.items?.length ? (
          <div className="text-center py-20 text-muted-foreground">
            <Gamepad2 className="mx-auto h-12 w-12 mb-4 opacity-30" />
            <p>{showFavorites ? "No favorites yet." : activeTag ? `No "${activeTag}" games yet.` : "No games published yet."}</p>
            {showFavorites && <Button className="mt-4" variant="outline" onClick={() => setShowFavorites(false)}>Show All</Button>}
            {!showFavorites && activeTag && <Button className="mt-4" variant="outline" onClick={() => setActiveTag(null)}>Clear Filter</Button>}
            {!showFavorites && !activeTag && <Button className="mt-4" variant="outline" onClick={() => navigate("/create")}>Create First Game</Button>}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {(showFavorites ? data.items.filter((g: any) => favSet.has(g.id)) : data.items).map((game: any) => (
              <GameCard
                key={game.id}
                game={game}
                onTagClick={(t) => { setShowFavorites(false); setActiveTag(t); }}
                isFav={favSet.has(game.id)}
                onToggleFav={isLoggedIn ? () => toggleFav.mutate(game.id) : undefined}
              />
            ))}
          </div>
        )}
        {/* Pagination */}
        {data && data.total > pageSize && (
          <div className="flex items-center justify-center gap-4 pt-4">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="mr-1 h-4 w-4" /> Prev
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {Math.ceil(data.total / pageSize)}
            </span>
            <Button variant="outline" size="sm" disabled={page * pageSize >= data.total} onClick={() => setPage(page + 1)}>
              Next <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
