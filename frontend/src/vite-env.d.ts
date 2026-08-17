/// <reference types="vite/client" />

interface Window {
  MonacoEnvironment?: {
    getWorker: (...args: unknown[]) => Worker;
  };
}
