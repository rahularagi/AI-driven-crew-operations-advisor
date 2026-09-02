'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { FlightLeg } from '@/types';

export function useFlights() {
  return useQuery<FlightLeg[]>({
    queryKey: ['flights-today'],
    queryFn: () => api.flightsToday() as Promise<FlightLeg[]>,
    refetchInterval: 30_000,
    retry: false,
  });
}
