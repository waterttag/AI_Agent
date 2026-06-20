import { useParams, Link } from "react-router-dom";
import { useGame } from "@/hooks/useGames";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/utils";
import { Loader2, ArrowLeft, Maximize2, Minimize2, User, Calendar, AlertTriangle, Home } from "lucide-react";
import { useState, useEffect } from "react";

export function PlayPage() {
  const { gameId } = useParams<{ gameId: string }>();
  const { data: game, isLoading, error } = useGame(gameId!);
  const [fullscreen, setFullscreen] = useState(false);
  const [iframeError, setIframeError] = useState(false);

  // Listen for Escape to exit fullscreen
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && fullscreen) setFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-40 gap-4">
        <Loader2 className="h-10 w-10 animate-spin text-primary" />
        <p className="text-muted-foreground">Loading game...</p>
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="text-center py-40 space-y-4">
        <AlertTriangle className="mx-auto h-12 w-12 text-destructive" />
        <p className="text-lg text-muted-foreground">Game not found</p>
        <Link to="/"><Button variant="outline"><ArrowLeft className="mr-2 h-4 w-4" /> Back to Home</Button></Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header — hidden in fullscreen */}
      {!fullscreen && (
        <>
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div className="space-y-2">
              <Link to="/" className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
                <ArrowLeft className="h-3 w-3" /> Back to Browse
              </Link>
              <h1 className="text-3xl font-bold">{game.title}</h1>
              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1"><User className="h-3 w-3" /> {game.author_name || "Author"}</span>
                <span className="flex items-center gap-1"><Calendar className="h-3 w-3" /> {formatDate(game.created_at)}</span>
              </div>
              <div className="flex gap-1.5 flex-wrap">
                {(game.tags || []).map((t: string) => (
                  <Badge key={t} variant="secondary">{t}</Badge>
                ))}
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => setFullscreen(true)}>
              <Maximize2 className="mr-2 h-4 w-4" />
              Fullscreen
            </Button>
          </div>

          {/* Description */}
          {game.description && (
            <p className="text-muted-foreground">{game.description}</p>
          )}
        </>
      )}

      {/* Game Player */}
      {game.game_url ? (
        <div className={`rounded-lg border border-border overflow-hidden bg-black ${fullscreen ? "fixed inset-0 z-50" : "aspect-video"}`}>
          {/* Fullscreen exit button */}
          {fullscreen && (
            <div className="absolute top-4 right-4 z-[60] flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => setFullscreen(false)}>
                <Minimize2 className="mr-2 h-4 w-4" /> Exit Fullscreen
              </Button>
              <Link to="/"><Button variant="outline" size="sm"><Home className="mr-2 h-4 w-4" /> Home</Button></Link>
            </div>
          )}
          {iframeError ? (
            <div className="flex flex-col items-center justify-center h-full gap-4 bg-card">
              <AlertTriangle className="h-12 w-12 text-yellow-500" />
              <div className="text-center">
                <p className="text-lg font-medium">Game failed to load</p>
                <p className="text-sm text-muted-foreground mt-1">The game file may be unavailable or corrupted.</p>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setIframeError(false)}>Retry</Button>
                <Link to="/"><Button variant="outline"><Home className="mr-2 h-4 w-4" /> Back to Home</Button></Link>
              </div>
            </div>
          ) : (
            <iframe
              src={game.game_url}
              className="w-full h-full"
              sandbox="allow-scripts allow-same-origin"
              title={game.title}
              allow="autoplay; fullscreen"
              onError={() => setIframeError(true)}
            />
          )}
        </div>
      ) : (
        <div className="aspect-video rounded-lg border border-border flex flex-col items-center justify-center gap-4 bg-card">
          <p className="text-muted-foreground">
            {game.status === "generating" ? (
              <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Game is being generated...</span>
            ) : game.status === "failed" ? (
              <span className="text-destructive">Game generation failed. The creator may retry.</span>
            ) : (
              "Game not yet available"
            )}
          </p>
          <Link to="/"><Button variant="outline" size="sm"><ArrowLeft className="mr-2 h-3 w-3" /> Browse More Games</Button></Link>
        </div>
      )}

      {/* Actions — hidden in fullscreen */}
      {!fullscreen && (
        <>
          <div className="flex items-center gap-4">
            <Link to="/"><Button variant="outline"><ArrowLeft className="mr-2 h-4 w-4" /> Back to Browse</Button></Link>
          </div>

          {/* Prompt (if available) */}
          {game.prompt_text && (
            <div className="p-4 rounded-lg bg-secondary/30 border border-border">
              <h3 className="text-sm font-medium text-muted-foreground mb-1">Generation Prompt</h3>
              <p className="text-sm italic">"{game.prompt_text}"</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
