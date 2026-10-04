import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { workflowDetail } from "../test/fixtures";
import { WorkflowTimeline } from "./WorkflowTimeline";

describe("WorkflowTimeline", () => {
  it("keeps exact history order, attempts, failure, and not-reached stages visible", () => {
    render(<WorkflowTimeline stages={workflowDetail.stages} />);
    const stages = screen.getAllByRole("listitem");
    expect(stages.map((stage) => stage.textContent)).toEqual([
      expect.stringContaining("Workflow started"),
      expect.stringContaining("gNMI deployment"),
      expect.stringContaining("Operational validation"),
    ]);
    expect(screen.getByText(/attempt 1/)).toBeInTheDocument();
    expect(screen.getByText("Activity did not complete")).toBeInTheDocument();
    expect(screen.getByText("Not Reached")).toBeInTheDocument();
  });
});
