import { create } from 'zustand';

export interface UserProfile {
  id: string;
  name: string;
  age: number;
  title: string;
  location: string;
  experience: string;
  specialty: string;
}

export const PERSONAS: Record<string, UserProfile> = {
  koen: {
    id: 'koen',
    name: 'Koen',
    age: 40,
    title: 'Inspecteur Voedselveiligheid Horeca',
    location: 'Regio Randstad',
    experience: '15 jaar',
    specialty: 'horeca',
  },
  fatima: {
    id: 'fatima',
    name: 'Fatima',
    age: 32,
    title: 'Inspecteur Productveiligheid',
    location: 'Regio Randstad',
    experience: '4 jaar',
    specialty: 'productveiligheid',
  },
  jan: {
    id: 'jan',
    name: 'Jan',
    age: 58,
    title: 'Senior inspecteur Voedselveiligheid',
    location: 'Regio Noord-Nederland',
    experience: '30+ jaar',
    specialty: 'voedselveiligheid',
  },
};

interface UserStore {
  currentUser: UserProfile | null;
  setUser: (userId: string) => void;
  clearUser: () => void;
  initializeUser: () => void;
}

export const useUserStore = create<UserStore>((set) => ({
  currentUser: null,

  setUser: (userId: string) => {
    const user = PERSONAS[userId];
    if (user) {
      localStorage.setItem('current_user', userId);
      set({ currentUser: user });
    }
  },

  clearUser: () => {
    localStorage.removeItem('current_user');
    set({ currentUser: null });
  },

  initializeUser: () => {
    const savedUserId = localStorage.getItem('current_user');
    if (savedUserId && PERSONAS[savedUserId]) {
      set({ currentUser: PERSONAS[savedUserId] });
    }
  },
}));

