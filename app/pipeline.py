# Pipeline orchestrator - chains all AI stages
# Stub: will be completed in Phase 9 (Step 9.5)
# See CLAUDE.PROJECT.MD for pipeline architecture:
#   preprocess -> guard -> rag -> generate (agent loop) -> postprocess


async def run_pipeline(raw_input: str, context: dict) -> dict:
    """Execute the full AI pipeline on raw input.

    Args:
        raw_input: Raw text from SMS or dashboard chat.
        context: Dict with channel, from_phone, team_id, etc.

    Returns:
        Dict with response text, actions taken, and metadata.
    """
    raise NotImplementedError("Pipeline stages not yet wired - see Phase 9")
