"""Available weather is useful without a baseline and never becomes a risk score."""
import json
import pandas as pd
import pytest
from agap.climate.available import weather_inputs, weather_windows, snapshot_weather, load_weather_preview


def daily():
    dates = pd.date_range('2020-12-01', '2021-02-01')
    return pd.DataFrame(dict(era5_cell='14.2,121.2', local_date=dates, tmean_c=26., tmax_c=31.,
                             precip_mm=2., temperature_hours=24, precipitation_hours=24))


def test_preceding_windows_exclude_cutoff_and_need_no_baseline():
    observations = daily()
    observations.loc[observations.local_date.eq('2021-01-15'), ['tmean_c', 'tmax_c', 'precip_mm']] = 1000.
    result = weather_windows(observations, '2021-01-01', '2021-01-31')
    row = result.set_index('cutoff').loc['2021-01-15']
    assert row.complete_7d and row.complete_30d
    assert row.tmean_7d_c == 26. and row.tmax_30d_c == 31.
    assert row.rainfall_7d_mm == 14. and row.rainfall_30d_mm == 60.
    assert 'hot_dry_score' not in result and 'temperature_anomaly_z' not in result


def test_incomplete_rain_is_not_zero_and_does_not_hide_valid_seven_days():
    observations = daily()
    observations.loc[observations.local_date.eq('2021-01-01'), 'precipitation_hours'] = 23
    row = weather_windows(observations, '2021-01-01', '2021-01-31').set_index('cutoff').loc['2021-01-15']
    assert row.complete_7d and not row.complete_30d
    assert pd.isna(row.rainfall_30d_mm) and row.rainfall_days_30d == 29
    assert row.tmean_30d_c == 26.


def test_weather_gaps_are_explicit_and_duplicate_days_are_rejected():
    observations = daily().loc[lambda d: ~d.local_date.eq('2021-01-14')]
    row = weather_windows(observations, '2021-01-01', '2021-01-31').set_index('cutoff').loc['2021-01-15']
    assert not row.complete_7d and pd.isna(row.tmean_7d_c)
    with pytest.raises(ValueError, match='Duplicate'):
        weather_windows(pd.concat([observations, observations.iloc[:1]]), '2021-01-01', '2021-01-31')


def test_preview_inputs_are_required_and_snapshotted(tmp_path):
    cfg = dict(weather_preview=dict(enabled=True))
    with pytest.raises(FileNotFoundError, match='prepare-weather'):
        weather_inputs(cfg, tmp_path)
    folder = tmp_path / 'data/processed/weather/laguna'
    folder.mkdir(parents=True)
    observations = daily()
    observations.to_parquet(folder / 'daily.parquet', index=False)
    weather_windows(observations, '2021-01-01', '2021-01-31').to_parquet(folder / 'windows.parquet', index=False)
    (folder / 'metadata.json').write_text(json.dumps(dict(model_use=False, baseline_available=False)))
    run = tmp_path / 'run'
    run.mkdir()
    snapshot_weather(cfg, tmp_path, run)
    assert len(weather_inputs(cfg, tmp_path)) == 3
    (folder / 'metadata.json').write_text('{}')
    loaded = load_weather_preview(run)
    assert loaded['metadata']['model_use'] is False
    assert len(loaded['daily']) == len(observations)
    assert load_weather_preview(tmp_path) is None
