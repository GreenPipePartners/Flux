import json
import math

from flux_sim.value_profile import ProfileSample, ValueProfile, fit_value_profile


def test_second_order_profile_fits_and_evaluates_quadratic_samples():
    profile = fit_value_profile((x, (2.0 * x * x) + (3.0 * x) + 4.0) for x in range(-2, 4))

    assert profile.kind == "polynomial2"
    assert profile.source == "fit"
    assert math.isclose(profile.evaluate(5.0), 69.0)


def test_second_order_profile_uses_least_squares_for_noisy_samples():
    samples = (
        ProfileSample(0.0, 1.0),
        ProfileSample(1.0, 2.0),
        ProfileSample(2.0, 5.0),
        ProfileSample(3.0, 10.2),
        ProfileSample(4.0, 17.0),
    )

    profile = ValueProfile.fit_second_order(samples)

    assert profile.kind == "polynomial2"
    assert math.isclose(profile.evaluate(5.0), 26.0, abs_tol=0.5)


def test_profile_falls_back_to_sine_when_polynomial_fit_is_not_possible():
    profile = fit_value_profile([(1.0, 10.0), (1.0, 12.0), (1.0, 14.0)])

    assert profile.kind == "sine"
    assert profile.source == "fallback"
    assert profile.baseline == 12.0
    assert profile.evaluate(0.0) == 12.0


def test_profile_round_trips_through_json_serializable_dict():
    profile = ValueProfile(kind="sine", baseline=10.0, amplitude=0.0, period=30.0, phase=0.5)

    payload = json.loads(json.dumps(profile.to_dict()))
    restored = ValueProfile.from_dict(payload)

    assert restored == profile
    assert math.isclose(restored.evaluate(15.0), profile.evaluate(15.0))


def test_profile_metadata_shape_fits_field_tag_config_or_mode_config():
    profile = fit_value_profile([(0.0, 3.0), (1.0, 6.0), (2.0, 11.0)])
    metadata = profile.to_metadata()

    assert set(metadata) == {"value_profile"}
    assert ValueProfile.from_metadata(metadata) == profile
    assert json.loads(json.dumps(metadata))["value_profile"]["kind"] == "polynomial2"
