"""Example script demonstrating how to use the Whoopy library.

This script shows how to authenticate with the Whoop API and retrieve
various types of data including cycles, sleep, recovery, and workouts.

To run this example:
    uv run python -m whoopy.example

Copyright (c) 2024 Felix Geilert
"""

import asyncio
import json
import os
from datetime import datetime, timedelta

from whoopy import WhoopClient, WhoopClientV2

BASE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


def load_config(config_path: str | None = None) -> dict:
    """Load configuration from JSON file."""
    if config_path is None:
        config_path = BASE_CONFIG_PATH
    print(f"Loading config from {config_path}")

    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        print("\nPlease create a config.json file with the following structure:")
        print(
            json.dumps(
                {
                    "client_id": "your_client_id",
                    "client_secret": "your_client_secret",
                    "redirect_uri": "http://localhost:1234",
                },
                indent=2,
            )
        )
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        res = json.load(f)
        assert isinstance(res, dict)
        
        # Handle both flat and nested config structures
        if "whoop" in res:
            # Nested structure (backward compatibility)
            config = res["whoop"]
            print("Note: Using nested config structure. Consider updating to flat structure.")
        else:
            # Flat structure (preferred)
            config = res
            
        return config


def example_sync() -> None:
    """Example using the synchronous API (v2 with sync wrapper)."""
    print("=== Synchronous Example (v2 API) ===\n")

    try:
        # Try to load existing client from saved credentials
        client = WhoopClient.from_config(config_path=BASE_CONFIG_PATH)
        print("Loaded client from saved credentials")
    except Exception as e:
        print(f"Could not load saved credentials: {e}")
        print("Starting OAuth flow...\n")

        # Load config and start OAuth flow
        config = load_config()
        client = WhoopClient.auth_flow(
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            redirect_uri=config.get("redirect_uri", "http://localhost:1234"),
            open_browser=True,
        )

        # Save credentials for future use
        client.save_token()
        print("Saved credentials for future use")

    # Get user profile
    print("\n--- User Profile ---")
    profile = client.user.get_profile()
    print(f"Name: {profile.first_name} {profile.last_name}")
    print(f"Email: {profile.email}")
    print(f"User ID: {profile.user_id}")

    # Get body measurements
    print("\n--- Body Measurements ---")
    measurements = client.user.get_body_measurements()
    print(f"Height: {measurements.height_meter:.2f} m")
    print(f"Weight: {measurements.weight_kilogram:.1f} kg")
    print(f"Max Heart Rate: {measurements.max_heart_rate} bpm")

    # Get recent cycles (last 7 days)
    print("\n--- Recent Cycles (Last 7 Days) ---")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    cycles = client.cycles.get_all(start=start_date, end=end_date, limit_per_page=10)

    print(f"Found {len(cycles)} cycles")
    for cycle in cycles[:3]:  # Show first 3
        print(f"\nCycle {cycle.id}:")
        print(f"  Start: {cycle.start}")
        print(f"  End: {cycle.end or 'Ongoing'}")
        if cycle.score:
            print(f"  Strain: {cycle.score.strain:.1f}")
            print(f"  Calories: {cycle.score.calories:.0f}")

    # Get recent sleep
    print("\n--- Recent Sleep Activities ---")
    sleep_activities = client.sleep.get_all(start=start_date, end=end_date, limit_per_page=5)

    print(f"Found {len(sleep_activities)} sleep activities")
    for sleep in sleep_activities[:2]:  # Show first 2
        print(f"\nSleep {sleep.id}:")
        print(f"  Duration: {sleep.duration_hours:.1f} hours")
        print(f"  Nap: {'Yes' if sleep.nap else 'No'}")
        if sleep.score and sleep.score.stage_summary:
            summary = sleep.score.stage_summary
            print(f"  Sleep Efficiency: {summary.sleep_efficiency_percentage:.1f}%")

    # Get recent workouts
    print("\n--- Recent Workouts ---")
    workouts = client.workouts.get_all(start=start_date, end=end_date, limit_per_page=5)

    print(f"Found {len(workouts)} workouts")
    for workout in workouts[:3]:  # Show first 3
        print(f"\nWorkout: {workout.sport_name}")
        print(f"  Duration: {workout.duration_hours:.1f} hours")
        if workout.score:
            print(f"  Strain: {workout.score.strain:.1f}")
            print(f"  Calories: {workout.score.calories:.0f}")

    # Get recovery data as DataFrame
    print("\n--- Recovery Data (as DataFrame) ---")
    recovery_df = client.recovery.get_dataframe(start=start_date, end=end_date)

    if not recovery_df.empty:
        print(f"Recovery data shape: {recovery_df.shape}")
        print("\nRecovery scores:")
        if "score.recovery_score" in recovery_df.columns:
            print(recovery_df[["cycle_id", "score.recovery_score", "score.hrv_rmssd_milli"]].head())
    else:
        print("No recovery data found")


async def example_async() -> None:
    """Example using the asynchronous API (v2)."""
    print("\n\n=== Asynchronous Example (v2 API) ===\n")

    try:
        # Create client from saved credentials or config
        client = WhoopClientV2.from_config(config_path=BASE_CONFIG_PATH)

        async with client as whoop:
            # Get user profile
            print("--- User Profile ---")
            profile = await whoop.user.get_profile()
            print(f"Name: {profile.first_name} {profile.last_name}")

            # Get recent data concurrently
            end_date = datetime.now()
            start_date = end_date - timedelta(days=3)

            print("\n--- Fetching data concurrently ---")

            # Fetch multiple data types concurrently
            cycles_task = whoop.cycles.get_all(start=start_date, end=end_date)
            sleep_task = whoop.sleep.get_all(start=start_date, end=end_date)
            workouts_task = whoop.workouts.get_all(start=start_date, end=end_date)

            cycles, sleep_activities, workouts = await asyncio.gather(cycles_task, sleep_task, workouts_task)

            MIN_EXAMPLES = 3  # Minimum number of examples to show
            print(f"Fetched {len(cycles)} cycles, {len(sleep_activities)} sleep activities, {len(workouts)} workouts")

            # Example of using async iterator
            print("\n--- Iterating through cycles ---")
            count = 0
            async for cycle in whoop.cycles.iterate(start=start_date, end=end_date):
                print(f"Cycle {cycle.id}: Strain {cycle.score.strain if cycle.score else 'N/A'}")
                count += 1
                if count >= MIN_EXAMPLES:  # Limit output
                    break

    except Exception as e:
        print(f"Error in async example: {e}")


def main() -> None:
    """Main function to run both examples."""
    print("Whoopy Example Script")
    print("====================\n")

    # Check if config exists
    if not os.path.exists("config.json"):
        print("No config.json found!")
        print("\nTo get started:")
        print("1. Create a Whoop developer account at https://developer.whoop.com")
        print("2. Create a new application to get your client_id and client_secret")
        print("3. Create a config.json file with your credentials")
        print("4. Run this script again with: uv run python -m whoopy.example")
        return

    # Run synchronous example
    try:
        example_sync()
    except Exception as e:
        print(f"Error in sync example: {e}")

    # Run asynchronous example
    try:
        asyncio.run(example_async())
    except Exception as e:
        print(f"Error in async example: {e}")

    print("\n\nExample completed!")


if __name__ == "__main__":
    main()
