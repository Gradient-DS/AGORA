import { ReactNode } from 'react';
import { Header } from './Header';
import { ConversationSidebar } from '@/components/history';
import { AdminPanel } from '@/components/admin';
import { useAdminStore } from '@/stores';

interface MainLayoutProps {
  children: ReactNode;
  onReconnect?: () => void;
}

export function MainLayout({ children, onReconnect }: MainLayoutProps) {
  const isAdminPanelOpen = useAdminStore((state) => state.isAdminPanelOpen);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header onReconnect={onReconnect} />
      <div className="flex-1 flex overflow-hidden relative">
        {isAdminPanelOpen ? (
          <main className="flex-1 overflow-hidden">
            <AdminPanel />
          </main>
        ) : (
          <>
            <ConversationSidebar />
            <main className="flex-1 overflow-hidden">
              {children}
            </main>
          </>
        )}
      </div>
    </div>
  );
}

