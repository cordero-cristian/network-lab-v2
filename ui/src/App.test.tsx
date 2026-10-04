import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { deviceDetail, devices, health } from "./test/fixtures";

describe("application routes and states", () => {
  it("renders the device route with keyboard-accessible primary navigation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => new Response(JSON.stringify(String(input).includes("/health") ? health : devices), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Devices" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "f004-leaf01" })).toHaveAttribute("href", "/devices/f004-leaf01");
  });

  it("renders a safe unknown-route state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(health), { status: 200 }));
    render(<MemoryRouter initialEntries={["/missing"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /route not found/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to overview/i })).toBeInTheDocument();
  });

  it("exposes current comparison as read-only sections without sensitive or mutation controls", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => new Response(JSON.stringify(String(input).includes("/health") ? health : deviceDetail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Configuration Drift" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Operational Health" })).toBeInTheDocument();
    expect(screen.queryByText(/password|credential|private key|raw configuration/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remediate|deploy|edit|acknowledge|waive|suppress|approve/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/live state/i)).not.toBeInTheDocument();
  });
});
