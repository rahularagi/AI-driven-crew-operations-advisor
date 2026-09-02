'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { HealthResponse } from '@/types';

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: () => api.health() as Promise<HealthResponse>,
    refetchInterval: 30_000,
    retry: false,
  });
}
