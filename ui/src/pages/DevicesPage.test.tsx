import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { devices } from "../test/fixtures";
import { DevicesPage } from "./DevicesPage";

describe("DevicesPage states", () => {
  it("keeps narrow-screen labels and keyboard device links", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(devices), { status: 200 }));
    render(<MemoryRouter><DevicesPage /></MemoryRouter>);
    const link = await screen.findByRole("link", { name: "f004-leaf01" });
    expect(link).toHaveAttribute("href", "/devices/f004-leaf01");
    expect(screen.getByText("172.31.46.12").closest("td")).toHaveAttribute("data-label", "Management");
  });

  it("does not describe unavailable inventory as empty", async () => {
    const unavailable = { ...devices, items: [], count: 0, availability: { ...devices.availability, status: "unavailable", message: "Device inventory is unavailable" } };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(unavailable), { status: 200 }));
    render(<MemoryRouter><DevicesPage /></MemoryRouter>);
    expect(await screen.findByText("Observations unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No records returned")).not.toBeInTheDocument();
  });
});
