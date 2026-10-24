import numpy as np

from agap.simulate.kidney import abnormal_screen, ckd_epi_2021


def test_reference_value_male():
    # 50-year-old male, Scr 1.0 mg/dL -> about 92 mL/min/1.73 m^2
    assert abs(ckd_epi_2021(1.0, 50, False) - 92) < 1.5


def test_female_lower_at_same_scr():
    # Same creatinine implies lower filtration in females (lower kappa)
    assert ckd_epi_2021(1.0, 40, True) < ckd_epi_2021(1.0, 40, False)


def test_monotonic_decreasing_in_creatinine():
    scr = np.linspace(0.4, 5.0, 50)
    egfr = ckd_epi_2021(scr, 55, False)
    assert np.all(np.diff(egfr) < 0)


def test_monotonic_decreasing_in_age():
    egfr = ckd_epi_2021(1.0, np.arange(18, 90), True)
    assert np.all(np.diff(egfr) < 0)


def test_abnormal_screen_rule():
    y = abnormal_screen([90, 55, 90, 59.9], [10, 10, 30, 29.9])
    assert y.tolist() == [0, 1, 1, 1]
