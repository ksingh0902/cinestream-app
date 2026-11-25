import { apiClient, request } from '../../api/client';
import {
  CompletePairingResponse,
  RegisterTvResponse,
  StartPairingResponse,
  TvControllerSummary,
  TvDeviceSummary,
} from './types';

export async function registerTvDevice(params: {
  tv_id?: string;
  name?: string;
  device_secret?: string;
}): Promise<RegisterTvResponse> {
  return apiClient.post<RegisterTvResponse>('/api/tv/register', params);
}

export async function startTvPairing(tvId: string): Promise<StartPairingResponse> {
  return apiClient.post<StartPairingResponse>('/api/tv/pairing/start', { tv_id: tvId });
}

export async function completeTvPairing(params: {
  pairing_id?: string;
  pairing_token?: string;
  code?: string;
  phone_name?: string;
}): Promise<CompletePairingResponse> {
  return apiClient.post<CompletePairingResponse>('/api/tv/pairing/complete', params);
}

export async function getTvDevices(): Promise<{ devices: TvDeviceSummary[] }> {
  return apiClient.get<{ devices: TvDeviceSummary[] }>('/api/tv/devices');
}

export async function heartbeatTvDevice(
  tvId: string
): Promise<{ ok: boolean; tv_id: string; controllers: TvControllerSummary[] }> {
  return apiClient.post<{ ok: boolean; tv_id: string; controllers: TvControllerSummary[] }>(
    `/api/tv/devices/${encodeURIComponent(tvId)}/heartbeat`,
    {}
  );
}

export async function revokeTvController(
  tvId: string,
  controllerId?: string
): Promise<{ ok: boolean; revoked_count: number; tv_id: string }> {
  return apiClient.post<{ ok: boolean; revoked_count: number; tv_id: string }>(
    `/api/tv/devices/${encodeURIComponent(tvId)}/revoke`,
    controllerId ? { controller_id: controllerId } : {}
  );
}

export async function deleteTvDevice(tvId: string): Promise<{ ok: boolean; tv_id: string }> {
  return request<{ ok: boolean; tv_id: string }>(
    `/api/tv/devices/${encodeURIComponent(tvId)}`,
    { method: 'DELETE' }
  );
}
