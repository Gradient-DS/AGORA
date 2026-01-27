/**
 * IndexedDB-based offline message buffer for AGORA HAI.
 *
 * Stores messages sent while offline and replays them on reconnection.
 */

interface BufferedMessage {
  id: string;
  content: string;
  timestamp: number;
  threadId: string;
  userId: string;
}

const DB_NAME = 'agora-offline-buffer';
const STORE_NAME = 'messages';

class OfflineMessageBuffer {
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        }
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onerror = () => reject(request.error);
    });
  }

  async addMessage(message: BufferedMessage): Promise<void> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const request = store.add(message);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getAndClearMessages(): Promise<BufferedMessage[]> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const getRequest = store.getAll();

      getRequest.onsuccess = () => {
        const messages = getRequest.result as BufferedMessage[];
        store.clear();
        resolve(messages.sort((a, b) => a.timestamp - b.timestamp));
      };

      getRequest.onerror = () => reject(getRequest.error);
    });
  }

  async getCount(): Promise<number> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const request = store.count();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
}

export const offlineBuffer = new OfflineMessageBuffer();
