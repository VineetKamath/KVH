"""The organiser material must stay byte-identical (SHA256SUMS.txt). Runs last-alphabetically-safe:
any test or code path that writes to DynamicPricing/ fails the build here."""
from app.services.seeding import verify_checksums


def test_organiser_files_match_sha256sums():
    assert verify_checksums() == 29
