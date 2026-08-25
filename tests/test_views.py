from deepdeck_agent import Decision, EventReader, Game


def card(instance_id: str, name: str, type_line: str, *, controller: str = "p1") -> dict:
    return {
        "instanceId": instance_id,
        "owner": controller,
        "controller": controller,
        "definition": {
            "id": name.lower(),
            "name": name,
            "typeLine": type_line,
            "manaCost": "",
            "power": "2" if "Creature" in type_line else None,
            "toughness": "2" if "Creature" in type_line else None,
            "rules": [],
        },
    }


def observation() -> dict:
    return {
        "turnNumber": 2,
        "activePlayer": 0,
        "step": "precombatMain",
        "players": [
            {
                "id": "p1",
                "name": "Me",
                "life": 40,
                "hand": [card("alexios-hand", "Alexios, Deimos of Kosmos", "Legendary Creature")],
                "battlefield": [card("mountain", "Mountain", "Basic Land")],
                "library": [],
                "graveyard": [],
                "exile": [],
                "sideboard": [],
                "commandZone": [],
                "manaPool": [],
            },
            {
                "id": "p2",
                "name": "Opponent",
                "life": 12,
                "hand": [],
                "battlefield": [card("bear", "Bear", "Creature", controller="p2")],
                "library": [],
                "graveyard": [],
                "exile": [],
                "sideboard": [],
                "commandZone": [],
                "manaPool": [],
            },
        ],
        "stack": [],
        "events": [
            {"sequence": 1, "turnNumber": 1, "step": "draw", "kind": "cardDrawn", "detail": {}},
            {
                "sequence": 2,
                "turnNumber": 2,
                "step": "precombatMain",
                "kind": "landPlayed",
                "detail": {},
            },
        ],
    }


def test_game_and_decision_helpers_find_sources_and_targets() -> None:
    game = Game(observation(), "p1")
    decision = Decision(
        "decision-1",
        "p1",
        {
            "kind": "priority",
            "options": [
                {"id": "pass", "kind": "passPriority", "playerId": "p1", "label": "Pass"},
                {
                    "id": "cast-alexios",
                    "kind": "castSpell",
                    "playerId": "p1",
                    "label": "Cast Alexios",
                    "cardInstanceId": "alexios-hand",
                    "paymentSources": ["mountain"],
                    "targets": {},
                },
                {
                    "id": "remove-bear",
                    "kind": "castSpell",
                    "playerId": "p1",
                    "label": "Remove Bear",
                    "targets": {"target": {"kind": "permanent", "instanceId": "bear"}},
                },
            ],
        },
        game,
    )

    cast = decision.actions_of("castSpell")[0]
    assert decision.card_for(cast).name == "Alexios, Deimos of Kosmos"
    assert decision.target_permanents(decision.actions[-1])[0].name == "Bear"
    assert game.me.available_mana_count == 1


def test_event_reader_returns_embedded_events_once() -> None:
    reader = EventReader()
    first = reader.read("game-1", observation())
    second = reader.read("game-1", observation())
    assert [event.kind for event in first] == ["cardDrawn", "landPlayed"]
    assert second == []
