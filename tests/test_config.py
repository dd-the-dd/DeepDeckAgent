from deepdeck_agent import AgentConfig, DeckPolicy, PlaySpeed, ServerTarget


def test_beginner_config_projects_the_current_engine_manifest() -> None:
    config = AgentConfig(
        agent_id="com.example.agent",
        name="Example",
        version="1.0.0",
        author="Example author",
        formats=("legacy", "commander"),
        decks=DeckPolicy.one_of("deck-a", "deck-b", "deck-a"),
        speeds=(PlaySpeed.MS_100, PlaySpeed.SECOND_1, PlaySpeed.SECONDS_10),
    )

    payload = config.manifest().model_dump(by_alias=True, mode="json")
    assert payload["compatibility"]["gameModes"] == ["legacy", "commander"]
    assert payload["compatibility"]["decks"] == {
        "selection": "allow-list",
        "deckIds": ["deck-a", "deck-b"],
    }
    assert payload["compatibility"]["timeControls"] == [
        "realtime",
        "standard",
        "extended",
    ]


def test_local_target_derives_websocket_and_keeps_secrets_out_of_config_defaults(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MTG_ENGINE_API_KEY", raising=False)
    target = ServerTarget.local("http://127.0.0.1:8787/")
    assert target.agent_url == "ws://127.0.0.1:8787/ai/agents/ws"
    assert target.engine_api_key is None


def test_runner_controller_id_is_stable_before_connection() -> None:
    from deepdeck_agent import Agent, AgentRunner

    config = AgentConfig(
        agent_id="org.example.agent",
        name="Example",
        version="1.0.0",
        author="Tester",
        formats=("legacy",),
    )
    runner = AgentRunner(Agent(), config, ServerTarget.local())
    assert runner.controller_id == "agent:org.example.agent"
