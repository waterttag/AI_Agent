import { Link, useNavigate } from "react-router-dom";
import { useGames } from "@/hooks/useGames";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/utils";
import { Gamepad2, Sparkles, ArrowRight, Play, User, Clock, Loader2 } from "lucide-react";

function GameCard({ game }: { game: any }) {
  const navigate = useNavigate();
  return (
    <Card
      className="group cursor-pointer overflow-hidden border-border hover:border-primary/50 transition-all duration-300 hover:shadow-lg hover:shadow-primary/10"
      onClick={() => navigate(`/play/${game.id}`)}
    >
      <div className="aspect-video bg-gradient-to-br from-primary/20 via-secondary/20 to-accent/20 flex items-center justify-center relative overflow-hidden">
        <Gamepad2 className="h-16 w-16 text-primary/40 group-hover:scale-110 transition-transform duration-300" />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
          <Play className="h-12 w-12 text-white opacity-0 group-hover:opacity-100 transition-opacity duration-300 drop-shadow-lg" />
        </div>
      </div>
      <CardContent className="p-4 space-y-3">
        <h3 className="font-semibold text-lg truncate">{game.title}</h3>
        <p className="text-sm text-muted-foreground line-clamp-2">{game.description}</p>
        <div className="flex flex-wrap gap-1.5">
          {(game.tags || []).slice(0, 3).map((t: string) => (
            <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
          ))}
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
          <span className="flex items-center gap-1"><User className="h-3 w-3" /> {game.author_name || "Author"}</span>
          <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {formatDate(game.created_at)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function HomePage() {
  const { data, isLoading, error } = useGames();
  const navigate = useNavigate();

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

      {/* Game Grid */}
      <section id="games-grid" className="space-y-6">
        <h2 className="text-2xl font-bold">Featured Games</h2>
        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : error ? (
          <div className="text-center py-20 text-muted-foreground">
            <p>Failed to load games. Make sure the backend is running.</p>
            <p className="text-sm mt-2">Run: cd backend && uvicorn app.main:app --reload</p>
          </div>
        ) : !data?.items?.length ? (
          <div className="text-center py-20 text-muted-foreground">
            <Gamepad2 className="mx-auto h-12 w-12 mb-4 opacity-30" />
            <p>No games published yet. Be the first creator!</p>
            <Button className="mt-4" variant="outline" onClick={() => navigate("/create")}>
              Create First Game
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {data.items.map((game: any) => (
              <GameCard key={game.id} game={game} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
