"""Unit tests for Whoop API v2 models.

Copyright (c) 2024 Felix Geilert
"""

from datetime import datetime, timezone
from uuid import UUID

from whoopy.models.models_v2 import (
    Cycle,
    CycleScore,
    Recovery,
    RecoveryScore,
    ScoreState,
    Sleep,
    SleepNeeded,
    SleepStageSummary,
    UserBasicProfile,
    UserBodyMeasurement,
    WorkoutScore,
    WorkoutV2,
    ZoneDurations,
)


class TestUserModels:
    """Test user-related models."""

    def test_user_basic_profile(self):
        """Test UserBasicProfile model."""
        profile = UserBasicProfile(user_id=12345, email="test@example.com", first_name="John", last_name="Doe")

        assert profile.user_id == 12345
        assert profile.email == "test@example.com"
        assert profile.first_name == "John"
        assert profile.last_name == "Doe"

    def test_user_body_measurement(self):
        """Test UserBodyMeasurement model."""
        measurement = UserBodyMeasurement(height_meter=1.80, weight_kilogram=75.5, max_heart_rate=190)

        assert measurement.height_meter == 1.80
        assert measurement.weight_kilogram == 75.5
        assert measurement.max_heart_rate == 190


class TestCycleModels:
    """Test cycle-related models."""

    def test_cycle_score(self):
        """Test CycleScore model with computed calories."""
        score = CycleScore(strain=12.5, kilojoule=2000.0, average_heart_rate=120, max_heart_rate=180)

        assert score.strain == 12.5
        assert score.kilojoule == 2000.0
        assert score.average_heart_rate == 120
        assert score.max_heart_rate == 180
        # Test computed property
        assert abs(score.calories - 478.011) < 0.01

    def test_cycle_complete(self):
        """Test Cycle model with complete data."""
        now = datetime.now(timezone.utc)
        cycle = Cycle(
            id=12345,
            user_id=67890,
            created_at=now,
            updated_at=now,
            start=now,
            end=now,
            timezone_offset="-05:00",
            score_state=ScoreState.SCORED,
            score=CycleScore(strain=10.0, kilojoule=1500.0, average_heart_rate=110, max_heart_rate=170),
        )

        assert cycle.id == 12345
        assert cycle.user_id == 67890
        assert cycle.is_complete is True
        assert cycle.duration_hours == 0.0
        assert cycle.score is not None
        assert cycle.score.strain == 10.0

    def test_cycle_ongoing(self):
        """Test ongoing cycle without end time."""
        now = datetime.now(timezone.utc)
        cycle = Cycle(
            id=12345,
            user_id=67890,
            created_at=now,
            updated_at=now,
            start=now,
            end=None,
            timezone_offset="-05:00",
            score_state=ScoreState.PENDING_SCORE,
        )

        assert cycle.is_complete is False
        assert cycle.duration_hours is None


class TestSleepModels:
    """Test sleep-related models."""

    def test_sleep_stage_summary(self):
        """Test SleepStageSummary with computed properties."""
        summary = SleepStageSummary(
            total_in_bed_time_milli=28800000,  # 8 hours
            total_awake_time_milli=1800000,  # 30 minutes
            total_no_data_time_milli=0,
            total_light_sleep_time_milli=14400000,  # 4 hours
            total_slow_wave_sleep_time_milli=7200000,  # 2 hours
            total_rem_sleep_time_milli=5400000,  # 1.5 hours
            sleep_cycle_count=4,
            disturbance_count=3,
        )

        # Test computed properties
        assert summary.total_sleep_time_milli == 27000000  # 7.5 hours
        assert abs(summary.sleep_efficiency_percentage - 93.75) < 0.01

    def test_sleep_needed(self):
        """Test SleepNeeded with computed total."""
        needed = SleepNeeded(
            baseline_milli=28800000,  # 8 hours
            need_from_sleep_debt_milli=3600000,  # 1 hour
            need_from_recent_strain_milli=1800000,  # 30 minutes
            need_from_recent_nap_milli=-1800000,  # -30 minutes
        )

        assert needed.total_need_milli == 32400000  # 9 hours

    def test_sleep_complete(self):
        """Test Sleep model with UUID."""
        sleep_id = UUID("12345678-1234-5678-1234-567812345678")
        now = datetime.now(timezone.utc)
        sleep = Sleep(
            id=sleep_id,
            v1_id=12345,
            user_id=67890,
            created_at=now,
            updated_at=now,
            start=now,
            end=now,
            timezone_offset="-05:00",
            nap=False,
            score_state=ScoreState.SCORED,
        )

        assert sleep.id == sleep_id
        assert sleep.v1_id == 12345
        assert sleep.nap is False
        assert sleep.duration_hours == 0.0


class TestRecoveryModels:
    """Test recovery-related models."""

    def test_recovery_score(self):
        """Test RecoveryScore model."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=75.5,
            resting_heart_rate=55.0,
            hrv_rmssd_milli=45.5,
            spo2_percentage=98.5,
            skin_temp_celsius=33.5,
        )

        assert score.user_calibrating is False
        assert score.recovery_score == 75.5
        assert score.resting_heart_rate == 55.0
        assert score.hrv_rmssd_milli == 45.5
        assert score.spo2_percentage == 98.5
        assert score.skin_temp_celsius == 33.5

    def test_recovery(self):
        """Test Recovery model."""
        sleep_id = UUID("12345678-1234-5678-1234-567812345678")
        now = datetime.now(timezone.utc)
        recovery = Recovery(
            cycle_id=12345,
            sleep_id=sleep_id,
            user_id=67890,
            created_at=now,
            updated_at=now,
            score_state=ScoreState.SCORED,
            score=RecoveryScore(
                user_calibrating=False, recovery_score=80.0, resting_heart_rate=60.0, hrv_rmssd_milli=50.0
            ),
        )

        assert recovery.cycle_id == 12345
        assert recovery.sleep_id == sleep_id
        assert recovery.score.recovery_score == 80.0


class TestWorkoutModels:
    """Test workout-related models."""

    def test_zone_durations(self):
        """Test ZoneDurations with computed properties."""
        zones = ZoneDurations(
            zone_zero_milli=300000,
            zone_one_milli=600000,
            zone_two_milli=900000,
            zone_three_milli=900000,
            zone_four_milli=600000,
            zone_five_milli=300000,
        )

        assert zones.total_duration_milli == 3600000  # 1 hour

        percentages = zones.to_dict_percentage()
        assert abs(percentages["zone_zero_percentage"] - 8.33) < 0.01
        assert abs(percentages["zone_one_percentage"] - 16.67) < 0.01
        assert abs(percentages["zone_two_percentage"] - 25.0) < 0.01
        assert abs(percentages["zone_three_percentage"] - 25.0) < 0.01
        assert abs(percentages["zone_four_percentage"] - 16.67) < 0.01
        assert abs(percentages["zone_five_percentage"] - 8.33) < 0.01

    def test_workout_score(self):
        """Test WorkoutScore with computed calories."""
        score = WorkoutScore(
            strain=8.5,
            average_heart_rate=140,
            max_heart_rate=180,
            kilojoule=1000.0,
            percent_recorded=98.5,
            distance_meter=5000.0,
            altitude_gain_meter=100.0,
            altitude_change_meter=20.0,
            zone_durations=ZoneDurations(
                zone_zero_milli=300000,
                zone_one_milli=600000,
                zone_two_milli=900000,
                zone_three_milli=900000,
                zone_four_milli=600000,
                zone_five_milli=300000,
            ),
        )

        assert score.strain == 8.5
        assert abs(score.calories - 239.005) < 0.01
        assert score.distance_meter == 5000.0

    def test_workout_v2(self):
        """Test WorkoutV2 model with UUID."""
        workout_id = UUID("87654321-4321-8765-4321-876543218765")
        now = datetime.now(timezone.utc)
        workout = WorkoutV2(
            id=workout_id,
            v1_id=54321,
            sport_id=1,
            user_id=67890,
            created_at=now,
            updated_at=now,
            start=now,
            end=now,
            timezone_offset="-05:00",
            sport_name="running",
            score_state=ScoreState.SCORED,
        )

        assert workout.id == workout_id
        assert workout.v1_id == 54321
        assert workout.sport_id == 1
        assert workout.sport_name == "running"
        assert workout.duration_hours == 0.0


class TestEnums:
    """Test enum values."""

    def test_score_state_enum(self):
        """Test ScoreState enum values."""
        assert ScoreState.SCORED == "SCORED"
        assert ScoreState.PENDING_SCORE == "PENDING_SCORE"
        assert ScoreState.UNSCORABLE == "UNSCORABLE"
