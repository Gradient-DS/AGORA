import { ReactNode } from 'react';
import { Header } from './Header';
import { ConversationSidebar } from '@/components/history';

interface MainLayoutProps {
  children: ReactNode;
  onReconnect?: () => void;
}

export function MainLayout({ children, onReconnect }: MainLayoutProps) {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header onReconnect={onReconnect} />
      <div className="flex-1 flex overflow-hidden relative">
        <ConversationSidebar />
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}

