import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateGame, useUploadAsset, useGenerateGame } from "@/hooks/useCreateGame";
import { useTaskPolling } from "@/hooks/useTaskPolling";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Sparkles, Upload, X, FileImage, Loader2, CheckCircle, XCircle, Play } from "lucide-react";

export function CreatePage() {
  const navigate = useNavigate();

  // Form state
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [promptText, setPromptText] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  // Mutations
  const createGame = useCreateGame();
  const uploadAsset = useUploadAsset();
  const generateGame = useGenerateGame();

  // State tracking
  const [step, setStep] = useState<"form" | "generating" | "done" | "error">("form");
  const [gameId, setGameId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  // Poll task status
  const { data: task } = useTaskPolling(taskId);

  const addTag = () => {
    const t = tagInput.trim().toLowerCase();
    if (t && !tags.includes(t) && tags.length < 8) {
      setTags([...tags, t]);
      setTagInput("");
    }
  };

  const removeTag = (t: string) => setTags(tags.filter((tag) => tag !== t));

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files).filter(
      (f) => f.type.startsWith("image/") || f.type.startsWith("audio/")
    );
    setFiles((prev) => [...prev, ...dropped].slice(0, 10));
  }, []);

  const removeFile = (idx: number) => setFiles(files.filter((_, i) => i !== idx));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !promptText.trim()) return;

    setStep("generating");
    setErrorMsg("");

    try {
      // 1. Create game draft
      const game = await createGame.mutateAsync({ title, description, tags, prompt_text: promptText });
      setGameId(game.id);

      // 2. Upload assets
      for (const file of files) {
        await uploadAsset.mutateAsync({ gameId: game.id, file });
      }

      // 3. Trigger generation
      const genTask = await generateGame.mutateAsync({ gameId: game.id, promptText });
      setTaskId(genTask.id);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to start generation. Check backend connection.");
      setStep("error");
    }
  };

  // Handle task completion
  if (task?.status === "completed" && step === "generating") {
    setStep("done");
  }
  if (task?.status === "failed" && step === "generating") {
    setErrorMsg(task.error_message || "Generation failed");
    setStep("error");
  }

  const canGenerate = title.trim() && promptText.trim() && step === "form";

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold">Create a Game</h1>
        <p className="text-muted-foreground">Describe your game idea and let AI bring it to life</p>
      </div>

      {/* Generating / Done / Error states */}
      {step === "generating" && (
        <Card className="border-border">
          <CardContent className="py-12 space-y-6 text-center">
            <Loader2 className="mx-auto h-12 w-12 animate-spin text-primary" />
            <div>
              <h2 className="text-xl font-semibold">AI is Building Your Game</h2>
              <p className="text-muted-foreground mt-1">
                Powered by DeepSeek — the Agent Harness orchestrates a multi-stage pipeline
              </p>
            </div>

            {/* Agent Pipeline Visualization */}
            <div className="w-full bg-secondary rounded-full h-3 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-primary to-purple-500 rounded-full transition-all duration-700"
                style={{ width: `${task?.progress || 5}%` }}
              />
            </div>

            {/* Pipeline Steps */}
            <div className="grid grid-cols-4 gap-2 text-xs text-muted-foreground">
              {[
                { label: "Preprocess", desc: "Analyze assets & build context", at: 10 },
                { label: "Generate", desc: "DeepSeek writes game code", at: 70 },
                { label: "Validate & Fix", desc: "HTML check + auto-repair", at: 85 },
                { label: "Deploy", desc: "Upload to MinIO, publish", at: 100 },
              ].map((s) => (
                <div
                  key={s.label}
                  className={`p-2 rounded border transition-colors ${
                    (task?.progress || 0) >= s.at
                      ? "border-primary/50 bg-primary/10 text-primary"
                      : "border-border bg-card"
                  }`}
                >
                  <div className="font-medium">{s.label}</div>
                  <div className="opacity-70">{s.desc}</div>
                </div>
              ))}
            </div>

            <p className="text-sm text-muted-foreground">
              Progress: {task?.progress || 0}% — this may take 20-60 seconds
            </p>
          </CardContent>
        </Card>
      )}

      {step === "done" && (
        <Card className="border-border border-green-500/30">
          <CardContent className="py-12 space-y-6 text-center">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
            <div>
              <h2 className="text-xl font-semibold text-green-500">Game Created!</h2>
              <p className="text-muted-foreground mt-1">Your AI-generated game is ready to play</p>
            </div>
            <div className="flex gap-4 justify-center">
              <Button onClick={() => navigate(`/play/${gameId}`)} size="lg">
                <Play className="mr-2 h-4 w-4" /> Play Now
              </Button>
              <Button variant="outline" onClick={() => { setStep("form"); setTaskId(null); setGameId(null); setFiles([]); setPromptText(""); setTitle(""); setDescription(""); setTags([]); }} size="lg">
                Create Another
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "error" && (
        <Card className="border-border border-red-500/30">
          <CardContent className="py-12 space-y-6 text-center">
            <XCircle className="mx-auto h-12 w-12 text-red-500" />
            <div>
              <h2 className="text-xl font-semibold text-red-500">Generation Failed</h2>
              <p className="text-muted-foreground mt-1">{errorMsg}</p>
            </div>
            <Button onClick={() => setStep("form")} variant="outline">Try Again</Button>
          </CardContent>
        </Card>
      )}

      {/* Creation Form */}
      {step === "form" && (
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Game Info */}
          <Card className="border-border">
            <CardHeader>
              <CardTitle>Game Details</CardTitle>
              <CardDescription>Basic information about your game</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Title *</label>
                <Input placeholder="My Awesome Game" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Description</label>
                <textarea
                  className="flex w-full min-h-[80px] rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="A short description shown on the game card..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={5000}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Tags</label>
                <div className="flex gap-2">
                  <Input placeholder="puzzle, platformer..." value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }} />
                  <Button type="button" variant="outline" onClick={addTag}>Add</Button>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {tags.map((t) => (
                    <Badge key={t} variant="secondary" className="cursor-pointer" onClick={() => removeTag(t)}>
                      {t} <X className="ml-1 h-3 w-3" />
                    </Badge>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Prompt */}
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" />
                Game Prompt *
              </CardTitle>
              <CardDescription>
                Describe your game in natural language. Be specific about genre, mechanics, controls, and visual style.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <textarea
                className="flex w-full min-h-[160px] rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder={`Examples:\n"Create a space shooter where the player controls a ship at the bottom, shooting falling asteroids. Include power-ups and a score system."\n\n"Make a memory card matching game with 16 cards. Use colorful emoji icons. Track the number of moves and add a timer."`}
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                required
                minLength={10}
                maxLength={10000}
              />
              <p className="text-xs text-muted-foreground">{promptText.length}/10000 characters</p>
            </CardContent>
          </Card>

          {/* Assets */}
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Upload className="h-5 w-5" />
                Assets (Optional)
              </CardTitle>
              <CardDescription>Upload sprites or images to inspire the AI</CardDescription>
            </CardHeader>
            <CardContent>
              <div
                className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-primary/50 transition-colors cursor-pointer"
                onDrop={handleFileDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => document.getElementById("file-upload")?.click()}
              >
                <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">Drag & drop images/audio here, or click to browse</p>
                <input id="file-upload" type="file" multiple accept="image/*,audio/*"
                  className="hidden"
                  onChange={(e) => setFiles((prev) => [...prev, ...Array.from(e.target.files || [])].slice(0, 10))} />
              </div>
              {files.length > 0 && (
                <div className="grid grid-cols-4 gap-3 mt-4">
                  {files.map((f, i) => (
                    <div key={i} className="relative group rounded-md overflow-hidden border border-border bg-secondary/30 p-2">
                      <FileImage className="h-8 w-8 mx-auto text-muted-foreground" />
                      <p className="text-xs truncate mt-1 text-center">{f.name}</p>
                      <button type="button" className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={() => removeFile(i)}>
                        <X className="h-4 w-4 text-destructive" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Submit */}
          <Button type="submit" className="w-full" size="lg" disabled={!canGenerate}>
            <Sparkles className="mr-2 h-5 w-5" />
            Generate Game with AI
          </Button>

          {!canGenerate && (
            <p className="text-xs text-center text-muted-foreground">
              Fill in the title and game prompt to enable generation
            </p>
          )}
        </form>
      )}
    </div>
  );
}
