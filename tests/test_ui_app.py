"""Functional tests for the editor, driven through Streamlit's AppTest.

These actually execute app.py in a headless runtime and click things, so a
broken widget or a bad rerun shows up in CI rather than in front of a user.
"""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = "ogsfrac/ui/app.py"


def _app(timeout=90):
    at = AppTest.from_file(APP, default_timeout=timeout)
    at.run()
    return at


def test_app_starts_without_exceptions():
    at = _app()
    assert not at.exception
    assert len(at.tabs) == 7


def test_no_errors_on_a_fresh_case():
    at = _app()
    assert [e.value for e in at.error] == []


def test_add_fracture_button_updates_the_case():
    at = _app()
    assert at.session_state.case["fractures"] == []
    at.button(key="FormSubmitter:my_form-Add fracture") if False else None
    add = next(b for b in at.button if "Add fracture" in b.label)
    add.click().run()
    assert not at.exception
    assert len(at.session_state.case["fractures"]) == 1
    # and its medium was created automatically
    assert {m["id"] for m in at.session_state.case["materials"]} == {0, 1}


def test_switching_process_rebuilds_variables():
    at = _app()
    assert set(at.session_state.case["process_variables"]) == {"pressure"}
    at.radio[0].set_value(3).run()  # THERMO_RICHARDS_MECHANICS
    assert not at.exception
    assert set(at.session_state.case["process_variables"]) == {
        "temperature", "pressure", "displacement"
    }


def test_domain_edit_propagates():
    at = _app()
    xmin = at.number_input(key=None) if False else at.number_input[0]
    xmin.set_value(-500.0).run()
    assert not at.exception
    assert at.session_state.case["domain"]["xmin"] == -500.0


def test_validation_shows_in_the_sidebar():
    at = _app()
    msgs = [w.value for w in at.warning]
    assert any("no boundary conditions" in m for m in msgs)
