import { describe, expect, it, vi } from "vitest";

import {
  cancelSpeech,
  createSpeechInputController,
  speakKorean,
  type SpeechEnvironment,
} from "@/features/questions/web-speech";

class FakeRecognition {
  continuous = true;
  interimResults = false;
  lang = "";
  maxAlternatives = 0;
  onerror: ((event: { error: string }) => void) | null = null;
  onresult:
    | ((event: {
        results: ArrayLike<{
          0: { transcript: string };
          isFinal: boolean;
          length: number;
        }>;
      }) => void)
    | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
}

function recognitionEnvironment(recognition: FakeRecognition): SpeechEnvironment {
  return {
    createRecognition: () => recognition,
    speechSynthesis: null,
    createUtterance: null,
  };
}

describe("web speech adapter", () => {
  it("keeps text mode available when recognition is unsupported", () => {
    const controller = createSpeechInputController({
      createRecognition: null,
      createUtterance: null,
      speechSynthesis: null,
    });

    expect(controller.supported).toBe(false);
  });

  it("configures Korean recognition and reports transcript without submit logic", () => {
    const recognition = new FakeRecognition();
    const onTranscript = vi.fn();
    const controller = createSpeechInputController(
      recognitionEnvironment(recognition),
    );

    controller.start(onTranscript, vi.fn());
    expect(recognition).toMatchObject({
      continuous: false,
      interimResults: true,
      lang: "ko-KR",
      maxAlternatives: 1,
    });
    recognition.onresult?.({
      results: {
        0: {
          0: { transcript: "현금 회수 근거" },
          isFinal: true,
          length: 1,
        },
        length: 1,
      },
    });

    expect(onTranscript).toHaveBeenCalledWith("현금 회수 근거");
  });

  it("reads with a Korean voice and cancels synthesis", () => {
    const cancel = vi.fn();
    const speak = vi.fn();
    const koreanVoice = { lang: "ko-KR", name: "한국어" };
    const environment: SpeechEnvironment = {
      createRecognition: null,
      createUtterance: (text) => ({ lang: "", text, voice: null }),
      speechSynthesis: {
        cancel,
        getVoices: () => [
          { lang: "en-US", name: "English" },
          koreanVoice,
        ],
        speak,
      },
    };

    expect(speakKorean("검증된 답변", environment)).toBe(true);
    expect(speak).toHaveBeenCalledWith(
      expect.objectContaining({
        lang: "ko-KR",
        text: "검증된 답변",
        voice: koreanVoice,
      }),
    );
    cancelSpeech(environment);
    expect(cancel).toHaveBeenCalled();
  });
});
