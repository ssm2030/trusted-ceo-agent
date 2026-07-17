import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TopTabs } from "@/features/shell/TopTabs";

describe("TopTabs", () => {
  it("renders the two approved Korean tabs", () => {
    render(<TopTabs activePath="/analysis" />);

    expect(screen.getByRole("link", { name: "분석 작업" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "결과 리포트" })).toHaveAttribute(
      "href",
      "/report",
    );
  });
});
