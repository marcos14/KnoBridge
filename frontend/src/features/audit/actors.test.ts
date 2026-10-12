import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";

import { actorLabel } from "./actors";

const t = i18n.t.bind(i18n);
const ACTORS = [{ id: "u1", name: "Ana Teste" }];

describe("actorLabel", () => {
  it("test_actor_label_uses_known_name", () => {
    expect(actorLabel("u1", ACTORS, t)).toBe("Ana Teste");
  });

  it("test_actor_label_names_events_without_actor_system", () => {
    expect(actorLabel(null, ACTORS, t)).toBe("Sistema");
  });

  it("test_actor_label_shows_id_of_unlisted_actor", () => {
    expect(actorLabel("u9", ACTORS, t)).toBe("Usuário u9");
  });
});
