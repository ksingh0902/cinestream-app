export interface TvControllerSummary {
  controller_id: string;
  phone_name: string;
  role: 'primary' | 'secondary' | string;
  created_at: number;
  last_seen_at: number;
}

export interface TvDeviceSummary {
  tv_id: string;
  name: string;
  online: boolean;
  nearby: boolean;
  same_network: boolean;
  last_seen_at: number;
  created_at: number;
  controller_count: number;
  controllers: TvControllerSummary[];
}

export interface RegisterTvResponse {
  tv_id: string;
  name: string;
  device_secret?: string;
  last_seen_at: number;
  created_at: number;
  controllers: TvControllerSummary[];
}

export interface StartPairingResponse {
  pairing_id: string;
  tv_id: string;
  tv_name: string;
  code: string;
  display_code: string;
  pairing_token: string;
  qr_path: string;
  expires_at: number;
  ttl_seconds: number;
}

export interface CompletePairingResponse {
  paired: boolean;
  tv_id: string;
  tv_name: string;
  controller_id: string;
  phone_name: string;
  role: 'primary' | 'secondary' | string;
  control_token: string;
  created_at: number;
}

export interface StoredTvIdentity {
  tvId: string;
  name: string;
  deviceSecret: string;
}

export interface StoredControllerAuth {
  tvId: string;
  tvName: string;
  controllerId: string;
  controlToken: string;
  phoneName: string;
  role: string;
  pairedAt: number;
}

export type TvPlaybackStatus = 'IDLE' | 'PLAYING' | 'PAUSED' | 'BUFFERING' | 'ENDED';

export interface TvPlaybackState {
  status: TvPlaybackStatus;
  mediaId?: number | null;
  currentTitle: string | null;
  currentEpisode: string | null;
  season?: number | null;
  episode?: number | null;
  isSeries?: boolean;
  currentPosition: number;
  duration: number;
  isPlaying: boolean;
  volume: number;
  muted?: boolean;
  playerKind?: string | null;
  updatedAt: number;
}

export type RemoteCommandType =
  | 'PLAY'
  | 'PAUSE'
  | 'SEEK_FORWARD'
  | 'SEEK_BACKWARD'
  | 'SEEK_TO'
  | 'LOAD_MEDIA'
  | 'NEXT_EPISODE'
  | 'PREVIOUS_EPISODE'
  | 'VOLUME_SET'
  | 'MUTE_TOGGLE'
  | 'NAVIGATE_UP'
  | 'NAVIGATE_DOWN'
  | 'NAVIGATE_LEFT'
  | 'NAVIGATE_RIGHT'
  | 'SELECT'
  | 'BACK'
  | 'HOME';

export interface RemoteCommandPayload {
  command: RemoteCommandType;
  seconds?: number;
  position?: number;
  volume?: number;
  media?: {
    id: number;
    title: string;
    year?: string | null;
    poster?: string | null;
    isSeries: boolean;
    season?: number;
    episode?: number;
    source?: string;
    isHindiDubbed?: boolean;
    duration_s?: number | null;
  };
}
