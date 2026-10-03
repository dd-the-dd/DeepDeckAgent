# Agent manifest contract

`AgentManifest` models `agent-manifest/v1`, the registration metadata sent to the
authoritative Rust engine. Protocol keys serialize in camel case. Always use
`model_dump(by_alias=True, mode="json", exclude_none=True)` when preparing a wire payload.

The SDK accepts the complete cross-repository contract, including `agentType`, author
`orcid` values, and scientific `publications`. `agentType` remains available for platform
classification even though older Engine builds ignore that field. Optional publication
metadata follows the Engine representation: title, authors, venue, year, DOI, arXiv ID,
URL, and citation.

All protocol models use Pydantic's `extra="forbid"` policy, including nested authors and
publications. An unknown field therefore raises `ValidationError` instead of being silently
discarded. Extending the wire contract requires updating the model and its compatibility
fixture before agents can emit the new field.

The maximal serialization used for compatibility testing lives at
[`tests/fixtures/agent_manifest_v1_maximal.json`](../tests/fixtures/agent_manifest_v1_maximal.json).
DeepDeckLearner carries the same fixture while its legacy protocol copy remains in place.
