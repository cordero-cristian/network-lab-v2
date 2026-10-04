import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { overview } from "../test/fixtures";
import { OverviewPage } from "./OverviewPage";

describe("OverviewPage states", () => {
  it("preserves healthy sections when recent activity is unavailable", async () => {
    const partial = {
      ...overview,
      activity: {
        availability: { ...overview.activity.availability, status: "unavailable" as const, message: "Temporal activity is unavailable" },
        items: [],
      },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(partial), { status: 200 }));
    render(<MemoryRouter><OverviewPage /></MemoryRouter>);
    expect((await screen.findAllByText("Temporal activity is unavailable")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("group", { name: /Current lab topology/ })).toBeInTheDocument();
    expect(screen.getByText("Observations unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/No admitted workflows were returned/)).not.toBeInTheDocument();
  });

  it("shows a safe route error when no prior response exists", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("socket detail that must not render"));
    render(<MemoryRouter><OverviewPage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Observation unavailable" })).toBeInTheDocument();
    expect(screen.getByText("The control-plane API is unavailable.")).toBeInTheDocument();
    expect(screen.queryByText(/socket detail/)).not.toBeInTheDocument();
  });

  it("uses shape-matched loading rows while the first observation is pending", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise<Response>(() => {}));
    render(<MemoryRouter><OverviewPage /></MemoryRouter>);
    expect(screen.getAllByLabelText("Loading").length).toBeGreaterThan(1);
  });
});
