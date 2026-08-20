// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import "./gw-figure.ts";
import { formatFigure, formatValue, nullSemantics, pointMark } from "./format.ts";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("formatValue", () => {
  it("renders thousands separators and keeps the served precision", () => {
    expect(formatValue("9853.24")).toBe("9,853.24");
    expect(formatValue("1000.000")).toBe("1,000.000");
  });

  it("does not round-trip a decimal string through a float", () => {
    expect(formatValue("0.1000000000000000055511151231257827")).toBe(
      "0.1000000000000000055511151231257827",
    );
  });

  it("passes a non-numeric value through untouched", () => {
    expect(formatValue("n/a")).toBe("n/a");
  });
});

describe("formatFigure", () => {
  it("always renders the unit next to the value", () => {
    expect(formatFigure({ value: "9853.24", unit: "ft", d: "drv_x" })).toBe("9,853.24 ft");
  });

  it("throws when a figure has no unit — the browser-side no-naked-numbers rule", () => {
    expect(() => formatFigure({ value: "9853.24", unit: "", d: "drv_x" })).toThrow(/unit/i);
  });

  it("throws when a figure has no derivation handle", () => {
    expect(() => formatFigure({ value: "9853.24", unit: "ft", d: "" })).toThrow(/handle/i);
  });

  it("never converts ft to m: the served unit is rendered as served", () => {
    expect(formatFigure({ value: "3000", unit: "ft", d: "drv_x" })).toBe("3,000 ft");
    expect(formatFigure({ value: "3000", unit: "m", d: "drv_x" })).toBe("3,000 m");
  });
});

describe("nullSemantics", () => {
  it("renders no report, reported zero and withheld as three distinct states", () => {
    const marks = (["reported", "reported_zero", "no_report", "withheld"] as const).map((state) =>
      nullSemantics(state),
    );
    expect(new Set(marks.map((mark) => mark.label)).size).toBe(4);
    expect(new Set(marks.map((mark) => mark.className)).size).toBe(4);
  });

  it("does not collapse a withheld month into a missing one", () => {
    expect(nullSemantics("withheld").label).not.toBe(nullSemantics("no_report").label);
  });

  it("marks an unknown state rather than guessing", () => {
    expect(nullSemantics("something_new").label).toBe("something_new");
  });
});

describe("pointMark", () => {
  it("distinguishes a plotted zero from a gap", () => {
    expect(pointMark(0, "reported_zero").plotted).toBe(true);
    expect(pointMark(null, "no_report").plotted).toBe(false);
    expect(pointMark(null, "withheld").plotted).toBe(false);
    expect(pointMark(null, "withheld").className).not.toBe(pointMark(null, "no_report").className);
  });
});

describe("<gw-figure>", () => {
  it("renders value, unit and a handle affordance", () => {
    const figure = document.createElement("gw-figure");
    figure.setAttribute("value", "9853.24");
    figure.setAttribute("unit", "ft");
    figure.setAttribute("handle", "drv_x#api10=3305301234&col=lateral_length_ft");
    figure.setAttribute("label", "lateral length");
    document.body.appendChild(figure);
    expect(figure.textContent).toContain("9,853.24 ft");
    expect(figure.querySelector("button")?.getAttribute("data-handle")).toBe(
      "drv_x#api10=3305301234&col=lateral_length_ft",
    );
  });

  it("throws when rendered without a unit", () => {
    const figure = document.createElement("gw-figure");
    figure.setAttribute("value", "9853.24");
    figure.setAttribute("handle", "drv_x");
    expect(() => document.body.appendChild(figure)).toThrow(/unit/i);
  });

  it("throws when rendered without a handle", () => {
    const figure = document.createElement("gw-figure");
    figure.setAttribute("value", "9853.24");
    figure.setAttribute("unit", "ft");
    expect(() => document.body.appendChild(figure)).toThrow(/handle/i);
  });

  it("labels the value for the glossary path", () => {
    const figure = document.createElement("gw-figure");
    figure.setAttribute("value", "12");
    figure.setAttribute("unit", "bbl");
    figure.setAttribute("handle", "drv_x");
    figure.setAttribute("label", "oil");
    document.body.appendChild(figure);
    expect(figure.querySelector(".gw-figure-label")?.textContent).toBe("oil");
  });
});
