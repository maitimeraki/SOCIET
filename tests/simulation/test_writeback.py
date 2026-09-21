"""Tests for WriteBackService."""
import pytest
from unittest.mock import MagicMock

from src.simulation.writeback import WriteBackService
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.communication_graph import CommPair


def _make_turn(agent_id, agent_name, content='test', stance='POS', confidence=0.8):
    return AgentTurn(agent_id=agent_id, agent_name=agent_name, content=content, stance=stance, confidence=confidence)


def _make_round(round_num, turns, pairs):
    return RoundResult(round_num=round_num, turns=turns, pairs=pairs)


class FakeSession:
    """Plain async context manager with a tracked run() coroutine."""
    def __init__(self, call_record=None, run_side_effect=None):
        self._calls = call_record or []
        self._run_se = run_side_effect

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def run(self, query, **kwargs):
        if self._run_se:
            raise self._run_se
        self._calls.append((query, kwargs))
        return None


class TestWriteBackServiceParams:
    """Verify UNWIND query is constructed with correct params and batched."""

    @pytest.mark.asyncio
    async def test_unwind_query_params(self):
        fake = FakeSession()
        mock_driver = MagicMock()
        mock_driver.session.return_value = fake

        svc = WriteBackService(mock_driver, 'testdb')
        turns = [
            _make_turn('a1', 'Alice', 'Alice says hi', stance='POS'),
            _make_turn('b1', 'Bob', 'Bob says hi', stance='NEG'),
        ]
        pairs = [CommPair(agent_a='a1', agent_b='b1')]
        rounds = [_make_round(1, turns, pairs)]

        await svc.persist_round_turns(rounds, 'ds_001')

        mock_driver.session.assert_called_once_with(database='testdb')
        assert len(fake._calls) == 1
        query, params = fake._calls[0]

        assert '$turns' in query
        assert '$dataset_id' in query
        assert params['dataset_id'] == 'ds_001'

        turn_list = params['turns']
        assert len(turn_list) == 2

        alice_edge = next(t for t in turn_list if t['speaker_name'] == 'Alice')
        assert alice_edge['round_no'] == 1
        assert alice_edge['summary'] == 'Alice says hi'
        assert alice_edge['stance'] == 'POS'
        assert alice_edge['target_name'] == 'Bob'

        bob_edge = next(t for t in turn_list if t['speaker_name'] == 'Bob')
        assert bob_edge['round_no'] == 1
        assert bob_edge['summary'] == 'Bob says hi'
        assert bob_edge['stance'] == 'NEG'
        assert bob_edge['target_name'] == 'Alice'

    @pytest.mark.asyncio
    async def test_one_query_per_round(self):
        sessions = []
        mock_driver = MagicMock()
        # Capture each created session for later inspection
        mock_driver.session.side_effect = lambda **kw: (sessions.append(FakeSession()) or sessions[-1])

        svc = WriteBackService(mock_driver, 'testdb')
        turns1 = [_make_turn('a1', 'Alice', 'r1'), _make_turn('b1', 'Bob', 'r1')]
        turns2 = [_make_turn('a1', 'Alice', 'r2'), _make_turn('b1', 'Bob', 'r2')]
        rounds = [
            _make_round(1, turns1, [CommPair(agent_a='a1', agent_b='b1')]),
            _make_round(2, turns2, [CommPair(agent_a='a1', agent_b='b1')]),
        ]

        await svc.persist_round_turns(rounds, 'ds_001')

        # two sessions were opened, each received one run() call
        assert len(sessions) == 2
        assert all(s._calls for s in sessions)

    @pytest.mark.asyncio
    async def test_resolves_target_name_from_turns(self):
        sessions = []
        mock_driver = MagicMock()
        mock_driver.session.side_effect = lambda **kw: (sessions.append(FakeSession()) or sessions[-1])

        svc = WriteBackService(mock_driver, 'db')
        turns = [
            _make_turn('x', 'Charlie', 'charlie content'),
            _make_turn('y', 'Dana', 'dana content'),
        ]
        rounds = [
            _make_round(1, turns, [CommPair(agent_a='x', agent_b='y')]),
            _make_round(2, turns, [CommPair(agent_a='y', agent_b='x')]),
        ]

        await svc.persist_round_turns(rounds, 'ds')

        all_turns = []
        for s in sessions:
            query, params = s._calls[0]
            all_turns.extend(params['turns'])

        assert len(all_turns) == 4
        assert {t['speaker_name'] for t in all_turns} == {'Charlie', 'Dana'}
        assert {t['target_name'] for t in all_turns} == {'Charlie', 'Dana'}

    @pytest.mark.asyncio
    async def test_self_reaction_skipped(self):
        fake = FakeSession()
        mock_driver = MagicMock()
        mock_driver.session.return_value = fake

        svc = WriteBackService(mock_driver, 'db')
        turns = [_make_turn('z', 'Zara', 'z self-talks')]
        rounds = [_make_round(1, turns, [CommPair(agent_a='z', agent_b='z')])]

        await svc.persist_round_turns(rounds, 'ds')

        # no run() called because turn_data is empty (self-reaction skipped)
        assert len(fake._calls) == 0


class TestErrorIsolation:
    """Failure in one turn/round does not abort others."""

    @pytest.mark.asyncio
    async def test_failure_in_one_round_is_silent(self):
        fake = FakeSession(run_side_effect=RuntimeError('connection lost'))
        mock_driver = MagicMock()
        mock_driver.session.return_value = fake

        svc = WriteBackService(mock_driver, 'db')
        turns = [_make_turn('a', 'A', 'a'), _make_turn('b', 'B', 'b')]
        rounds = [_make_round(1, turns, [CommPair(agent_a='a', agent_b='b')])]

        # Must not raise
        await svc.persist_round_turns(rounds, 'ds')

    @pytest.mark.asyncio
    async def test_failure_in_one_round_does_not_abort_others(self):
        # Round 1: ok, Round 2: fails, Round 3: ok
        sessions = []
        call_count = [0]

        def factory(**kw):
            s = FakeSession()
            sessions.append(s)
            call_count[0] += 1
            if call_count[0] == 2:
                s._run_se = RuntimeError('db error')
            return s

        mock_driver = MagicMock()
        mock_driver.session.side_effect = factory

        svc = WriteBackService(mock_driver, 'db')
        turns = [_make_turn('a', 'A', 'a'), _make_turn('b', 'B', 'b')]
        rounds = [
            _make_round(1, turns, [CommPair(agent_a='a', agent_b='b')]),
            _make_round(2, turns, [CommPair(agent_a='a', agent_b='b')]),
            _make_round(3, turns, [CommPair(agent_a='a', agent_b='b')]),
        ]

        await svc.persist_round_turns(rounds, 'ds')

        # Rounds 1 and 3 succeeded (run() was called each time)
        successful = [s for s in sessions if s._calls]
        assert len(successful) == 2

    @pytest.mark.asyncio
    async def test_empty_rounds_list_noop(self):
        mock_driver = MagicMock()
        svc = WriteBackService(mock_driver, 'db')
        await svc.persist_round_turns([], 'ds')
        mock_driver.session.assert_not_called()


class TestResolveTargetName:
    """Unit tests for _resolve_target_name."""

    def test_resolves_existing(self):
        turns = [_make_turn('id1', 'Alice'), _make_turn('id2', 'Bob')]
        result = WriteBackService._resolve_target_name('id2', turns)
        assert result == 'Bob'

    def test_missing_id_returns_none(self):
        turns = [_make_turn('id1', 'Alice')]
        result = WriteBackService._resolve_target_name('unknown', turns)
        assert result is None

    def test_empty_turns_returns_none(self):
        result = WriteBackService._resolve_target_name('any', [])
        assert result is None
