import { create } from "zustand";
export const useUiStore = create((set) => ({
    aiHealthSeenAt: undefined,
    selectedPhotoId: undefined,
    setAIHealthSeenAt: (value) => set({ aiHealthSeenAt: value }),
    setSelectedPhotoId: (selectedPhotoId) => set({ selectedPhotoId }),
}));
