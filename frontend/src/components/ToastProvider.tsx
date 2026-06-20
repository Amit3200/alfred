import {
  CheckCircleFilled,
  CloseOutlined,
  ExclamationCircleFilled,
} from "@ant-design/icons";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

type ToastType = "success" | "error";

type ToastItem = {
  id: number;
  type: ToastType;
  title: string;
  description: string;
};

type ToastContextValue = {
  showToast: (type: ToastType, text: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

function parseToastText(type: ToastType, text: string) {
  const colon = text.indexOf(": ");
  if (colon > 0 && colon < 24) {
    return {
      title: text.slice(0, colon),
      description: text.slice(colon + 2),
    };
  }
  return {
    title: type === "success" ? "Success" : "Something went wrong",
    description: text,
  };
}

function ToastCard({ toast, onClose }: { toast: ToastItem; onClose: () => void }) {
  const Icon = toast.type === "success" ? CheckCircleFilled : ExclamationCircleFilled;

  return (
    <div className={`alfred-toast-card alfred-toast-card-${toast.type}`} role="status">
      <Icon className="alfred-toast-card-icon" aria-hidden />
      <div className="alfred-toast-card-body">
        <div className="alfred-toast-card-title">{toast.title}</div>
        <div className="alfred-toast-card-desc">{toast.description}</div>
      </div>
      <button type="button" className="alfred-toast-card-close" onClick={onClose} aria-label="Dismiss">
        <CloseOutlined />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (type: ToastType, text: string) => {
      const { title, description } = parseToastText(type, text);
      const id = ++idRef.current;
      setToasts((current) => [...current.slice(-3), { id, type, title, description }]);
      timersRef.current.set(
        id,
        setTimeout(() => dismiss(id), 4500),
      );
    },
    [dismiss],
  );

  useEffect(
    () => () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current.clear();
    },
    [],
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="alfred-toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onClose={() => dismiss(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

/** Standalone helper — set by ToastProvider on mount. */
let globalShowToast: ToastContextValue["showToast"] | null = null;

export function bindGlobalToast(show: ToastContextValue["showToast"]) {
  globalShowToast = show;
}

export function showToast(type: ToastType, text: string) {
  if (globalShowToast) {
    globalShowToast(type, text);
    return;
  }
  console.warn("[toast]", type, text);
}
