from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from hati.config import DecisionConfig
from hati.decision import authorize
from hati.models import (
    AnimalLabel,
    Classification,
    DecisionOutcome,
    EventRecord,
    SystemState,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
ZONE = "COOP_DOOR_ZONE"
PROTECTED_ZONES = frozenset({ZONE})
CONFIG = DecisionConfig(
    minimum_usable_observations=5,
    predator_consensus_required=4,
    cooldown_seconds=600,
    predator_labels=frozenset({"raccoon", "fox", "coyote", "opossum", "skunk"}),
)


def observation(index: int, label: AnimalLabel) -> Classification:
    predator = label in {
        AnimalLabel.RACCOON,
        AnimalLabel.FOX,
        AnimalLabel.COYOTE,
        AnimalLabel.OPOSSUM,
        AnimalLabel.SKUNK,
    }
    return Classification(
        frame_id=f"frame-{index}",
        animal=label,
        predator=predator,
        confidence=0.9,
        safe_to_deter=predator,
    )


def event(labels: list[AnimalLabel], zone: str = ZONE) -> EventRecord:
    return EventRecord(
        event_id="test-event",
        start_time=NOW,
        camera_id="coop-g4",
        zone=zone,
        trigger_reason="test",
        classifications=[observation(i, label) for i, label in enumerate(labels)],
    )


class AuthorizationTests(unittest.TestCase):
    def test_four_of_five_raccoon_observations_authorize(self) -> None:
        record = authorize(
            event([AnimalLabel.RACCOON] * 4 + [AnimalLabel.UNKNOWN]),
            SystemState(armed=True, actuator_available=True),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual(DecisionOutcome.AUTHORIZE, record.outcome)
        self.assertEqual("PREDATOR_CONSENSUS", record.reason_code)
        self.assertEqual(4, record.predator_votes)

    def test_human_veto_overrides_predator_consensus(self) -> None:
        record = authorize(
            event([AnimalLabel.RACCOON] * 4 + [AnimalLabel.HUMAN]),
            SystemState(armed=True, actuator_available=True),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual(DecisionOutcome.DENY, record.outcome)
        self.assertEqual("HUMAN_VETO", record.reason_code)
        self.assertTrue(record.human_veto)

    def test_chicken_is_denied_for_low_consensus(self) -> None:
        record = authorize(
            event([AnimalLabel.CHICKEN] * 5),
            SystemState(armed=True, actuator_available=True),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual(DecisionOutcome.DENY, record.outcome)
        self.assertEqual("LOW_CONSENSUS", record.reason_code)

    def test_unknown_is_denied(self) -> None:
        record = authorize(
            event([AnimalLabel.UNKNOWN] * 5),
            SystemState(armed=True, actuator_available=True),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual(DecisionOutcome.DENY, record.outcome)

    def test_resident_animals_are_denied(self) -> None:
        for label in (AnimalLabel.DOG, AnimalLabel.GOOSE, AnimalLabel.CAT):
            with self.subTest(label=label):
                record = authorize(
                    event([label] * 5),
                    SystemState(armed=True, actuator_available=True),
                    CONFIG,
                    PROTECTED_ZONES,
                    now=NOW,
                )
                self.assertEqual(DecisionOutcome.DENY, record.outcome)

    def test_raccoon_without_safe_to_deter_claim_is_denied(self) -> None:
        observations = [observation(i, AnimalLabel.RACCOON) for i in range(5)]
        observations = [
            Classification(
                frame_id=item.frame_id,
                animal=item.animal,
                predator=item.predator,
                confidence=item.confidence,
                safe_to_deter=False,
            )
            for item in observations
        ]
        unsafe_event = event([])
        unsafe_event.classifications = observations
        record = authorize(
            unsafe_event,
            SystemState(armed=True, actuator_available=True),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual(DecisionOutcome.DENY, record.outcome)
        self.assertEqual("LOW_CONSENSUS", record.reason_code)

    def test_outside_zone_is_denied(self) -> None:
        record = authorize(
            event([AnimalLabel.RACCOON] * 5, zone="DRIVEWAY"),
            SystemState(armed=True, actuator_available=True),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual("OUTSIDE_ZONE", record.reason_code)

    def test_disarmed_system_suppresses_valid_consensus(self) -> None:
        record = authorize(
            event([AnimalLabel.RACCOON] * 5),
            SystemState(armed=False, actuator_available=True),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual(DecisionOutcome.SUPPRESS, record.outcome)
        self.assertEqual("DISARMED", record.reason_code)

    def test_unavailable_actuator_suppresses(self) -> None:
        record = authorize(
            event([AnimalLabel.RACCOON] * 5),
            SystemState(armed=True, actuator_available=False),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual("ACTUATOR_UNAVAILABLE", record.reason_code)

    def test_cooldown_suppresses_and_reports_remaining_time(self) -> None:
        record = authorize(
            event([AnimalLabel.RACCOON] * 5),
            SystemState(
                armed=True,
                actuator_available=True,
                cooldown_until=NOW + timedelta(seconds=42),
            ),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual("COOLDOWN_ACTIVE", record.reason_code)
        self.assertIn("42 seconds", record.explanation)

    def test_duplicate_event_suppresses(self) -> None:
        record = authorize(
            event([AnimalLabel.RACCOON] * 5),
            SystemState(
                armed=True,
                actuator_available=True,
                event_already_actuated=True,
            ),
            CONFIG,
            PROTECTED_ZONES,
            now=NOW,
        )
        self.assertEqual("DUPLICATE_EVENT", record.reason_code)


if __name__ == "__main__":
    unittest.main()
