"""Example script demonstrating how to use the Whoopy library.

This script shows how to authenticate with the Whoop API and retrieve
various types of data including cycles, sleep, recovery, and workouts.

To run this example:
    uv run python -m whoopy.example

Copyright (c) 2024 Felix Geilert
"""

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from whoopy import WhoopClient, WhoopClientV2
from whoopy.exceptions import RateLimitError, ResourceNotFoundError
from whoopy.utils import OAuth2Helper


def configure_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level."""

    # Set logging level based on verbosity
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Set specific loggers
    logging.getLogger("whoopy").setLevel(level)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)  # Always quiet for aiohttp
    logging.getLogger("urllib3").setLevel(logging.WARNING)  # Always quiet for urllib3


BASE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


def load_config(config_path: str | None = None) -> dict[str, Any]:
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

        return config  # type: ignore[no-any-return]


def example_sync(verbose: bool = False) -> None:
    """Example using the synchronous API (v2 with sync wrapper)."""
    print("=== Synchronous Example (v2 API) ===\n")

    # Configure logging for this example
    configure_logging(verbose)

    client = None
    try:
        # Load config first
        config = load_config(BASE_CONFIG_PATH)

        # Try to load token
        oauth_helper = OAuth2Helper(client_id=config["client_id"], client_secret=config["client_secret"])
        token_info = oauth_helper.load_token()

        if token_info:
            # Create client with existing token and throttling
            client = WhoopClient(
                token_info=token_info,
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                request_delay=0.2,  # 200ms between requests
                max_concurrent_requests=3,  # Limit concurrent requests
                logger=logging.getLogger("whoopy") if verbose else None,
            )
            if verbose:
                print("Loaded client from saved credentials (verbose mode enabled)")
            else:
                print("Loaded client from saved credentials")
        else:
            raise Exception("No saved token - need to authenticate")

        # Check if we actually have a token
        if client.token_info is None:
            print("No saved credentials found")
            raise Exception("No saved token - need to authenticate")

        print("Loaded client from saved credentials")

        # Check if token needs refresh
        if client.token_info.is_expired:
            print("Token is expired, refreshing...")
            try:
                client.refresh_token()
                client.save_token()
                print("Token refreshed successfully")
            except Exception as refresh_error:
                print(f"Failed to refresh token: {refresh_error}")
                print("Starting new OAuth flow...\n")
                raise  # Re-raise to trigger OAuth flow

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
            request_delay=0.2,  # Apply throttling from the start
            max_concurrent_requests=3,
        )

        # Save credentials for future use
        client.save_token()
        print("Saved credentials for future use")

    # Use context manager to ensure proper cleanup
    with client:
        # Get user profile
        print("\n--- User Profile ---")
        try:
            profile = client.user.get_profile()
            print(f"Name: {profile.first_name} {profile.last_name}")
            print(f"Email: {profile.email}")
            print(f"User ID: {profile.user_id}")
        except Exception as e:
            print(f"Failed to get user profile: {e}")
            if "session" in str(e).lower() or "closed" in str(e).lower():
                print("Session appears to be closed. This might be a client initialization issue.")
            return

        # Get body measurements
        print("\n--- Body Measurements ---")
        try:
            measurements = client.user.get_body_measurements()
            print(f"Height: {measurements.height_meter:.2f} m")
            print(f"Weight: {measurements.weight_kilogram:.1f} kg")
            print(f"Max Heart Rate: {measurements.max_heart_rate} bpm")
        except Exception as e:
            print(f"Failed to get body measurements: {e}")

        # Get recent cycles (last 7 days)
        print("\n--- Recent Cycles (Last 7 Days) ---")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        try:
            print("About to call cycles.get_all...")
            cycles = client.cycles.get_all(start=start_date, end=end_date, limit_per_page=10)
            print(f"Found {len(cycles)} cycles")
            for cycle in cycles[:3]:  # Show first 3
                print(f"\nCycle {cycle.id}:")
                print(f"  Start: {cycle.start}")
                print(f"  End: {cycle.end or 'Ongoing'}")
                if cycle.score:
                    print(f"  Strain: {cycle.score.strain:.1f}")
                    print(f"  Calories: {cycle.score.calories:.0f}")
        except Exception as e:
            print(f"Failed to get cycles: {e}")

        # Get recent sleep
        print("\n--- Recent Sleep Activities ---")
        try:
            sleep_activities = client.sleep.get_all(start=start_date, end=end_date, limit_per_page=5)
            print(f"Found {len(sleep_activities)} sleep activities")
            for sleep in sleep_activities[:2]:  # Show first 2
                print(f"\nSleep {sleep.id}:")
                print(f"  Duration: {sleep.duration_hours:.1f} hours")
                print(f"  Nap: {'Yes' if sleep.nap else 'No'}")
                if sleep.score and sleep.score.stage_summary:
                    summary = sleep.score.stage_summary
                    print(f"  Sleep Efficiency: {summary.sleep_efficiency_percentage:.1f}%")
        except ResourceNotFoundError:
            print("No sleep data found for the specified date range")
        except RateLimitError as e:
            print(f"Rate limit reached for sleep data: {e}")
            print("Consider increasing request_delay or reducing date range")
        except Exception as e:
            print(f"Failed to get sleep data: {e}")

        # Get recent workouts (limit to 3 days to avoid rate limits)
        print("\n--- Recent Workouts (Last 3 Days) ---")
        try:
            # Use a shorter date range for workouts to avoid excessive API calls
            workout_start = end_date - timedelta(days=3)
            workouts = client.workouts.get_all(
                start=workout_start,
                end=end_date,
                limit_per_page=25,  # Larger page size to reduce API calls
                max_records=10,  # Limit total records to prevent rate limits
            )
            print(f"Found {len(workouts)} workouts (limited to 10 most recent)")
            for workout in workouts[:3]:  # Show first 3
                print(f"\nWorkout: {workout.sport_name}")
                print(f"  Duration: {workout.duration_hours:.1f} hours")
                if workout.score:
                    print(f"  Strain: {workout.score.strain:.1f}")
                    print(f"  Calories: {workout.score.calories:.0f}")
        except ResourceNotFoundError:
            print("No workouts found for the specified date range")
        except RateLimitError as e:
            print(f"Rate limit reached for workouts: {e}")
            print("Consider increasing request_delay or reducing date range")
        except Exception as e:
            print(f"Failed to get workouts: {e}")

        # Get recovery data as DataFrame
        # Note: Recovery endpoints often return 404 even with proper scopes.
        # This appears to be a user/subscription-specific limitation.
        print("\n--- Recovery Data (as DataFrame) ---")
        try:
            recovery_df = client.recovery.get_dataframe(start=start_date, end=end_date)
            if not recovery_df.empty:
                print(f"Recovery data shape: {recovery_df.shape}")
                print("\nRecovery scores:")
                if "score.recovery_score" in recovery_df.columns:
                    print(recovery_df[["cycle_id", "score.recovery_score", "score.hrv_rmssd_milli"]].head())
            else:
                print("No recovery data found")
        except ResourceNotFoundError:
            print("No recovery data available for this user")
            print("Note: Recovery data may not be available for all users or subscription levels")
        except RateLimitError as e:
            print(f"Rate limit reached for recovery data: {e}")
        except Exception as e:
            print(f"Failed to get recovery data: {e}")


async def example_async(verbose: bool = False) -> None:
    """Example using the asynchronous API (v2)."""
    print("\n\n=== Asynchronous Example (v2 API) ===\n")

    # Logging is already configured from sync example

    try:
        # Load config first
        config = load_config(BASE_CONFIG_PATH)

        # Try to load token
        oauth_helper = OAuth2Helper(client_id=config["client_id"], client_secret=config["client_secret"])
        token_info = oauth_helper.load_token()

        if not token_info:
            print("No saved credentials found. Please run the sync example first to authenticate.")
            return

        # Create client with existing token and throttling
        client = WhoopClientV2(  # type: ignore[misc]
            token_info=token_info,
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            request_delay=0.2,  # 200ms between requests
            max_concurrent_requests=3,  # Limit concurrent requests
            logger=logging.getLogger("whoopy") if verbose else None,
        )

        # Check if token needs refresh before starting
        if client.token_info.is_expired:
            print("Token is expired. It will be refreshed when the client initializes.")

        async with client as whoop:
            # Get user profile
            print("--- User Profile ---")
            try:
                profile = await whoop.user.get_profile()
                print(f"Name: {profile.first_name} {profile.last_name}")
            except Exception as e:
                print(f"Failed to get user profile: {e}")
                if "unauthorized" in str(e).lower() or "authentication" in str(e).lower():
                    print("Authentication failed. Token might be invalid.")
                    return

            # Get recent data concurrently
            end_date = datetime.now()
            start_date = end_date - timedelta(days=3)

            print("\n--- Fetching data concurrently ---")

            # Fetch multiple data types concurrently
            try:
                cycles_task = whoop.cycles.get_all(start=start_date, end=end_date, limit_per_page=25)
                sleep_task = whoop.sleep.get_all(start=start_date, end=end_date, limit_per_page=25)
                workouts_task = whoop.workouts.get_all(
                    start=start_date,
                    end=end_date,
                    limit_per_page=25,
                    max_records=10,  # Limit to prevent excessive API calls
                )

                cycles: Any
                sleep_activities: Any
                workouts: Any
                cycles, sleep_activities, workouts = await asyncio.gather(
                    cycles_task,
                    sleep_task,
                    workouts_task,
                    return_exceptions=True,  # Don't fail if one request fails
                )

                # Handle results
                if isinstance(cycles, Exception):
                    if isinstance(cycles, ResourceNotFoundError):
                        print("No cycles found for the specified date range")
                    elif isinstance(cycles, RateLimitError):
                        print(f"Rate limit reached for cycles: {cycles}")
                    else:
                        print(f"Failed to fetch cycles: {cycles}")
                    cycles = []
                if isinstance(sleep_activities, Exception):
                    if isinstance(sleep_activities, ResourceNotFoundError):
                        print("No sleep activities found for the specified date range")
                    elif isinstance(sleep_activities, RateLimitError):
                        print(f"Rate limit reached for sleep: {sleep_activities}")
                    else:
                        print(f"Failed to fetch sleep: {sleep_activities}")
                    sleep_activities = []
                if isinstance(workouts, Exception):
                    if isinstance(workouts, ResourceNotFoundError):
                        print("No workouts found for the specified date range")
                    elif isinstance(workouts, RateLimitError):
                        print(f"Rate limit reached for workouts: {workouts}")
                    else:
                        print(f"Failed to fetch workouts: {workouts}")
                    workouts = []

                MIN_EXAMPLES = 3  # Minimum number of examples to show
                print(
                    f"Fetched {len(cycles)} cycles, {len(sleep_activities)} sleep activities, {len(workouts)} workouts"
                )

                # Example of using async iterator
                print("\n--- Iterating through cycles ---")
                count = 0
                try:
                    async for cycle in whoop.cycles.iterate(start=start_date, end=end_date):
                        print(f"Cycle {cycle.id}: Strain {cycle.score.strain if cycle.score else 'N/A'}")
                        count += 1
                        if count >= MIN_EXAMPLES:  # Limit output
                            break
                except ResourceNotFoundError:
                    print("No cycles found to iterate through")
                except RateLimitError as e:
                    print(f"Rate limit reached during iteration: {e}")
                    print("\nTip: To avoid rate limits, consider:")
                    print("  - Increasing request_delay (current: 0.2s)")
                    print("  - Reducing the date range for queries")
                    print("  - Using smaller limit_per_page values")
            except Exception as e:
                print(f"Error fetching data: {e}")

    except Exception as e:
        print(f"Error in async example: {e}")
        import traceback

        traceback.print_exc()


def main() -> None:
    """Main function to run both examples."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Whoopy Example Script - Demonstrates Whoop API v2 usage")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging output")
    parser.add_argument("--sync-only", action="store_true", help="Run only the synchronous example")
    parser.add_argument("--async-only", action="store_true", help="Run only the asynchronous example")
    args = parser.parse_args()

    print("Whoopy Example Script")
    print("====================\n")

    if args.verbose:
        print("Verbose mode enabled\n")

    # Check if config exists (try multiple locations)
    config_locations = ["config.json", BASE_CONFIG_PATH, os.path.join(os.path.dirname(__file__), "config.json")]

    config_exists = any(os.path.exists(path) for path in config_locations)

    if not config_exists:
        print("No config.json found!")
        print("\nTo get started:")
        print("1. Create a Whoop developer account at https://developer.whoop.com")
        print("2. Create a new application to get your client_id and client_secret")
        print("3. Create a config.json file with your credentials")
        print("4. Run this script again with: uv run python -m whoopy.example")
        print(f"\nSearched in: {', '.join(config_locations)}")
        return

    # Run examples based on arguments
    if not args.async_only:
        # Run synchronous example
        try:
            print("Starting sync example...")
            example_sync(verbose=args.verbose)
        except Exception as e:
            print(f"Error in sync example: {e}")
            if args.verbose:
                import traceback

                traceback.print_exc()

    if not args.sync_only:
        # Run asynchronous example
        try:
            print("\nStarting async example...")
            asyncio.run(example_async(verbose=args.verbose))
        except Exception as e:
            print(f"Error in async example: {e}")
            if args.verbose:
                import traceback

                traceback.print_exc()

    print("\n\nExample completed!")

    # Flush any pending log messages
    logging.shutdown()


if __name__ == "__main__":
    main()
