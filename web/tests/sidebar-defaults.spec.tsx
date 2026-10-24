import { beforeEach, expect, it } from "vitest";
import {
  readNavLayout,
  writeNavLayout,
  resolveNavLayout,
} from "@/lib/sidebar-layout";
import {
  PRIMARY_NAV_HREFS,
  DEFAULT_COLLAPSED_NAV,
  SECONDARY_NAV,
} from "@/components/sidebar/nav-entries";

beforeEach(() => localStorage.clear());

it("new profiles see five primary entries and the folded features", () => {
  expect(readNavLayout()).toBeNull();
  const resolved = resolveNavLayout(
    PRIMARY_NAV_HREFS,
    readNavLayout(),
    DEFAULT_COLLAPSED_NAV
  );
  expect(resolved.visible).toEqual([
    "/chat",
    "/partners",
    "/learning",
    "/space",
    "/kanban",
  ]);
  // Fork addition: the legacy interactive Courses surface folds into "More"
  // by default, so the five primary entries above stay the default layout.
  expect(resolved.collapsed).toEqual([
    "/interactive-courses",
    "/co-writer",
    "/agents",
  ]);
  expect(resolved.customized).toBe(false);
  expect(SECONDARY_NAV.map(item => item.href)).toEqual(["/settings"]);
});

it("storage round trips an intentionally expanded layout without reapplying defaults", () => {
  writeNavLayout({ order: PRIMARY_NAV_HREFS, collapsed: [] });
  expect(readNavLayout()).toEqual({ order: PRIMARY_NAV_HREFS, collapsed: [] });
  expect(
    resolveNavLayout(PRIMARY_NAV_HREFS, readNavLayout(), DEFAULT_COLLAPSED_NAV)
      .collapsed
  ).toEqual([]);
});
