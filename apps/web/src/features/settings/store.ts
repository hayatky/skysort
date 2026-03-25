import { create } from "zustand";

interface SettingsState {
  aiHealthSeenAt?: string;
  selectedPhotoId?: string;
  setAIHealthSeenAt: (value: string) => void;
  setSelectedPhotoId: (value?: string) => void;
}

export const useUiStore = create<SettingsState>((set) => ({
  aiHealthSeenAt: undefined,
  selectedPhotoId: undefined,
  setAIHealthSeenAt: (value) => set({ aiHealthSeenAt: value }),
  setSelectedPhotoId: (selectedPhotoId) => set({ selectedPhotoId }),
}));
