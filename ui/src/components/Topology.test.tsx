import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { topology } from "../test/fixtures";
import { Topology } from "./Topology";

describe("Topology", () => {
  it("renders truthful link and visible node status semantics as keyboard links", async () => {
    const user = userEvent.setup();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    render(<MemoryRouter><Topology graph={topology} /></MemoryRouter>);
    expect(screen.getByText(/Logical BGP intent/)).toBeInTheDocument();
    const leaf = screen.getByRole("link", { name: /open f004-leaf01, status degraded/i });
    expect(leaf).toHaveAttribute("href", "/devices/f004-leaf01");
    leaf.focus();
    await user.keyboard("{Tab}");
    const detail = screen.getByRole("link", { name: /open device detail/i });
    expect(detail).toHaveAttribute("href", "/devices/f004-leaf01");
    expect(screen.getByText("! Degraded")).toBeInTheDocument();
    expect(leaf.querySelector("rect.topology__plate")).toHaveAttribute("height", "106");
    expect(106 * ((375 - 76) / 760)).toBeGreaterThanOrEqual(40);
    expect(screen.getByText(/Logical BGP link: f004-leaf01 to f004-spine01/i)).toBeInTheDocument();
  });

  it("keeps node links exposed and marks missing relationships as incomplete", () => {
    render(<MemoryRouter><Topology graph={{ ...topology, links: [] }} /></MemoryRouter>);
    expect(screen.getByRole("group", { name: /Current lab topology/ })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /open f004-/i })).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("Relationship data incomplete");
    expect(screen.getByText(/no authoritative physical or logical links/i)).toBeInTheDocument();
  });
});
