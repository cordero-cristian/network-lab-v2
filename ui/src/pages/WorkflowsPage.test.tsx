import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { workflows } from "../test/fixtures";
import { WorkflowsPage } from "./WorkflowsPage";

describe("WorkflowsPage states", () => {
  it("renders exact backend outcomes with narrow-screen labels and pinned keyboard links", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(workflows), { status: 200 }));
    render(<MemoryRouter><WorkflowsPage /></MemoryRouter>);
    expect(await screen.findByText("Deployment Failed")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Deployment.*deploy-device-config/i });
    expect(link.getAttribute("href")).toContain(`run_id=${workflows.items[0].run_id}`);
    expect(screen.getByText("f004-leaf01").closest("td")).toHaveAttribute("data-label", "Device");
    expect(screen.getByText(workflows.items[0].event_id!.slice(0, 8) + "…").closest("td")).toHaveAttribute("data-label", "Event");
    expect(screen.getByRole("table").parentElement).toHaveClass("responsive-table");
  });

  it("does not describe unavailable workflow visibility as empty", async () => {
    const unavailable = { ...workflows, items: [], count: 0, availability: { ...workflows.availability, status: "unavailable", message: "Temporal workflow data is unavailable" } };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(unavailable), { status: 200 }));
    render(<MemoryRouter><WorkflowsPage /></MemoryRouter>);
    expect(await screen.findByText("Observations unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No records returned")).not.toBeInTheDocument();
  });

  it("names an unavailable retained event identifier as a gap", async () => {
    const missingEvent = { ...workflows, items: [{ ...workflows.items[0], event_id: null }] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(missingEvent), { status: 200 }));
    render(<MemoryRouter><WorkflowsPage /></MemoryRouter>);
    expect(await screen.findByText("Not retained")).toBeInTheDocument();
  });
});
