import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AllocationDonut, PerformanceChart, PriceChart, ProjectionChart, ShareBars } from "./charts";

/** The transparent hover layer every line chart puts over its plot area. */
function hoverLayer(figure: HTMLElement): Element {
  const rect = figure.querySelector('rect[fill="transparent"]');
  if (!rect) throw new Error("no hover layer");
  return rect;
}

describe("charts", () => {
  it("shows a price tooltip on hover and hides it on leave", () => {
    render(
      <PriceChart
        axis
        label="AAPL closing prices"
        points={[
          { t: "2026-10-01T00:00:00Z", close: 220 },
          { t: "2026-10-15T00:00:00Z", close: 230 },
          { t: "2026-10-30T00:00:00Z", close: 226 },
        ]}
      />,
    );
    const figure = screen.getByRole("figure", { name: "AAPL closing prices" });
    fireEvent.pointerMove(hoverLayer(figure), { clientX: 0 });
    expect(screen.getByRole("tooltip")).toHaveTextContent("220.00");
    fireEvent.pointerLeave(hoverLayer(figure));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("needs two points to draw a line", () => {
    const { container } = render(<PriceChart label="One" points={[{ t: "2026-10-01", close: 1 }]} />);
    expect(container).toBeEmptyDOMElement();
    const { container: perf } = render(<PerformanceChart benchmarkLabel="S&P 500" points={[]} />);
    expect(perf).toBeEmptyDOMElement();
  });

  it("compares a portfolio with its benchmark", () => {
    render(
      <PerformanceChart
        benchmarkLabel="S&P 500 (SPY)"
        benchmarkShort="SPY"
        points={[
          { date: "2026-01-02", portfolio: 100, benchmark: 100 },
          { date: "2026-06-01", portfolio: 108, benchmark: 104 },
          { date: "2026-10-30", portfolio: 112.5, benchmark: 109 },
        ]}
      />,
    );
    const figure = screen.getByRole("figure", { name: "This portfolio compared with S&P 500 (SPY)" });
    expect(figure).toHaveTextContent("+12.5%");
    fireEvent.pointerMove(hoverLayer(figure), { clientX: 0 });
    expect(screen.getByRole("tooltip")).toHaveTextContent("Jan 2, 2026");
  });

  it("projects a goal band against its target", () => {
    render(
      <ProjectionChart
        target={50000}
        series={[0, 30, 60].map((month) => ({
          month,
          date: `2027-0${1 + month / 30}-01`,
          contributed: 10000 + month * 600,
          values: { pessimistic: 10000 + month * 600, expected: 10000 + month * 650, optimistic: 10000 + month * 700 },
        }))}
      />,
    );
    const figure = screen.getByRole("figure");
    fireEvent.pointerMove(hoverLayer(figure), { clientX: 0 });
    expect(screen.getByRole("tooltip")).toHaveTextContent("$10,000");
  });

  it("highlights a donut segment from the chart or the legend", () => {
    render(
      <AllocationDonut
        label="By asset class"
        slices={[
          { key: "etf", label: "Stock funds", weight: 0.7, value: 7000, color: "red" },
          { key: "bond_etf", label: "Bond funds", weight: 0.3, value: 3000, color: "blue" },
        ]}
      />,
    );
    const figure = screen.getByRole("figure", { name: "By asset class" });
    const segment = figure.querySelector("circle");
    if (!segment) throw new Error("no segment");
    fireEvent.pointerEnter(segment);
    expect(figure).toHaveTextContent("Stock funds");
    expect(segment.getAttribute("stroke-width")).toBe("26");
    fireEvent.pointerLeave(segment);
    expect(segment.getAttribute("stroke-width")).toBe("22");

    fireEvent.pointerEnter(screen.getByText("Bond funds").closest("li") as HTMLElement);
    expect(figure.querySelectorAll("circle")[1]?.getAttribute("stroke-width")).toBe("26");
    const { container } = render(<AllocationDonut label="Empty" slices={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("labels share bars with percentages and dollar values", () => {
    render(<ShareBars label="Sectors" data={[{ label: "Technology", weight: 0.625, value: 12500 }, { label: "Energy", weight: 0.375 }]} />);
    const list = screen.getByRole("list", { name: "Sectors" });
    expect(list).toHaveTextContent("Technology");
    expect(list).toHaveTextContent("62.5%");
  });
});
