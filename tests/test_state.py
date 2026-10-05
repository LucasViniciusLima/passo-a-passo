import pytest

from app.recorder.state import InvalidTransition, RecorderState, StateMachine


def test_fluxo_completo_e_tempo_sem_pausas():
    m = StateMachine()
    assert m.state is RecorderState.IDLE and not m.accepts_clicks
    m.go(RecorderState.RECORDING, now=0)
    assert m.accepts_clicks
    m.go(RecorderState.PAUSED, now=5)
    assert not m.accepts_clicks  # pausado: hook ativo, eventos descartados
    assert m.elapsed(now=100) == 5
    m.go(RecorderState.RECORDING, now=100)
    assert m.elapsed(now=103) == 8
    m.go(RecorderState.FINISHED, now=104)
    assert m.elapsed(now=999) == 9


def test_transicoes_invalidas():
    m = StateMachine()
    with pytest.raises(InvalidTransition):
        m.go(RecorderState.PAUSED, now=0)
    m.go(RecorderState.RECORDING, now=0)
    m.go(RecorderState.FINISHED, now=1)
    with pytest.raises(InvalidTransition):
        m.go(RecorderState.RECORDING, now=2)
