"""Data models for Whoop API v2 using Pydantic v2.

Copyright (c) 2024 Felix Geilert
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, computed_field


class ScoreState(str, Enum):
    """Enumeration of possible score states."""

    SCORED = "SCORED"
    PENDING_SCORE = "PENDING_SCORE"
    UNSCORABLE = "UNSCORABLE"


class BaseWhoopModel(BaseModel):
    """Base model with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )


# User Models
class UserBasicProfile(BaseWhoopModel):
    """Basic user profile information."""

    user_id: int
    email: str
    first_name: str
    last_name: str


class UserBodyMeasurement(BaseWhoopModel):
    """User body measurements."""

    height_meter: float
    weight_kilogram: float
    max_heart_rate: int


# Cycle Models
class CycleScore(BaseWhoopModel):
    """Cycle scoring metrics."""

    strain: float
    kilojoule: float
    average_heart_rate: int
    max_heart_rate: int

    @computed_field  # type: ignore[misc]
    def calories(self) -> float:
        """Convert kilojoules to calories."""
        return self.kilojoule / 4.184


class Cycle(BaseWhoopModel):
    """Physiological cycle data."""

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime | None = None
    timezone_offset: str
    score_state: ScoreState
    score: CycleScore | None = None

    @computed_field  # type: ignore[misc]
    def duration_hours(self) -> float | None:
        """Calculate cycle duration in hours."""
        if self.end:
            return (self.end - self.start).total_seconds() / 3600
        return None

    @computed_field  # type: ignore[misc]
    def is_complete(self) -> bool:
        """Check if the cycle is complete."""
        return self.end is not None


# Sleep Models
class SleepStageSummary(BaseWhoopModel):
    """Summary of sleep stages."""

    total_in_bed_time_milli: int
    total_awake_time_milli: int
    total_no_data_time_milli: int
    total_light_sleep_time_milli: int
    total_slow_wave_sleep_time_milli: int
    total_rem_sleep_time_milli: int
    sleep_cycle_count: int
    disturbance_count: int

    @computed_field  # type: ignore[misc]
    def total_sleep_time_milli(self) -> int:
        """Calculate total sleep time."""
        return (
            self.total_light_sleep_time_milli + self.total_slow_wave_sleep_time_milli + self.total_rem_sleep_time_milli
        )

    @computed_field  # type: ignore[misc]
    @property
    def sleep_efficiency_percentage(self) -> float:
        """Calculate sleep efficiency as percentage."""
        if self.total_in_bed_time_milli == 0:
            return 0.0
        # Access the method result directly
        total_sleep = self.total_sleep_time_milli
        return (total_sleep / self.total_in_bed_time_milli) * 100


class SleepNeeded(BaseWhoopModel):
    """Breakdown of sleep need."""

    baseline_milli: int
    need_from_sleep_debt_milli: int
    need_from_recent_strain_milli: int
    need_from_recent_nap_milli: int

    @computed_field  # type: ignore[misc]
    def total_need_milli(self) -> int:
        """Calculate total sleep need."""
        return (
            self.baseline_milli
            + self.need_from_sleep_debt_milli
            + self.need_from_recent_strain_milli
            + self.need_from_recent_nap_milli
        )


class SleepScore(BaseWhoopModel):
    """Sleep scoring metrics."""

    stage_summary: SleepStageSummary
    sleep_needed: SleepNeeded
    respiratory_rate: float | None = None
    sleep_performance_percentage: float | None = None
    sleep_consistency_percentage: float | None = None
    sleep_efficiency_percentage: float | None = None


class Sleep(BaseWhoopModel):
    """Sleep activity data."""

    id: UUID
    v1_id: int | None = Field(None, description="Legacy v1 ID")
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime
    timezone_offset: str
    nap: bool
    score_state: ScoreState
    score: SleepScore | None = None

    @computed_field  # type: ignore[misc]
    def duration_hours(self) -> float:
        """Calculate sleep duration in hours."""
        return (self.end - self.start).total_seconds() / 3600


# Recovery Models
class RecoveryScore(BaseWhoopModel):
    """Recovery scoring metrics."""

    user_calibrating: bool
    recovery_score: float
    resting_heart_rate: float
    hrv_rmssd_milli: float
    spo2_percentage: float | None = None
    skin_temp_celsius: float | None = None


class Recovery(BaseWhoopModel):
    """Recovery data."""

    cycle_id: int
    sleep_id: UUID
    user_id: int
    created_at: datetime
    updated_at: datetime
    score_state: ScoreState
    score: RecoveryScore | None = None


# Workout Models
class ZoneDurations(BaseWhoopModel):
    """Time spent in each heart rate zone."""

    zone_zero_milli: int
    zone_one_milli: int
    zone_two_milli: int
    zone_three_milli: int
    zone_four_milli: int
    zone_five_milli: int

    @computed_field  # type: ignore[misc]
    def total_duration_milli(self) -> int:
        """Calculate total workout duration."""
        return (
            self.zone_zero_milli
            + self.zone_one_milli
            + self.zone_two_milli
            + self.zone_three_milli
            + self.zone_four_milli
            + self.zone_five_milli
        )

    def to_dict_percentage(self) -> dict[str, float]:
        """Convert zone durations to percentages."""
        # Access the computed field value directly
        total = self.total_duration_milli
        if total == 0:
            return {f"zone_{i}_percentage": 0.0 for i in range(6)}

        return {
            "zone_zero_percentage": (self.zone_zero_milli / total) * 100,
            "zone_one_percentage": (self.zone_one_milli / total) * 100,
            "zone_two_percentage": (self.zone_two_milli / total) * 100,
            "zone_three_percentage": (self.zone_three_milli / total) * 100,
            "zone_four_percentage": (self.zone_four_milli / total) * 100,
            "zone_five_percentage": (self.zone_five_milli / total) * 100,
        }


class WorkoutScore(BaseWhoopModel):
    """Workout scoring metrics."""

    strain: float
    average_heart_rate: int
    max_heart_rate: int
    kilojoule: float
    percent_recorded: float
    distance_meter: float | None = None
    altitude_gain_meter: float | None = None
    altitude_change_meter: float | None = None
    zone_durations: ZoneDurations

    @computed_field  # type: ignore[misc]
    def calories(self) -> float:
        """Convert kilojoules to calories."""
        return self.kilojoule / 4.184


class WorkoutV2(BaseWhoopModel):
    """Workout activity data."""

    id: UUID
    v1_id: int | None = Field(None, description="Legacy v1 ID")
    sport_id: int | None = Field(None, description="Legacy sport ID")
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime
    timezone_offset: str
    sport_name: str
    score_state: ScoreState
    score: WorkoutScore | None = None

    @computed_field  # type: ignore[misc]
    def duration_hours(self) -> float:
        """Calculate workout duration in hours."""
        return (self.end - self.start).total_seconds() / 3600


# Collection Response Models
class PaginatedResponse(BaseWhoopModel):
    """Base class for paginated responses."""

    next_token: str | None = None

    @computed_field  # type: ignore[misc]
    def has_more(self) -> bool:
        """Check if there are more pages."""
        return self.next_token is not None


class PaginatedCycleResponse(PaginatedResponse):
    """Paginated response for cycles."""

    records: list[Cycle]


class PaginatedSleepResponse(PaginatedResponse):
    """Paginated response for sleep activities."""

    records: list[Sleep]


class RecoveryCollection(PaginatedResponse):
    """Paginated response for recoveries."""

    records: list[Recovery]


class WorkoutCollection(PaginatedResponse):
    """Paginated response for workouts."""

    records: list[WorkoutV2]


# Sport ID mapping (for backward compatibility)
SPORT_IDS = {
    1: "running",
    2: "cycling",
    3: "swimming",
    4: "strength_training",
    5: "yoga",
    6: "pilates",
    7: "spinning",
    8: "elliptical",
    9: "stairmaster",
    10: "rowing",
    11: "bootcamp",
    12: "boxing",
    13: "functional_fitness",
    14: "dance",
    15: "barre",
    16: "hiking",
    17: "golf",
    18: "tennis",
    19: "squash",
    20: "basketball",
    21: "soccer",
    22: "football",
    23: "hockey",
    24: "lacrosse",
    25: "rugby",
    26: "volleyball",
    27: "softball",
    28: "baseball",
    29: "skiing",
    30: "snowboarding",
    31: "crossfit",
    32: "rock_climbing",
    33: "surfing",
    34: "paddleboarding",
    35: "kayaking",
    36: "ice_bath",
    37: "meditation",
    38: "other",
    39: "walking",
    40: "water_polo",
    41: "wrestling",
    42: "martial_arts",
    43: "gymnastics",
    44: "track_field",
    45: "roller_skating",
    46: "ice_skating",
    47: "crew",
    48: "cricket",
    49: "pickleball",
    50: "inline_skating",
    51: "skateboarding",
    52: "badminton",
    53: "table_tennis",
    54: "climbing",
    55: "assault_bike",
    56: "parkour",
    57: "jiu_jitsu",
    58: "rotational",
    59: "jump_rope",
    60: "skiing_nordic",
    61: "manual_labor",
    62: "ultimate",
    63: "motocross",
    64: "stairs",
    65: "sailing",
    66: "hyrox",
    67: "canoeing",
    68: "field_hockey",
    69: "ruck",
    70: "triathlon",
    71: "paddle_tennis",
    72: "stretching",
    73: "gaelic_football",
    74: "hurling_camogie",
    75: "australian_football",
    76: "sauna",
    77: "calisthenics",
    78: "massage_rolling",
    79: "breathwork",
    80: "wheelchair_push",
    81: "waterski_wakeboard",
    82: "wind_kite_surfing",
    83: "bowling",
    84: "duathlon",
    85: "biathlon",
    86: "netball",
    87: "horseback_riding",
    88: "scuba_diving",
    89: "freediving",
    90: "boxing_bag",
    91: "tennis_paddle",
    92: "hunting",
    93: "fishing",
    94: "shooting",
    95: "archery",
    96: "rafting",
    97: "kickboxing",
    98: "muay_thai",
    99: "weightlifting",
    100: "powerlifting",
    101: "spartan",
    102: "tough_mudder",
    103: "flag_football",
    104: "racquetball",
    105: "fencing",
    106: "trampoline",
    107: "nordic_walking",
    108: "prehab_rehab",
    109: "sled",
    110: "tubing",
    111: "rodeo",
    112: "wrestling_entertainment",
}


# Helper functions for DataFrame conversion
def models_to_dataframe(models: list[BaseWhoopModel]) -> pd.DataFrame:
    """
    Convert a list of Pydantic models to a pandas DataFrame.

    This function takes a list of Whoop data models and converts them to a
    DataFrame with normalized/flattened structure. Datetime columns are
    automatically converted to pandas datetime types.

    Args:
        models: List of BaseWhoopModel instances to convert

    Returns:
        DataFrame with flattened structure from the models, or empty DataFrame if no models
    """
    if not models:
        return pd.DataFrame()

    # Convert models to dictionaries
    data = [model.model_dump() for model in models]

    # Create DataFrame
    df = pd.json_normalize(data)

    # Convert datetime columns
    datetime_columns = [col for col in df.columns if col.endswith("_at") or col in ["start", "end"]]
    for col in datetime_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    return df
