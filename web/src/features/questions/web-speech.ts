export type RecognitionResult = {
  0: { transcript: string };
  isFinal: boolean;
  length: number;
};

export interface RecognitionLike {
  abort(): void;
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onerror: ((event: { error: string }) => void) | null;
  onresult:
    | ((event: { results: ArrayLike<RecognitionResult> }) => void)
    | null;
  start(): void;
  stop(): void;
}

export type SpeechVoiceLike = {
  lang: string;
  name: string;
};

export type SpeechUtteranceLike = {
  lang: string;
  text: string;
  voice: SpeechVoiceLike | null;
};

export type SpeechSynthesisLike = {
  cancel(): void;
  getVoices(): SpeechVoiceLike[];
  speak(utterance: SpeechUtteranceLike): void;
};

export type SpeechEnvironment = {
  createRecognition: (() => RecognitionLike) | null;
  createUtterance: ((text: string) => SpeechUtteranceLike) | null;
  speechSynthesis: SpeechSynthesisLike | null;
};

export interface SpeechInputController {
  abort(): void;
  start(
    onTranscript: (text: string) => void,
    onError: (code: string) => void,
  ): void;
  stop(): void;
  supported: boolean;
}

function browserSpeechEnvironment(): SpeechEnvironment {
  if (typeof window === "undefined") {
    return {
      createRecognition: null,
      createUtterance: null,
      speechSynthesis: null,
    };
  }
  const Recognition =
    window.SpeechRecognition ?? window.webkitSpeechRecognition;
  return {
    createRecognition:
      Recognition === undefined ? null : () => new Recognition(),
    createUtterance:
      typeof window.SpeechSynthesisUtterance === "undefined"
        ? null
        : (text) => new window.SpeechSynthesisUtterance(text),
    speechSynthesis:
      window.speechSynthesis === undefined
        ? null
        : window.speechSynthesis,
  };
}

export function createSpeechInputController(
  environment: SpeechEnvironment = browserSpeechEnvironment(),
): SpeechInputController {
  const recognition = environment.createRecognition?.() ?? null;
  if (recognition === null) {
    return {
      abort: () => undefined,
      start: () => undefined,
      stop: () => undefined,
      supported: false,
    };
  }
  recognition.lang = "ko-KR";
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  return {
    abort: () => recognition.abort(),
    start: (onTranscript, onError) => {
      recognition.onresult = (event) => {
        let transcript = "";
        for (let index = 0; index < event.results.length; index += 1) {
          transcript += event.results[index]?.[0]?.transcript ?? "";
        }
        const normalized = transcript.trim();
        if (normalized.length > 0) {
          onTranscript(normalized);
        }
      };
      recognition.onerror = (event) => onError(event.error);
      recognition.start();
    },
    stop: () => recognition.stop(),
    supported: true,
  };
}

export function speakKorean(
  text: string,
  environment: SpeechEnvironment = browserSpeechEnvironment(),
): boolean {
  if (
    text.trim().length === 0 ||
    environment.speechSynthesis === null ||
    environment.createUtterance === null
  ) {
    return false;
  }
  const utterance = environment.createUtterance(text);
  utterance.lang = "ko-KR";
  utterance.voice =
    environment.speechSynthesis
      .getVoices()
      .find((voice) => voice.lang.toLowerCase().startsWith("ko")) ?? null;
  environment.speechSynthesis.speak(utterance);
  return true;
}

export function cancelSpeech(
  environment: SpeechEnvironment = browserSpeechEnvironment(),
): void {
  environment.speechSynthesis?.cancel();
}
