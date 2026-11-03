import { describe, expect, it } from "vitest";
import { HAPPENING_SPRITES, SPRITES } from "./pixels";

describe("sprites", () => {
  it("draws every villager as 16 x 16 pixels in its own palette", () => {
    for (const [name, { rows, palette }] of Object.entries(SPRITES)) {
      expect(rows, name).toHaveLength(16);
      for (const row of rows) {
        expect(row, name).toHaveLength(16);
        for (const char of row) if (char !== ".") expect(palette[char], `${name} ${char}`).toBeDefined();
      }
    }
  });
});

describe("happening figures (M15)", () => {
  it("draws every happening figure as 10 x 10 pixels in its own palette", () => {
    expect(Object.keys(HAPPENING_SPRITES).sort()).toEqual(["animal", "peddler", "postman", "repair", "visitor"]);
    for (const [figure, { rows, palette }] of Object.entries(HAPPENING_SPRITES)) {
      expect(rows, figure).toHaveLength(10);
      for (const row of rows) {
        expect(row, figure).toHaveLength(10);
        for (const char of row) if (char !== ".") expect(palette[char], `${figure} ${char}`).toBeDefined();
      }
    }
  });
});
