'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { Proposal } from '@/types';

export function useProposals() {
  return useQuery<Proposal[]>({
    queryKey: ['proposals'],
    queryFn: () => api.proposals() as Promise<Proposal[]>,
    refetchInterval: 10_000,
    retry: false,
  });
}
