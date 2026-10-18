"use client";

import { create } from "zustand";
import type { Alert, AutonomyMode, Health } from "./api";

type GraphGuardStore = {
  selectedAlertId: string | null;
  selectedEntityId: string | null;
  autonomy: AutonomyMode | null;
  health: Health | null;
  apiOffline: boolean;
  policyVersion: string | null;
  selectedEvidenceId: string | null;
  setSelection: (alert: Alert | null) => void;
  setAutonomy: (mode: AutonomyMode) => void;
  setHealth: (health: Health | null) => void;
  setApiOffline: (offline: boolean) => void;
  setPolicyVersion: (version: string | null) => void;
  setSelectedEvidenceId: (id: string | null) => void;
};

export const useGraphGuardStore = create<GraphGuardStore>((set) => ({
  selectedAlertId: null,
  selectedEntityId: null,
  autonomy: null,
  health: null,
  apiOffline: true,
  policyVersion: null,
  selectedEvidenceId: null,
  setSelection: (alert) => set({ selectedAlertId: alert?.id ?? null, selectedEntityId: alert?.entity_id ?? null, selectedEvidenceId: null }),
  setAutonomy: (autonomy) => set({ autonomy }),
  setHealth: (health) => set({ health, apiOffline: !health?.ok }),
  setApiOffline: (apiOffline) => set({ apiOffline }),
  setPolicyVersion: (policyVersion) => set({ policyVersion }),
  setSelectedEvidenceId: (selectedEvidenceId) => set({ selectedEvidenceId }),
}));
