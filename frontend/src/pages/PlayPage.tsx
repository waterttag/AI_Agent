import { useParams, Link, useNavigate } from "react-router-dom";
import { useGame } from "@/hooks/useGames";
import { usePublishGame } from "@/hooks/usePublishGame";
import { useAuthStore } from "@/lib/auth-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/utils";
import { Loader2, ArrowLeft, Maximize2, Minimize2, User, Calendar, AlertTriangle, Home, Send, Eye, History, ChevronDown, ChevronUp, Heart } from "lucide-react";
import { useTasks } from "@/hooks/useTasks";
import { useToggleFavorite, useFavoriteStatus } from "@/hooks/useFavorites";
import { useState, useEffect } from "react";

export function PlayPage() {
  const { gameId } = useParams<{ gameId: string }>();
  const { data: game, isLoading, error } = useGame(gameId!);
  const [fullscreen, setFullscreen] = useState(false);
  const [iframeError, setIframeError] = useState(false);
  const publishGame = usePublishGame();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isAuthor = user && game && user.id === game.author_id;
  const isPreview = game?.status === "preview";
  const [showHistory, setShowHistory] = useState(false);
  const { data: tasks } = useTasks(isAuthor ? gameId! : null);
  const { data: favStatus } = useFavoriteStatus(gameId!);
  const toggleFav = useToggleFavorite();

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
            <div className="flex items-center gap-2">
              {user && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleFav.mutate(game.id)}
                >
                  <Heart className={`mr-1 h-4 w-4 ${favStatus?.favorited ? "fill-red-500 text-red-500" : ""}`} />
                  {favStatus?.favorited ? "Favorited" : "Favorite"}
                  {favStatus ? ` (${favStatus.count})` : ""}
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => setFullscreen(true)}>
                <Maximize2 className="mr-2 h-4 w-4" />
                Fullscreen
              </Button>
            </div>
          </div>

          {/* Description */}
          {game.description && (
            <p className="text-muted-foreground">{game.description}</p>
          )}

          {/* Preview banner — shown to author only */}
          {isPreview && isAuthor && (
            <div className="flex items-center gap-4 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Eye className="h-5 w-5 text-yellow-500" />
                  <span className="font-semibold text-yellow-500">Preview Mode</span>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  This game is not yet published. Only you can see it. Review and publish when ready.
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/create`)}
                >
                  Edit & Regenerate
                </Button>
                <Button
                  size="sm"
                  onClick={() => publishGame.mutate(game.id)}
                  disabled={publishGame.isPending}
                >
                  {publishGame.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="mr-2 h-4 w-4" />
                  )}
                  Publish Now
                </Button>
              </div>
            </div>
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

          {/* Version History — for author only */}
          {isAuthor && tasks && tasks.length > 0 && (
            <div className="rounded-lg border border-border">
              <button
                className="w-full flex items-center justify-between p-4 text-sm font-medium hover:bg-secondary/20 transition-colors"
                onClick={() => setShowHistory(!showHistory)}
              >
                <span className="flex items-center gap-2">
                  <History className="h-4 w-4 text-primary" />
                  Version History ({tasks.length})
                </span>
                {showHistory ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
              {showHistory && (
                <div className="px-4 pb-4 space-y-2">
                  {tasks.map((t: any, i: number) => (
                    <div key={t.id} className="flex items-center justify-between text-xs py-2 border-t border-border first:border-0">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          t.status === "completed" ? "bg-green-500/20 text-green-400" :
                          t.status === "failed" ? "bg-red-500/20 text-red-400" :
                          "bg-secondary text-muted-foreground"
                        }`}>
                          {t.status}
                        </span>
                        <span className="text-muted-foreground">
                          {new Date(t.created_at).toLocaleString()}
                        </span>
                      </div>
                      <span className="text-muted-foreground">
                        {t.progress}%
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
