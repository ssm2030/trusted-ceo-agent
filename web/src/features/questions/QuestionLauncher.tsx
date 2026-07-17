import type { RefObject } from "react";

import styles from "@/features/questions/QuestionExperience.module.css";

type QuestionLauncherProps = {
  buttonRef: RefObject<HTMLButtonElement | null>;
  onOpen: () => void;
};

export function QuestionLauncher({
  buttonRef,
  onOpen,
}: QuestionLauncherProps) {
  return (
    <button
      aria-label="결과에 질문하기"
      className={styles.launcher}
      onClick={onOpen}
      ref={buttonRef}
      title="결과에 질문하기"
      type="button"
    >
      <span aria-hidden="true" className={styles.launcherIcon}>
        ?
      </span>
    </button>
  );
}
