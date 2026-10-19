from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _widget(widgets, label):
    return next(widget for widget in widgets if widget.label == label)


def _requirements_page():
    app = AppTest.from_file(str(APP_PATH)).run()
    _widget(app.selectbox, "Navigate").set_value("Application Requirements")
    return app.run()


def test_permitted_region_field_is_conditional_and_exact_options_are_shown():
    app = _requirements_page()
    residency = _widget(app.radio, "Data Residency")
    assert list(residency.options) == ["On-site Only", "Specific Region Only", "No Restriction"]
    assert not any(widget.label == "Permitted Region" for widget in app.text_input)

    residency.set_value("Specific Region Only")
    app.run()
    assert any(widget.label == "Permitted Region" for widget in app.text_input)

    _widget(app.radio, "Data Residency").set_value("No Restriction")
    app.run()
    assert not any(widget.label == "Permitted Region" for widget in app.text_input)


def test_region_value_is_preserved_when_switching_residency_options():
    app = _requirements_page()
    _widget(app.radio, "Data Residency").set_value("Specific Region Only")
    app.run()
    _widget(app.text_input, "Permitted Region").set_value("India")
    app.run()

    _widget(app.radio, "Data Residency").set_value("On-site Only")
    app.run()
    assert not any(widget.label == "Permitted Region" for widget in app.text_input)

    _widget(app.radio, "Data Residency").set_value("Specific Region Only")
    app.run()
    region = _widget(app.text_input, "Permitted Region")
    assert region.value == "India"
    region.set_value("")
    app.run()

    _widget(app.radio, "Data Residency").set_value("No Restriction")
    app.run()
    _widget(app.radio, "Data Residency").set_value("Specific Region Only")
    app.run()
    assert _widget(app.text_input, "Permitted Region").value == ""
