import { describe, expect, it } from "vitest";
import { SPRITES } from "./pixels";

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
