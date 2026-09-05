// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import "./gw-figure.ts";
import {
  NULL_SEMANTICS_STATES,
  roundTo,
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

describe("formatFigure digits", () => {
  it("renders to a fixed precision when asked and as served when not", () => {
    const figure = { value: "21000.000", unit: "bbl", d: "drv_x" };
    expect(formatFigure(figure, 0)).toBe("21,000 bbl");
    expect(formatFigure(figure)).toBe("21,000.000 bbl");
  });

  it("rounds half up and carries into the whole part", () => {
    expect(formatFigure({ value: "9.5", unit: "bbl", d: "drv_x" }, 0)).toBe("10 bbl");
    expect(formatFigure({ value: "9.49", unit: "bbl", d: "drv_x" }, 0)).toBe("9 bbl");
    expect(formatFigure({ value: "1.056", unit: "bbl", d: "drv_x" }, 2)).toBe("1.06 bbl");
    expect(formatFigure({ value: "0.04", unit: "bbl", d: "drv_x" }, 1)).toBe("0.0 bbl");
    expect(formatFigure({ value: "0.05", unit: "bbl", d: "drv_x" }, 1)).toBe("0.1 bbl");
  });

  it("keeps a value already shorter than the precision asked for", () => {
    expect(formatFigure({ value: "3000", unit: "ft", d: "drv_x" }, 2)).toBe("3,000 ft");
  });

  it("never routes a large value through a float", () => {
    expect(
      formatFigure({ value: "123456789012345678901.5", unit: "bbl", d: "drv_x" }, 0),
    ).toBe("123,456,789,012,345,678,902 bbl");
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

  it("knows the lease's filing as its own state, not as this well's report", () => {
    // The four above are what a well-grain jurisdiction emits. A lease-grain one emits a
    // fifth, and labelling it `reported` says the well reported a number it never filed.
    const mark = nullSemantics("lease_reported");

    expect(mark.label).toBe("lease reported");
    expect(mark.className).toBe("gw-state-lease-reported");
    expect(mark.className).not.toBe(nullSemantics("reported").className);
    expect(mark.title).toContain("share");
  });
});


describe("roundTo refuses a precision that is not one", () => {
  it.each([-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY])("throws on %s", (digits) => {
    expect(() => roundTo("21000.000", digits)).toThrow(/non-negative integer/);
  });
});

describe("gw-figure's digits attribute", () => {
  const mount = (digits: string | null): string => {
    const el = document.createElement("gw-figure");
    el.setAttribute("value", "21000.456");
    el.setAttribute("unit", "bbl");
    el.setAttribute("handle", "drv_test#col=x");
    if (digits !== null) el.setAttribute("digits", digits);
    document.body.replaceChildren(el);
    return el.textContent ?? "";
  };
  it("rounds only on a non-negative integer", () => {
    expect(mount("0")).toContain("21,000 bbl");
    expect(mount("1")).toContain("21,000.5 bbl");
  });
  it.each(["", "NaN", "-1", "1.5", "two"])("treats %j as unset and renders as served", (raw) => {
    expect(mount(raw)).toContain("21,000.456 bbl");
  });
});

describe("sumDecimal", () => {
  it("sums on the decimal string at the widest scale it was handed, exactly", async () => {
    const { sumDecimal } = await import("./format.ts");
    expect(sumDecimal(["7.462", "10.113", "81.876"])).toBe("99.451");
    expect(sumDecimal(["1000", "1001", null, ""])).toBe("2001");
    expect(sumDecimal(["0.5", "-0.75", "2"])).toBe("1.75");
    expect(sumDecimal([])).toBe("0");
  });
});
