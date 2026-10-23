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


def test_public_target_derives_runner_url_and_reads_the_agent_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPDECK_API_KEY", "ddl_agent_example")
    monkeypatch.delenv("DEEPDECK_AGENT_URL", raising=False)
    target = ServerTarget.deepdeckleague(platform_url="https://staging.deepdeckleague.com/api/v1/")
    assert target.agent_url == "wss://staging.deepdeckleague.com/api/v1/agents/connect"
    assert target.account_token == "ddl_agent_example"


def test_public_target_loads_agent_key_from_dotenv(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPDECK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPDECK_ACCESS_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "DEEPDECK_API_KEY=ddl_agent_from_dotenv\n",
        encoding="utf-8",
    )

    target = ServerTarget.deepdeckleague()

    assert target.account_token == "ddl_agent_from_dotenv"


def test_public_target_defaults_to_production_not_staging(monkeypatch) -> None:
    monkeypatch.setattr("deepdeck_agent.config._load_working_directory_dotenv", lambda: None)
    monkeypatch.delenv("DEEPDECK_PLATFORM_URL", raising=False)
    monkeypatch.delenv("DEEPDECK_AGENT_URL", raising=False)
    target = ServerTarget.deepdeckleague(api_key="ddl_agent_isolated_test")
    assert target.platform_url == "https://www.deepdeckleague.com/api/v1"
    assert target.agent_url == "wss://www.deepdeckleague.com/api/v1/agents/connect"


def test_target_repr_does_not_expose_account_or_engine_credentials() -> None:
    target = ServerTarget(
        "deepdeckleague",
        "wss://example.test/agents",
        engine_api_key="engine_secret_not_for_logs",
        account_token="ddl_agent_secret_not_for_logs",
    )
    assert "engine_secret" not in repr(target)
    assert "ddl_agent_secret" not in repr(target)
