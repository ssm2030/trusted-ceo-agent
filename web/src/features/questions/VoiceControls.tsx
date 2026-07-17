"use client";

import {
  useEffect,
  useState,
  type MouseEvent,
  type PointerEvent,
} from "react";

import {
  cancelSpeech,
  speakKorean,
  type SpeechInputController,
} from "@/features/questions/web-speech";
import styles from "@/features/questions/QuestionExperience.module.css";

type VoiceControlsProps = {
  answerText: string;
  cancelReadout?: () => void;
  controller: SpeechInputController;
  onTranscript: (text: string) => void;
  readAnswer?: (text: string) => boolean;
};

export function VoiceControls({
  answerText,
  cancelReadout = cancelSpeech,
  controller,
  onTranscript,
  readAnswer = speakKorean,
}: VoiceControlsProps) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [listening, setListening] = useState(false);

  useEffect(
    () => () => {
      controller.abort();
      cancelReadout();
    },
    [cancelReadout, controller],
  );

  if (!controller.supported) {
    return null;
  }

  const start = () => {
    if (!acknowledged || listening) {
      return;
    }
    setListening(true);
    controller.start(
      (transcript) => {
        onTranscript(transcript);
        setListening(false);
      },
      () => setListening(false),
    );
  };
  const stop = () => {
    if (!listening) {
      return;
    }
    controller.stop();
    setListening(false);
  };
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (event.detail !== 0) {
      return;
    }
    if (listening) {
      stop();
    } else {
      start();
    }
  };
  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    start();
  };

  return (
    <div className={styles.voicePanel}>
      <p className={styles.voiceDisclosure}>
        브라우저와 운영체제가 음성을 외부 서비스에서 처리할 수 있습니다.
        음성은 저장하지 않으며, 인식된 텍스트를 확인한 뒤 직접 전송합니다.
      </p>
      <label className={styles.checkLabel}>
        <input
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.currentTarget.checked)}
          type="checkbox"
        />
        음성 처리 안내 확인
      </label>
      <div className={styles.voiceActions}>
        <button
          aria-pressed={listening}
          className={styles.voiceButton}
          disabled={!acknowledged}
          onClick={handleClick}
          onPointerCancel={stop}
          onPointerDown={handlePointerDown}
          onPointerUp={stop}
          type="button"
        >
          {listening ? "말하기 중지" : "누르고 말하기"}
        </button>
        {answerText.length === 0 ? null : (
          <button
            className={styles.voiceButton}
            onClick={() => void readAnswer(answerText)}
            type="button"
          >
            답변 읽기
          </button>
        )}
      </div>
    </div>
  );
}
