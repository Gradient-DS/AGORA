# User Profiles Feature

## Overview

The HAI application now supports user profiles based on the three personas defined in the PERSONAS_AND_SCENARIOS document. This feature allows users to start inspections as different inspector personas, providing a personalized experience.

## Personas

### 1. Inspecteur Koen
- **Age:** 40 years
- **Title:** Inspecteur Voedselveiligheid Horeca
- **Location:** Regio Randstad
- **Experience:** 15 years
- **Specialty:** Horeca

### 2. Inspecteur Fatima
- **Age:** 32 years
- **Title:** Inspecteur Productveiligheid
- **Location:** Regio Randstad
- **Experience:** 4 years
- **Specialty:** Productveiligheid

### 3. Inspecteur Jan
- **Age:** 58 years
- **Title:** Senior inspecteur Voedselveiligheid
- **Location:** Regio Noord-Nederland
- **Experience:** 30+ years
- **Specialty:** Voedselveiligheid

## Features

### User Selection
- In the Header, the "+ Nieuwe Inspectie" button has been replaced with a dropdown menu
- Users can now select "+ Nieuwe Inspectie als" and choose from the three personas
- Each persona is displayed with their name, title, and years of experience

### Personalized Experience
- The selected user's name is displayed in the header with a badge
- The chat interface greets the user by name when starting a new conversation
- The chat header displays "Chat met {Name}" to indicate which persona is active
- User selection is persisted in localStorage across sessions

### User Store
- New `useUserStore` Zustand store manages user state
- `PERSONAS` constant contains all available user profiles
- User selection is saved to localStorage for persistence
- `initializeUser()` loads the saved user on app startup

## Implementation Details

### Files Modified
1. `src/stores/useUserStore.ts` - New store for user management
2. `src/stores/index.ts` - Export user store and types
3. `src/components/layout/Header.tsx` - Added dropdown for persona selection
4. `src/components/chat/ChatInterface.tsx` - Added personalized greeting
5. `src/App.tsx` - Initialize user store on startup
6. `src/components/ui/dropdown-menu.tsx` - New UI component for dropdown

### Dependencies Added
- `@radix-ui/react-dropdown-menu` - Accessible dropdown menu component

## Installation

To install the new dependency, run:

```bash
cd HAI
pnpm install @radix-ui/react-dropdown-menu
```

## Usage

1. Start the application
2. Click on the "+ Nieuwe Inspectie als" dropdown in the header
3. Select one of the three personas (Koen, Fatima, or Jan)
4. The application will reload with the selected persona
5. The chat will greet the selected persona by name

## Future Enhancements

Possible future enhancements to the user profile system:
- Send user context to the backend for persona-specific responses
- Add more detailed user preferences
- Allow customization of user profiles
- Add user profile settings page
- Track usage statistics per persona
- Customize agent behavior based on persona characteristics (e.g., experience level)

