'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { FtlState } from '@/types';

export function useCrewFtl(crewId: string) {
  return useQuery<FtlState>({
    queryKey: ['ftl', crewId],
    queryFn: () => api.crewFtl(crewId) as Promise<FtlState>,
    refetchInterval: 60_000,
    retry: false,
    enabled: !!crewId,
  });
}
