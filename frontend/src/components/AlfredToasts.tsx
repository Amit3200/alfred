import { useEffect } from "react";
import { bindGlobalToast, ToastProvider, useToast } from "./ToastProvider";

function ToastBinder() {
  const { showToast } = useToast();
  useEffect(() => {
    bindGlobalToast(showToast);
    return () => bindGlobalToast(() => {});
  }, [showToast]);
  return null;
}

export function AlfredToasts({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <ToastBinder />
      {children}
    </ToastProvider>
  );
}
