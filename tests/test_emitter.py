"""Tests for ``bridge/emitter.py`` — SingleValue line formatting.

These lock down the ASCII-safe conversions (Ω→Ohm, µ→u), the base-unit
``si_value`` scaling, the letters-only mode tokens, and the overload/ASCII
trailing-space behaviour that TestController relies on.
"""
from bridge.emitter import Emitter


def test_numeric_default_format(make_reading):
    # Default template "{mode} {si_value}" with 607.80 V on DCV.
    assert Emitter().format_reading(make_reading()) == "DCV 607.80"


def test_negative(make_reading):
    r = make_reading(is_negative=True)
    assert Emitter().format_reading(r) == "DCV -607.80"


def test_si_scaling_mv_to_base_units(make_reading):
    # 45.30 mV -> base-unit 0.04530 (TestController re-applies the prefix).
    r = make_reading(
        function_name="DCmV", unit="V", mantissa=4530,
        decimal_pos=2, display_digit_count=4, prefix="m",
    )
    assert Emitter().format_reading(r) == "DCmV 0.04530"


def test_ohm_is_ascii_safe(make_reading):
    # Ω is not in ISO-8859-1; TestController would see "?" without the map.
    r = make_reading(
        function_name="Resistance", unit="Ω", mantissa=1025,
        decimal_pos=2, display_digit_count=4, prefix="k",
    )
    e = Emitter(line_format="{value} {unit}")
    assert e.format_reading(r) == "10.25 kOhm"


def test_micro_prefix_is_ascii_safe(make_reading):
    r = make_reading(
        function_name="DCµA", unit="A", mantissa=450,
        decimal_pos=1, display_digit_count=3, prefix="µ",
    )
    e = Emitter(line_format="{value} {unit}")
    assert e.format_reading(r) == "4.50 uA"


def test_overload_has_mode_and_trailing_space(make_reading):
    # Overload is emitted as "{mode} OL " (trailing space, never bare "OL"):
    # TC's valueText handler reads one char past the token, so a last-token
    # "OL" drops the socket; a trailing unit pollutes the multi-mode token.
    assert Emitter().format_reading(make_reading(is_overload=True)) == "DCV OL "


def test_overload_single_mode_has_no_mode(make_reading):
    # Template without {mode}: overload is "OL " (value + space).
    e = Emitter(line_format="{value} {unit}")
    assert e.format_reading(make_reading(is_overload=True)) == "OL "


def test_temperature_overload_shows_dashes(make_reading):
    # Display accommodation (NOT protocol behavior): the meter's LCD shows
    # "----" for a temperature overload even though the SDK reports plain "OL"
    # (the protocol only sends the OL flag — see captures cap-010).
    assert Emitter().format_reading(
        make_reading(function_name="T1", unit="°C", is_overload=True)
    ) == "TEMPONEC ---- "
    assert Emitter().format_reading(
        make_reading(function_name="T1", unit="°F", is_overload=True)
    ) == "TEMPONEF ---- "
    # Non-temperature overloads still emit "OL".
    assert Emitter().format_reading(
        make_reading(function_name="Resistance", is_overload=True)
    ) == "RES OL "


def test_ascii_has_mode_and_trailing_space(make_reading):
    r = make_reading(is_ascii=True, ascii_text="Auto")
    assert Emitter().format_reading(r) == "DCV Auto "


def test_gap_line(make_reading):
    # Data-gap keep-alive: dedicated "?" token (not a real meter ASCII output)
    # with a trailing space so TestController shows "?" instead of dropping the
    # socket on a silence gap.
    assert Emitter().gap_line() == "? "
    # Multi-mode: the last reading's mode token keeps a column to show "?" in.
    assert Emitter().gap_line(make_reading()) == "DCV ? "
    # Template without {mode}: no mode token.
    e = Emitter(line_format="{value} {unit}")
    assert e.gap_line(make_reading()) == "? "


def test_mode_tokens(make_reading):
    e = Emitter()
    assert e._mode_text(make_reading(function_name="DC+ACV")) == "DCACV"
    assert e._mode_text(make_reading(function_name="T1", unit="°C")) == "TEMPONEC"
    assert e._mode_text(make_reading(function_name="T1", unit="°F")) == "TEMPONEF"
    assert e._mode_text(make_reading(function_name="T2", unit="°F")) == "TEMPTWOF"
    assert e._mode_text(make_reading(function_name="T1-T2", unit="°F")) == "TEMPDIFFF"
    assert e._mode_text(make_reading(function_name="Capacitance")) == "CAP"
    # Hz functions follow the Hz-suffix convention (must match the #value
    # selectors in testcontroller/BrymenBM78xBT.txt: VFDHz / LINEHz).
    assert e._mode_text(make_reading(function_name="Hz of VFD-ACV")) == "VFDHz"
    assert e._mode_text(make_reading(function_name="Hz of Line Signal")) == "LINEHz"
    # Unknown function -> letters-only fallback from the canonical name.
    assert e._mode_text(make_reading(function_name="Mystery Mode")) == "MysteryMode"


def test_fahrenheit_numeric(make_reading):
    # A Fahrenheit reading emits the °F mode token so TestController selects
    # the F #value row (the value itself is already in °F — no scaling).
    r = make_reading(
        function_name="T1", unit="°F", mantissa=7700,
        decimal_pos=2, display_digit_count=4,
    )
    assert Emitter().format_reading(r) == "TEMPONEF 77.00"


def test_malformed_template_falls_back_to_plain(make_reading):
    e = Emitter(line_format="{bogus}")
    assert e.format_reading(make_reading()) == "607.80 V"


def test_format_frame_skips_none_readings(make_reading):
    from brymenble.parsers import StreamFrame
    frame = StreamFrame(
        info=None, readings=[make_reading(), None, make_reading(is_overload=True)]
    )
    assert Emitter().format_frame(frame) == ["DCV 607.80", "DCV OL "]
