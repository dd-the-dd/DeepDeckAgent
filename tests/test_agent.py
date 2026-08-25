import pytest

from deepdeck_agent import Agent, Decision, Game, RandomAgent


def decision(kind: str, options: list[dict], choice: dict | None = None) -> Decision:
    raw = {"kind": kind, "options": options}
    if choice:
        raw["choice"] = choice
    return Decision("d1", "p1", raw, Game({"players": [{"id": "p1"}]}, "p1"))


@pytest.mark.asyncio
async def test_base_agent_dispatches_each_decision_to_its_named_method() -> None:
    class RecordingAgent(Agent):
        called = ""

        async def choose_priority(self, current):
            self.called = "priority"
            return current.actions[1]

    agent = RecordingAgent()
    response = await agent.make_decision(
        decision(
            "priority",
            [
                {"id": "pass", "kind": "passPriority"},
                {"id": "cast", "kind": "castSpell"},
            ],
        )
    )
    assert agent.called == "priority"
    assert response.action_id == "cast"


@pytest.mark.asyncio
async def test_random_baseline_is_reproducible_and_always_legal() -> None:
    current = decision(
        "priority",
        [
            {"id": "one", "kind": "castSpell"},
            {"id": "two", "kind": "passPriority"},
            {"id": "three", "kind": "playLand"},
        ],
    )
    left = RandomAgent(seed=7)
    right = RandomAgent(seed=7)
    left_ids = [(await left.make_decision(current)).action_id for _ in range(6)]
    right_ids = [(await right.make_decision(current)).action_id for _ in range(6)]
    assert left_ids == right_ids
    assert set(left_ids) <= {"one", "two", "three"}
    assert len(set(left_ids)) > 1


@pytest.mark.asyncio
async def test_base_and_random_agents_answer_card_choices() -> None:
    current = decision(
        "resolutionChoice",
        [{"id": "choose", "kind": "chooseResolution"}],
        {
            "kind": "cardSelection",
            "decisionId": "cards",
            "candidateCardInstanceIds": ["a", "b", "c"],
            "minimum": 2,
            "maximum": 2,
        },
    )
    assert (await Agent().make_decision(current)).card_instance_ids == ["a", "b"]
    assert set((await RandomAgent(seed=4).make_decision(current)).card_instance_ids or []) <= {
        "a",
        "b",
        "c",
    }
