import { ReactNode } from 'react';
import { Header } from './Header';

interface MainLayoutProps {
  children: ReactNode;
  onReconnect?: () => void;
}

export function MainLayout({ children, onReconnect }: MainLayoutProps) {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header onReconnect={onReconnect} />
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}

