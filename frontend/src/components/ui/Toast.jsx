import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import "./Toast.css";

const ToastContext = createContext(null);

/** Short-lived confirmations ("Lecture deleted"). Errors needing action stay in context, not in toasts. */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id) => setToasts((all) => all.filter((toast) => toast.id !== id)), []);

  const show = useCallback(
    (message, tone = "success") => {
      const id = ++nextId.current;
      setToasts((all) => [...all, { id, message, tone }]);
      setTimeout(() => dismiss(id), 4000);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast--${toast.tone}`}>
            <span>{toast.message}</span>
            <button type="button" className="toast__close" aria-label="Dismiss" onClick={() => dismiss(toast.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside <ToastProvider>");
  return value;
}
