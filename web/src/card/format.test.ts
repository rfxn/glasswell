// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import "./gw-figure.ts";
import {
  NULL_SEMANTICS_STATES,
  formatFigure,
  formatMonth,
  formatValue,
  formatVolume,
  nullSemantics,
  pointMark,
} from "./format.ts";

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

  it("can carry a label for assistive tech without printing it twice", () => {
    // Inside a <dt>/<dd> pair the label is already the <dt>: the card read
    // "Lateral length | lateral length 15,073.98 ft".
    const figure = document.createElement("gw-figure");
    figure.setAttribute("value", "12");
    figure.setAttribute("unit", "bbl");
    figure.setAttribute("handle", "drv_x");
    figure.setAttribute("label", "lateral length");
    figure.setAttribute("label-hidden", "");
    document.body.appendChild(figure);

    expect(figure.querySelector(".gw-figure-label")).toBeNull();
    expect(figure.querySelector("button")?.getAttribute("aria-label")).toBe(
      "Lineage for lateral length",
    );
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

describe("formatMonth", () => {
  it("renders a production month the way a reader reads it, not the way the wire sends it", () => {
    expect(formatMonth("2025-10")).toBe("Oct 2025");
    expect(formatMonth("2026-01")).toBe("Jan 2026");
  });

  it("passes anything that is not a month through untouched", () => {
    expect(formatMonth("latest")).toBe("latest");
    expect(formatMonth("2025-13")).toBe("2025-13");
  });
});

describe("formatVolume", () => {
  it("rounds a monthly volume to whole units — three decimals on a month is noise", () => {
    expect(formatVolume("70965.000")).toBe("70,965");
    expect(formatVolume("70965.500")).toBe("70,966");
    expect(formatVolume("70965.499")).toBe("70,965");
  });

  it("keeps a zero a zero, because reported_zero is a fact, not a gap", () => {
    expect(formatVolume("0.000")).toBe("0");
  });

  it("does not go through a float, so a long decimal cannot drift", () => {
    expect(formatVolume("123456789012345678901.4")).toBe("123,456,789,012,345,678,901");
  });

  it("passes a non-numeric string through", () => {
    expect(formatVolume("n/a")).toBe("n/a");
  });
});

describe("the null-semantics key", () => {
  it("names the four states the API can emit, in the order the strip renders them", () => {
    expect([...NULL_SEMANTICS_STATES]).toEqual([
      "reported",
      "reported_zero",
      "withheld",
      "no_report",
    ]);
  });

  it("gives each state its own swatch and its own words, so 18 squares can be decoded", () => {
    const marks = NULL_SEMANTICS_STATES.map((state) => nullSemantics(state));

    expect(new Set(marks.map((mark) => mark.className)).size).toBe(4);
    expect(marks.every((mark) => mark.label.length > 0 && mark.title.length > 0)).toBe(true);
    expect(marks.every((mark) => mark.className !== "gw-state-unknown")).toBe(true);
  });
});
