"""Integration tests: round → VerdictSynthesizer → WriteBackService flow."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.simulation.verdict import VerdictSynthesizer
from src.simulation.writeback import WriteBackService
from src.simulation.pair_turn import RoundResult, AgentTurn, CommPair
from src.simulation.agent_node import Stance


def _make_turn(agent_id: str, agent_name: str, content: str, stance: str, confidence: float) -> AgentTurn:
    return AgentTurn(
        agent_id=agent_id,
        agent_name=agent_name,
        content=content,
        stance=stance,
        confidence=confidence,
        references=["EntityA", "EntityB"],
    )


def _make_pair(a_id: str, b_id: str) -> CommPair:
    return CommPair(agent_a=a_id, agent_b=b_id)


class TestVerdictSynthesizerFromRound:
    """test_verdict_synthesizer_from_round — fixture round of 5 turns flows through VerdictSynthesizer."""

    def test_produces_debate_verdict_with_cluster_details(self):
        # 5 turns: 3 POSITIVE, 2 NEGATIVE
        turns = [
            _make_turn("a1", "Alice", "AI will help humanity", "POSITIVE", 0.9),
            _make_turn("a2", "Bob", "AI poses real risks", "NEGATIVE", 0.8),
            _make_turn("a3", "Carol", "I support AI development", "POSITIVE", 0.85),
            _make_turn("a4", "Dave", "We should be cautious about AI", "NEGATIVE", 0.75),
            _make_turn("a5", "Eve", "AI has great potential", "POSITIVE", 0.9),
        ]
        pairs = [
            _make_pair("a1", "a2"),
            _make_pair("a3", "a4"),
        ]
        round_result = RoundResult(round_num=1, turns=turns, pairs=pairs)

        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(rounds=[round_result], profiles=[])

        assert verdict.overall_stance is not None
        assert isinstance(verdict.overall_stance, Stance)
        assert 0.0 <= verdict.confidence_score <= 1.0
        assert len(verdict.cluster_details) > 0

        # POSITIVE cluster should dominate (3 turns vs 2)
        assert Stance.POSITIVE in verdict.cluster_details
        assert verdict.cluster_details[Stance.POSITIVE].count == 3

        # NEGATIVE cluster should exist
        assert Stance.NEGATIVE in verdict.cluster_details
        assert verdict.cluster_details[Stance.NEGATIVE].count == 2

        assert verdict.rounds_executed == 1
        assert verdict.summary != ""

    def test_empty_rounds_returns_neutral_verdict(self):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(rounds=[], profiles=[])

        assert verdict.overall_stance == Stance.NEUTRAL
        assert verdict.confidence_score == 0.0
        assert verdict.cluster_details == {}


class TestWriteBackPersistsRound:
    """test_writeback_persists_round — mocked driver verifies session.run is called."""

    @pytest.mark.asyncio
    async def test_persist_round_turns_calls_session_run(self):
        # Build mock session / driver chain
        mock_result = AsyncMock()
        mock_result.data = AsyncMock(return_value=[])  # consumed by async with
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_driver = MagicMock()
        mock_driver.session = MagicMock(return_value=mock_session)

        turns = [
            _make_turn("a1", "Alice", "AI is great", "POSITIVE", 0.9),
            _make_turn("a2", "Bob", "AI is risky", "NEGATIVE", 0.8),
        ]
        pairs = [_make_pair("a1", "a2")]
        round_result = RoundResult(round_num=1, turns=turns, pairs=pairs)

        service = WriteBackService(mock_driver, "neo4j")
        await service.persist_round_turns(rounds=[round_result], dataset_id="test-ds-42")

        # session() called with the configured database name
        mock_driver.session.assert_called_once_with(database="neo4j")

        # run() called once for the single round
        mock_session.run.assert_called_once()

        # dataset_id passed through
        call_kwargs = mock_session.run.call_args.kwargs
        assert call_kwargs.get("dataset_id") == "test-ds-42"
        assert "turns" in call_kwargs

    @pytest.mark.asyncio
    async def test_persist_multiple_rounds_calls_run_per_round(self):
        mock_result = AsyncMock()
        mock_result.data = AsyncMock(return_value=[])
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_driver = MagicMock()
        mock_driver.session = MagicMock(return_value=mock_session)

        round1 = RoundResult(
            round_num=1,
            turns=[
                _make_turn("a1", "Alice", "AI helps", "POSITIVE", 0.9),
                _make_turn("a2", "Bob", "AI helps too", "POSITIVE", 0.8),
            ],
            pairs=[_make_pair("a1", "a2")],
        )
        round2 = RoundResult(
            round_num=2,
            turns=[
                _make_turn("a1", "Alice", "AI still helps", "POSITIVE", 0.85),
                _make_turn("a2", "Bob", "AI now seems harmful", "NEGATIVE", 0.7),
            ],
            pairs=[_make_pair("a1", "a2")],
        )

        service = WriteBackService(mock_driver, "neo4j")
        await service.persist_round_turns(rounds=[round1, round2], dataset_id="multi-round")

        assert mock_session.run.call_count == 2
