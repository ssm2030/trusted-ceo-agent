import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { VoiceControls } from "@/features/questions/VoiceControls";
import type { SpeechInputController } from "@/features/questions/web-speech";

function supportedController(
  transcript = "인식된 질문",
): SpeechInputController {
  return {
    abort: vi.fn(),
    start: vi.fn((onTranscript) => onTranscript(transcript)),
    stop: vi.fn(),
    supported: true,
  };
}

describe("VoiceControls", () => {
  it("requires disclosure acknowledgement and only fills the draft", async () => {
    const user = userEvent.setup();
    const controller = supportedController();
    const onTranscript = vi.fn();
    render(
      <VoiceControls
        answerText=""
        controller={controller}
        onTranscript={onTranscript}
      />,
    );

    expect(
      screen.getByText(
      /브라우저와 운영체제가 음성을 외부 서비스에서 처리할 수 있습니다/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "누르고 말하기" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", { name: "음성 처리 안내 확인" }),
    );
    await user.click(screen.getByRole("button", { name: "누르고 말하기" }));

    expect(controller.start).toHaveBeenCalled();
    expect(onTranscript).toHaveBeenCalledWith("인식된 질문");
    expect(screen.queryByText("질문을 전송했습니다")).not.toBeInTheDocument();
  });

  it("hides voice actions when unsupported", () => {
    render(
      <VoiceControls
        answerText="답변"
        controller={{
          abort: vi.fn(),
          start: vi.fn(),
          stop: vi.fn(),
          supported: false,
        }}
        onTranscript={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "누르고 말하기" }),
    ).not.toBeInTheDocument();
  });
});
