"""Tests for ``bridge/emitter.py`` — SingleValue line formatting.

These lock down the ASCII-safe conversions (Ω→Ohm, µ→u), the base-unit
``si_value`` scaling, the letters-only mode tokens, and the overload/ASCII
bare-text behaviour that TestController relies on.
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


def test_overload_is_bare_text(make_reading):
    # Overload must be exactly "OL" (matched by TestController #valueText).
    assert Emitter().format_reading(make_reading(is_overload=True)) == "OL"


def test_ascii_is_bare_text(make_reading):
    r = make_reading(is_ascii=True, ascii_text="Auto")
    assert Emitter().format_reading(r) == "Auto"


def test_mode_tokens(make_reading):
    e = Emitter()
    assert e._mode_text(make_reading(function_name="DC+ACV")) == "DCACV"
    assert e._mode_text(make_reading(function_name="T1")) == "TC"
    assert e._mode_text(make_reading(function_name="Capacitance")) == "CAP"
    # Unknown function -> letters-only fallback from the canonical name.
    assert e._mode_text(make_reading(function_name="Mystery Mode")) == "MysteryMode"


def test_malformed_template_falls_back_to_plain(make_reading):
    e = Emitter(line_format="{bogus}")
    assert e.format_reading(make_reading()) == "607.80 V"


def test_format_frame_skips_none_readings(make_reading):
    from brymen.parsers import StreamFrame
    frame = StreamFrame(
        info=None, readings=[make_reading(), None, make_reading(is_overload=True)]
    )
    assert Emitter().format_frame(frame) == ["DCV 607.80", "OL"]
