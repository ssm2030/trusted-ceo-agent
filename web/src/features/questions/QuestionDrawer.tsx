"use client";

import {
  useEffect,
  useRef,
  type ReactNode,
  type UIEvent,
} from "react";

import styles from "@/features/questions/QuestionExperience.module.css";

type QuestionDrawerProps = {
  children: ReactNode;
  composer: ReactNode;
  modeLabel: string | null;
  onClose: () => void;
  onScrollTopChange: (scrollTop: number) => void;
  open: boolean;
  scopeLabel: string;
  scrollTop: number;
};

export function QuestionDrawer({
  children,
  composer,
  modeLabel,
  onClose,
  onScrollTopChange,
  open,
  scopeLabel,
  scrollTop,
}: QuestionDrawerProps) {
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  useEffect(() => {
    if (open && bodyRef.current !== null) {
      bodyRef.current.scrollTop = scrollTop;
    }
  }, [open, scrollTop]);

  if (!open) {
    return null;
  }

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    onScrollTopChange(event.currentTarget.scrollTop);
  };

  return (
    <section
      aria-label="결과 질문 창"
      aria-modal="false"
      className={styles.drawer}
      role="dialog"
    >
      <header className={styles.drawerHeader}>
        <div>
          <p className={styles.eyebrow}>근거 범위 질문</p>
          <h2 className={styles.drawerTitle}>결과에 질문하기</h2>
          <span className={styles.scope}>{scopeLabel}</span>
          {modeLabel === null ? null : (
            <span className={styles.mode}>{modeLabel}</span>
          )}
        </div>
        <button
          aria-label="질문 창 닫기"
          autoFocus
          className={styles.closeButton}
          onClick={onClose}
          type="button"
        >
          닫기
        </button>
      </header>
      <div
        className={styles.drawerBody}
        onScroll={handleScroll}
        ref={bodyRef}
      >
        {children}
      </div>
      {composer}
    </section>
  );
}
