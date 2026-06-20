// --- User ---
export interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// --- Game ---
export interface GameAsset {
  id: string;
  game_id: string;
  asset_type: "image" | "audio" | "reference";
  original_filename: string;
  oss_url: string;
  file_size: number | null;
  created_at: string;
}

export interface Game {
  id: string;
  title: string;
  description: string;
  cover_image_url: string | null;
  game_url: string | null;
  author_id: string;
  author_name?: string | null;
  tags: string[];
  status: "draft" | "generating" | "preview" | "published" | "failed";
  prompt_text: string | null;
  play_count: number;
  created_at: string;
  updated_at: string;
  assets: GameAsset[];
}

export interface GameListResponse {
  items: Game[];
  total: number;
  page: number;
  size: number;
}

// --- Task ---
export interface GenerationTask {
  id: string;
  game_id: string;
  user_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  result_oss_url: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}
