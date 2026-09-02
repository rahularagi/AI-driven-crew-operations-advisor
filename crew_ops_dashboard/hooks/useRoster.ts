'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { RosterRow } from '@/types';

export function useRoster(start: string, end: string) {
  return useQuery<RosterRow[]>({
    queryKey: ['roster', start, end],
    queryFn: () => api.roster(start, end) as Promise<RosterRow[]>,
    refetchInterval: 60_000,
    retry: false,
    enabled: !!start && !!end,
  });
}
